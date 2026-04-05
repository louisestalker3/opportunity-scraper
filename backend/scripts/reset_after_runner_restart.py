"""
Reset DB state after a hard stop of the build runner / Opportunity Scraper stack.

Run from backend/ (so .env is picked up):
  cd backend && python scripts/reset_after_runner_restart.py

Uses a synchronous engine so it works whether DATABASE_URL uses asyncpg or psycopg2.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

from dotenv import load_dotenv

# Override machine-level DATABASE_URL (often malformed → user "u") with repo .env.
_env = BACKEND / ".env"
if _env.exists():
    load_dotenv(_env, override=True)
else:
    _ex = REPO_ROOT / ".env.example"
    if _ex.exists():
        load_dotenv(_ex, override=True)

from sqlalchemy import create_engine, text

from app.config import settings


def _sync_database_url() -> str:
    u = settings.database_url
    if "+asyncpg" in u:
        return u.replace("+asyncpg", "+psycopg2", 1)
    return u


def main() -> None:
    engine = create_engine(_sync_database_url())
    with engine.begin() as conn:
        r1 = conn.execute(
            text(
                """
                UPDATE project_tasks
                SET status = 'ready',
                    retry_after = NULL,
                    updated_at = NOW()
                WHERE status IN ('in_progress', 'paused', 'waiting_for_agent')
                """
            )
        )
        r2 = conn.execute(
            text(
                """
                UPDATE pipeline_items
                SET run_status = 'stopped',
                    run_url = NULL,
                    updated_at = NOW()
                WHERE run_status IN ('starting', 'stopping', 'running')
                """
            )
        )
        r3 = conn.execute(
            text(
                """
                UPDATE pipeline_items
                SET build_status = 'failed',
                    updated_at = NOW()
                WHERE build_status = 'building'
                """
            )
        )
        n1 = r1.rowcount if r1.rowcount is not None else -1
        n2 = r2.rowcount if r2.rowcount is not None else -1
        n3 = r3.rowcount if r3.rowcount is not None else -1
        print(f"Reset project_tasks (stuck agent states): {n1} row(s)")
        print(f"Reset pipeline_items (run stuck): {n2} row(s)")
        print(f"Reset pipeline_items (build stuck): {n3} row(s)")


if __name__ == "__main__":
    main()
