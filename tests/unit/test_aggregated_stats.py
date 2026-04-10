"""Test aggregated glucose statistics (batch queries)."""
import pytest
from datetime import datetime, timedelta
from src.nightscout_client import get_aggregated_glucose_stats
from unittest.mock import patch
from tests.utils.nightscout_report_oracle import (
    compute_glucose_distribution_oracle,
)


def sample_glucose_entries(
    start_date: str, days: int = 3, readings_per_day: int = 288
):
    """Helper: Generate sample glucose entries for testing
    (288 = 5-min intervals over 24h).
    """
    entries = []
    base = datetime.fromisoformat(start_date.replace("Z", "+00:00"))

    for day_offset in range(days):
        for reading_num in range(readings_per_day):
            ts = base + timedelta(days=day_offset, minutes=reading_num * 5)
            # Simple pattern: 130 avg + small variation
            sgv = 130 + (reading_num % 50) - 25
            entries.append({
                "sgv": sgv,
                "dateString": ts.isoformat().replace("+00:00", "Z"),
                "device": "pump",
            })
    return entries


class TestAggregatedGlucoseStats:
    """Given-When-Then tests for batch glucose statistics."""

    @patch("src.nightscout_client.get_entries_by_range")
    def test_glucose_stats_contain_one_entry_per_calendar_day(
        self, mock_get_entries
    ):
        # Given: 3 days of glucose data
        entries = sample_glucose_entries("2026-01-01T00:00:00Z", days=3)
        mock_get_entries.return_value = entries

        # When: requesting aggregated stats for those 3 days
        result = get_aggregated_glucose_stats(
            "2026-01-01T00:00:00Z", "2026-01-03T23:59:59Z"
        )

        # Then: result contains daily breakdown with correct structure
        assert "days" in result
        assert len(result["days"]) == 3
        assert result["days"][0]["date"] == "2026-01-01"
        assert result["days"][1]["date"] == "2026-01-02"
        assert result["days"][2]["date"] == "2026-01-03"
        assert all("avg" in day for day in result["days"])
        assert all("median" in day for day in result["days"])
        assert all("std_dev" in day for day in result["days"])
        assert all("tir_pct" in day for day in result["days"])

    @patch("src.nightscout_client.get_entries_by_range")
    def test_glucose_stats_include_overall_summary_with_hba1c_and_weekday_averages(
        self, mock_get_entries
    ):
        # Given: 2 days of glucose data
        entries = sample_glucose_entries("2026-01-05T00:00:00Z", days=2)
        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-05T00:00:00Z", "2026-01-06T23:59:59Z"
        )

        # Then: result contains summary with overall metrics
        assert "summary" in result
        assert "overall_avg" in result["summary"]
        assert "overall_std_dev" in result["summary"]
        assert "overall_tir_pct" in result["summary"]
        assert "estimated_hba1c" in result["summary"]
        assert "best_day" in result["summary"]
        assert "worst_day" in result["summary"]
        assert "weekday_avgs" in result["summary"]

    @patch("src.nightscout_client.get_entries_by_range")
    def test_day_with_lowest_average_glucose_is_identified_as_best_day(
        self, mock_get_entries
    ):
        # Given: 4 days with varying control (day 2 best, day 4 worst)
        entries = []
        dates = [
            "2026-02-01", "2026-02-02", "2026-02-03", "2026-02-04"
        ]
        glucose_patterns = [
            [140] * 288,      # day 1: okay
            [120] * 288,      # day 2: best (lowest avg)
            [145] * 288,      # day 3: okay
            [200] * 288,      # day 4: worst (highest avg)
        ]

        for date, pattern in zip(dates, glucose_patterns):
            base = datetime.fromisoformat(f"{date}T00:00:00Z")
            for i, sgv in enumerate(pattern):
                ts = base + timedelta(minutes=i * 5)
                entries.append({
                    "sgv": sgv,
                    "dateString": ts.isoformat().replace(
                        "+00:00", "Z"
                    ),
                })

        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-02-01T00:00:00Z", "2026-02-04T23:59:59Z"
        )

        # Then: best and worst days are correctly identified
        assert result["summary"]["best_day"] == "2026-02-02"
        assert result["summary"]["worst_day"] == "2026-02-04"

    @patch("src.nightscout_client.get_entries_by_range")
    def test_glucose_stats_include_average_per_weekday_for_full_week(
        self, mock_get_entries
    ):
        # Given: 7 days of data (one full week)
        # Jan 6 2026 is Monday
        entries = sample_glucose_entries(
            "2026-01-06T00:00:00Z", days=7
        )
        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-06T00:00:00Z", "2026-01-12T23:59:59Z"
        )

        # Then: weekday averages include all 7 days
        assert "weekday_avgs" in result["summary"]
        weekday_avgs = result["summary"]["weekday_avgs"]
        assert len(weekday_avgs) == 7
        assert "Monday" in weekday_avgs
        assert "Sunday" in weekday_avgs

    @patch("src.nightscout_client.get_entries_by_range")
    def test_glucose_stats_for_empty_date_range_returns_empty_days_list(
        self, mock_get_entries
    ):
        # Given: no entries for date range
        mock_get_entries.return_value = []

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-01T00:00:00Z", "2026-01-02T23:59:59Z"
        )

        # Then: returns empty but well-formed response
        assert result["days"] == []
        assert result["period_from"] == "2026-01-01T00:00:00Z"
        assert result["period_to"] == "2026-01-02T23:59:59Z"

    @patch("src.nightscout_client.get_entries_by_range")
    def test_entries_missing_sgv_field_are_excluded_from_readings_count(
        self, mock_get_entries
    ):
        # Given: mixed entries, some without 'sgv' field
        base = datetime.fromisoformat("2026-01-10T00:00:00Z")
        entries = [
            {
                "sgv": 130,
                "dateString": base.isoformat().replace("+00:00", "Z"),
            },
            {
                "sgv": 135,
                "dateString": (
                    base + timedelta(minutes=5)
                ).isoformat().replace("+00:00", "Z"),
            },
            {
                "dateString": (
                    base + timedelta(minutes=10)
                ).isoformat().replace("+00:00", "Z"),
            },  # Missing sgv
            {
                "sgv": 128,
                "dateString": (
                    base + timedelta(minutes=15)
                ).isoformat().replace("+00:00", "Z"),
            },
        ]
        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-10T00:00:00Z", "2026-01-10T23:59:59Z"
        )

        # Then: only valid sgv entries are counted
        assert result["total_readings"] == 3  # not 4
        assert result["days"][0]["readings"] == 3

    @patch("src.nightscout_client.get_entries_by_range")
    def test_day_with_all_readings_in_range_has_100_percent_tir(
        self, mock_get_entries
    ):
        # Given: readings across 2 days with clear TIR categories
        base = datetime.fromisoformat("2026-01-15T00:00:00Z")
        entries = []

        # Day 1: Mix of low/in/high readings
        for i in range(96):  # ~8 hours worth
            ts = base + timedelta(minutes=i * 5)
            if i < 32:
                entries.append({
                    "sgv": 60,
                    "dateString": ts.isoformat().replace("+00:00", "Z"),
                })  # low
            elif i < 64:
                entries.append({
                    "sgv": 125,
                    "dateString": ts.isoformat().replace("+00:00", "Z"),
                })  # in range
            else:
                entries.append({
                    "sgv": 220,
                    "dateString": ts.isoformat().replace("+00:00", "Z"),
                })  # high

        # Day 2: All in-range
        for i in range(96, 288):
            ts = base + timedelta(days=1, minutes=(i - 96) * 5)
            entries.append({
                "sgv": 125,
                "dateString": ts.isoformat().replace("+00:00", "Z"),
            })

        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-15T00:00:00Z", "2026-01-16T23:59:59Z"
        )

        # Then: daily structure has both days, TIR metrics present
        assert len(result["days"]) == 2
        assert "tir_pct" in result["days"][0]
        assert "tir_low_pct" in result["days"][0]
        assert "tir_high_pct" in result["days"][0]
        # Day 1 has mixed readings, Day 2 is high TIR
        assert result["days"][1]["tir_pct"] == 100.0  # All in range

    @patch("src.nightscout_client.get_entries_by_range")
    def test_average_glucose_of_170_yields_estimated_hba1c_of_7_6(
        self, mock_get_entries
    ):
        # Given: 1 day with average glucose 170 mg/dL
        base = datetime.fromisoformat("2026-01-20T00:00:00Z")
        entries = [
            {
                "sgv": 170,
                "dateString": (
                    base + timedelta(minutes=i * 5)
                ).isoformat().replace("+00:00", "Z")
            }
            for i in range(288)  # 288 readings = full 24h at 5-min
        ]
        mock_get_entries.return_value = entries

        # When: requesting aggregated stats
        result = get_aggregated_glucose_stats(
            "2026-01-20T00:00:00Z", "2026-01-20T23:59:59Z"
        )

        # Then: HbA1c estimate uses formula (avg + 46.7) / 28.7
        # (170 + 46.7) / 28.7 = 216.7 / 28.7 ≈ 7.55 → rounds to 7.6
        assert result["summary"]["estimated_hba1c"] == 7.6

    @patch("src.nightscout_client.get_entries_by_range")
    def test_thirty_days_of_stats_are_fetched_in_a_single_api_call(
        self, mock_get_entries
    ):
        # Given: mock setup
        mock_get_entries.return_value = sample_glucose_entries(
            "2026-03-01T00:00:00Z", days=30
        )

        # When: requesting 30 days of stats
        result = get_aggregated_glucose_stats(
            "2026-03-01T00:00:00Z", "2026-03-30T23:59:59Z"
        )

        # Then: exactly ONE API call was made (not 30)
        mock_get_entries.assert_called_once()
        assert len(result["days"]) == 30

    @patch("src.nightscout_client.get_entries_by_range")
    def test_summary_metrics_match_nightscout_distribution_oracle(
        self, mock_get_entries
    ):
        # Given: mixed glucose values over one day
        base = datetime.fromisoformat("2026-01-21T00:00:00Z")
        values = [60, 65, 70, 90, 120, 140, 170, 179, 180, 220]
        entries = [
            {
                "sgv": sgv,
                "dateString": (
                    base + timedelta(minutes=i * 5)
                ).isoformat().replace("+00:00", "Z"),
            }
            for i, sgv in enumerate(values)
        ]
        mock_get_entries.return_value = entries

        # When: computing MCP stats and independent Nightscout oracle
        result = get_aggregated_glucose_stats(
            "2026-01-21T00:00:00Z", "2026-01-21T23:59:59Z"
        )
        oracle = compute_glucose_distribution_oracle(entries)

        # Then: overlapping summary metrics match Nightscout logic
        summary = result["summary"]
        assert result["total_readings"] == oracle["overall"]["count"]
        assert summary["overall_avg"] == oracle["overall"]["mean"]
        assert summary["overall_std_dev"] == oracle["overall"]["stddev"]
        assert (
            summary["estimated_hba1c"]
            == oracle["overall"]["estimated_hba1c_dcct"]
        )
        assert (
            summary["overall_tir_low_pct"]
            == oracle["ranges"]["low"]["pct"]
        )
        assert (
            summary["overall_tir_pct"]
            == oracle["ranges"]["normal"]["pct"]
        )
        assert (
            summary["overall_tir_high_pct"]
            == oracle["ranges"]["high"]["pct"]
        )


class TestTirBoundaries:
    """Boundary tests: TIR range is [70, 180) and high is >= 180.
    Tight range (TITR) is [70, 140] inclusive.
    """

    def _single_day_result(self, sgv_values: list[int]) -> dict:
        """Helper: run aggregation for one day with given sgv values."""
        base = datetime.fromisoformat("2026-01-01T00:00:00Z")
        entries = [
            {
                "sgv": sgv,
                "dateString": (
                    base + timedelta(minutes=i * 5)
                ).isoformat().replace("+00:00", "Z"),
            }
            for i, sgv in enumerate(sgv_values)
        ]
        with patch("src.nightscout_client.get_entries_by_range",
                   return_value=entries):
            result = get_aggregated_glucose_stats(
                "2026-01-01T00:00:00Z", "2026-01-01T23:59:59Z"
            )
        return result["days"][0]

    @pytest.mark.parametrize(
        "sgv,expected_tir,expected_low,expected_high",
        [
            (69,  0.0,   100.0, 0.0),   # below range
            (70,  100.0, 0.0,   0.0),   # lower boundary (inclusive)
            (180, 0.0,   0.0,   100.0), # high starts at 180
            (181, 0.0,   0.0,   100.0), # above range
        ],
    )
    def test_reading_at_tir_boundary_is_classified_in_correct_zone(
        self, sgv, expected_tir, expected_low, expected_high
    ):
        # Given: a single reading exactly at or around the boundary
        # When: computing TIR stats
        day = self._single_day_result([sgv])

        # Then: reading is classified in the correct zone
        assert day["tir_pct"] == expected_tir
        assert day["tir_low_pct"] == expected_low
        assert day["tir_high_pct"] == expected_high

    @pytest.mark.parametrize(
        "sgv,expected_titr",
        [
            (69,  0.0),    # below range → not in tight range
            (70,  100.0),  # lower boundary (inclusive)
            (140, 100.0),  # tight upper boundary (inclusive)
            (141, 0.0),    # just above tight range
            (180, 0.0),    # in TIR but not in TITR
        ],
    )
    def test_reading_at_titr_boundary_is_classified_in_correct_zone(
        self, sgv, expected_titr
    ):
        # Given: a single reading exactly at or around TITR boundary
        # When: computing TIR stats
        day = self._single_day_result([sgv])

        # Then: reading is classified correctly for tight range
        assert day["titr_pct"] == expected_titr

    def test_tir_low_in_and_high_percentages_always_sum_to_100(self):
        # Given: readings in all three zones
        # When: computing TIR stats
        day = self._single_day_result([69, 70, 180, 181])

        # Then: percentages always sum to 100%
        total = (
            day["tir_pct"]
            + day["tir_low_pct"]
            + day["tir_high_pct"]
        )
        assert total == 100.0

