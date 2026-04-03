# MCP Nightscout

FastMCP server providing tools for diabetes type 1 management via Nightscout API.

## Key files
- `src/server.py` — MCP tools + auth middleware + health endpoint
- `src/nightscout_client.py` — HTTP client for Nightscout REST API v1
- `src/log_filter.py` + `src/log_config.yaml` — JSON logging, filters /health
- `tests/test_auth.py` — auth middleware tests (pytest-asyncio)

## Stack
- Python 3.12, FastMCP, httpx, uvicorn
- Docker → GitLab CI → Kubernetes (deploy/ templates)

## Environment variables
- `NIGHTSCOUT_URL` — Nightscout instance base URL
- `NIGHTSCOUT_API_SECRET` — API secret (hashed SHA1)
- `NIGHTSCOUT_TOKEN` — readable token (alternative to api-secret)
- `NIGHTSCOUT_TIMEOUT` — request timeout (default 30s)
- `MCP_AUTH_TOKEN` — MCP server auth token (optional for local dev)

## Adding a new tool
1. If it needs a new API call, add it to `nightscout_client.py`
2. Add `@mcp.tool()` function in `server.py` with clear docstring
3. Run `docker compose up --build` to test locally
