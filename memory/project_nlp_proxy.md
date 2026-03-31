---
name: NLP Proxy Architecture
description: All Claude NLP calls go through nlp_proxy.py on the host — Docker containers can't use macOS Keychain OAuth
type: project
---

All NLP modules (name_suggester, logo_generator, clone_analyzer, idea_generator, proposal_generator, app_plan_generator, sentiment, summarizer, entity_extraction) call claude via HTTP to a host-side proxy.

**Why:** Docker containers can't access macOS Keychain, so the `claude` CLI's OAuth tokens are unavailable inside Docker. The proxy runs on the host where claude is already authenticated.

**How to apply:**
- `nlp_proxy.py` runs on port 8002 on the host. Start it alongside build_runner.py with `python3 nlp_proxy.py`.
- `backend/app/nlp/claude_cli.py` calls `http://host.docker.internal:8002/claude` via httpx.
- docker-compose.yml has `extra_hosts: host.docker.internal:host-gateway` on api and worker services.
- The `claude` binary path on host is `/Users/louise/.local/bin/claude`.
