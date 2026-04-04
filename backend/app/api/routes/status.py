"""
Runner status / heartbeat endpoint.

build_runner.py (and any future agent) calls POST /api/status/heartbeat
every few seconds. GET /api/status/runners returns each runner's name,
last-seen timestamp, and whether it's considered alive (seen within 20s).

Runners can also POST /api/status/log to push log lines that the UI can poll.
"""
import subprocess
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# In-process store: { runner_name: last_seen_epoch_float }
_heartbeats: dict[str, float] = {}

# Rolling log buffer per runner — keeps last 500 lines each
_LOG_MAX = 500
_logs: dict[str, deque] = {}

# A runner is considered alive if its last heartbeat was within this window
_ALIVE_WINDOW_SECONDS = 20


class HeartbeatRequest(BaseModel):
    runner: str
    meta: dict[str, Any] | None = None


class LogRequest(BaseModel):
    runner: str
    line: str


class LogEntry(BaseModel):
    ts: float
    line: str


class RunnerStatus(BaseModel):
    runner: str
    alive: bool
    last_seen: float | None
    last_seen_ago: float | None


@router.post("/heartbeat", status_code=204)
async def heartbeat(body: HeartbeatRequest) -> None:
    _heartbeats[body.runner] = time.time()


@router.post("/log", status_code=204)
async def push_log(body: LogRequest) -> None:
    if body.runner not in _logs:
        _logs[body.runner] = deque(maxlen=_LOG_MAX)
    _logs[body.runner].append({"ts": time.time(), "line": body.line})


@router.get("/logs/{runner}", response_model=list[LogEntry])
async def get_logs(runner: str, tail: int = 200) -> list[LogEntry]:
    buf = _logs.get(runner, deque())
    entries = list(buf)
    return entries[-tail:]


_ROOT = Path(__file__).parents[4]
_VENV_BIN = _ROOT / "backend" / "venv" / "bin"
_VENV_SCRIPTS = _ROOT / "backend" / "venv" / "Scripts"  # Windows

def _venv(name: str) -> str:
    """Return path to a venv executable, preferring Scripts (Windows) over bin."""
    win = _VENV_SCRIPTS / (name + ".exe")
    if win.exists():
        return str(win)
    return str(_VENV_BIN / name)


_RESTART_COMMANDS: dict[str, list[str]] = {
    "build_runner": [
        sys.executable,
        str(_ROOT / "build_runner.py"),
    ],
    "celery": [
        _venv("celery"),
        "-A", "app.workers.celery_app", "worker",
        "--loglevel=warning", "--pool=solo",
    ],
}

# Map runner name → subprocess.Popen handle (so we can kill before restart)
_runner_procs: dict[str, Any] = {}


@router.post("/restart/{runner}", status_code=204)
async def restart_runner(runner: str) -> None:
    if runner not in _RESTART_COMMANDS:
        raise HTTPException(status_code=404, detail=f"No restart command for runner '{runner}'")

    cmd = _RESTART_COMMANDS[runner]
    cwd = str(_ROOT / "backend") if runner == "celery" else str(_ROOT)

    # Kill existing process if we launched it
    existing = _runner_procs.get(runner)
    if existing is not None:
        try:
            existing.terminate()
        except Exception:
            pass

    import os
    env = os.environ.copy()
    # Ensure claude.cmd is findable on Windows
    npm_bin = str(Path.home() / "AppData" / "Roaming" / "npm")
    if npm_bin not in env.get("PATH", ""):
        env["PATH"] = npm_bin + os.pathsep + env.get("PATH", "")
    env["CLAUDE_BIN"] = str(Path(npm_bin) / "claude.cmd")

    # Clear the log buffer so the UI shows a fresh slate
    _logs.pop(runner, None)

    proc = subprocess.Popen(cmd, cwd=cwd, env=env)
    _runner_procs[runner] = proc


@router.get("/runners", response_model=list[RunnerStatus])
async def get_runners() -> list[RunnerStatus]:
    now = time.time()
    known = {"build_runner", "celery"}
    for name in _heartbeats:
        known.add(name)

    result = []
    for name in sorted(known):
        last = _heartbeats.get(name)
        ago = (now - last) if last is not None else None
        result.append(RunnerStatus(
            runner=name,
            alive=ago is not None and ago < _ALIVE_WINDOW_SECONDS,
            last_seen=last,
            last_seen_ago=round(ago, 1) if ago is not None else None,
        ))
    return result
