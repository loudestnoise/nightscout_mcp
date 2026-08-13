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


def get_tdd_by_day(days: int = 7) -> dict:
    """Get Total Daily Dose (TDD) of insulin for each day in the last N days.

    Implements Trio's TDD calculation:
    - Bolus: sum of all bolus insulin doses
    - Temp Basal: actual insulin from temp basals, accounting for overlaps and suspensions
    - Scheduled Basal: insulin from scheduled basal during gaps between temp basals

    Args:
        days: Number of days to analyze (default 7)

    Returns:
        dict with 'days' list (each day's TDD breakdown) and 'summary' (overall stats)
    """
    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    date_to = now.replace(
        hour=23, minute=59, second=59, microsecond=999999
    ).isoformat()

    # Fetch all treatments for the period
    treatments = get_treatments_by_range(date_from, date_to, count=999999)

    if not treatments:
        return {
            "period_days": days,
            "days": [],
            "summary": {
                "total_bolus_units": 0,
                "average_daily_bolus": 0,
                "average_tdd": 0,
            }
        }

    # Organize treatments by day
    by_day: dict[str, dict] = {}

    for treatment in treatments:
        if "created_at" not in treatment:
            continue
        try:
            ts = datetime.fromisoformat(
                treatment["created_at"].replace("Z", "+00:00")
            )
            day_key = ts.strftime("%Y-%m-%d")

            if day_key not in by_day:
                by_day[day_key] = {
                    "boluses": [],
                    "temp_basals": [],
                    "suspends": [],
                    "resumes": [],
                }

            # Collect boluses
            if treatment.get("insulin") and treatment.get("eventType") in [
                "Bolus", "Meal Bolus", "Correction Bolus", "Snack Bolus"
            ]:
                by_day[day_key]["boluses"].append(treatment["insulin"])

            # Collect temp basals with full info
            if treatment.get("eventType") == "Temp Basal" and treatment.get("rate"):
                by_day[day_key]["temp_basals"].append({
                    "timestamp": ts,
                    "rate": treatment.get("rate", 0),
                    "duration": treatment.get("duration", 0),
                })

            # Collect suspend/resume events
            if treatment.get("eventType") == "Suspend":
                by_day[day_key]["suspends"].append(ts)
            elif treatment.get("eventType") == "Resume":
                by_day[day_key]["resumes"].append(ts)

        except (ValueError, KeyError):
            pass

    # Fetch basal profile for scheduled basal calculations
    basal_profile = None
    try:
        profiles = get_profiles()
        if profiles and isinstance(profiles, list) and len(profiles) > 0:
            profile = profiles[0]
            # Nightscout profile structure: store -> defaultProfile -> basal
            if isinstance(profile, dict) and "store" in profile:
                store = profile["store"]
                # Get the default profile name
                default_profile_name = profile.get(
                    "defaultProfile", "default"
                )
                if default_profile_name in store:
                    profile_data = store[default_profile_name]
                    if "basal" in profile_data:
                        basal_profile = profile_data["basal"]
    except Exception:
        basal_profile = None

    # Calculate TDD for each day
    daily_tdd = []
    total_bolus = 0
    total_basal = 0

    for day_key in sorted(by_day.keys()):
        day_data = by_day[day_key]

        # Bolus: simple sum
        bolus_units = sum(day_data["boluses"])

        # Temp Basal: account for overlaps and suspensions
        temp_basal_units = _calculate_temp_basal_insulin(
            day_data["temp_basals"],
            day_data["suspends"],
            day_data["resumes"],
        )

        # Scheduled Basal: fill gaps between temp basals with profile basal rates
        scheduled_basal_units = 0
        if basal_profile:
            scheduled_basal_units = _calculate_scheduled_basal_insulin(
                day_data["temp_basals"],
                basal_profile,
                day_key,
            )

        total_basal_units = temp_basal_units + scheduled_basal_units
        tdd_units = bolus_units + total_basal_units
        total_bolus += bolus_units
        total_basal += total_basal_units

        daily_tdd.append({
            "date": day_key,
            "bolus_units": round(bolus_units, 2),
            "bolus_count": len(day_data["boluses"]),
            "temp_basal_units": round(temp_basal_units, 2),
            "scheduled_basal_units": round(scheduled_basal_units, 2),
            "total_basal_units": round(total_basal_units, 2),
            "temp_basal_count": len(day_data["temp_basals"]),
            "tdd_units": round(tdd_units, 2),
        })

    # Summary
    num_days = len(daily_tdd) if daily_tdd else 1
    avg_daily_bolus = total_bolus / num_days if num_days > 0 else 0
    avg_tdd = (total_bolus + total_basal) / num_days if num_days > 0 else 0

    return {
        "period_days": days,
        "days": daily_tdd,
        "summary": {
            "total_bolus_units": round(total_bolus, 2),
            "total_basal_units": round(total_basal, 2),
            "total_tdd_units": round(total_bolus + total_basal, 2),
            "average_daily_bolus": round(avg_daily_bolus, 2),
            "average_daily_basal": round(total_basal / num_days, 2) if num_days > 0 else 0,
            "average_tdd": round(avg_tdd, 2),
        }
    }


def _calculate_scheduled_basal_insulin(
    temp_basals: list, basal_profile: list, day_key: str
) -> float:
    """Calculate scheduled basal insulin delivered during gaps between temp basals.

    Algorithm:
    1. Find gaps between temp basal events
    2. For each gap, look up the profile basal rate for that time of day
    3. Calculate insulin = rate × gap_duration_hours
    4. Sum all gaps
    """
    if not temp_basals or not basal_profile:
        return 0

    # Sort temp basals by timestamp
    sorted_basals = sorted(temp_basals, key=lambda x: x["timestamp"])

    # Find gaps between temp basals
    day_start = datetime.fromisoformat(f"{day_key}T00:00:00+00:00")
    day_end = datetime.fromisoformat(f"{day_key}T23:59:59+00:00")
    now = datetime.now(timezone.utc)
    current_end = min(day_end, now)

    gaps = []

    # Gap before first temp basal
    if sorted_basals:
        first_basal_start = sorted_basals[0]["timestamp"]
        if first_basal_start > day_start:
            gaps.append((day_start, first_basal_start))

        # Gaps between temp basals
        for i in range(len(sorted_basals) - 1):
            current = sorted_basals[i]
            next_basal = sorted_basals[i + 1]

            # End of current basal
            current_end_time = current["timestamp"] + timedelta(
                minutes=current["duration"]
            )

            # Start of next basal
            next_start = next_basal["timestamp"]

            # If there's a gap between them
            if current_end_time < next_start:
                gaps.append((current_end_time, next_start))

        # Gap after last temp basal
        last_basal = sorted_basals[-1]
        last_basal_end = last_basal["timestamp"] + timedelta(
            minutes=last_basal["duration"]
        )
        if last_basal_end < current_end:
            gaps.append((last_basal_end, current_end))
    else:
        # No temp basals, entire day is gap
        gaps.append((day_start, current_end))

    # Calculate insulin for each gap using profile rates
    total_insulin = 0

    for gap_start, gap_end in gaps:
        current_time = gap_start
        while current_time < gap_end:
            # Find basal rate for current time
            rate = _get_basal_rate_for_time(current_time, basal_profile)

            if not rate:
                break

            # Find next rate change (either profile switch or gap end)
            next_rate_change = _get_next_profile_switch(
                current_time, basal_profile
            )
            if next_rate_change is None or next_rate_change > gap_end:
                next_rate_change = gap_end

            # Ensure we don't go past the gap end
            end_time = min(next_rate_change, gap_end)

            # Calculate insulin for this segment
            if end_time > current_time:
                duration_hours = (
                    (end_time - current_time).total_seconds() / 3600
                )
                insulin = rate * duration_hours
                total_insulin += insulin

            current_time = end_time

    return total_insulin


def _get_basal_rate_for_time(time: datetime, basal_profile: list) -> float:
    """Get basal rate from profile for a specific time of day."""
    # Extract time of day as minutes from midnight
    minutes_from_midnight = time.hour * 60 + time.minute

    # Find applicable profile entry
    applicable_rate = None
    for entry in basal_profile:
        # Entry format: {"time": "00:00", "timeAsSeconds": 0, "value": 0.5}
        if "timeAsSeconds" in entry:
            entry_minutes = entry["timeAsSeconds"] // 60
            if entry_minutes <= minutes_from_midnight:
                applicable_rate = entry.get("value", 0)

    return applicable_rate


def _get_next_profile_switch(time: datetime, basal_profile: list) -> datetime:
    """Find the next time the basal rate changes in the profile."""
    current_minutes = time.hour * 60 + time.minute
    day_start = datetime(
        time.year, time.month, time.day, tzinfo=timezone.utc
    )

    next_switch = None
    for entry in basal_profile:
        if "timeAsSeconds" in entry:
            entry_minutes = entry["timeAsSeconds"] // 60
            if entry_minutes > current_minutes:
                next_switch = day_start + timedelta(minutes=entry_minutes)
                break

    return next_switch


def _calculate_temp_basal_insulin(
    temp_basals: list, suspends: list, resumes: list
) -> float:
    """Calculate actual temp basal insulin delivery, accounting for overlaps and suspensions.

    Algorithm from Trio's TDDStorage.calculateTempBasalInsulin():
    1. Create merged timeline of temp basals and suspend/resume pairs
    2. Sort by start time
    3. For each temp basal, check if next event starts before it ends
    4. If yes, clip end time to next event start
    5. Handle overlapping suspensions
    6. Sum insulin delivered in actual time windows
    """
    if not temp_basals:
        return 0

    # Build timeline of events
    timeline = []

    # Add temp basals to timeline
    for tb in temp_basals:
        start = tb["timestamp"]
        end = start + timedelta(minutes=tb["duration"])
        timeline.append({
            "start": start,
            "end": end,
            "type": "temp_basal",
            "rate": tb["rate"],
        })

    # Add suspend/resume pairs to timeline
    for i, suspend_time in enumerate(suspends):
        if i < len(resumes):
            resume_time = resumes[i]
            timeline.append({
                "start": suspend_time,
                "end": resume_time,
                "type": "suspend",
                "rate": None,
            })

    # Sort by start time
    timeline.sort(key=lambda x: x["start"])

    # Calculate insulin delivery
    total_insulin = 0
    current_time = datetime.now(timezone.utc)
    last_suspend_end = None

    for i, event in enumerate(timeline):
        if event["type"] == "temp_basal":
            # Adjust end for ongoing temp basals
            actual_end = min(event["end"], current_time)
            actual_start = event["start"]

            # Check if next event (any type) interrupts this one
            if i + 1 < len(timeline):
                next_event = timeline[i + 1]
                if next_event["start"] < actual_end and next_event["type"] != "suspend":
                    actual_end = next_event["start"]

            # Adjust for overlapping suspensions
            if last_suspend_end and last_suspend_end > actual_start:
                actual_start = last_suspend_end

            # Calculate insulin if duration is valid
            duration_minutes = max(0, (actual_end - actual_start).total_seconds() / 60)
            if duration_minutes > 0 and event["rate"]:
                duration_hours = duration_minutes / 60
                insulin = event["rate"] * duration_hours
                if insulin > 0:
                    total_insulin += insulin

        elif event["type"] == "suspend":
            # Track when suspensions end for later temp basals
            last_suspend_end = event["end"]

    return total_insulin


def get_tir_by_day(
    days: int = 7, low: int = 70, high: int = 180
) -> dict:
    """Get Time-In-Range stats for each day in the last N days.

    Args:
        days: Number of days to analyze (default 7)
        low: Low threshold in mg/dL (default 70)
        high: High threshold in mg/dL (default 180)

    Returns:
        dict with 'days' list (each day's TIR stats) and 'summary' (overall stats)
    """
    now = datetime.now(timezone.utc)
    date_from = (now - timedelta(days=days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()
    date_to = now.replace(
        hour=23, minute=59, second=59, microsecond=999999
    ).isoformat()

    # Fetch all readings for the period
    readings = get_entries_by_range(date_from, date_to, count=999999)

    if not readings:
        return {
            "period_days": days,
            "days": [],
            "summary": {
                "total_readings": 0,
                "average_glucose": 0,
                "tir_pct": 0,
            }
        }

    # Group by day and compute TIR for each
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

    # Compute TIR for each day
    daily_tir = []
    all_values = []
    for day_key in sorted(by_day.keys()):
        values = by_day[day_key]
        all_values.extend(values)

        total = len(values)
        below_low = sum(1 for v in values if v < low)
        above_high = sum(1 for v in values if v >= high)
        in_range = total - below_low - above_high
        avg = sum(values) / total if total > 0 else 0

        daily_tir.append({
            "date": day_key,
            "readings": total,
            "average_glucose": round(avg, 1),
            "min": min(values),
            "max": max(values),
            "tir_pct": round(in_range / total * 100, 1) if total > 0 else 0,
            "below_range_pct": round(below_low / total * 100, 1) if total > 0 else 0,
            "above_range_pct": round(above_high / total * 100, 1) if total > 0 else 0,
        })

    # Compute overall summary
    total_readings = len(all_values)
    if total_readings > 0:
        overall_avg = sum(all_values) / total_readings
        overall_below = sum(1 for v in all_values if v < low)
        overall_above = sum(1 for v in all_values if v >= high)
        overall_in_range = total_readings - overall_below - overall_above
        overall_tir = (overall_in_range / total_readings * 100)
    else:
        overall_avg = overall_tir = 0

    return {
        "period_days": days,
        "thresholds": {"low": low, "high": high},
        "days": daily_tir,
        "summary": {
            "total_readings": total_readings,
            "average_glucose": round(overall_avg, 1),
            "tir_pct": round(overall_tir, 1),
            "min": min(all_values) if all_values else 0,
            "max": max(all_values) if all_values else 0,
        }
    }

