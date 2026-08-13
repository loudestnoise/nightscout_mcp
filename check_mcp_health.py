#!/usr/bin/env python3
"""Check MCP Docker service health and log to Nightscout."""

import sys
import subprocess
import json
from datetime import datetime, timezone


def check_health(url):
    """Check MCP health endpoint."""
    try:
        result = subprocess.run(
            ["curl", "-s", url],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"status": "down", "error": "connection failed"}
        data = json.loads(result.stdout)
        return data
    except Exception as e:
        return {"status": "down", "error": str(e)}


def log_to_nightscout(status):
    """Log status to Nightscout via MCP."""
    token = os.environ.get("MCP_AUTH_TOKEN")
    mcp_url = f"http://localhost:8000/mcp/{token}"

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "log_treatment",
            "arguments": {
                "event_type": "Note",
                "notes": f"MCP status: {status['status']}. Nightscout API: {status.get('nightscout_api', 'unknown')}",
            },
        },
        "id": 1,
    }

    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-X",
                "POST",
                mcp_url,
                "-H",
                "Content-Type: application/json",
                "-H",
                "Accept: application/json, text/event-stream",
                "-d",
                json.dumps(payload),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def format_output(status, service_name):
    """Format status for display."""
    emoji = "✅" if status.get("status") == "ok" else "❌"

    output = f"{emoji} {service_name}: {status.get('status', 'unknown').upper()}"

    # Show API-specific details if available
    if status.get("nightscout_api") is not None:
        ns_api = "✅" if status.get("nightscout_api") else "❌"
        output += f" | Nightscout API: {ns_api}"

    if status.get("error"):
        output += f" | Error: {status['error']}"

    return output


def main():
    # Check both MCP services
    ns_status = check_health("http://localhost:8000/health")
    oura_status = check_health("http://localhost:8001/health")

    print(format_output(ns_status, "Nightscout MCP"))
    print(format_output(oura_status, "Oura MCP"))

    # Log to Nightscout if healthy
    if ns_status.get("status") == "ok":
        status_summary = f"Nightscout: {ns_status['status']}, Oura: {oura_status.get('status', 'unknown')}"
        log_to_nightscout({"status": status_summary, "nightscout_api": ns_status.get("nightscout_api")})


if __name__ == "__main__":
    main()
