"""Oracle for Nightscout glucose distribution report logic.

This mirrors the core formulas from Nightscout's
`lib/report_plugins/glucosedistribution.js` for test comparisons.
"""

from __future__ import annotations

from datetime import datetime
from statistics import mean, median, pstdev


def _parse_entry(entry: dict) -> tuple[datetime, int, float] | None:
    if "sgv" not in entry or "dateString" not in entry:
        return None
    try:
        ts = datetime.fromisoformat(entry["dateString"].replace("Z", "+00:00"))
    except ValueError:
        return None
    sgv = entry["sgv"]
    bg_value = entry.get("bgValue", sgv)
    return ts, sgv, bg_value


def _floor_one_decimal(value: float) -> float:
    return int(value * 10) / 10


def _round_one_decimal(value: float) -> float:
    return round(value, 1)


def compute_glucose_distribution_oracle(
    entries: list[dict],
    target_low: int = 70,
    target_high: int = 180,
) -> dict:
    """Compute report-like metrics following Nightscout distribution logic."""
    parsed = [p for p in (_parse_entry(e) for e in entries) if p is not None]
    if not parsed:
        return {
            "ranges": {
                "low": {"pct": 0.0, "count": 0},
                "normal": {"pct": 0.0, "count": 0},
                "high": {"pct": 0.0, "count": 0},
            },
            "overall": {
                "count": 0,
                "mean": 0.0,
                "median": 0.0,
                "stddev": 0.0,
                "estimated_hba1c_dcct": 0.0,
                "estimated_hba1c_ifcc": 0,
            },
        }

    parsed.sort(key=lambda x: x[0])
    total = len(parsed)

    low_vals = sorted([sgv for _, sgv, _ in parsed if 0 < sgv < target_low])
    normal_vals = sorted(
        [sgv for _, sgv, _ in parsed if target_low <= sgv < target_high]
    )
    high_vals = sorted([sgv for _, sgv, _ in parsed if sgv >= target_high])

    def range_stats(values: list[int]) -> dict:
        count = len(values)
        pct = _round_one_decimal((100 * count) / total)
        if count == 0:
            return {
                "pct": pct,
                "count": 0,
                "mean": None,
                "median": None,
                "stddev": None,
            }
        midpoint = count // 2
        return {
            "pct": pct,
            "count": count,
            "mean": _floor_one_decimal(mean(values)),
            "median": float(values[midpoint]),
            "stddev": _floor_one_decimal(pstdev(values)),
        }

    low = range_stats(low_vals)
    high = range_stats(high_vals)
    normal = range_stats(normal_vals)

    # Nightscout enforces exact 100% by recomputing normal from low/high.
    normal["pct"] = _round_one_decimal(100 - low["pct"] - high["pct"])

    all_sgv = [sgv for _, sgv, _ in parsed]
    all_bg_mgdl = [bg for _, _, bg in parsed]
    avg = mean(all_sgv)
    avg_mgdl = mean(all_bg_mgdl)

    estimated_dcct = _round_one_decimal((avg_mgdl + 46.7) / 28.7)
    estimated_ifcc = round((((avg_mgdl + 46.7) / 28.7) - 2.15) * 10.929)

    return {
        "ranges": {"low": low, "normal": normal, "high": high},
        "overall": {
            "count": total,
            "mean": _round_one_decimal(avg),
            "median": _round_one_decimal(float(median(all_sgv))),
            "stddev": _round_one_decimal(pstdev(all_sgv)),
            "estimated_hba1c_dcct": estimated_dcct,
            "estimated_hba1c_ifcc": estimated_ifcc,
        },
    }

