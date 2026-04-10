## Integration Tests

The project includes focused end-to-end integration tests that validate
aggregated glucose statistics against the Nightscout oracle
(reference implementation). These tests are minimal and fast.

### Running Integration Tests

Integration tests require a live Nightscout instance and are
**automatically skipped** if environment variables are not set
(safe for public repository commits).

To enable integration tests locally:

**Linux/macOS:**
```bash
export NIGHTSCOUT_INTEGRATION_URL=https://your-nightscout.duckdns.org
export NIGHTSCOUT_INTEGRATION_TOKEN=your-readable-token
pytest tests/integration/test_aggregated_stats.py -v
```

**Windows PowerShell:**
```powershell
$env:NIGHTSCOUT_INTEGRATION_URL="https://your-nightscout.duckdns.org"
$env:NIGHTSCOUT_INTEGRATION_TOKEN="your-readable-token"
python -m pytest tests/integration/test_aggregated_stats.py -v
```

### Test Data Requirements

Integration tests expect:
- **Date range:** 7+ days of CGM data
- **Readings:** ~500+ readings per day (5-minute intervals)
- **Token type:** Readable token (not API secret)


### What Integration Tests Validate

Two critical tests against the Nightscout oracle:

1. **Single-Day Oracle Validation** 
   (`test_single_day_aggregation_matches_oracle_metrics`):
   - ✅ Total readings count (exact match)
   - ✅ TIR percentages: low/normal/high (exact match)
   - ✅ Average glucose (within 0.1)
   - ✅ Standard deviation (within 0.1)
   - ✅ HbA1c estimate (within 0.2)

2. **7-Day Summary Oracle Validation**
   (`test_seven_day_aggregation_matches_oracle_summary`):
   - ✅ Total readings across period (exact match)
   - ✅ Overall TIR percentages (exact match)
   - ✅ Overall average glucose (within 0.1)
   - ✅ Overall standard deviation (within 0.1)
   - ✅ HbA1c estimate (within 0.2)

If both tests pass, **all aggregation logic is correct**.

### Test Isolation & Safety

- Tests run **only with explicit environment variables**
- No test data is modified; all tests are read-only queries
- Safe for CI/CD pipelines and public repository commits
- Uses pytest `@pytest.mark.skipif` to skip when not configured
- Laufzeit: ~2-3 Sekunden

