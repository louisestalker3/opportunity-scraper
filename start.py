#!/usr/bin/env python3
"""
Opportunity Scraper — unified startup manager.

Starts and supervises all host-side background services:
  - nlp_proxy.py     (port 8002 — Claude NLP for Docker containers)
  - build_runner.py  (polls API, runs claude to build apps)
  - docker-compose   (the main app stack)

Usage:
    python3 start.py            # start everything
    python3 start.py --no-docker  # host services only (skip docker-compose)
    python3 start.py status     # show what's running and exit
"""
import argparse
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
NLP_PROXY = HERE / "nlp_proxy.py"
BUILD_RUNNER = HERE / "build_runner.py"
PYTHON = sys.executable

# ─── Colour helpers ───────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

green  = lambda t: _c("32", t)
yellow = lambda t: _c("33", t)
red    = lambda t: _c("31", t)
bold   = lambda t: _c("1",  t)
dim    = lambda t: _c("2",  t)


# ─── Port / process checks ────────────────────────────────────────────────────

def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_pids(script_name: str) -> list[int]:
    """Return PIDs of python processes running the given script filename."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", script_name], text=True
        ).strip()
        return [int(p) for p in out.splitlines() if p.strip()]
    except subprocess.CalledProcessError:
        return []


# ─── Service descriptor ───────────────────────────────────────────────────────

class Service:
    def __init__(self, name: str, script: Path, check_fn, label: str):
        self.name = name
        self.script = script
        self.check_fn = check_fn   # () -> bool  — returns True if already running
        self.label = label
        self.proc: subprocess.Popen | None = None

    def is_running(self) -> bool:
        # Check if our own subprocess is still alive
        if self.proc is not None and self.proc.poll() is None:
            return True
        # Fall back to system-wide check (already running externally)
        return self.check_fn()

    def start(self) -> bool:
        """Launch the script as a background subprocess. Returns True on success."""
        if self.is_running():
            return True
        try:
            self.proc = subprocess.Popen(
                [PYTHON, str(self.script)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            # Give it a moment to fail fast (e.g. port already in use)
            time.sleep(0.8)
            if self.proc.poll() is not None:
                out, _ = self.proc.communicate()
                print(red(f"  [!] {self.name} exited immediately:"), out.decode()[:200])
                return False
            return True
        except Exception as exc:
            print(red(f"  [!] Failed to start {self.name}: {exc}"))
            return False

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ─── Services ─────────────────────────────────────────────────────────────────

nlp_service = Service(
    name="nlp_proxy",
    script=NLP_PROXY,
    check_fn=lambda: port_in_use(8002),
    label="NLP proxy      (port 8002)",
)

build_service = Service(
    name="build_runner",
    script=BUILD_RUNNER,
    check_fn=lambda: bool(find_pids("build_runner.py")),
    label="Build runner   (polls API)",
)

HOST_SERVICES = [nlp_service, build_service]


# ─── Status command ───────────────────────────────────────────────────────────

def cmd_status():
    print(bold("\nOpportunity Scraper — service status\n"))

    rows = [
        ("nlp_proxy.py",   port_in_use(8002),           "port 8002"),
        ("build_runner.py", bool(find_pids("build_runner.py")), "background process"),
        ("docker-compose",  port_in_use(8001),           "port 8001 (API)"),
        ("frontend (vite)", port_in_use(5173),           "port 5173"),
    ]

    for name, running, detail in rows:
        status = green("● running") if running else dim("○ stopped")
        print(f"  {status}  {name:<22} {dim(detail)}")
    print()


# ─── Main start ───────────────────────────────────────────────────────────────

def cmd_start(with_docker: bool):
    print(bold("\nOpportunity Scraper — starting services\n"))

    # 1. Host background services
    for svc in HOST_SERVICES:
        already = svc.check_fn()
        if already:
            print(green("  ✓") + f" {svc.label}  {dim('(already running)')}")
        else:
            print(yellow("  ↑") + f" {svc.label}  starting…", end="", flush=True)
            ok = svc.start()
            if ok:
                print(f"\r{green('  ✓')} {svc.label}  {green('started')}         ")
            else:
                print(f"\r{red('  ✗')} {svc.label}  {red('FAILED')}         ")

    # 2. docker-compose
    docker_proc: subprocess.Popen | None = None
    if with_docker:
        already_up = port_in_use(8001)
        if already_up:
            print(green("  ✓") + f" docker-compose        {dim('(already running)')}")
        else:
            print(yellow("  ↑") + "  docker-compose        starting…")
            try:
                docker_proc = subprocess.Popen(
                    ["docker-compose", "up", "--build"],
                    cwd=str(HERE),
                )
            except FileNotFoundError:
                try:
                    docker_proc = subprocess.Popen(
                        ["docker", "compose", "up", "--build"],
                        cwd=str(HERE),
                    )
                except Exception as exc:
                    print(red(f"  [!] Could not start docker-compose: {exc}"))

    print()
    print(bold("All services started.") + "  Press Ctrl+C to stop.\n")

    # ── Supervise: restart crashed host services, forward docker output ───────
    def _shutdown(sig, frame):
        print(f"\n{yellow('Shutting down…')}")
        for svc in HOST_SERVICES:
            svc.stop()
        if docker_proc and docker_proc.poll() is None:
            docker_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    while True:
        for svc in HOST_SERVICES:
            if not svc.is_running():
                print(yellow(f"  [restart] {svc.name} stopped — restarting…"))
                svc.start()

        if docker_proc is not None and docker_proc.poll() is not None:
            print(red("  [!] docker-compose exited."))
            docker_proc = None

        time.sleep(5)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Opportunity Scraper startup manager")
    parser.add_argument("command", nargs="?", default="start", choices=["start", "status"])
    parser.add_argument("--no-docker", action="store_true", help="Skip docker-compose")
    args = parser.parse_args()

    if args.command == "status":
        cmd_status()
    else:
        cmd_start(with_docker=not args.no_docker)
