"""
When importing a local git repo into the pipeline, detect common port usage,
record deployment-friendly defaults, and write small env templates so
Opportunity Scraper can assign registry ports via start.sh while deployments
can keep conventional defaults from .env.deploy.example.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Skip heavy / irrelevant subtrees when walking
_SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".git",
        "dist",
        "build",
        ".next",
        "coverage",
        "__pycache__",
        ".venv",
        "venv",
    }
)


def _read_text(path: Path, max_bytes: int = 400_000) -> str | None:
    try:
        return path.read_bytes()[:max_bytes].decode("utf-8", errors="replace")
    except Exception:
        return None


def _first_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except (ValueError, IndexError):
        return None


def detect_ports_in_repo(repo: Path) -> dict[str, int]:
    """
    Best-effort detection of frontend / API / DB ports from config and entrypoints.
    Returns keys only when a value was found; missing keys are filled with
    conventional defaults when merging for deployment files.
    """
    out: dict[str, int] = {}

    # docker-compose.yml — host port in "1234:5678"
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
        p = repo / name
        if p.exists():
            txt = _read_text(p)
            if txt:
                # first published port (host side)
                m = re.search(r"^\s*-\s*[\"']?(\d+):(\d+)", txt, re.MULTILINE)
                if m:
                    try:
                        out.setdefault("frontend", int(m.group(1)))
                    except ValueError:
                        pass
                m2 = re.search(r"POSTGRES|5432|5433", txt)
                if m2 and "db" not in out:
                    mm = re.search(r"(\d{4,5}):5432", txt)
                    if mm:
                        try:
                            out["db"] = int(mm.group(1))
                        except ValueError:
                            pass

    # Nest / Express listen
    for rel in (
        "backend/src/main.ts",
        "backend/src/main.js",
        "src/main.ts",
        "src/main.js",
        "server/src/main.ts",
    ):
        p = repo / rel
        if p.exists():
            txt = _read_text(p)
            if txt:
                port = _first_int(
                    r"listen\s*\([^)]*process\.env\.(?:PORT|API_PORT)\s*\?\?\s*(\d+)",
                    txt,
                ) or _first_int(r"listen\s*\(\s*(\d+)", txt)
                if port:
                    out.setdefault("api", port)
                    break

    # Vite proxy / dev server
    for p in repo.rglob("vite.config.*"):
        if any(x in p.parts for x in _SKIP_DIR_NAMES):
            continue
        txt = _read_text(p)
        if not txt:
            continue
        port = _first_int(r"localhost:(\d+)", txt) or _first_int(r"127\.0\.0\.1:(\d+)", txt)
        if port:
            out.setdefault("frontend", port)
        m = re.search(r"target:\s*[`'\"]?https?://(?:127\.0\.0\.1|localhost):(\d+)", txt, re.DOTALL)
        if m:
            try:
                out.setdefault("api", int(m.group(1)))
            except ValueError:
                pass
        break

    # Next.js — dev port in package.json script
    for pkg_dir in (repo / "frontend", repo / "web", repo / "client", repo):
        pkg = pkg_dir / "package.json"
        if not pkg.exists():
            continue
        try:
            data = json.loads(pkg.read_text())
        except Exception:
            continue
        dev = (data.get("scripts") or {}).get("dev", "")
        if isinstance(dev, str):
            m = re.search(r"(?:-p|--port)\s+(\d+)", dev)
            if m:
                try:
                    out.setdefault("frontend", int(m.group(1)))
                except ValueError:
                    pass
        if "next" in json.dumps(data).lower():
            break

    # package.json at root — nest start
    root_pkg = repo / "package.json"
    if root_pkg.exists():
        try:
            data = json.loads(root_pkg.read_text())
        except Exception:
            data = {}
        dev = (data.get("scripts") or {}).get("start:dev", "")
        if isinstance(dev, str) and "nest" in dev.lower():
            out.setdefault("api", out.get("api", 3000))

    # .env.example DATABASE_URL host port
    for env_path in (repo / ".env.example", repo / "backend" / ".env.example", repo / "frontend" / ".env.example"):
        if not env_path.exists():
            continue
        txt = _read_text(env_path)
        if not txt or "DATABASE_URL" not in txt:
            continue
        m = re.search(r":(\d{4,5})/", txt)
        if m:
            try:
                out.setdefault("db", int(m.group(1)))
            except ValueError:
                pass
        break

    return out


def _defaults_for_plan(detected: dict[str, int]) -> dict[str, int]:
    return {
        "frontend": int(detected.get("frontend", 3000)),
        "api": int(detected.get("api", 3000)),
        "db": int(detected.get("db", 5432)),
    }


def write_import_port_artifacts(
    repo: Path,
    slug: str,
    registry_ports: dict[str, int],
    detected: dict[str, int],
) -> list[str]:
    """
    Write .env.deploy.example (deployment defaults) and ensure a short
    .env.scraper.example describing registry-driven local runs.
    Returns list of relative paths written or updated.
    """
    written: list[str] = []
    deploy_defaults = _defaults_for_plan(detected)

    deploy_lines = [
        "# Deployment / Docker defaults (original or detected ports from import).",
        "# Copy to .env or your orchestrator — independent of Opportunity Scraper registry.",
        f"# Project slug: {slug}",
        "",
        f"FRONTEND_PORT={deploy_defaults['frontend']}",
        f"API_PORT={deploy_defaults['api']}",
        f"DB_PORT={deploy_defaults['db']}",
        f"NEXT_PUBLIC_API_PORT={deploy_defaults['api']}",
        "",
        "# Example DATABASE_URL (adjust user/password/db name)",
        f"# DATABASE_URL=postgresql://user:password@localhost:{deploy_defaults['db']}/appdb",
        "",
    ]
    deploy_path = repo / ".env.deploy.example"
    try:
        deploy_path.write_text("\n".join(deploy_lines) + "\n", encoding="utf-8")
        written.append(".env.deploy.example")
    except Exception:
        pass

    scraper_lines = [
        "# Opportunity Scraper — local runs use the port registry (9002+).",
        "# start.sh (generated or heuristic) sets FRONTEND_PORT, API_PORT, DB_PORT.",
        "# NEXT_PUBLIC_API_PORT is written to frontend/.env.local to match API_PORT.",
        f"# Registry snapshot at import: frontend={registry_ports.get('frontend')} "
        f"api={registry_ports.get('api')} db={registry_ports.get('db')}",
        "",
        f"# Defaults if you deploy without the scraper (see .env.deploy.example): "
        f"frontend={deploy_defaults['frontend']} api={deploy_defaults['api']} db={deploy_defaults['db']}",
        "",
    ]
    scraper_path = repo / ".env.scraper.example"
    try:
        scraper_path.write_text("\n".join(scraper_lines) + "\n", encoding="utf-8")
        written.append(".env.scraper.example")
    except Exception:
        pass

    # Optional: frontend/.env.example stub for Next (do not overwrite rich files)
    for fe in ("frontend", "web", "client"):
        fe_dir = repo / fe
        if not fe_dir.is_dir():
            continue
        pkg = fe_dir / "package.json"
        if not pkg.exists():
            continue
        try:
            data = json.loads(pkg.read_text())
        except Exception:
            continue
        if "next" not in json.dumps(data).lower():
            continue
        env_ex = fe_dir / ".env.example"
        block = (
            "\n# --- Opportunity Scraper (local) ---\n"
            "# NEXT_PUBLIC_API_PORT is injected by repo start.sh from API_PORT.\n"
            f"# For production defaults see ../../.env.deploy.example (api={deploy_defaults['api']}).\n"
            "NEXT_PUBLIC_API_PORT=3000\n"
        )
        try:
            if env_ex.exists():
                cur = env_ex.read_text(encoding="utf-8", errors="replace")
                if "Opportunity Scraper" not in cur:
                    env_ex.write_text(cur.rstrip() + block, encoding="utf-8")
                    written.append(str(env_ex.relative_to(repo)))
            else:
                env_ex.write_text(
                    "# Example env for Next.js\n"
                    f"NEXT_PUBLIC_API_PORT={deploy_defaults['api']}\n" + block,
                    encoding="utf-8",
                )
                written.append(str(env_ex.relative_to(repo)))
        except Exception:
            pass
        break

    return written


def build_app_plan_port_fields(
    slug: str,
    display_name: str,
    registry_ports: dict[str, int],
    detected: dict[str, int],
    written: list[str],
) -> dict[str, Any]:
    """Merge port metadata into the app_plan JSON structure."""
    deploy_defaults = _defaults_for_plan(detected)
    return {
        "slug": slug,
        "app_name": display_name,
        "scale": "large",
        "ports": registry_ports,
        "deployment_default_ports": deploy_defaults,
        "port_assignment": "opportunity_registry",
        "port_env": {
            "frontend": "FRONTEND_PORT",
            "api": "API_PORT",
            "db": "DB_PORT",
        },
        "import_port_detection": {
            "detected_raw": {k: int(v) for k, v in detected.items()},
            "artifacts_written": written,
        },
    }
