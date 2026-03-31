"""
Shared utility for calling the claude CLI directly as a subprocess.
"""
import json
import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

# Allow overriding the claude binary path via env var; otherwise find it on PATH
_CLAUDE_BIN = os.environ.get("CLAUDE_BIN") or shutil.which("claude") or "claude"


class ProxyUnavailableError(RuntimeError):
    """Raised when the claude CLI cannot be found or fails to respond."""


async def call_claude(prompt: str, system: str | None = None, raise_on_unavailable: bool = False) -> str:
    """
    Call claude via the CLI and return the text output.
    Returns empty string on failure unless raise_on_unavailable=True.
    """
    full_prompt = f"{system}\n\n---\n\n{prompt}" if system else prompt
    cmd = [_CLAUDE_BIN, "-p", full_prompt, "--output-format", "text"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            msg = f"claude exited {result.returncode}: {result.stderr[:300]}"
            logger.error(msg)
            if raise_on_unavailable:
                raise ProxyUnavailableError(msg)
            return ""
        return result.stdout.strip()
    except FileNotFoundError:
        msg = f"claude binary not found at '{_CLAUDE_BIN}' — install Claude Code CLI first"
        logger.error(msg)
        if raise_on_unavailable:
            raise ProxyUnavailableError(msg)
        return ""
    except subprocess.TimeoutExpired:
        msg = "claude timed out"
        logger.error(msg)
        if raise_on_unavailable:
            raise ProxyUnavailableError(msg)
        return ""
    except Exception as exc:
        logger.error("claude call failed: %s", exc)
        if raise_on_unavailable:
            raise ProxyUnavailableError(str(exc))
        return ""


def strip_code_fence(raw: str) -> str:
    """Remove ```json ... ``` fences from Claude output."""
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    if raw.endswith("```"):
        raw = raw[:-3].strip()
    return raw


async def call_claude_json(prompt: str, system: str | None = None) -> dict | list | None:
    """Call claude and parse the JSON response. Returns None on failure."""
    raw = await call_claude(prompt, system)
    if not raw:
        return None
    try:
        return json.loads(strip_code_fence(raw))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse claude JSON output: %s\nRaw: %.500s", exc, raw)
        return None
