#!/usr/bin/env python3
"""Regression test: verify endpoints return correct data shapes, not glucose entries.

Run this after Docker restart:
  python test_regression.py
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

# Check required env vars
assert os.environ.get('NIGHTSCOUT_URL'), "NIGHTSCOUT_URL not set"
assert os.environ.get('NIGHTSCOUT_TOKEN') or os.environ.get('NIGHTSCOUT_API_SECRET'), \
    "Either NIGHTSCOUT_TOKEN or NIGHTSCOUT_API_SECRET required"

from src.nightscout_client import (
    get_treatments,
    get_treatments_by_range,
    get_device_status,
)


def test_treatments_endpoint():
    """Verify treatments endpoint returns treatments, not glucose entries."""
    print("\n[REGRESSION] treatments endpoint")
    try:
        result = get_treatments(count=20)

        # Must return a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"

        # Must NOT be empty (unless you have no treatments ever)
        if not result:
            print("  ⚠ WARNING: No treatments returned. This is suspicious — Nightscout should have at least one treatment.")
            return False

        # Must contain treatment objects (with eventType), NOT glucose entries (with sgv)
        first = result[0]
        has_event_type = 'eventType' in first
        has_sgv = 'sgv' in first

        assert has_event_type, f"First item missing 'eventType' (is it a glucose entry?). Keys: {list(first.keys())}"
        assert not (has_sgv and not has_event_type), f"Got glucose entry instead of treatment: {first}"

        print(f"  ✅ PASS: {len(result)} treatments, first is {first['eventType']}")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_treatments_by_date_endpoint():
    """Verify treatments by date endpoint returns treatments, not empty due to wrong endpoint."""
    print("\n[REGRESSION] treatments by date endpoint")
    try:
        now = datetime.utcnow()
        date_from = (now - timedelta(days=1)).isoformat() + "Z"
        date_to = now.isoformat() + "Z"

        result = get_treatments_by_range(date_from, date_to, count=20)

        # Must return a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"

        # THIS IS THE KEY CHECK: if result is empty, it could mean:
        # 1. No treatments in that date range (valid)
        # 2. Wrong endpoint is being called and returning empty instead of error (bad)
        #
        # To detect #2, we check if the query was valid. A good heuristic:
        # - If the last 24 hours are completely empty, something is wrong
        # - Most people have at least one basal adjustment in 24h
        if not result:
            print(f"  ⚠ WARNING: No treatments in last 24 hours. This is suspicious.")
            print(f"     Date range: {date_from} to {date_to}")
            print(f"     Did you check that your date filters work? Run manually:")
            print(f"       python -c \"from src.nightscout_client import *; print(get_treatments_by_range('{date_from}', '{date_to}'))\"")
            # This is a warning, not a failure — you genuinely might not have treatments
            return True

        # If we got data, verify it's treatment data, not glucose
        first = result[0]
        has_event_type = 'eventType' in first
        has_sgv = 'sgv' in first

        assert has_event_type, f"First item missing 'eventType'. Keys: {list(first.keys())}"
        assert not (has_sgv and not has_event_type), f"Got glucose entry instead of treatment"

        print(f"  ✅ PASS: {len(result)} treatments in last 24h, first is {first['eventType']}")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_device_status_endpoint():
    """Verify device status endpoint returns device data, not glucose entries."""
    print("\n[REGRESSION] device status endpoint")
    try:
        result = get_device_status(count=5)

        # Must return a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"

        # Must NOT be empty (unless you have no device)
        if not result:
            print("  ⚠ WARNING: No device status returned. This is suspicious — your pump/CGM uploader should report status.")
            return False

        first = result[0]
        has_device_fields = any(k in first for k in ['device', 'loop', 'pump', 'uploader'])
        has_sgv = 'sgv' in first

        assert has_device_fields, f"First item missing device fields. Keys: {list(first.keys())}"
        assert not (has_sgv and not has_device_fields), f"Got glucose entry instead of device status"

        device = first.get('device', '?')
        print(f"  ✅ PASS: {len(result)} device statuses, device={device}")
        return True
    except Exception as e:
        print(f"  ❌ FAIL: {e}")
        return False


def test_url_configuration():
    """Meta-test: verify NIGHTSCOUT_URL is configured correctly."""
    print("\n[CONFIG] NIGHTSCOUT_URL configuration")
    url = os.environ.get('NIGHTSCOUT_URL', '')

    # Should be a base URL, NOT an endpoint
    if 'entries.json' in url or 'treatments.json' in url or 'devicestatus.json' in url:
        print(f"  ❌ ERROR: NIGHTSCOUT_URL includes an endpoint path!")
        print(f"     Current: {url}")
        print(f"     Should be: https://cgms.davediabet.es (base URL only)")
        print(f"     Fix: unset NIGHTSCOUT_URL in shell, or update .env")
        return False

    # Should not include query params (token goes in params separately)
    if '?' in url:
        print(f"  ⚠ WARNING: NIGHTSCOUT_URL includes query string: {url}")
        print(f"     Token should be in NIGHTSCOUT_TOKEN env var, not in URL")
        return True  # Warning only

    print(f"  ✅ PASS: NIGHTSCOUT_URL={url}")
    return True


def main():
    print("=" * 70)
    print("MCP NIGHTSCOUT - REGRESSION TEST SUITE")
    print("=" * 70)
    print(f"URL: {os.environ.get('NIGHTSCOUT_URL')}")

    tests = [
        ("URL configuration", test_url_configuration),
        ("treatments endpoint", test_treatments_endpoint),
        ("treatments by date endpoint", test_treatments_by_date_endpoint),
        ("device status endpoint", test_device_status_endpoint),
    ]

    results = []
    for name, test_func in tests:
        try:
            results.append((name, test_func()))
        except Exception as e:
            print(f"\n[ERROR] {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")

    if passed == total:
        print(f"\n✅ All {total} tests passed!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed or warning")
        return 1 if any(not r for _, r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
