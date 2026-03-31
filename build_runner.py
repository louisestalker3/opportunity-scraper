#!/usr/bin/env python3
"""
Local build runner — runs on the host, outside Docker.
Uses `claude --dangerously-skip-permissions` as a fully autonomous agent
to build a complete application in the target directory.

Usage:
    python3 build_runner.py

Keep running in a terminal tab while using the opportunity scraper.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

API_BASE = os.environ.get("API_BASE", "http://localhost:9000")
REPOS_PATH = Path(os.environ.get("REPOS_PATH", Path.home() / "repos"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
POLL_INTERVAL = 4

# ─── Port registry ────────────────────────────────────────────────────────────
# All port management lives in the 9000+ range.
# The registry is a JSON file keyed by project slug.
# A special "__app__" entry reserves Opportunity Scraper's own ports so they
# are never handed out to generated projects.
#
# Layout:
#   9000        → Opportunity Scraper API          (reserved as __app__.api)
#   9001        → Opportunity Scraper frontend      (reserved as __app__.frontend)
#   9002+       → allocated to generated projects, 3 ports each (frontend/api/db)

_PORT_REGISTRY_FILE = Path(__file__).parent / ".port_registry.json"
_PORT_RANGE_START = 9002        # first port available for generated projects
_PORT_RANGE_END   = 19999       # ~3333 projects before we run out

# The app's own ports — written into the registry under a reserved key so the
# allocator never hands them to a generated project.
_APP_PORTS = {
    "api":      int(os.environ.get("APP_API_PORT",      9000)),
    "frontend": int(os.environ.get("APP_FRONTEND_PORT", 9001)),
}


def _load_registry() -> dict:
    if _PORT_REGISTRY_FILE.exists():
        try:
            return json.loads(_PORT_REGISTRY_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_registry(registry: dict) -> None:
    _PORT_REGISTRY_FILE.write_text(json.dumps(registry, indent=2))


def _ensure_app_reserved() -> None:
    """Write the app's own ports into the registry so they're never allocated."""
    registry = _load_registry()
    if registry.get("__app__") != _APP_PORTS:
        registry["__app__"] = _APP_PORTS
        _save_registry(registry)


def _is_port_free(port: int) -> bool:
    """Return True if nothing is currently bound to this port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def allocate_project_ports(slug: str) -> dict:
    """
    Return {frontend, api, db} port assignments for the given project slug.
    Reuses existing allocations so rebuilds always get the same ports.
    Scans _PORT_RANGE_START..._PORT_RANGE_END for free ports on first allocation.
    """
    _ensure_app_reserved()
    registry = _load_registry()

    if slug in registry:
        return registry[slug]

    # Collect every port already spoken for (across all projects + app itself)
    used: set[int] = set()
    for entry in registry.values():
        used.update(entry.values())

    def next_free(exclude: set[int]) -> int:
        for port in range(_PORT_RANGE_START, _PORT_RANGE_END):
            if port not in exclude and _is_port_free(port):
                exclude.add(port)
                return port
        raise RuntimeError(f"No free ports in range {_PORT_RANGE_START}–{_PORT_RANGE_END}")

    ports = {
        "frontend": next_free(used),
        "api":      next_free(used),
        "db":       next_free(used),
    }
    registry[slug] = ports
    _save_registry(registry)
    print(f"  [ports] {slug}: frontend={ports['frontend']} api={ports['api']} db={ports['db']}")
    return ports

_SESSIONS_FILE = Path(__file__).parent / ".build_sessions"

BUILD_PROMPT_LARGE = """You are building a complete, production-ready web application from scratch.

Work in the CURRENT DIRECTORY. Create every file needed for a fully working app.

App plan:
{plan_json}

Tech stack: FastAPI (backend) + React + Vite (frontend) + PostgreSQL + TypeScript throughout.

IMPORTANT — NO DOCKER. Everything runs natively on the host machine.
Pre-allocated ports (do not use any other ports):
  Frontend: {port_frontend}
  API:      {port_api}
  Database: {port_db}  (local PostgreSQL, DB name = slug from app plan)

Your job:
1. Create the full project structure:
   - backend/   → FastAPI app, SQLAlchemy 2.0 async, Alembic migrations
   - frontend/  → React + Vite, TypeScript, Tailwind CSS
   - start.sh   → starts all services natively (uvicorn + vite + pg)
   - stop.sh    → stops all services cleanly
   - install.sh → installs dependencies (pip, npm), creates venv, runs migrations

2. Write complete, working code for every file — no stubs, no TODOs, no placeholder functions

3. Backend (FastAPI):
   - SQLAlchemy 2.0 async with asyncpg
   - Alembic for migrations
   - Full CRUD endpoints for each resource
   - JWT auth (python-jose), bcrypt password hashing (passlib)
   - Pydantic v2 schemas
   - Use port {port_api} for uvicorn, PostgreSQL on port {port_db}

4. Frontend (React + Vite):
   - TypeScript + Tailwind CSS
   - TanStack Query v5 for data fetching
   - React Router v6
   - Complete pages with real forms and data fetching
   - Vite dev server on port {port_frontend}, proxy /api to localhost:{port_api}

5. start.sh must use environment variable overrides with sensible defaults so it works
   both standalone (deployed) and when launched by OpportunityScraper (which injects ports):
   ```bash
   FRONTEND_PORT=${FRONTEND_PORT:-3000}
   API_PORT=${API_PORT:-8000}
   DB_PORT=${DB_PORT:-5432}
   ```
   - Start PostgreSQL if not running (use pg_ctl or brew services), using $DB_PORT
   - Create the DB if it doesn't exist
   - Start uvicorn on $API_PORT in background, write PID to .pids/api.pid
   - Start vite dev server on $FRONTEND_PORT in background, write PID to .pids/frontend.pid
   - Print the URL: http://localhost:$FRONTEND_PORT

6. stop.sh must:
   - Read PIDs from .pids/ and kill each process cleanly

7. install.sh must:
   - python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
   - npm install (in frontend/)
   - alembic upgrade head

8. .env with DATABASE_URL, SECRET_KEY, etc. — use the default ports (3000/8000/5432) as defaults
9. README.md with setup and run instructions
10. .gitignore

Write every file. The app must start cleanly by running: ./install.sh && ./start.sh
"""

BUILD_PROMPT_SMALL = """You are building a complete, production-ready web application from scratch.

Work in the CURRENT DIRECTORY. Create every file needed for a fully working app.

App plan:
{plan_json}

Tech stack: Python (Flask) + SQLite + vanilla HTML/CSS/JS (no build step needed).

IMPORTANT — NO DOCKER. Everything runs natively on the host machine.
Pre-allocated ports (do not use any other ports):
  App: {port_frontend}  (Flask serves both API and HTML)

Your job:
1. Create a simple, self-contained Python web app — minimal dependencies
2. Write complete, working code for every file — no stubs, no TODOs, no placeholder functions
3. Structure:
   - app.py          → Flask app, routes, SQLite with sqlite3 module
   - templates/      → Jinja2 HTML templates
   - static/         → CSS and JS files
   - schema.sql      → database schema (applied on first run)
   - start.sh        → starts the Flask app in background, writes PID to .pids/app.pid
   - stop.sh         → kills the PID in .pids/app.pid
   - install.sh      → python3 -m venv venv && pip install flask

4. Backend (Flask):
   - sqlite3 with context managers, prepared statements (no SQL injection)
   - Flask sessions for auth (login/register/logout), SECRET_KEY in .env
   - SQL schema applied at startup if DB doesn't exist
   - Run on port {port_frontend}

5. Frontend:
   - Tailwind CSS via CDN (no build step)
   - Clean, modern UI
   - Forms POST to Flask routes (PRG pattern where appropriate)

6. start.sh must use env var overrides with sensible defaults (works standalone or via scraper):
   ```bash
   APP_PORT=${APP_PORT:-5000}
   ```
   Write PID to .pids/app.pid and print: http://localhost:$APP_PORT
7. stop.sh must read .pids/app.pid and kill cleanly
8. install.sh: python3 -m venv venv && source venv/bin/activate && pip install flask python-dotenv

9. .env with SECRET_KEY
10. README with setup instructions
11. .gitignore

Write every file. The app must start cleanly by running: ./install.sh && ./start.sh
"""


# ─── API helpers ──────────────────────────────────────────────────────────────

def _headers(session_id: str) -> dict:
    return {"Content-Type": "application/json", "X-Session-ID": session_id}


def _post(path: str, session_id: str, payload: dict) -> bool:
    import urllib.request
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(payload).encode(),
        headers=_headers(session_id),
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
        return True
    except Exception as e:
        print(f"  [api] POST {path} failed: {e}")
        return False


def _get(path: str, session_id: str):
    import urllib.request
    req = urllib.request.Request(f"{API_BASE}{path}", headers={"X-Session-ID": session_id})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return None


def post_log(item_id: str, session_id: str, message: str) -> None:
    _post(f"/api/pipeline/{item_id}/build-log", session_id, {"message": message})


def mark_built(item_id: str, session_id: str, repo_url: str) -> None:
    _post(f"/api/pipeline/{item_id}/build-result", session_id,
          {"build_status": "built", "built_repo_url": repo_url})


def mark_failed(item_id: str, session_id: str) -> None:
    _post(f"/api/pipeline/{item_id}/build-result", session_id, {"build_status": "failed"})


def get_building_items(session_id: str) -> list[dict]:
    items = _get("/api/pipeline", session_id)
    return [i for i in (items or []) if i.get("build_status") == "building"]


def get_run_pending_items(session_id: str) -> list[dict]:
    items = _get("/api/pipeline", session_id)
    return [i for i in (items or []) if i.get("run_status") in ("starting", "stopping")]


def get_ready_tasks() -> list[dict]:
    """Returns all tasks with status=ready (global, no session required)."""
    import urllib.request
    req = urllib.request.Request(f"{API_BASE}/api/tasks/runner/ready")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return []


def get_waiting_tasks() -> list[dict]:
    """Returns waiting_for_agent tasks whose retry_after has passed."""
    import urllib.request
    req = urllib.request.Request(f"{API_BASE}/api/tasks/runner/waiting")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception:
        return []


def set_run_result(item_id: str, session_id: str, run_status: str, run_url: str | None = None) -> None:
    payload: dict = {"run_status": run_status}
    if run_url:
        payload["run_url"] = run_url
    _post(f"/api/pipeline/{item_id}/run-result", session_id, payload)


# ─── Stream parser ────────────────────────────────────────────────────────────

def _extract_log_line(event: dict) -> str | None:
    """Pull a human-readable progress line from a stream-json event."""
    t = event.get("type")

    if t == "assistant":
        lines = []
        for block in event.get("message", {}).get("content", []):
            if block.get("type") == "text":
                text = block["text"].strip()
                if text:
                    lines.append(text)
            elif block.get("type") == "tool_use":
                name = block.get("name", "")
                inp = block.get("input", {})
                if name == "Write":
                    lines.append(f"✍  Writing {inp.get('file_path', '')}")
                elif name == "Edit":
                    lines.append(f"✏️  Editing {inp.get('file_path', '')}")
                elif name == "Bash":
                    cmd = inp.get("command", "")[:80]
                    lines.append(f"▶  {cmd}")
                elif name == "Read":
                    lines.append(f"📖 Reading {inp.get('file_path', '')}")
                elif name in ("Glob", "Grep"):
                    lines.append(f"🔍 {name}: {inp.get('pattern', inp.get('glob', ''))}")
        return "\n".join(lines) if lines else None

    if t == "result":
        if event.get("is_error"):
            return f"❌ Error: {event.get('result', '')[:120]}"
        turns = event.get("num_turns", "?")
        cost = event.get("total_cost_usd", 0)
        return f"✅ Claude finished ({turns} turns, ${cost:.3f})"

    return None


# ─── Claude agent runner ──────────────────────────────────────────────────────

def run_claude_agent(target_dir: Path, prompt: str, item_id: str, session_id: str) -> bool:
    """
    Run claude as a fully autonomous agent in target_dir.
    Stream every meaningful event to the build log.
    Returns True on success.
    """
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]

    print(f"  [claude] spawning agent in {target_dir}")
    post_log(item_id, session_id, f"🤖 Claude agent started in {target_dir.name}/")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(target_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        success = False
        for raw_line in proc.stdout:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            log_line = _extract_log_line(event)
            if log_line:
                print(f"  [claude] {log_line[:120]}")
                post_log(item_id, session_id, log_line)

            if event.get("type") == "result":
                success = not event.get("is_error", False)

        proc.wait(timeout=30)
        return success

    except subprocess.TimeoutExpired:
        proc.kill()
        post_log(item_id, session_id, "⏱️  Claude agent timed out")
        return False
    except Exception as e:
        post_log(item_id, session_id, f"❌ Agent error: {e}")
        return False


# ─── Git / GitHub ─────────────────────────────────────────────────────────────

def get_gh_user() -> str:
    try:
        out = subprocess.run(["gh", "api", "user", "--jq", ".login"],
                             capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return os.environ.get("GH_USER", "unknown")


def git_push(target_dir: Path, slug: str, app_name: str,
             item_id: str, session_id: str) -> str:
    def run(cmd: list[str]) -> str:
        r = subprocess.run(cmd, cwd=str(target_dir),
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            raise RuntimeError(f"{' '.join(cmd[:2])}: {r.stderr.strip()}")
        return r.stdout.strip()

    gh_user = get_gh_user()
    repo_url = f"https://github.com/{gh_user}/{slug}"

    post_log(item_id, session_id, "📦 Initialising git repository...")
    git_dir = target_dir / ".git"
    if not git_dir.exists():
        run(["git", "init", "-b", "main"])
        run(["git", "add", "."])
        run(["git", "commit", "-m",
             f"Initial build: {app_name}\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"])
    else:
        run(["git", "add", "."])
        subprocess.run(["git", "commit", "-m", "Rebuild: regenerated files"],
                       cwd=str(target_dir), capture_output=True, text=True, timeout=30)

    post_log(item_id, session_id, f"🔒 Creating private GitHub repo: {slug}...")
    out = subprocess.run(
        ["gh", "repo", "create", slug, "--private"],
        cwd=str(target_dir), capture_output=True, text=True, timeout=60,
    )
    if out.returncode != 0 and "already exists" not in (out.stderr + out.stdout).lower():
        raise RuntimeError(f"gh repo create: {out.stderr.strip()}")

    post_log(item_id, session_id, "⬆️  Pushing to GitHub...")
    gh_token = subprocess.run(["gh", "auth", "token"],
                               capture_output=True, text=True).stdout.strip()
    token_url = f"https://{gh_token}@github.com/{gh_user}/{slug}.git"

    subprocess.run(["git", "remote", "remove", "origin"],
                   cwd=str(target_dir), capture_output=True, text=True)
    run(["git", "remote", "add", "origin", token_url])
    run(["git", "push", "-u", "origin", "main"])

    return repo_url


# ─── Build one item ──────────────────────────────────────────────────────────

def build_item(item: dict, session_id: str) -> None:
    item_id = item["id"]
    app_plan_raw = item.get("app_plan")
    if not app_plan_raw:
        mark_failed(item_id, session_id)
        return

    try:
        plan = json.loads(app_plan_raw)
    except Exception:
        mark_failed(item_id, session_id)
        return

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "new-app").lower())[:64] or "new-app"
    app_name = plan.get("app_name", slug)
    target_dir = REPOS_PATH / slug

    print(f"\n[build] {app_name} → {target_dir}")
    post_log(item_id, session_id, f"🚀 Build started: {app_name}")

    target_dir.mkdir(parents=True, exist_ok=True)

    ports = allocate_project_ports(slug)
    post_log(item_id, session_id,
             f"🔌 Allocated ports — frontend:{ports['frontend']} api:{ports['api']} db:{ports['db']}")

    scale = plan.get("scale", "large")
    template = BUILD_PROMPT_SMALL if scale == "small" else BUILD_PROMPT_LARGE
    prompt = template.format(
        plan_json=json.dumps(plan, indent=2),
        port_frontend=ports["frontend"],
        port_api=ports["api"],
        port_db=ports["db"],
    )
    success = run_claude_agent(target_dir, prompt, item_id, session_id)

    if not success:
        post_log(item_id, session_id, "❌ Build failed during code generation")
        mark_failed(item_id, session_id)
        return

    # Check something was actually written
    files_written = list(target_dir.rglob("*"))
    if len(files_written) < 3:
        post_log(item_id, session_id, "❌ No files were generated")
        mark_failed(item_id, session_id)
        return

    post_log(item_id, session_id, f"📁 {len(files_written)} files generated")

    try:
        repo_url = git_push(target_dir, slug, app_name, item_id, session_id)
        post_log(item_id, session_id, f"✅ Done! {repo_url}")
        mark_built(item_id, session_id, repo_url)
    except Exception as e:
        post_log(item_id, session_id, f"❌ Git push failed: {e}")
        mark_failed(item_id, session_id)


# ─── Native process run helpers ──────────────────────────────────────────────
# Projects are started via their own start.sh / stop.sh scripts.
# PIDs are tracked in .pids/ inside each project directory.

def _get_frontend_port(slug: str) -> int | None:
    """Return the frontend port from the registry, or None."""
    registry = _load_registry()
    entry = registry.get(slug, {})
    return entry.get("frontend") or entry.get("api") or None


def _kill_pids(target_dir: Path) -> None:
    """Kill all PIDs recorded in target_dir/.pids/"""
    pids_dir = target_dir / ".pids"
    if not pids_dir.exists():
        return
    for pid_file in pids_dir.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 15)  # SIGTERM
            print(f"  [run] Sent SIGTERM to PID {pid} ({pid_file.name})")
        except (ProcessLookupError, ValueError):
            pass
        except Exception as e:
            print(f"  [run] Could not kill {pid_file.name}: {e}")


NATIVE_SETUP_PROMPT = """You are migrating an existing project to run natively (no Docker).

Your ONLY jobs are:
1. Create start.sh — starts all services natively using env var ports with sensible defaults
2. Create stop.sh — stops all processes by killing PIDs in .pids/
3. Fix any config files that have hardcoded ports or Docker-specific hostnames

Port conventions (use these env vars with defaults):
  FRONTEND_PORT=${FRONTEND_PORT:-3000}
  API_PORT=${API_PORT:-8000}
  DB_PORT=${DB_PORT:-5432}
  APP_PORT=${APP_PORT:-5000}   # for single-process apps

start.sh MUST begin with:
```bash
#!/usr/bin/env bash
set -e

# Add Homebrew PostgreSQL to PATH (macOS)
for pg_bin in /opt/homebrew/opt/postgresql@15/bin /opt/homebrew/opt/postgresql@16/bin /opt/homebrew/opt/postgresql@17/bin /opt/homebrew/opt/postgresql@18/bin /opt/homebrew/bin /usr/local/opt/postgresql@15/bin; do
  [ -d "$pg_bin" ] && export PATH="$pg_bin:$PATH"
done

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
```

start.sh MUST:
- Set port defaults at the top using the above pattern
- mkdir -p .pids .logs
- For Python backends: check for venv with `[ ! -f venv/bin/uvicorn ]` (or flask/gunicorn) and create+install if missing
- For Node frontends: check for node_modules with `[ ! -d frontend/node_modules ]` and npm install if missing
- Wait for PostgreSQL with `pg_isready -d postgres` (not the app db, which may not exist yet)
- Start each process in the background (&), redirect stdout+stderr to .logs/<name>.log
- Write each PID: echo $! > .pids/<name>.pid
- Use full venv path for Python: `$ROOT_DIR/backend/venv/bin/uvicorn` not just `uvicorn`
- Print: echo "Started. Open: http://localhost:$FRONTEND_PORT"

stop.sh MUST:
- Loop over .pids/*.pid, kill each, remove file

Config files to check and fix:
- vite.config.ts/js: proxy target must use env var, e.g. `http://localhost:${process.env.API_PORT ?? '8000'}`
- .env / .env.example: replace Docker service hostnames (db, api, redis) with localhost and env var ports
- requirements.txt: unpin pydantic to `>=2.11.0` if pinned to 2.10.x or older (Python 3.14 wheels)
- Any app config that hardcodes a port number or Docker hostname

Do NOT:
- Change any application logic
- Refactor code
- Create docker-compose.yml

Read the project structure first, then write start.sh, stop.sh, and fix any config files.
"""


def _generate_start_sh(target_dir: Path, slug: str, item_id: str | None = None,
                       session_id: str | None = None) -> bool:
    """
    Use Claude to generate native start.sh/stop.sh and fix any hardcoded ports/
    Docker hostnames in config files. Falls back to heuristic if Claude unavailable.
    Returns True if start.sh was created.
    """
    print(f"  [run] Running Claude to generate native start scripts for {slug}...")
    if item_id and session_id:
        post_log(item_id, session_id, f"🔧 Generating native start scripts for {slug}...")

    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", NATIVE_SETUP_PROMPT, "--dangerously-skip-permissions",
             "--output-format", "stream-json", "--verbose"],
            cwd=str(target_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=180,
        )
        # Parse result from stream
        success = False
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
                if ev.get("type") == "result":
                    success = not ev.get("is_error", False)
            except Exception:
                pass

        if success and (target_dir / "start.sh").exists():
            (target_dir / "start.sh").chmod(0o755)
            if (target_dir / "stop.sh").exists():
                (target_dir / "stop.sh").chmod(0o755)
            print(f"  [run] Claude generated start.sh for {slug}")
            return True
    except Exception as e:
        print(f"  [run] Claude failed ({e}), falling back to heuristic")

    # ── Heuristic fallback ────────────────────────────────────────────────────
    has_frontend = (target_dir / "frontend").is_dir()
    has_backend = (target_dir / "backend").is_dir()
    has_requirements = (
        (target_dir / "requirements.txt").exists()
        or (target_dir / "backend" / "requirements.txt").exists()
    )
    has_app_py = (target_dir / "app.py").exists()
    has_vite = any((target_dir / f).exists() for f in [
        "vite.config.ts", "vite.config.js",
        "frontend/vite.config.ts", "frontend/vite.config.js",
    ])
    has_pkg = (target_dir / "package.json").exists()

    lines = [
        "#!/usr/bin/env bash", "set -e",
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"',
        'cd "$ROOT_DIR"', "",
        "# Add Homebrew PostgreSQL to PATH (macOS)",
        "for pg_bin in /opt/homebrew/opt/postgresql@15/bin /opt/homebrew/opt/postgresql@16/bin /opt/homebrew/opt/postgresql@17/bin /opt/homebrew/opt/postgresql@18/bin /opt/homebrew/bin /usr/local/opt/postgresql@15/bin; do",
        '  [ -d "$pg_bin" ] && export PATH="$pg_bin:$PATH"',
        "done", "",
        "FRONTEND_PORT=${FRONTEND_PORT:-3000}",
        "API_PORT=${API_PORT:-8000}",
        "APP_PORT=${APP_PORT:-5000}",
        "", "mkdir -p .pids .logs", "",
    ]
    generated = False

    if has_backend and has_requirements:
        lines += [
            'if [ ! -f "$ROOT_DIR/backend/venv/bin/uvicorn" ]; then',
            '  echo "Creating backend venv..."',
            '  python3 -m venv "$ROOT_DIR/backend/venv"',
            '  "$ROOT_DIR/backend/venv/bin/pip" install -q -r "$ROOT_DIR/backend/requirements.txt"',
            "fi",
            '(cd "$ROOT_DIR/backend" && "$ROOT_DIR/backend/venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port "$API_PORT" > "$ROOT_DIR/.logs/api.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/api.pid"', "",
        ]
        generated = True
    if has_app_py:
        lines += [
            'if [ ! -f "$ROOT_DIR/venv/bin/python" ]; then python3 -m venv "$ROOT_DIR/venv" && "$ROOT_DIR/venv/bin/pip" install -q -r "$ROOT_DIR/requirements.txt" 2>/dev/null || true; fi',
            'PORT="$APP_PORT" "$ROOT_DIR/venv/bin/python" app.py > "$ROOT_DIR/.logs/app.log" 2>&1 &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True
    if has_frontend and has_vite:
        lines += [
            'if [ ! -d "$ROOT_DIR/frontend/node_modules" ]; then npm --prefix "$ROOT_DIR/frontend" install --silent; fi',
            '(cd "$ROOT_DIR/frontend" && npm run dev -- --port "$FRONTEND_PORT" --host 0.0.0.0 > "$ROOT_DIR/.logs/frontend.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/frontend.pid"', "",
        ]
        generated = True
    elif has_pkg and not has_backend:
        lines += [
            'if [ ! -d "$ROOT_DIR/node_modules" ]; then npm --prefix "$ROOT_DIR" install --silent; fi',
            '(cd "$ROOT_DIR" && npm run dev -- --port "$FRONTEND_PORT" --host 0.0.0.0 > "$ROOT_DIR/.logs/app.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True

    if not generated:
        return False

    lines += ['echo "Started. Open: http://localhost:${FRONTEND_PORT}"']
    (target_dir / "start.sh").write_text("\n".join(lines) + "\n")
    (target_dir / "start.sh").chmod(0o755)
    (target_dir / "stop.sh").write_text(
        "#!/usr/bin/env bash\n"
        'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"\n'
        'for f in "$ROOT_DIR"/.pids/*.pid; do\n'
        '  [ -f "$f" ] || continue\n'
        '  kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"\n'
        "done\necho 'Stopped.'\n"
    )
    (target_dir / "stop.sh").chmod(0o755)
    return True


def start_project(item: dict, session_id: str) -> None:
    item_id = item["id"]
    slug = re.sub(r"[^a-z0-9\-]", "", json.loads(item.get("app_plan") or "{}").get("slug", "")) or item_id[:8]
    target_dir = REPOS_PATH / slug

    print(f"\n[run] Starting {slug}")
    if not target_dir.exists():
        print(f"  [run] Directory not found: {target_dir}")
        set_run_result(item_id, session_id, "failed")
        return

    start_script = target_dir / "start.sh"

    # Auto-generate start.sh if missing
    if not start_script.exists():
        print(f"  [run] No start.sh found — running Claude to generate one...")
        if not _generate_start_sh(target_dir, slug, item_id, session_id):
            print(f"  [run] Could not generate start.sh for {slug}.")
            set_run_result(item_id, session_id, "failed")
            return

    try:
        start_script.chmod(start_script.stat().st_mode | 0o111)

        # Inject registry-allocated ports as env vars, overriding start.sh defaults
        ports = allocate_project_ports(slug)
        env = os.environ.copy()
        env["FRONTEND_PORT"] = str(ports["frontend"])
        env["API_PORT"]      = str(ports["api"])
        env["DB_PORT"]       = str(ports["db"])
        env["APP_PORT"]      = str(ports["frontend"])  # single-process apps

        result = subprocess.run(
            ["bash", "start.sh"],
            cwd=str(target_dir),
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode != 0:
            print(f"  [run] start.sh failed:\n{result.stderr[:400]}")
            set_run_result(item_id, session_id, "failed")
            return

        run_url = f"http://localhost:{ports['frontend']}"
        print(f"  [run] Started. URL: {run_url}")
        set_run_result(item_id, session_id, "running", run_url)

    except subprocess.TimeoutExpired:
        print("  [run] start.sh timed out")
        set_run_result(item_id, session_id, "failed")
    except Exception as e:
        print(f"  [run] Error: {e}")
        set_run_result(item_id, session_id, "failed")


def stop_project(item: dict, session_id: str) -> None:
    item_id = item["id"]
    slug = re.sub(r"[^a-z0-9\-]", "", json.loads(item.get("app_plan") or "{}").get("slug", "")) or item_id[:8]
    target_dir = REPOS_PATH / slug

    print(f"\n[run] Stopping {slug}")
    if not target_dir.exists():
        set_run_result(item_id, session_id, "stopped")
        return

    stop_script = target_dir / "stop.sh"
    if stop_script.exists():
        try:
            stop_script.chmod(stop_script.stat().st_mode | 0o111)
            subprocess.run(["bash", "stop.sh"], cwd=str(target_dir),
                           capture_output=True, text=True, timeout=30)
        except Exception:
            pass
    # Always kill tracked PIDs as safety net
    _kill_pids(target_dir)
    print(f"  [run] Stopped.")
    set_run_result(item_id, session_id, "stopped")


# ─── Task execution ──────────────────────────────────────────────────────────

RATE_LIMIT_PHRASES = (
    "rate limit", "usage limit", "overloaded", "529", "quota",
    "too many requests", "RateLimitError",
)

TASK_PROMPT = """You are working on an existing codebase in the CURRENT DIRECTORY.

Project: {app_name}
Task type: {task_type}
Priority: {priority}

## Task
**{title}**

{description}

## Instructions
- Read the relevant files first to understand the existing code structure.
- Make only the changes needed to complete this task.
- Do not refactor unrelated code or add unrequested features.
- After completing the task, write a brief summary of:
  1. What you changed and why
  2. Any files created or modified
  3. Any important decisions or trade-offs

Be concise and focused. Complete the task precisely as described."""


def _task_api_url(item_id: str, task_id: str, suffix: str = "") -> str:
    return f"{API_BASE}/api/pipeline/{item_id}/tasks/{task_id}{suffix}"


def update_task_status(item_id: str, task_id: str, status: str,
                       agent_response: str | None = None,
                       retry_after_iso: str | None = None) -> None:
    import urllib.request
    payload: dict = {"status": status}
    if agent_response is not None:
        payload["agent_response"] = agent_response
    if retry_after_iso:
        payload["retry_after"] = retry_after_iso

    req = urllib.request.Request(
        _task_api_url(item_id, task_id, "/runner-update"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"  [task-api] runner-update failed: {e}")


def append_task_output(item_id: str, task_id: str, output: str) -> None:
    import urllib.request
    req = urllib.request.Request(
        _task_api_url(item_id, task_id, "/append-output"),
        data=json.dumps({"output": output}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception:
        pass


def pause_project_tasks(item_id: str) -> None:
    import urllib.request
    req = urllib.request.Request(
        f"{API_BASE}/api/tasks/runner/pause-project/{item_id}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"  [task-api] pause-project failed: {e}")


def resume_project_tasks(item_id: str) -> None:
    import urllib.request
    req = urllib.request.Request(
        f"{API_BASE}/api/tasks/runner/resume-project/{item_id}",
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        print(f"  [task-api] resume-project failed: {e}")


def _is_rate_limited(output: str) -> bool:
    lower = output.lower()
    return any(phrase.lower() in lower for phrase in RATE_LIMIT_PHRASES)


def run_claude_agent_for_task(target_dir: Path, prompt: str,
                               item_id: str, task_id: str) -> tuple[bool, bool]:
    """
    Run claude agent for a project task.
    Returns (success, rate_limited).
    Streams output to the task's agent_response field.
    """
    cmd = [
        CLAUDE_BIN,
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]

    print(f"  [task] Running Claude for task {task_id[:8]}... in {target_dir.name}/")
    append_task_output(item_id, task_id, f"🤖 Agent started in {target_dir.name}/\n")

    rate_limited = False
    full_output = []

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(target_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        success = False
        for raw_line in proc.stdout:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            log_line = _extract_log_line(event)
            if log_line:
                full_output.append(log_line)
                # Check every line for rate limit signals
                if _is_rate_limited(log_line):
                    rate_limited = True
                append_task_output(item_id, task_id, log_line)

            if event.get("type") == "result":
                success = not event.get("is_error", False)
                result_text = event.get("result", "")
                if result_text:
                    full_output.append(result_text)
                    if _is_rate_limited(result_text):
                        rate_limited = True
                    append_task_output(item_id, task_id, result_text)

        # Also check stderr for rate limit messages
        stderr_output = proc.stderr.read()
        if stderr_output and _is_rate_limited(stderr_output):
            rate_limited = True

        proc.wait(timeout=30)

        combined = "\n".join(full_output)
        if _is_rate_limited(combined):
            rate_limited = True

        return success and not rate_limited, rate_limited

    except subprocess.TimeoutExpired:
        proc.kill()
        append_task_output(item_id, task_id, "⏱️  Agent timed out")
        return False, False
    except Exception as e:
        append_task_output(item_id, task_id, f"❌ Agent error: {e}")
        return False, False


def execute_task(task: dict) -> None:
    """Execute a single project task using Claude Code."""
    item_id = task["pipeline_item_id"]
    task_id = task["task_id"]

    import json as _json
    plan = {}
    try:
        plan = _json.loads(task.get("app_plan") or "{}")
    except Exception:
        pass

    slug = re.sub(r"[^a-z0-9\-]", "", plan.get("slug", "")) or item_id[:8]
    app_name = task.get("chosen_name") or plan.get("app_name", slug)
    target_dir = REPOS_PATH / slug

    print(f"\n[task] {app_name} — {task['type']}: {task['title'][:60]}")

    # Mark in_progress
    update_task_status(item_id, task_id, "in_progress")

    if not target_dir.exists():
        msg = f"❌ Project directory not found: {target_dir}. Build the app first."
        append_task_output(item_id, task_id, msg)
        update_task_status(item_id, task_id, "done",
                           agent_response=msg)
        return

    # Migration tasks use NATIVE_SETUP_PROMPT instead of the generic task prompt
    if task.get("type") == "migrate":
        prompt = NATIVE_SETUP_PROMPT
    else:
        prompt = TASK_PROMPT.format(
            app_name=app_name,
            task_type=task.get("type", "feature"),
            priority=task.get("priority", "medium"),
            title=task.get("title", ""),
            description=task.get("description") or "No additional description provided.",
        )

    success, rate_limited = run_claude_agent_for_task(target_dir, prompt, item_id, task_id)

    if rate_limited:
        from datetime import datetime, timedelta
        retry_at = (datetime.utcnow() + timedelta(minutes=65)).isoformat()
        print(f"  [task] Rate limited! Pausing project tasks. Retry after {retry_at}")
        update_task_status(item_id, task_id, "waiting_for_agent",
                           agent_response="⏳ Hit Claude usage limit. Will retry automatically.",
                           retry_after_iso=retry_at)
        pause_project_tasks(item_id)
    elif success:
        print(f"  [task] Done: {task['title'][:60]}")
        # For migrate tasks, ensure scripts are executable
        if task.get("type") == "migrate":
            for script in ["start.sh", "stop.sh", "install.sh"]:
                p = target_dir / script
                if p.exists():
                    p.chmod(p.stat().st_mode | 0o111)
        update_task_status(item_id, task_id, "done")
        # Commit changes to git
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=str(target_dir), capture_output=True, timeout=30
            )
            subprocess.run(
                ["git", "commit", "-m",
                 f"{task['type']}: {task['title'][:72]}\n\nCo-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"],
                cwd=str(target_dir), capture_output=True, timeout=30
            )
        except Exception:
            pass
    else:
        print(f"  [task] Failed: {task['title'][:60]}")
        update_task_status(item_id, task_id, "done",
                           agent_response="❌ Task failed. Check the output above.")


# ─── Main loop ───────────────────────────────────────────────────────────────

def _send_heartbeat() -> None:
    """Tell the API this runner is alive. Fire-and-forget — never raises."""
    import urllib.request
    try:
        req = urllib.request.Request(
            f"{API_BASE}/api/status/heartbeat",
            data=b'{"runner":"build_runner"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


def main():
    print("Opportunity Scraper — Build Runner")
    print(f"Polling {API_BASE} every {POLL_INTERVAL}s...\n")

    _ensure_app_reserved()

    in_progress: set[str] = set()
    task_check_counter = 0  # only poll for waiting tasks every N cycles

    while True:
        _send_heartbeat()
        try:
            # ── Build + run ops (session-based) ──────────────────────────────
            if _SESSIONS_FILE.exists():
                session_ids = set(
                    l.strip() for l in _SESSIONS_FILE.read_text().splitlines() if l.strip()
                )
                for session_id in session_ids:
                    for item in get_building_items(session_id):
                        if item["id"] not in in_progress:
                            lock = Path(__file__).parent / f".build_lock_{item['id']}"
                            if lock.exists():
                                print(f"[runner] Lock exists for {item['id']}, skipping")
                                continue
                            lock.touch()
                            in_progress.add(item["id"])
                            print(f"[runner] Picked up build: {item['id']}")
                            try:
                                build_item(item, session_id)
                            finally:
                                in_progress.discard(item["id"])
                                lock.unlink(missing_ok=True)

                    for item in get_run_pending_items(session_id):
                        if item["id"] not in in_progress:
                            lock = Path(__file__).parent / f".run_lock_{item['id']}"
                            if lock.exists():
                                continue
                            lock.touch()
                            in_progress.add(item["id"])
                            print(f"[runner] Picked up run op ({item.get('run_status')}): {item['id']}")
                            try:
                                if item.get("run_status") == "starting":
                                    start_project(item, session_id)
                                elif item.get("run_status") == "stopping":
                                    stop_project(item, session_id)
                            finally:
                                in_progress.discard(item["id"])
                                lock.unlink(missing_ok=True)

            # ── Project tasks (global polling) ────────────────────────────────
            for task in get_ready_tasks():
                task_id = task["task_id"]
                if task_id not in in_progress:
                    lock = Path(__file__).parent / f".task_lock_{task_id}"
                    if lock.exists():
                        continue
                    lock.touch()
                    in_progress.add(task_id)
                    try:
                        execute_task(task)
                    finally:
                        in_progress.discard(task_id)
                        lock.unlink(missing_ok=True)

            # ── Retry waiting tasks (check every ~5 minutes) ──────────────────
            task_check_counter += 1
            if task_check_counter >= 75:  # 75 * 4s = 5 minutes
                task_check_counter = 0
                for task in get_waiting_tasks():
                    task_id = task["task_id"]
                    item_id = task["pipeline_item_id"]
                    if task_id not in in_progress:
                        print(f"[runner] Retrying rate-limited task {task_id[:8]}")
                        # Resume any paused sibling tasks
                        resume_project_tasks(item_id)
                        lock = Path(__file__).parent / f".task_lock_{task_id}"
                        if lock.exists():
                            continue
                        lock.touch()
                        in_progress.add(task_id)
                        try:
                            # Reset to ready so it gets picked up on next poll
                            update_task_status(item_id, task_id, "ready",
                                               agent_response="🔄 Retrying after rate limit pause...\n")
                        finally:
                            in_progress.discard(task_id)
                            lock.unlink(missing_ok=True)

        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)
        except Exception as e:
            print(f"[runner] Error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
