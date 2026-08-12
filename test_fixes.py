#!/usr/bin/env python3
"""Test script to verify that the broken tools are now returning correct data.

Run this to verify the fixes:
  python test_fixes.py
"""

import os
import sys
from datetime import datetime, timedelta

# Ensure we can import from src
sys.path.insert(0, os.path.dirname(__file__))

# Required environment variables
assert os.environ.get('NIGHTSCOUT_URL'), "NIGHTSCOUT_URL not set"
assert os.environ.get('NIGHTSCOUT_TOKEN') or os.environ.get('NIGHTSCOUT_API_SECRET'), \
    "Either NIGHTSCOUT_TOKEN or NIGHTSCOUT_API_SECRET must be set"

from src.nightscout_client import (
    get_server_status,
    get_treatments,
    get_treatments_by_range,
    get_device_status,
)


def test_server_status():
    """Test that server_status returns a dict, not a list."""
    print("\n[TEST] server_status()")
    try:
        result = get_server_status()

        # Should be a dict
        assert isinstance(result, dict), f"Expected dict, got {type(result)}"
        assert 'status' in result, "Missing 'status' field in server status"
        assert 'version' in result, "Missing 'version' field in server status"

        print(f"  ✓ PASS: Returns dict with status='{result['status']}', version={result['version']}")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


def test_get_treatments():
    """Test that get_treatments returns treatment objects, not glucose entries."""
    print("\n[TEST] get_treatments(count=5)")
    try:
        result = get_treatments(count=5)

        # Should be a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) > 0, "Expected at least one treatment"

        # First item should be a treatment (has eventType), not glucose (has sgv)
        first = result[0]
        assert isinstance(first, dict), "Expected dict items in list"
        assert 'eventType' in first, f"Treatment missing 'eventType' field. Keys: {list(first.keys())}"
        assert 'sgv' not in first, f"Got glucose entry instead of treatment. Keys: {list(first.keys())}"

        print(f"  ✓ PASS: Returns {len(result)} treatments")
        print(f"           First treatment: eventType='{first['eventType']}'")
        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


def test_get_treatments_by_range():
    """Test that get_treatments_by_range returns treatments, not glucose entries."""
    print("\n[TEST] get_treatments_by_range (last 24 hours)")
    try:
        now = datetime.utcnow()
        date_from = (now - timedelta(days=1)).isoformat() + "Z"
        date_to = now.isoformat() + "Z"

        result = get_treatments_by_range(date_from, date_to, count=10)

        # Should be a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"

        if len(result) > 0:
            # First item should be a treatment, not glucose
            first = result[0]
            assert isinstance(first, dict), "Expected dict items"
            assert 'eventType' in first, f"Treatment missing 'eventType'. Keys: {list(first.keys())}"
            assert 'sgv' not in first, f"Got glucose entry instead of treatment. Keys: {list(first.keys())}"
            print(f"  ✓ PASS: Returns {len(result)} treatments by date range")
            print(f"           First treatment: eventType='{first['eventType']}'")
        else:
            print(f"  ⚠ WARNING: No treatments found in date range (this is OK if you haven't had any)")

        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


def test_get_device_status():
    """Test that get_device_status returns device status, not glucose entries."""
    print("\n[TEST] get_latest_device_status(count=1)")
    try:
        result = get_device_status(count=1)

        # Should be a list
        assert isinstance(result, list), f"Expected list, got {type(result)}"
        assert len(result) > 0, "Expected at least one device status"

        # First item should have device info, not glucose data
        first = result[0]
        assert isinstance(first, dict), "Expected dict items"

        # Should have device identifier
        assert any(k in first for k in ['device', 'loop', 'pump', 'uploader']), \
            f"Device status missing expected fields. Keys: {list(first.keys())}"

        # Should NOT be glucose entry
        if 'sgv' in first:
            raise ValueError(f"Got glucose entry instead of device status. Keys: {list(first.keys())}")

        print(f"  ✓ PASS: Returns device status")
        if 'device' in first:
            print(f"           Device: {first['device']}")
        if 'loop' in first:
            print(f"           Loop status available: IOB={first['loop'].get('iob', {}).get('iob')}")

        return True
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False


def main():
    print("=" * 70)
    print("MCP NIGHTSCOUT - TOOL FIX VERIFICATION")
    print("=" * 70)
    print(f"Nightscout URL: {os.environ.get('NIGHTSCOUT_URL')}")

    tests = [
        ("server_status", test_server_status),
        ("get_treatments", test_get_treatments),
        ("get_treatments_by_range", test_get_treatments_by_range),
        ("get_device_status", test_get_device_status),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            results.append((test_name, test_func()))
        except Exception as e:
            print(f"\n[ERROR] {test_name}: {e}")
            results.append((test_name, False))

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! The tools are working correctly.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed. See errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
