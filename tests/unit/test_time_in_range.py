"""Unit tests for calculate_time_in_range tool behavior."""

from unittest.mock import patch

import pytest

from src.server import calculate_time_in_range


@pytest.mark.parametrize(
    "sgv,expected_in_range,expected_above",
    [
        (179, 100.0, 0.0),
        (180, 0.0, 100.0),
    ],
)
def test_reading_at_high_threshold_is_classified_as_above_range(
    sgv: int,
    expected_in_range: float,
    expected_above: float,
):
    # Given: one glucose reading at or around the high threshold
    entries = [{"sgv": sgv, "dateString": "2026-01-01T12:00:00Z"}]

    # When: calculating time in range with high threshold 180
    with patch("src.server.get_entries_by_range", return_value=entries):
        result = calculate_time_in_range(hours=24, low=70, high=180)

    # Then: threshold behavior matches Nightscout-style high >= 180
    assert result["time_in_range_pct"] == expected_in_range
    assert result["time_above_range_pct"] == expected_above


def test_result_uses_estimated_hba1c_field_name():
    # Given: one valid glucose reading
    entries = [{"sgv": 120, "dateString": "2026-01-01T12:00:00Z"}]

    # When: calculating time in range
    with patch("src.server.get_entries_by_range", return_value=entries):
        result = calculate_time_in_range(hours=24, low=70, high=180)

    # Then: response uses the HbA1c field name
    assert "estimated_hba1c" in result
    assert "estimated_a1c" not in result


