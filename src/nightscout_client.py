import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

NIGHTSCOUT_URL = os.environ.get("NIGHTSCOUT_URL", "")
NIGHTSCOUT_API_SECRET = os.environ.get("NIGHTSCOUT_API_SECRET", "")
NIGHTSCOUT_TOKEN = os.environ.get("NIGHTSCOUT_TOKEN", "")
REQUEST_TIMEOUT = int(os.environ.get("NIGHTSCOUT_TIMEOUT", "30"))


def _headers() -> dict:
    """Build auth headers for Nightscout API."""
    h: dict = {"Content-Type": "application/json", "Accept": "application/json"}
    if NIGHTSCOUT_API_SECRET:
        h["api-secret"] = NIGHTSCOUT_API_SECRET
    return h


def _params() -> dict:
    """Build query params with token if set."""
    if NIGHTSCOUT_TOKEN:
        return {"token": NIGHTSCOUT_TOKEN}
    return {}


def _url(path: str) -> str:
    base = NIGHTSCOUT_URL.rstrip("/")
    return f"{base}/api/v1/{path.lstrip('/')}"


def _get(path: str, params: Optional[dict] = None) -> any:
    p = {**_params(), **(params or {})}
    resp = httpx.get(_url(path), headers=_headers(), params=p, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: any) -> any:
    resp = httpx.post(
        _url(path), headers=_headers(), params=_params(),
        json=data, timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _put(path: str, data: any) -> any:
    resp = httpx.put(
        _url(path), headers=_headers(), params=_params(),
        json=data, timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _delete(path: str) -> any:
    resp = httpx.delete(
        _url(path), headers=_headers(), params=_params(),
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else {"ok": True}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def health_check() -> bool:
    try:
        resp = httpx.get(
            f"{NIGHTSCOUT_URL.rstrip('/')}/api/v1/status.json",
            headers=_headers(), params=_params(), timeout=5,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------------------
# Server status / settings
# ---------------------------------------------------------------------------

def get_server_status() -> dict:
    return _get("status.json")


# ---------------------------------------------------------------------------
# Entries (CGM readings)
# ---------------------------------------------------------------------------

def get_entries(count: int = 10, find: Optional[dict] = None) -> list:
    params = {"count": str(count)}
    if find:
        for k, v in find.items():
            params[f"find[{k}]"] = str(v)
    return _get("entries.json", params)


def get_entries_by_range(date_from: str, date_to: str, count: int = 1000) -> list:
    params = {
        "find[dateString][$gte]": date_from,
        "find[dateString][$lte]": date_to,
        "count": str(count),
    }
    return _get("entries.json", params)


# ---------------------------------------------------------------------------
# Treatments (insulin, carbs, temp basals, notes)
# ---------------------------------------------------------------------------

def get_treatments(count: int = 10, find: Optional[dict] = None) -> list:
    params = {"count": str(count)}
    if find:
        for k, v in find.items():
            params[f"find[{k}]"] = str(v)
    return _get("treatments.json", params)


def get_treatments_by_range(date_from: str, date_to: str, count: int = 1000) -> list:
    params = {
        "find[created_at][$gte]": date_from,
        "find[created_at][$lte]": date_to,
        "count": str(count),
    }
    return _get("treatments.json", params)


def add_treatment(treatment: dict) -> any:
    return _post("treatments", [treatment])


def delete_treatment(treatment_id: str) -> any:
    return _delete(f"treatments/{treatment_id}")


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def get_profiles() -> list:
    return _get("profile.json")


def update_profile(profile: dict) -> any:
    return _put("profile", profile)


# ---------------------------------------------------------------------------
# Device status (pump, loop, uploader)
# ---------------------------------------------------------------------------

def get_device_status(count: int = 1) -> list:
    return _get("devicestatus.json", {"count": str(count)})
