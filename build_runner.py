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
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("API_BASE", "http://localhost:9000")
REPOS_PATH = Path(os.environ.get("REPOS_PATH", Path.home() / "repos"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"
POLL_INTERVAL = 4


def _local_ip() -> str:
    """Return the machine's LAN IP (e.g. 192.168.x.x)."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


LOCAL_IP = _local_ip()

# On Windows, .cmd files must be invoked via cmd.exe
def _claude_cmd(*args: str) -> list[str]:
    if CLAUDE_BIN.lower().endswith(".cmd"):
        return ["cmd", "/c", CLAUDE_BIN, *args]
    return [CLAUDE_BIN, *args]

# Locate bash — on Windows the scheduled task may not have Git on PATH
_GIT_BASH_CANDIDATES = [
    r"C:\Program Files\Git\usr\bin\bash.exe",
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\usr\bin\bash.exe",
]
BASH_BIN: str = (
    shutil.which("bash")
    or next((p for p in _GIT_BASH_CANDIDATES if Path(p).exists()), None)
    or "bash"
)


def _bash_git_usr_bin() -> Path | None:
    """
    Git for Windows: dirname.exe / mkdir.exe live in usr\\bin next to bash.exe.
    Scheduled tasks often have an empty PATH — this path must not depend on env PATH.
    """
    candidates: list[Path] = []
    wb = shutil.which("bash")
    if wb:
        try:
            candidates.append(Path(wb).resolve())
        except Exception:
            pass
    for cand in _GIT_BASH_CANDIDATES:
        p = Path(cand)
        if p.is_file():
            try:
                candidates.append(p.resolve())
            except Exception:
                pass
    if Path(BASH_BIN).is_file():
        try:
            candidates.append(Path(BASH_BIN).resolve())
        except Exception:
            pass
    for bash_p in candidates:
        for parent in (bash_p.parent, bash_p.parent.parent):
            usr_bin = parent / "usr" / "bin"
            if usr_bin.is_dir():
                return usr_bin
    return None


def _win_dir_to_msys_git_path(p: Path) -> str:
    """Windows path -> MSYS path for export inside bash -c (spaces OK)."""
    try:
        s = str(p.resolve())
    except Exception:
        s = str(p)
    if len(s) >= 3 and s[1] == ":" and s[2] in (os.sep, "/"):
        drive = s[0].lower()
        rest = s[3:].replace("\\", "/")
        return f"/{drive}/{rest}"
    return s.replace("\\", "/")


def _bash_argv_run_start_sh() -> list[str]:
    """
    argv for running start.sh. On Windows, wrap in bash -c so PATH includes
    Git usr/bin even when the parent env['PATH'] is empty or ignored by a child.
    """
    if sys.platform != "win32":
        return [BASH_BIN, "start.sh"]
    u = _bash_git_usr_bin()
    if not u:
        return [BASH_BIN, "start.sh"]
    msys = _win_dir_to_msys_git_path(u)
    return [
        BASH_BIN,
        "-c",
        f'export PATH="{msys}:$PATH"; exec bash ./start.sh',
    ]


def _pid_alive(pid: int) -> bool:
    """True if a process with this PID exists (Windows + Unix)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but not ours — treat as holder alive
    except (OSError, AttributeError, ValueError):
        return False


def _try_acquire_side_lock(lock: Path) -> bool:
    """
    Cross-process lock for build/run/task. If a stale .lock file is left behind
    after a crash, the recorded PID is dead — we remove it and acquire.

    Returns True if this process owns the lock (caller must unlink in finally).
    Returns False if another live process holds the lock.
    """
    if lock.exists():
        try:
            raw = lock.read_text().strip()
            if raw.isdigit():
                pid = int(raw)
                if _pid_alive(pid):
                    return False
                print(f"[runner] Removing stale lock {lock.name} (pid {pid} not running)")
        except Exception:
            pass
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            return False
    try:
        lock.write_text(str(os.getpid()))
        return True
    except Exception:
        return False


def _win_git_paths_for_env() -> list[str]:
    """
    Git for Windows puts dirname, mkdir, cat, etc. in usr\\bin.
    Scheduled tasks often omit those; prepend so subprocess bash finds them.
    """
    if sys.platform != "win32":
        return []
    dirs: list[Path] = []
    u0 = _bash_git_usr_bin()
    if u0 is not None:
        dirs.append(u0)
    for base in (
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ):
        if not base:
            continue
        b = Path(base)
        dirs.extend([b / "Git" / "usr" / "bin", b / "Git" / "bin"])
    la = os.environ.get("LOCALAPPDATA", "")
    if la:
        dirs.append(Path(la) / "Programs" / "Git" / "usr" / "bin")
    scoop_git = Path.home() / "scoop" / "apps" / "git" / "current" / "usr" / "bin"
    if scoop_git.is_dir():
        dirs.append(scoop_git)
    # Bash we actually invoke — derive usr/bin even when PATH is empty
    try:
        bash_p = Path(BASH_BIN).resolve()
        if bash_p.is_file():
            for parent in (bash_p.parent, bash_p.parent.parent):
                cand = parent / "usr" / "bin"
                if cand.is_dir():
                    dirs.append(cand)
                if (parent / "mkdir.exe").is_file() or (parent / "dirname.exe").is_file():
                    dirs.append(parent)
    except Exception:
        pass
    git_exe = shutil.which("git")
    if git_exe:
        p = Path(git_exe).resolve()
        for parent in (p.parent, p.parent.parent):
            cand = parent / "usr" / "bin"
            if cand.is_dir():
                dirs.append(cand)
    # `where git` works when PATH is empty but System32 is still on PATH
    try:
        wr = subprocess.run(
            ["where", "git"],
            capture_output=True,
            text=True,
            timeout=8,
            encoding="utf-8",
            errors="replace",
        )
        if wr.returncode == 0 and wr.stdout:
            for line in wr.stdout.splitlines():
                line = line.strip()
                if not line.lower().endswith("git.exe"):
                    continue
                p = Path(line).resolve()
                for parent in (p.parent, p.parent.parent):
                    cand = parent / "usr" / "bin"
                    if cand.is_dir():
                        dirs.append(cand)
    except Exception:
        pass
    out: list[str] = []
    seen: set[str] = set()
    for d in dirs:
        if not d.is_dir():
            continue
        s = str(d.resolve())
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _win_node_paths_for_env() -> list[str]:
    """node.exe / npm.cmd live here; scheduled tasks often omit them from PATH."""
    if sys.platform != "win32":
        return []
    candidates: list[Path | None] = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "nodejs",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "ms" / "nodejs",
        Path.home() / "AppData" / "Roaming" / "npm",
    ]
    node = shutil.which("node")
    if node:
        candidates.append(Path(node).resolve().parent)
    out: list[str] = []
    seen: set[str] = set()
    for d in candidates:
        if d is None:
            continue
        try:
            if d.is_dir():
                s = str(d.resolve())
                if s not in seen:
                    seen.add(s)
                    out.append(s)
        except Exception:
            pass
    return out


# MSYS paths for generated start.sh/stop.sh (best-effort; scripts avoid dirname/mkdir/touch/cat)
_GIT_BASH_EXPORT_PATH_LINE = (
    'export PATH="/c/Program Files/Git/usr/bin:/c/Program Files/Git/bin:'
    '/c/Program Files (x86)/Git/usr/bin:/c/Program Files (x86)/Git/bin:$PATH"'
)

# No dirname(1): works when PATH is empty (Windows scheduled tasks / minimal Git Bash)
_BASH_ROOT_DIR_LINES = (
    '_script="${BASH_SOURCE[0]:-$0}"',
    '_dir="${_script%/*}"',
    'if [[ "$_dir" == "$_script" ]] || [[ -z "$_dir" ]]; then',
    '  _dir="."',
    "fi",
    'ROOT_DIR="$(cd "$_dir" && pwd)"',
)

# .pids / .logs and log stubs — no mkdir(1)/touch(1); PYTHON is set before this line in start.sh
_MKDIRS_AND_TOUCH_PY = (
    '"$PYTHON" -c "import pathlib; '
    "pathlib.Path('.pids').mkdir(parents=True, exist_ok=True); "
    "pathlib.Path('.logs').mkdir(parents=True, exist_ok=True); "
    "[pathlib.Path(p).touch() for p in "
    "('.logs/api.log', '.logs/frontend.log', '.logs/app.log', '.logs/prisma.log')]\"" 
)


def _mkdirs_touch_line_explicit(py_exe: str) -> str:
    """Same as _MKDIRS_AND_TOUCH_PY but with an absolute interpreter (patching old start.sh)."""
    return (
        f'"{py_exe}" -c "import pathlib; '
        "pathlib.Path('.pids').mkdir(parents=True, exist_ok=True); "
        "pathlib.Path('.logs').mkdir(parents=True, exist_ok=True); "
        "[pathlib.Path(p).touch() for p in "
        "('.logs/api.log', '.logs/frontend.log', '.logs/app.log', '.logs/prisma.log')]" + '"'
    )


def _write_stop_sh_windows_safe(target_dir: Path) -> None:
    """stop.sh without dirname/cat; kill is a bash builtin."""
    (target_dir / "stop.sh").write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "# No dirname/cat — PATH may be empty on Windows scheduled tasks\n"
        f"{_GIT_BASH_EXPORT_PATH_LINE}\n"
        + "\n".join(_BASH_ROOT_DIR_LINES)
        + '\ncd "$ROOT_DIR"\n'
        'for f in "$ROOT_DIR"/.pids/*.pid; do\n'
        '  [ -f "$f" ] || continue\n'
        '  read -r pid < "$f" || true\n'
        "  pid=\"${pid//$'\\r'/}\"\n"
        '  [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true; rm -f "$f"\n'
        "done\necho 'Stopped.'\n"
    )
    (target_dir / "stop.sh").chmod(0o755)


def _start_sh_needs_windows_fix(txt: str) -> bool:
    """True if start.sh still relies on dirname/mkdir from PATH (breaks empty-PATH Git Bash)."""
    if '_script="${BASH_SOURCE[0]:-$0}"' in txt:
        return False
    if "pathlib.Path('.pids').mkdir" in txt or "pathlib.path('.pids').mkdir" in txt.lower():
        return False
    if (
        re.search(r"\$\(\s*dirname\s", txt)
        or re.search(r"dirname\s+[\"']?\$0", txt)
        or re.search(r"dirname\s+\$\{", txt)
        or re.search(r"dirname\s+\$0\b", txt)
    ):
        return True
    if re.search(r"^\s*mkdir\s+-p\b", txt, re.MULTILINE) and "pathlib.path('.pids')" not in txt.lower():
        return True
    return False


def _patch_start_sh_remove_dirname_mkdir(path: Path, py_exe: str) -> bool:
    """In-place fix for common Claude-generated patterns when heuristics do not match the repo."""
    try:
        t = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    orig = t
    new_root = "\n".join(_BASH_ROOT_DIR_LINES)
    for pat in (
        r"^ROOT_DIR\s*=\s*\"\$\(cd\s*\"\$\(dirname\s+\"\$0\"\)\"\s*&&\s*pwd\)\"\s*$",
        r"^ROOT_DIR\s*=\s*\"\$\(cd\s*\"\$\(dirname\s+\"\$\{BASH_SOURCE\[0\]\}\"\)\"\s*&&\s*pwd\)\"\s*$",
        r"^ROOT_DIR\s*=\s*\"\$\(cd\s*\"\$\(dirname\s+\$0\)\"\s*&&\s*pwd\)\"\s*$",
    ):
        if re.search(pat, t, re.MULTILINE):
            t = re.sub(pat, new_root, t, count=1, flags=re.MULTILINE)
            break
    if t == orig:
        for old in (
            'ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"',
        ):
            if old in t:
                t = t.replace(old, new_root)
                break
    mk = _mkdirs_touch_line_explicit(py_exe)
    for pat in (r"^\s*mkdir\s+-p\s+\.pids\s+\.logs\s*$", r"^\s*mkdir\s+-p\s+\.pids\s+\.logs\s*\r?$"):
        if re.search(pat, t, re.MULTILINE):
            t = re.sub(pat, mk, t, count=1, flags=re.MULTILINE)
            break
    for _ in range(4):
        nt = re.sub(r"^touch\s+[^\n]+\n", "", t, count=1, flags=re.MULTILINE)
        if nt == t:
            break
        t = nt
    if t == orig:
        return False
    path.write_text(t, encoding="utf-8")
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except Exception:
        pass
    return True


def _maybe_rewrite_start_scripts_for_windows(target_dir: Path) -> bool:
    """
    Before running start.sh on Windows: replace scripts that still use dirname/mkdir.
    Prefer full heuristic regeneration; fall back to regex patch + stop.sh rewrite.
    """
    if sys.platform != "win32":
        return False
    start = target_dir / "start.sh"
    if not start.exists():
        return False
    try:
        txt = start.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return False
    if not _start_sh_needs_windows_fix(txt):
        return False
    if _heuristic_write_start_scripts(target_dir):
        return True
    py_exe = sys.executable.replace(chr(92), "/")
    if _patch_start_sh_remove_dirname_mkdir(start, py_exe):
        _write_stop_sh_windows_safe(target_dir)
        return True
    return False


def _push_log(line: str) -> None:
    """Send a log line to the API. Fire-and-forget."""
    try:
        data = json.dumps({"runner": "build_runner", "line": line}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/status/log",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass


_builtin_print = print


def print(*args, **kwargs):  # noqa: A001
    """Override print to also forward output to the API log endpoint."""
    _builtin_print(*args, **kwargs)
    line = " ".join(str(a) for a in args)
    _push_log(line)

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


_last_ready_tasks_error_log = 0.0


def get_ready_tasks() -> list[dict]:
    """Returns all tasks with status=ready (global, no session required)."""
    import urllib.request

    global _last_ready_tasks_error_log
    req = urllib.request.Request(f"{API_BASE}/api/tasks/runner/ready")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        now = time.time()
        if now - _last_ready_tasks_error_log >= 60:
            _last_ready_tasks_error_log = now
            print(f"[runner] get_ready_tasks failed ({API_BASE}/api/tasks/runner/ready): {e}")
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
    cmd = _claude_cmd(
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    )

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


def _kill_pids(target_dir: Path, *, quiet: bool = False) -> None:
    """Kill all PIDs recorded in target_dir/.pids/"""
    pids_dir = target_dir / ".pids"
    if not pids_dir.exists():
        return
    for pid_file in pids_dir.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 15)  # SIGTERM
            if not quiet:
                print(f"  [run] Sent SIGTERM to PID {pid} ({pid_file.name})")
        except (ProcessLookupError, ValueError):
            pass
        except Exception as e:
            if not quiet:
                print(f"  [run] Could not kill {pid_file.name}: {e}")


def _run_stop_sh_for_project(target_dir: Path, *, quiet: bool = False) -> None:
    """Run stop.sh if present, then SIGTERM any PIDs in .pids/ (frees dev server ports)."""
    stop_script = target_dir / "stop.sh"
    if stop_script.exists():
        try:
            stop_script.chmod(stop_script.stat().st_mode | 0o111)
            senv = os.environ.copy()
            if sys.platform == "win32":
                extra = os.pathsep.join(_win_git_paths_for_env() + _win_node_paths_for_env())
                if extra:
                    senv["PATH"] = extra + os.pathsep + senv.get("PATH", "")
            subprocess.run(
                [BASH_BIN, "stop.sh"],
                cwd=str(target_dir),
                capture_output=True,
                text=True,
                timeout=30,
                env=senv,
            )
        except Exception:
            pass
    _kill_pids(target_dir, quiet=quiet)


def _port_in_use_error(text: str) -> bool:
    """True if combined stderr/stdout indicates a TCP listen port conflict."""
    t = (text or "").lower()
    if "eaddrinuse" in t:
        return True
    if "address already in use" in t:
        return True
    if "port is already in use" in t:
        return True
    if "only one usage of each socket address" in t:
        return True
    return "already in use" in t and ("listen" in t or "bind" in t or "port" in t)


def _force_kill_listeners_on_ports_win(port_nums: list[int]) -> None:
    """Kill processes listening on the given TCP ports (Windows)."""
    nums = [int(p) for p in port_nums if p and 1 <= int(p) <= 65535]
    if not nums:
        return
    joined = ",".join(str(p) for p in nums)
    ps = (
        f"$ports = @({joined}); "
        "foreach ($p in $ports) { "
        "$c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue; "
        "foreach ($x in @($c)) { "
        "Stop-Process -Id $x.OwningProcess -Force -ErrorAction SilentlyContinue } }"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            timeout=45,
            capture_output=True,
        )
    except Exception:
        pass


def _force_kill_listeners_on_ports_unix(port_nums: list[int]) -> None:
    """Kill processes listening on the given TCP ports (macOS/Linux)."""
    nums = [int(p) for p in port_nums if p and 1 <= int(p) <= 65535]
    if not nums:
        return
    for p in nums:
        try:
            r = subprocess.run(
                ["lsof", "-t", f"-iTCP:{p}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if r.returncode != 0 or not (r.stdout or "").strip():
                continue
            for pid_s in (r.stdout or "").strip().split():
                try:
                    pid = int(pid_s)
                    if pid > 0:
                        os.kill(pid, 9)
                except (ProcessLookupError, ValueError, OSError):
                    pass
        except FileNotFoundError:
            try:
                subprocess.run(
                    ["fuser", "-k", f"{p}/tcp"],
                    capture_output=True,
                    timeout=8,
                )
            except Exception:
                pass
        except Exception:
            pass


def _force_kill_listeners_on_registry_ports(ports: dict) -> None:
    """
    Opportunity Scraper reserves frontend/api/db per app (9000+ range).
    If something is still bound, kill listeners so we can start cleanly.
    """
    keys = ("frontend", "api", "db")
    nums = [int(ports[k]) for k in keys if k in ports and ports[k] is not None]
    if not nums:
        return
    if sys.platform == "win32":
        _force_kill_listeners_on_ports_win(nums)
    else:
        _force_kill_listeners_on_ports_unix(nums)


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

# Repo root WITHOUT dirname(1) — Windows scheduled tasks often have empty PATH
_script="${BASH_SOURCE[0]:-$0}"
_dir="${_script%/*}"
if [[ "$_dir" == "$_script" ]] || [[ -z "$_dir" ]]; then _dir="."; fi
ROOT_DIR="$(cd "$_dir" && pwd)"
```

start.sh MUST:
- Set port defaults at the top using the above pattern
- Also set: PYTHON="${PYTHON:-$(which python3 2>/dev/null || which python)}"
- Create .pids and .logs using: `"$PYTHON" -c "import pathlib; pathlib.Path('.pids').mkdir(parents=True, exist_ok=True); pathlib.Path('.logs').mkdir(parents=True, exist_ok=True); ..."` (do NOT use mkdir/touch — PATH may lack coreutils on Windows)
- For Python backends: check for venv Scripts/uvicorn.exe (Windows) or bin/uvicorn (Unix) and create+install if missing; use full venv path
- For Node (Vite/React): check for node_modules and npm install if missing; pass --port and --host 0.0.0.0
- For Next.js: use `npm run dev -- -p $FRONTEND_PORT` (Next uses -p not --port)
- For NestJS: use `PORT=$API_PORT npm run start:dev`
- For Prisma (backend/prisma/schema.prisma): source `backend/.env` if present, then `export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}"` before `npm run start:dev` (use 5432 for local Postgres; DB_PORT is not the DB server port unless you run Postgres on that port)
- For PHP or plain HTML: use `php -S 0.0.0.0:$APP_PORT -t ./public` (or ./ if no public/ dir); use $(which php) for portability
- For PostgreSQL: wait with `pg_isready -d postgres` before starting dependent services
- Start each process in the background (&), redirect stdout+stderr to .logs/<name>.log
- Write each PID: echo $! > .pids/<name>.pid
- On Windows the venv executables are in Scripts/ not bin/ — check both: `Scripts/uvicorn.exe` then `bin/uvicorn`
- Print: echo "Started. Open: http://localhost:$FRONTEND_PORT" (or $APP_PORT for single-process)

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


def _heuristic_write_start_scripts(target_dir: Path) -> bool:
    """
    Write start.sh/stop.sh from repo layout (Python, Nest, Next, Vite, etc.).
    Returns True if a known stack was detected and files were written.
    """
    backend_req = target_dir / "backend" / "requirements.txt"
    has_pyproject_backend = (target_dir / "backend" / "pyproject.toml").exists()
    # Prefer frontend/, else first alternate with package.json (Vite apps often use client/ or web/)
    frontend_subdir = "frontend"
    if not (target_dir / "frontend").is_dir():
        for name in ("client", "web", "ui"):
            if (target_dir / name).is_dir() and (target_dir / name / "package.json").exists():
                frontend_subdir = name
                break
    has_frontend = (target_dir / frontend_subdir).is_dir()
    has_backend  = (target_dir / "backend").is_dir()
    has_requirements = (
        (target_dir / "requirements.txt").exists()
        or backend_req.exists()
    )
    has_app_py  = (target_dir / "app.py").exists()
    has_laravel = (target_dir / "artisan").exists() and (target_dir / "composer.json").exists()

    # Node project detection helpers
    def _pkg(d: Path) -> dict:
        p = d / "package.json"
        if p.exists():
            try:
                import json as _j; return _j.loads(p.read_text())
            except Exception:
                pass
        return {}

    root_pkg      = _pkg(target_dir)
    frontend_pkg  = _pkg(target_dir / frontend_subdir)
    backend_pkg   = _pkg(target_dir / "backend")

    def _is_next(pkg: dict)   -> bool: return "next" in pkg.get("dependencies", {}) or "next" in pkg.get("devDependencies", {})
    def _is_nest(pkg: dict)   -> bool: return "@nestjs/core" in pkg.get("dependencies", {})
    has_nest_cli = has_backend and (target_dir / "backend" / "nest-cli.json").exists()
    def _is_vite(pkg: dict)   -> bool: return "vite" in pkg.get("devDependencies", {}) or "vite" in pkg.get("dependencies", {})
    def _has_dev(pkg: dict)   -> bool: return "dev" in pkg.get("scripts", {})

    has_vite = (
        any((target_dir / f).exists() for f in ["vite.config.ts", "vite.config.js"])
        or any((target_dir / frontend_subdir / f).exists() for f in ["vite.config.ts", "vite.config.js"])
        or _is_vite(root_pkg) or _is_vite(frontend_pkg)
    )
    _fe_dir = f'"$ROOT_DIR/{frontend_subdir}"'
    has_pkg = bool(root_pkg)

    # PHP / HTML detection
    php_files  = list(target_dir.glob("*.php")) + list(target_dir.glob("public/*.php")) + list((target_dir / "src").glob("*.php") if (target_dir / "src").exists() else [])
    html_files = list(target_dir.glob("*.html")) + list(target_dir.glob("public/*.html"))
    has_php    = bool(php_files) or (target_dir / "composer.json").exists()
    has_html   = bool(html_files) and not has_php
    # Serve HTML through PHP dev server too (gracefully handles future PHP additions)
    serve_via_php = has_php or has_html

    # Determine public root for PHP server
    php_docroot = '"$ROOT_DIR/public"' if (target_dir / "public").is_dir() else '"$ROOT_DIR"'

    py_exe = sys.executable.replace(chr(92), "/")

    lines = [
        "#!/usr/bin/env bash", "set -e",
        "# Git Bash on Windows: PATH may be empty — no dirname/mkdir/touch (use bash + $PYTHON)",
        _GIT_BASH_EXPORT_PATH_LINE,
        *_BASH_ROOT_DIR_LINES,
        'cd "$ROOT_DIR"', "",
        "# Add Homebrew PostgreSQL to PATH (macOS)",
        "for pg_bin in /opt/homebrew/opt/postgresql@15/bin /opt/homebrew/opt/postgresql@16/bin /opt/homebrew/opt/postgresql@17/bin /opt/homebrew/opt/postgresql@18/bin /opt/homebrew/bin /usr/local/opt/postgresql@15/bin; do",
        '  [ -d "$pg_bin" ] && export PATH="$pg_bin:$PATH"',
        "done", "",
        "FRONTEND_PORT=${FRONTEND_PORT:-3000}",
        "API_PORT=${API_PORT:-8000}",
        "DB_PORT=${DB_PORT:-5432}",
        "APP_PORT=${APP_PORT:-5000}",
        f'PYTHON="${{PYTHON:-{py_exe}}}"',
        "",
        _MKDIRS_AND_TOUCH_PY,
        "",
    ]
    generated = False

    # ── Python FastAPI/uvicorn backend ────────────────────────────────────────
    # Backend deps must live under backend/ (root-level requirements.txt alone is ambiguous)
    if has_backend and (backend_req.exists() or has_pyproject_backend):
        if backend_req.exists():
            _pip_install = (
                '  "$ROOT_DIR/backend/venv/Scripts/pip.exe" install -q -r "$ROOT_DIR/backend/requirements.txt" '
                '2>/dev/null || "$ROOT_DIR/backend/venv/bin/pip" install -q -r "$ROOT_DIR/backend/requirements.txt"'
            )
        else:
            _pip_install = (
                '  "$ROOT_DIR/backend/venv/Scripts/pip.exe" install -q -e "$ROOT_DIR/backend" '
                '2>/dev/null || "$ROOT_DIR/backend/venv/bin/pip" install -q -e "$ROOT_DIR/backend"'
            )
        lines += [
            'if [ ! -f "$ROOT_DIR/backend/venv/Scripts/uvicorn.exe" ] && [ ! -f "$ROOT_DIR/backend/venv/bin/uvicorn" ]; then',
            '  echo "Creating backend venv..."',
            '  "$PYTHON" -m venv "$ROOT_DIR/backend/venv"',
            _pip_install,
            "fi",
            'UVICORN="$ROOT_DIR/backend/venv/Scripts/uvicorn.exe"; [ -f "$UVICORN" ] || UVICORN="$ROOT_DIR/backend/venv/bin/uvicorn"',
            '(cd "$ROOT_DIR" && npx --yes kill-port@2 "$API_PORT" 2>/dev/null) || true',
            '(cd "$ROOT_DIR/backend" && "$UVICORN" app.main:app --host 0.0.0.0 --port "$API_PORT" > "$ROOT_DIR/.logs/api.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/api.pid"', "",
        ]
        generated = True

    # ── NestJS backend ────────────────────────────────────────────────────────
    has_prisma = (target_dir / "backend" / "prisma" / "schema.prisma").exists()
    prisma_prep = (
        [
            '(cd "$ROOT_DIR/backend" && npx prisma generate >> "$ROOT_DIR/.logs/prisma.log" 2>&1) || true',
            '(cd "$ROOT_DIR/backend" && npx prisma migrate deploy >> "$ROOT_DIR/.logs/prisma.log" 2>&1) || exit 1',
            "",
        ]
        if has_prisma else []
    )
    if (_is_nest(backend_pkg) or has_nest_cli) and has_backend:
        nest_prisma_env: list[str] = []
        if has_prisma:
            nest_prisma_env = [
                'if [ -f "$ROOT_DIR/backend/.env" ]; then',
                '  set -a',
                '  . "$ROOT_DIR/backend/.env"',
                '  set +a',
                "fi",
                'export DATABASE_URL="${DATABASE_URL:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}"',
                "",
            ]
        lines += [
            *nest_prisma_env,
            'if [ ! -d "$ROOT_DIR/backend/node_modules" ]; then npm --prefix "$ROOT_DIR/backend" install --silent; fi',
            *prisma_prep,
            '(cd "$ROOT_DIR" && npx --yes kill-port@2 "$API_PORT" 2>/dev/null) || true',
            '(cd "$ROOT_DIR/backend" && {',
            '  echo "[start.sh] Starting Nest PORT=$API_PORT cwd=$(pwd)"',
            '  PORT="$API_PORT" npm run start:dev',
            '}) > "$ROOT_DIR/.logs/api.log" 2>&1 &',
            'echo $! > "$ROOT_DIR/.pids/api.pid"', "",
        ]
        generated = True
    elif _is_nest(root_pkg) and not has_frontend:
        lines += [
            'if [ ! -d "$ROOT_DIR/node_modules" ]; then npm install --silent; fi',
            '(cd "$ROOT_DIR" && npx --yes kill-port@2 "$API_PORT" 2>/dev/null) || true',
            '(cd "$ROOT_DIR" && {',
            '  echo "[start.sh] Starting Nest PORT=$API_PORT cwd=$(pwd)"',
            '  PORT="$API_PORT" npm run start:dev',
            '}) > "$ROOT_DIR/.logs/api.log" 2>&1 &',
            'echo $! > "$ROOT_DIR/.pids/api.pid"', "",
        ]
        generated = True

    # ── Plain Flask/Python app ────────────────────────────────────────────────
    if has_app_py:
        lines += [
            'if [ ! -f "$ROOT_DIR/venv/Scripts/python.exe" ] && [ ! -f "$ROOT_DIR/venv/bin/python" ]; then',
            '  "$PYTHON" -m venv "$ROOT_DIR/venv"',
            '  "$ROOT_DIR/venv/Scripts/pip.exe" install -q -r "$ROOT_DIR/requirements.txt" 2>/dev/null || "$ROOT_DIR/venv/bin/pip" install -q -r "$ROOT_DIR/requirements.txt" 2>/dev/null || true',
            "fi",
            'VENV_PY="$ROOT_DIR/venv/Scripts/python.exe"; [ -f "$VENV_PY" ] || VENV_PY="$ROOT_DIR/venv/bin/python"',
            'PORT="$APP_PORT" "$VENV_PY" app.py > "$ROOT_DIR/.logs/app.log" 2>&1 &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True

    # ── Next.js (frontend/subfolder or root) ──────────────────────────────────
    if _is_next(frontend_pkg) and has_frontend:
        lines += [
            f'printf "NEXT_PUBLIC_API_PORT=%s\\n" "$API_PORT" > "$ROOT_DIR/{frontend_subdir}/.env.local"',
            '(cd "$ROOT_DIR" && npx --yes kill-port@2 "$FRONTEND_PORT" 2>/dev/null) || true',
            f'if [ ! -d "$ROOT_DIR/{frontend_subdir}/node_modules" ]; then npm --prefix "$ROOT_DIR/{frontend_subdir}" install --silent; fi',
            f'(cd {_fe_dir} && npm run dev -- -p "$FRONTEND_PORT" > "$ROOT_DIR/.logs/frontend.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/frontend.pid"', "",
        ]
        generated = True
    elif _is_next(root_pkg):
        lines += [
            'printf "NEXT_PUBLIC_API_PORT=%s\\n" "$API_PORT" > "$ROOT_DIR/.env.local"',
            '(cd "$ROOT_DIR" && npx --yes kill-port@2 "$FRONTEND_PORT" 2>/dev/null) || true',
            'if [ ! -d "$ROOT_DIR/node_modules" ]; then npm install --silent; fi',
            '(cd "$ROOT_DIR" && npm run dev -- -p "$FRONTEND_PORT" > "$ROOT_DIR/.logs/app.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True

    # ── Vite frontend ─────────────────────────────────────────────────────────
    elif has_frontend and has_vite:
        lines += [
            f'if [ ! -d "$ROOT_DIR/{frontend_subdir}/node_modules" ]; then npm --prefix "$ROOT_DIR/{frontend_subdir}" install --silent; fi',
            f'(cd {_fe_dir} && npm run dev -- --port "$FRONTEND_PORT" --host 0.0.0.0 > "$ROOT_DIR/.logs/frontend.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/frontend.pid"', "",
        ]
        generated = True
    elif _is_vite(root_pkg) or (has_pkg and _has_dev(root_pkg) and not has_backend and not serve_via_php):
        lines += [
            'if [ ! -d "$ROOT_DIR/node_modules" ]; then npm install --silent; fi',
            '(cd "$ROOT_DIR" && npm run dev -- --port "$FRONTEND_PORT" --host 0.0.0.0 > "$ROOT_DIR/.logs/app.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True

    # ── Laravel ───────────────────────────────────────────────────────────────
    _php_search = (
        'PHP_BIN=""; '
        'for _p in /c/xampp/php/php.exe /c/php/php.exe /c/php8/php.exe /c/php82/php.exe /c/php83/php.exe '
        '"/c/Program Files/PHP/php.exe" "$(which php 2>/dev/null || true)"; do '
        '[ -f "$_p" ] && PHP_BIN="$_p" && break; done; '
        '[ -z "$PHP_BIN" ] && { echo "ERROR: PHP not found" >&2; exit 1; }'
    )
    if has_laravel:
        lines += [
            _php_search,
            '"$PHP_BIN" artisan migrate --force 2>/dev/null || true',
            '"$PHP_BIN" artisan serve --host=0.0.0.0 --port="$APP_PORT" > "$ROOT_DIR/.logs/app.log" 2>&1 &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"',
            'if [ -f "$ROOT_DIR/package.json" ]; then',
            '  if [ ! -d "$ROOT_DIR/node_modules" ]; then npm --prefix "$ROOT_DIR" install --silent; fi',
            '  (cd "$ROOT_DIR" && npm run dev > "$ROOT_DIR/.logs/vite.log" 2>&1) &',
            '  echo $! > "$ROOT_DIR/.pids/vite.pid"',
            'fi', "",
        ]
        generated = True

    # ── PHP / HTML (served via PHP built-in dev server) ───────────────────────
    elif serve_via_php:
        lines += [
            _php_search,
            f'(cd "$ROOT_DIR" && "$PHP_BIN" -S 0.0.0.0:"$APP_PORT" -t {php_docroot} > "$ROOT_DIR/.logs/app.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"',
            'echo "Started. Open: http://localhost:${APP_PORT}"', "",
        ]
        generated = True

    # ── Generic Node (package.json with dev script) ───────────────────────────
    if not generated and has_pkg and _has_dev(root_pkg):
        lines += [
            'if [ ! -d "$ROOT_DIR/node_modules" ]; then npm install --silent; fi',
            '(cd "$ROOT_DIR" && npm run dev > "$ROOT_DIR/.logs/app.log" 2>&1) &',
            'echo $! > "$ROOT_DIR/.pids/app.pid"', "",
        ]
        generated = True

    if not generated:
        return False

    lines += ['echo "Started. Open: http://localhost:${FRONTEND_PORT}"']
    (target_dir / "start.sh").write_text("\n".join(lines) + "\n")
    (target_dir / "start.sh").chmod(0o755)
    _write_stop_sh_windows_safe(target_dir)
    return True


def _generate_start_sh(target_dir: Path, slug: str, item_id: str | None = None,
                       session_id: str | None = None) -> bool:
    """
    Prefer layout-based start.sh/stop.sh (instant, no CLI). If the repo is not
    recognized, try Claude to write scripts and fix Docker-specific config.
    """
    if _heuristic_write_start_scripts(target_dir):
        print(f"  [run] Wrote native start scripts (layout detection) for {slug}")
        return True

    if item_id and session_id:
        post_log(item_id, session_id, f"🔧 Generating native start scripts for {slug}...")

    print(f"  [run] Running Claude to generate native start scripts for {slug}...")
    try:
        proc = subprocess.run(
            _claude_cmd("-p", NATIVE_SETUP_PROMPT, "--dangerously-skip-permissions",
             "--output-format", "stream-json", "--verbose"),
            cwd=str(target_dir),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=180,
        )
        stream_ok = False
        for line in proc.stdout.splitlines():
            try:
                ev = json.loads(line)
                if ev.get("type") == "result":
                    stream_ok = not ev.get("is_error", False)
            except Exception:
                pass

        start_path = target_dir / "start.sh"
        if start_path.exists():
            start_path.chmod(0o755)
            if (target_dir / "stop.sh").exists():
                (target_dir / "stop.sh").chmod(0o755)
            print(f"  [run] Claude generated start.sh for {slug}")
            return True

        err_tail = (proc.stderr or "").strip()
        if err_tail:
            print(f"  [run] Claude stderr: {err_tail[:800]}")
        if proc.returncode != 0:
            print(f"  [run] Claude exited {proc.returncode}")
        elif not stream_ok:
            print(f"  [run] Claude finished without start.sh (stream_ok={stream_ok})")
        else:
            print(f"  [run] Claude reported success but start.sh missing")
    except Exception as e:
        print(f"  [run] Claude failed ({e})")

    print(f"  [run] Could not generate start.sh (unrecognized layout; Claude did not write one)")
    return False


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
        print(f"  [run] No start.sh found — generating one (layout detection, then Claude if needed)...")
        if not _generate_start_sh(target_dir, slug, item_id, session_id):
            print(f"  [run] Could not generate start.sh for {slug}.")
            set_run_result(item_id, session_id, "failed")
            return

    # Windows: rewrite legacy/Claude start.sh that still call dirname/mkdir before first run
    if _maybe_rewrite_start_scripts_for_windows(target_dir):
        print("  [run] Refreshed start.sh/stop.sh for Windows (no dirname/mkdir)")

    # Free ports / PIDs from a previous run (avoids EADDRINUSE on Next/Nest dev servers)
    _run_stop_sh_for_project(target_dir, quiet=True)

    try:
        start_script.chmod(start_script.stat().st_mode | 0o111)

        # Inject registry-allocated ports as env vars, overriding start.sh defaults
        ports = allocate_project_ports(slug)
        # Free listeners on this project's ports before start.sh (Nest/Next often run in background
        # and leave start.sh exiting 0, so EADDRINUSE would not trigger the retry path below).
        _force_kill_listeners_on_registry_ports(ports)
        env = os.environ.copy()
        env["FRONTEND_PORT"] = str(ports["frontend"])
        env["API_PORT"]      = str(ports["api"])
        env["DB_PORT"]       = str(ports["db"])
        env["APP_PORT"]      = str(ports["frontend"])  # single-process apps
        env["PYTHON"]        = sys.executable           # so start.sh can use $PYTHON instead of python3
        if (target_dir / "backend" / "prisma" / "schema.prisma").exists():
            # Default Postgres is on 5432; registry DB_PORT is reserved for optional per-project Postgres.
            env.setdefault(
                "DATABASE_URL",
                "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
            )

        # On Windows, Git Bash + Node/npm are often missing from PATH (scheduled tasks).
        # Do not use bash --login — it can hang sourcing profiles on Windows.
        if sys.platform == "win32":
            extra = os.pathsep.join(_win_git_paths_for_env() + _win_node_paths_for_env())
            if extra:
                env["PATH"] = extra + os.pathsep + env.get("PATH", "")

        start_cmd = _bash_argv_run_start_sh()
        result = subprocess.run(
            start_cmd,
            cwd=str(target_dir),
            capture_output=True, text=True, timeout=600,
            env=env,
        )
        err = (result.stderr or "") + (result.stdout or "")
        low = err.lower()
        if result.returncode != 0 and (
            "dirname: command not found" in low
            or "mkdir: command not found" in low
        ) and _heuristic_write_start_scripts(target_dir):
            print("  [run] Regenerated start.sh/stop.sh (no dirname/mkdir); retrying...")
            start_script.chmod(start_script.stat().st_mode | 0o111)
            result = subprocess.run(
                _bash_argv_run_start_sh(),
                cwd=str(target_dir),
                capture_output=True, text=True, timeout=600,
                env=env,
            )

        err = (result.stderr or "") + (result.stdout or "")
        if result.returncode != 0 and _port_in_use_error(err):
            print(
                "  [run] Registry ports in use — force-killing listeners "
                f"({ports['frontend']}, {ports['api']}, {ports['db']}) and retrying once..."
            )
            _force_kill_listeners_on_registry_ports(ports)
            _run_stop_sh_for_project(target_dir, quiet=True)
            result = subprocess.run(
                start_cmd,
                cwd=str(target_dir),
                capture_output=True, text=True, timeout=600,
                env=env,
            )

        if result.returncode != 0:
            err = (result.stderr or "") + (result.stdout or "")
            print(f"  [run] start.sh failed:\n{err[:400]}")
            if "dirname: command not found" in err.lower() or "mkdir: command not found" in err.lower():
                print(
                    "  [run] Hint: remove start.sh (and stop.sh) in the project folder, then Start again "
                    "— or fix PATH so Git usr/bin is visible to bash."
                )
            set_run_result(item_id, session_id, "failed")
            return

        run_url = f"http://{LOCAL_IP}:{ports['frontend']}"
        print(f"  [run] Started. URL: {run_url}")
        set_run_result(item_id, session_id, "running", run_url)

    except subprocess.TimeoutExpired:
        print("  [run] start.sh timed out (10m) — try npm install manually in the project repo")
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

    _run_stop_sh_for_project(target_dir)
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
    cmd = _claude_cmd(
        "-p", prompt,
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    )

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
            # ── Project tasks FIRST (builder / Claude) ─────────────────────────
            # Run/build/start ops below can block for minutes (npm, start.sh timeout).
            # If they ran first, ready tasks would never be polled — agent looked "stuck".
            for task in get_ready_tasks():
                task_id = task["task_id"]
                if task_id not in in_progress:
                    lock = Path(__file__).parent / f".task_lock_{task_id}"
                    if not _try_acquire_side_lock(lock):
                        continue
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
                        if not _try_acquire_side_lock(lock):
                            continue
                        in_progress.add(task_id)
                        try:
                            # Reset to ready so it gets picked up on next poll
                            update_task_status(item_id, task_id, "ready",
                                               agent_response="🔄 Retrying after rate limit pause...\n")
                        finally:
                            in_progress.discard(task_id)
                            lock.unlink(missing_ok=True)

            # ── Build + run ops (session-based) ──────────────────────────────
            if _SESSIONS_FILE.exists():
                session_ids = set(
                    l.strip() for l in _SESSIONS_FILE.read_text().splitlines() if l.strip()
                )
                for session_id in session_ids:
                    for item in get_building_items(session_id):
                        if item["id"] not in in_progress:
                            lock = Path(__file__).parent / f".build_lock_{item['id']}"
                            if not _try_acquire_side_lock(lock):
                                print(f"[runner] Lock held for build {item['id']}, skipping")
                                continue
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
                            if not _try_acquire_side_lock(lock):
                                continue
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

        except KeyboardInterrupt:
            print("\nStopped.")
            sys.exit(0)
        except Exception as e:
            print(f"[runner] Error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
