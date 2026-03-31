#!/usr/bin/env bash
# start.sh — start all Opportunity Scraper processes
# Port scheme: everything lives in 9000+
#   9000  → FastAPI backend
#   9001  → React frontend (Vite)
#   9002+ → generated project ports (managed by build_runner port registry)
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${GREEN}[start]${NC} $*"; }
warn() { echo -e "${YELLOW}[start]${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"
PIDS=()

APP_API_PORT="${APP_API_PORT:-9000}"
APP_FRONTEND_PORT="${APP_FRONTEND_PORT:-9001}"

# ── Load .env ─────────────────────────────────────────────────────────────────

if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -o allexport
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/.env"
    set +o allexport
fi

# ── Locate binaries ──────────────────────────────────────────────────────────

PG_CTL=""
PG_ISREADY=""
REDIS_SERVER=""
REDIS_CLI=""
PGDATA_USER="$HOME/pgdata15"

for candidate in \
    /opt/homebrew/opt/postgresql@15/bin \
    /opt/homebrew/opt/postgresql@16/bin \
    /opt/homebrew/bin \
    /usr/local/bin \
    /usr/bin; do
    [[ -z "$PG_ISREADY"   && -x "$candidate/pg_isready"   ]] && PG_ISREADY="$candidate/pg_isready"
    [[ -z "$PG_CTL"       && -x "$candidate/pg_ctl"       ]] && PG_CTL="$candidate/pg_ctl"
    [[ -z "$REDIS_CLI"    && -x "$candidate/redis-cli"    ]] && REDIS_CLI="$candidate/redis-cli"
    [[ -z "$REDIS_SERVER" && -x "$candidate/redis-server" ]] && REDIS_SERVER="$candidate/redis-server"
done

# Also search common compiled-from-source locations
for candidate in /tmp/redis-stable/src "$HOME/redis/src"; do
    [[ -z "$REDIS_CLI"    && -x "$candidate/redis-cli"    ]] && REDIS_CLI="$candidate/redis-cli"
    [[ -z "$REDIS_SERVER" && -x "$candidate/redis-server" ]] && REDIS_SERVER="$candidate/redis-server"
done

# ── Ensure PostgreSQL is running ──────────────────────────────────────────────

check_postgres() {
    [[ -n "$PG_ISREADY" ]] && "$PG_ISREADY" -q 2>/dev/null && return 0
    return 1
}

if ! check_postgres; then
    warn "PostgreSQL not running — starting..."
    if [[ -n "$PG_CTL" && -d "$PGDATA_USER" ]]; then
        "$PG_CTL" -D "$PGDATA_USER" -l "$PGDATA_USER/postgres.log" start 2>/dev/null || true
    elif [[ "$OS" == "Darwin" ]]; then
        brew services start postgresql@15 2>/dev/null || brew services start postgresql 2>/dev/null || true
    else
        sudo systemctl start postgresql 2>/dev/null || sudo service postgresql start 2>/dev/null || true
    fi
    sleep 3
    check_postgres || { echo -e "${RED}PostgreSQL failed to start — run install.sh first${NC}"; exit 1; }
fi

# ── Ensure Redis is running ───────────────────────────────────────────────────

check_redis() {
    [[ -n "$REDIS_CLI" ]] && "$REDIS_CLI" ping &>/dev/null 2>&1 && return 0
    return 1
}

if ! check_redis; then
    warn "Redis not running — starting..."
    if [[ -n "$REDIS_SERVER" ]]; then
        "$REDIS_SERVER" --daemonize yes --logfile /tmp/redis.log 2>/dev/null || true
    elif [[ "$OS" == "Darwin" ]]; then
        brew services start redis 2>/dev/null || true
    else
        sudo systemctl start redis-server 2>/dev/null || sudo service redis-server start 2>/dev/null || true
    fi
    sleep 2
    check_redis || { echo -e "${RED}Redis not available — install Redis first${NC}"; exit 1; }
fi

# ── Activate venv ─────────────────────────────────────────────────────────────

VENV="$SCRIPT_DIR/backend/venv"
if [[ ! -d "$VENV" ]]; then
    echo -e "${RED}Virtual environment not found — run ./install.sh first${NC}"
    exit 1
fi

# Add pg bin dir to PATH so child processes can reach psql/pg_isready
for pg_bin_dir in \
    /opt/homebrew/opt/postgresql@15/bin \
    /opt/homebrew/opt/postgresql@16/bin \
    /opt/homebrew/bin \
    /usr/local/bin; do
    if [[ -d "$pg_bin_dir" ]]; then
        export PATH="$pg_bin_dir:$PATH"
        break
    fi
done

# shellcheck source=/dev/null
source "$VENV/bin/activate"

LOG_DIR="$SCRIPT_DIR/.logs"
mkdir -p "$LOG_DIR"

# ── Cleanup on exit ───────────────────────────────────────────────────────────

cleanup() {
    echo ""
    info "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait "${PIDS[@]}" 2>/dev/null || true
    info "All processes stopped."
}
trap cleanup EXIT INT TERM

# ── Start services ────────────────────────────────────────────────────────────

cd "$SCRIPT_DIR/backend"

info "Starting FastAPI backend on :${APP_API_PORT}..."
APP_API_PORT="$APP_API_PORT" APP_FRONTEND_PORT="$APP_FRONTEND_PORT" \
    uvicorn app.main:app --host 0.0.0.0 --port "$APP_API_PORT" --reload \
    > "$LOG_DIR/api.log" 2>&1 &
PIDS+=($!)
echo -e "  ${CYAN}API${NC}    → http://localhost:${APP_API_PORT}  (log: .logs/api.log)"

info "Starting Celery worker..."
CELERY_WORKER=true API_BASE="http://localhost:${APP_API_PORT}" \
    celery -A app.workers.celery_app worker --loglevel=warning --pool=solo \
    > "$LOG_DIR/celery.log" 2>&1 &
PIDS+=($!)
echo -e "  ${CYAN}Worker${NC} → background tasks         (log: .logs/celery.log)"

info "Starting Celery beat scheduler..."
CELERY_WORKER=true API_BASE="http://localhost:${APP_API_PORT}" \
    celery -A app.workers.celery_app beat --loglevel=warning \
    > "$LOG_DIR/celery_beat.log" 2>&1 &
PIDS+=($!)
echo -e "  ${CYAN}Beat${NC}   → scheduled tasks          (log: .logs/celery_beat.log)"

cd "$SCRIPT_DIR/frontend"

info "Starting React frontend on :${APP_FRONTEND_PORT}..."
npm run dev -- --host 0.0.0.0 --port "$APP_FRONTEND_PORT" \
    > "$LOG_DIR/frontend.log" 2>&1 &
PIDS+=($!)
echo -e "  ${CYAN}UI${NC}     → http://localhost:${APP_FRONTEND_PORT}  (log: .logs/frontend.log)"

cd "$SCRIPT_DIR"

info "Starting build runner..."
APP_API_PORT="$APP_API_PORT" APP_FRONTEND_PORT="$APP_FRONTEND_PORT" \
    API_BASE="http://localhost:${APP_API_PORT}" \
    python3 build_runner.py \
    > "$LOG_DIR/build_runner.log" 2>&1 &
PIDS+=($!)
echo -e "  ${CYAN}Runner${NC} → background poller         (log: .logs/build_runner.log)"

echo ""
echo -e "${GREEN}All services started.${NC} Press Ctrl+C to stop everything."
echo -e "Port range 9002+ is reserved for generated projects."
echo ""

# Wait for any child to exit unexpectedly
wait -n "${PIDS[@]}" 2>/dev/null || true
echo -e "${YELLOW}A process exited unexpectedly. Check logs in .logs/${NC}"
