import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import sys
import json

import httpx

NIGHTSCOUT_URL = os.environ.get("NIGHTSCOUT_URL", "")
NIGHTSCOUT_API_SECRET = os.environ.get("NIGHTSCOUT_API_SECRET", "")
NIGHTSCOUT_TOKEN = os.environ.get("NIGHTSCOUT_TOKEN", "")
REQUEST_TIMEOUT = int(os.environ.get("NIGHTSCOUT_TIMEOUT", "30"))

# DEBUG: Log environment variables on startup
print(f"[DEBUG] NIGHTSCOUT_URL={NIGHTSCOUT_URL!r}", file=sys.stderr)
print(f"[DEBUG] NIGHTSCOUT_TOKEN={NIGHTSCOUT_TOKEN!r}", file=sys.stderr)
print(f"[DEBUG] NIGHTSCOUT_API_SECRET={'***' if NIGHTSCOUT_API_SECRET else 'not set'}", file=sys.stderr)


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
    base_params = _params()
    params_merged = {**base_params, **(params or {})}
    url = _url(path)

    # DETAILED DEBUG LOGGING
    print(f"[DEBUG] _get(path={path!r}, params={params!r})", file=sys.stderr)
    print(f"[DEBUG]   base_params={base_params}", file=sys.stderr)
    print(f"[DEBUG]   merged_params={params_merged}", file=sys.stderr)
    print(f"[DEBUG]   _url(path)={url}", file=sys.stderr)

    resp = httpx.get(url, headers=_headers(), params=params_merged, timeout=REQUEST_TIMEOUT)
    print(f"[DEBUG]   actual request URL: {resp.request.url}", file=sys.stderr)
    resp.raise_for_status()
    result = resp.json()
    # LOG WHAT DATA WAS RETURNED
    if isinstance(result, list) and result:
        first_item = result[0]
        print(f"[DEBUG] Response from {path}: list with {len(result)} items", file=sys.stderr)
        print(f"[DEBUG] First item keys: {list(first_item.keys()) if isinstance(first_item, dict) else type(first_item)}", file=sys.stderr)
        if isinstance(first_item, dict):
            print(f"[DEBUG] First item: sgv={first_item.get('sgv')}, eventType={first_item.get('eventType')}, device={first_item.get('device')}", file=sys.stderr)
    elif isinstance(result, dict):
        print(f"[DEBUG] Response from {path}: dict with keys {list(result.keys())[:5]}", file=sys.stderr)
    return result


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
    """Get Nightscout server status. Must return a dict, not a list."""
    print(f"[DEBUG] get_server_status() called", file=sys.stderr)
    result = _get("status.json")
    # Verify we got a dict, not a list of entries
    if isinstance(result, list):
        error_msg = f"get_server_status returned a list instead of dict. Expected server status, got: {result[0] if result else 'empty list'}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)
    if not isinstance(result, dict):
        error_msg = f"get_server_status returned unexpected type: {type(result)}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)
    print(f"[DEBUG] get_server_status() returning dict with status={result.get('status')}", file=sys.stderr)
    return result


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
    """Fetch treatments from /api/v1/treatments.json endpoint.

    Returns a list of treatment objects with fields like:
    - eventType: 'Bolus', 'Meal Bolus', 'Temp Basal', 'Carb Correction', etc.
    - insulin: insulin amount in units (for boluses)
    - carbs: carbs in grams (for carb entries)
    - created_at: ISO 8601 timestamp
    """
    print(f"[DEBUG] get_treatments(count={count}) called", file=sys.stderr)
    params = {"count": str(count)}
    if find:
        for k, v in find.items():
            params[f"find[{k}]"] = str(v)
    result = _get("treatments.json", params)

    # Validate we got a list of treatments, not glucose entries
    if not isinstance(result, list):
        error_msg = f"treatments endpoint returned non-list: {type(result)}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

    # Check if we accidentally got glucose entries (they have 'sgv' field, not 'eventType')
    if result and isinstance(result[0], dict):
        first = result[0]
        has_sgv = 'sgv' in first
        has_event_type = 'eventType' in first
        print(f"[DEBUG] First item: has_sgv={has_sgv}, has_eventType={has_event_type}", file=sys.stderr)
        if has_sgv and not has_event_type:
            error_msg = f"treatments endpoint returned glucose entries instead of treatments. Got: {json.dumps(first, default=str)}"
            print(f"[ERROR] {error_msg}", file=sys.stderr)
            raise ValueError(error_msg)

    print(f"[DEBUG] get_treatments() returning {len(result)} items", file=sys.stderr)
    return result


def get_treatments_by_range(date_from: str, date_to: str, count: int = 1000) -> list:
    """Fetch treatments by date range from /api/v1/treatments.json endpoint.

    Args:
        date_from: Start date in ISO 8601 format (e.g., '2026-08-12T00:00:00Z')
        date_to: End date in ISO 8601 format (e.g., '2026-08-12T23:59:59Z')
        count: Maximum number of treatments to return

    Returns:
        List of treatment objects with eventType, insulin, carbs, timestamps, etc.
    """
    params = {
        "find[created_at][$gte]": date_from,
        "find[created_at][$lte]": date_to,
        "count": str(count),
    }
    result = _get("treatments.json", params)

    # Validate we got a list of treatments, not glucose entries
    if not isinstance(result, list):
        raise ValueError(f"treatments endpoint returned non-list: {type(result)}")

    # Check if we accidentally got glucose entries
    if result and isinstance(result[0], dict):
        first = result[0]
        if 'sgv' in first and 'eventType' not in first:
            raise ValueError(f"treatments endpoint returned glucose entries instead of treatments. Got: {first}")

    return result


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
    """Get device status from /api/v1/devicestatus.json endpoint.

    Returns a list of device status objects containing:
    - device: device name (e.g., 'Trio', 'iPhone')
    - loop: loop algorithm status and decisions
    - pump: pump status (battery, bolusing, etc.)
    - uploader: CGM uploader info
    - created_at: timestamp

    NOT glucose entries - those have 'sgv' field.
    """
    print(f"[DEBUG] get_device_status(count={count}) called", file=sys.stderr)
    result = _get("devicestatus.json", {"count": str(count)})

    # Validate we got device status, not glucose entries
    if not isinstance(result, list):
        error_msg = f"devicestatus endpoint returned non-list: {type(result)}"
        print(f"[ERROR] {error_msg}", file=sys.stderr)
        raise ValueError(error_msg)

    # Check if we accidentally got glucose entries (they have 'sgv' field, devices have 'device', 'loop', or 'pump')
    if result and isinstance(result[0], dict):
        first = result[0]
        has_sgv = 'sgv' in first
        has_device_fields = any(k in first for k in ['device', 'loop', 'pump', 'uploader'])
        print(f"[DEBUG] First item: has_sgv={has_sgv}, has_device_fields={has_device_fields}, keys={list(first.keys())[:5]}", file=sys.stderr)
        if has_sgv and not has_device_fields:
            error_msg = f"devicestatus endpoint returned glucose entries instead of device status. Got: {json.dumps(first, default=str)}"
            print(f"[ERROR] {error_msg}", file=sys.stderr)
            raise ValueError(error_msg)

    print(f"[DEBUG] get_device_status() returning {len(result)} items", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Aggregated statistics (batch queries)
# ---------------------------------------------------------------------------

def get_aggregated_glucose_stats(date_from: str, date_to: str) -> dict:
    """Fetch all glucose readings for a date range in ONE API call
    and aggregate by day. Returns daily stats and weekly/overall
    summaries.

    Args:
        date_from: Start date in ISO format
            (e.g. '2026-01-03T00:00:00Z')
        date_to: End date in ISO format
            (e.g. '2026-04-03T23:59:59Z')

    Returns:
        dict with 'days' (list of daily stats) and 'summary'
    """
    # Single API call for entire range
    readings = get_entries_by_range(
        date_from, date_to, count=999999
    )

    if not readings:
        return {
            "period_from": date_from,
            "period_to": date_to,
            "days": [],
            "summary": {}
        }

    # Group readings by day
    by_day: dict[str, list] = {}
    for entry in readings:
        if "sgv" not in entry or "dateString" not in entry:
            continue
        try:
            ts = datetime.fromisoformat(
                entry["dateString"].replace("Z", "+00:00")
            )
            day_key = ts.strftime("%Y-%m-%d")
            by_day.setdefault(day_key, []).append(entry["sgv"])
        except (ValueError, KeyError):
            pass

    # Compute daily stats
    daily_stats = []
    all_readings = []
    for day_key in sorted(by_day.keys()):
        values = by_day[day_key]
        all_readings.extend(values)
        avg = sum(values) / len(values)
        below_70 = sum(1 for v in values if v < 70)
        above_180 = sum(1 for v in values if v >= 180)
        in_range = len(values) - below_70 - above_180
        in_tight_range = sum(1 for v in values if 70 <= v <= 140)
        sorted_vals = sorted(values)
        median = sorted_vals[len(values) // 2]
        std_dev = (
            sum((v - avg) ** 2 for v in values) / len(values)
        ) ** 0.5

        daily_stats.append({
            "date": day_key,
            "avg": round(avg, 1),
            "median": median,
            "std_dev": round(std_dev, 1),
            "min": min(values),
            "max": max(values),
            "readings": len(values),
            "tir_pct": round(in_range / len(values) * 100, 1),
            "titr_pct": round(
                in_tight_range / len(values) * 100, 1
            ),
            "tir_low_pct": round(below_70 / len(values) * 100, 1),
            "tir_high_pct": round(
                above_180 / len(values) * 100, 1
            ),
        })

    # Compute overall summary
    overall_avg = (
        sum(all_readings) / len(all_readings) if all_readings else 0
    )
    overall_below_70 = sum(1 for v in all_readings if v < 70)
    overall_above_180 = sum(1 for v in all_readings if v >= 180)
    overall_in_range = (
        len(all_readings) - overall_below_70 - overall_above_180
    )
    overall_in_tight_range = sum(
        1 for v in all_readings if 70 <= v <= 140
    )
    overall_std_dev = (
        (
            sum((v - overall_avg) ** 2 for v in all_readings)
            / len(all_readings)
        ) ** 0.5
        if all_readings
        else 0
    )
    estimated_hba1c = (
        round((overall_avg + 46.7) / 28.7, 1) if overall_avg > 0 else 0
    )

    # Weekday breakdown
    weekday_stats: dict[str, list] = {
        "Monday": [],
        "Tuesday": [],
        "Wednesday": [],
        "Thursday": [],
        "Friday": [],
        "Saturday": [],
        "Sunday": []
    }
    weekday_names = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday"
    ]
    for day_key in by_day:
        ts = datetime.fromisoformat(f"{day_key}T00:00:00Z")
        weekday = weekday_names[ts.weekday()]
        weekday_stats[weekday].extend(by_day[day_key])

    weekday_avgs = {
        day: round(sum(vals) / len(vals), 1) if vals else 0
        for day, vals in weekday_stats.items()
    }

    best_day = (
        min(daily_stats, key=lambda x: x["avg"]) if daily_stats else None
    )
    worst_day = (
        max(daily_stats, key=lambda x: x["avg"]) if daily_stats else None
    )

    return {
        "period_from": date_from,
        "period_to": date_to,
        "total_readings": len(all_readings),
        "days": daily_stats,
        "summary": {
            "overall_avg": round(overall_avg, 1),
            "overall_std_dev": round(overall_std_dev, 1),
            "overall_tir_pct": (
                round(
                    overall_in_range / len(all_readings) * 100, 1
                )
                if all_readings
                else 0
            ),
            "overall_titr_pct": (
                round(
                    overall_in_tight_range / len(all_readings) * 100,
                    1,
                )
                if all_readings
                else 0
            ),
            "overall_tir_low_pct": (
                round(
                    overall_below_70 / len(all_readings) * 100, 1
                )
                if all_readings
                else 0
            ),
            "overall_tir_high_pct": (
                round(
                    overall_above_180 / len(all_readings) * 100, 1
                )
                if all_readings
                else 0
            ),
            "estimated_hba1c": estimated_hba1c,
            "best_day": best_day["date"] if best_day else None,
            "best_day_avg": best_day["avg"] if best_day else None,
            "worst_day": worst_day["date"] if worst_day else None,
            "worst_day_avg": worst_day["avg"] if worst_day else None,
            "weekday_avgs": weekday_avgs,
        }
    }

