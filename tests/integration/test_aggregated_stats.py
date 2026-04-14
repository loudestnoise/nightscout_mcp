"""Integration tests: aggregated glucose stats against real Nightscout.

These tests run against a real Nightscout instance. They are skipped
if NIGHTSCOUT_INTEGRATION_URL and NIGHTSCOUT_INTEGRATION_TOKEN
environment variables are not set (for safe public repo commits).

To enable integration tests locally:
  export NIGHTSCOUT_INTEGRATION_URL=https://your-nightscout.duckdns.org
  export NIGHTSCOUT_INTEGRATION_TOKEN=your-token-here
"""

import os
import pytest
from src.nightscout_client import get_aggregated_glucose_stats
from tests.utils.nightscout_report_oracle import (
    compute_glucose_distribution_oracle,
)

# Integration test markers
INTEGRATION_URL = os.environ.get("NIGHTSCOUT_INTEGRATION_URL")
INTEGRATION_TOKEN = os.environ.get("NIGHTSCOUT_INTEGRATION_TOKEN")
SKIP_INTEGRATION = not (INTEGRATION_URL and INTEGRATION_TOKEN)


@pytest.fixture(autouse=True)
def setup_integration_env():
    """Configure Nightscout client for integration test if env vars set."""
    if not SKIP_INTEGRATION:
        os.environ["NIGHTSCOUT_URL"] = INTEGRATION_URL
        os.environ["NIGHTSCOUT_TOKEN"] = INTEGRATION_TOKEN
        # Reload the module to pick up new env vars
        import importlib
        import src.nightscout_client
        importlib.reload(src.nightscout_client)
    yield
    # Cleanup: restore original env if any


@pytest.mark.skipif(
    SKIP_INTEGRATION,
    reason="NIGHTSCOUT_INTEGRATION_URL and "
           "NIGHTSCOUT_INTEGRATION_TOKEN not set"
)
class TestAggregatedGlucoseStats:
    """Integration tests against real Nightscout instance.

    These tests validate that aggregation logic matches the Nightscout
    oracle (reference implementation). They require a live Nightscout
    instance and will only run when integration env vars are configured.
    """

    def test_single_day_aggregation_matches_oracle_metrics(self):
        # Given: one day of real data + oracle baseline
        date_from = "2026-03-29T00:00:00Z"
        date_to = "2026-03-29T23:59:59Z"

        # When: requesting aggregated stats and oracle
        from src.nightscout_client import get_entries_by_range
        raw = get_entries_by_range(date_from, date_to, count=999999)
        oracle = compute_glucose_distribution_oracle(raw)
        result = get_aggregated_glucose_stats(date_from, date_to)

        # Then: MCP aggregation matches oracle across all
        # key metrics
        day = result["days"][0]
        summary = result["summary"]

        # Exact match: total readings
        assert day["readings"] == oracle["overall"]["count"]

        # Within 0.1: overall average
        assert abs(day["avg"] - oracle["overall"]["mean"]) < 0.1

        # Within 0.1: standard deviation
        assert abs(
            day["std_dev"] - oracle["overall"]["stddev"]
        ) < 0.1

        # Exact match: TIR percentages
        assert day["tir_pct"] == \
            oracle["ranges"]["normal"]["pct"]
        assert day["tir_low_pct"] == \
            oracle["ranges"]["low"]["pct"]
        assert day["tir_high_pct"] == \
            oracle["ranges"]["high"]["pct"]

        # Within 0.2: HbA1c (allowing rounding)
        assert abs(
            summary["estimated_hba1c"]
            - oracle["overall"]["estimated_hba1c_dcct"]
        ) < 0.2


    def test_seven_day_aggregation_matches_oracle_summary(self):
        # Given: 7 days of real data + oracle baseline
        date_from = "2026-03-29T00:00:00Z"
        date_to = "2026-04-04T23:59:59Z"

        # When: requesting aggregated stats and oracle
        from src.nightscout_client import get_entries_by_range
        raw = get_entries_by_range(date_from, date_to, count=999999)
        oracle = compute_glucose_distribution_oracle(raw)
        result = get_aggregated_glucose_stats(date_from, date_to)

        # Then: summary metrics match oracle for full period
        summary = result["summary"]

        # Exact match: total readings
        assert result["total_readings"] == \
            oracle["overall"]["count"]

        # Within 0.1: overall average
        assert abs(
            summary["overall_avg"] - oracle["overall"]["mean"]
        ) < 0.1

        # Within 0.1: standard deviation
        assert abs(
            summary["overall_std_dev"]
            - oracle["overall"]["stddev"]
        ) < 0.1

        # Exact match: TIR percentages for full period
        assert summary["overall_tir_pct"] == \
            oracle["ranges"]["normal"]["pct"]
        assert summary["overall_tir_low_pct"] == \
            oracle["ranges"]["low"]["pct"]
        assert summary["overall_tir_high_pct"] == \
            oracle["ranges"]["high"]["pct"]

        # Within 0.2: HbA1c (allowing rounding)
        assert abs(
            summary["estimated_hba1c"]
            - oracle["overall"]["estimated_hba1c_dcct"]
        ) < 0.2

