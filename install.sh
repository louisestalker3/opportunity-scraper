#!/usr/bin/env bash
# install.sh — set up Opportunity Scraper for local development
# Supports macOS (Homebrew) and Linux (apt)
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[install]${NC} $*"; }
warn()    { echo -e "${YELLOW}[install]${NC} $*"; }
error()   { echo -e "${RED}[install]${NC} $*" >&2; exit 1; }
check()   { echo -e "${GREEN}  ✓${NC} $*"; }
missing() { echo -e "${YELLOW}  ✗${NC} $*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OS="$(uname -s)"

# ── Detect package manager ────────────────────────────────────────────────────

install_pkg() {
    if [[ "$OS" == "Darwin" ]]; then
        brew install "$@"
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y "$@"
    else
        error "Unsupported OS or missing package manager. Install manually: $*"
    fi
}

# ── System dependencies ────────────────────────────────────────────────────────

info "Checking system dependencies..."

if ! command -v python3 &>/dev/null; then
    warn "python3 not found — installing..."
    if [[ "$OS" == "Darwin" ]]; then
        brew install python@3.12
    else
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    fi
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)'; then
    check "Python $PYTHON_VERSION"
else
    error "Python 3.11+ required (found $PYTHON_VERSION)"
fi

if ! command -v node &>/dev/null; then
    warn "node not found — installing..."
    if [[ "$OS" == "Darwin" ]]; then
        brew install node
    else
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
    fi
fi
check "Node $(node --version)"

if ! command -v npm &>/dev/null; then
    error "npm not found — install Node.js first"
fi
check "npm $(npm --version)"

if ! command -v psql &>/dev/null; then
    warn "PostgreSQL client not found — installing..."
    if [[ "$OS" == "Darwin" ]]; then
        brew install postgresql@15
        brew link --force postgresql@15
    else
        sudo apt-get update && sudo apt-get install -y postgresql postgresql-client libpq-dev
    fi
fi
check "PostgreSQL $(psql --version | awk '{print $3}')"

if ! command -v redis-cli &>/dev/null; then
    warn "Redis not found — installing..."
    if [[ "$OS" == "Darwin" ]]; then
        brew install redis
    else
        sudo apt-get update && sudo apt-get install -y redis-server
    fi
fi
check "Redis $(redis-cli --version | awk '{print $2}')"

# ── Ensure PostgreSQL is running and create database ───────────────────────────

info "Ensuring PostgreSQL is running..."
if [[ "$OS" == "Darwin" ]]; then
    brew services start postgresql@15 2>/dev/null || brew services start postgresql 2>/dev/null || true
    sleep 1
else
    sudo systemctl enable postgresql --now 2>/dev/null || sudo service postgresql start 2>/dev/null || true
    sleep 1
fi

info "Creating database 'opportunity_scraper' if it doesn't exist..."
if [[ "$OS" == "Darwin" ]]; then
    # macOS: postgres typically runs as current user
    createdb opportunity_scraper 2>/dev/null && check "Database created" || check "Database already exists"
else
    sudo -u postgres createdb opportunity_scraper 2>/dev/null && check "Database created" \
        || check "Database already exists (or already set up)"
fi

# ── Ensure Redis is running ────────────────────────────────────────────────────

info "Ensuring Redis is running..."
if [[ "$OS" == "Darwin" ]]; then
    brew services start redis 2>/dev/null || true
else
    sudo systemctl enable redis-server --now 2>/dev/null \
        || sudo service redis-server start 2>/dev/null || true
fi
check "Redis started"

# ── Backend Python venv ────────────────────────────────────────────────────────

info "Setting up Python virtual environment..."
cd "$SCRIPT_DIR/backend"

if [[ ! -d venv ]]; then
    python3 -m venv venv
fi
# shellcheck source=/dev/null
source venv/bin/activate

pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
check "Python dependencies installed"

# Install Playwright Chromium (used by scrapers)
python -m playwright install chromium --with-deps 2>/dev/null \
    || warn "Playwright install failed — scraping features that use Chromium may not work"

# ── Run database migrations ────────────────────────────────────────────────────

info "Running database migrations..."
# Detect the right DATABASE_URL for migrations
if [[ "$OS" == "Darwin" ]]; then
    # macOS postgres runs as current user, no password needed
    export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://localhost/opportunity_scraper}"
else
    export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:postgres@localhost:5432/opportunity_scraper}"
fi

alembic upgrade head
check "Migrations applied"

deactivate
cd "$SCRIPT_DIR"

# ── Frontend npm install ────────────────────────────────────────────────────────

info "Installing frontend dependencies..."
cd "$SCRIPT_DIR/frontend"
npm install --silent
check "Frontend dependencies installed"
cd "$SCRIPT_DIR"

# ── Create .env if missing ─────────────────────────────────────────────────────

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    info "Creating .env from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    if [[ "$OS" == "Darwin" ]]; then
        # macOS postgres runs as current user, no password
        sed -i '' 's|postgresql+asyncpg://postgres:postgres@localhost|postgresql+asyncpg://localhost|' "$SCRIPT_DIR/.env"
    fi
    check ".env created — edit it to add API keys"
else
    check ".env already exists"
fi

# ── Summary ────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}Installation complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Edit .env and set ANTHROPIC_API_KEY (and optional Reddit/Twitter keys)"
echo "  2. Run: ./start.sh"
echo ""
