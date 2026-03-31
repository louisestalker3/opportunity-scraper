"""
Runner status / heartbeat endpoint.

build_runner.py (and any future agent) calls POST /api/status/heartbeat
every few seconds. GET /api/status/runners returns each runner's name,
last-seen timestamp, and whether it's considered alive (seen within 20s).
"""
import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# In-process store: { runner_name: last_seen_epoch_float }
_heartbeats: dict[str, float] = {}

# A runner is considered alive if its last heartbeat was within this window
_ALIVE_WINDOW_SECONDS = 20


class HeartbeatRequest(BaseModel):
    runner: str   # e.g. "build_runner", "celery"
    meta: dict[str, Any] | None = None   # optional extra info (tasks in flight, etc.)


class RunnerStatus(BaseModel):
    runner: str
    alive: bool
    last_seen: float | None   # unix timestamp, None if never seen
    last_seen_ago: float | None  # seconds since last heartbeat


@router.post("/heartbeat", status_code=204)
async def heartbeat(body: HeartbeatRequest) -> None:
    _heartbeats[body.runner] = time.time()


@router.get("/runners", response_model=list[RunnerStatus])
async def get_runners() -> list[RunnerStatus]:
    now = time.time()
    # Always include known runners even if they've never sent a heartbeat
    known = {"build_runner", "celery"}
    seen = set(_heartbeats.keys())
    for name in seen:
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
