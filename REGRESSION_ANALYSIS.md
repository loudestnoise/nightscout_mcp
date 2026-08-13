# Regression Analysis: Broken Treatments/DeviceStatus Endpoints

**Status**: FIXED ✅

## The Problem (2026-08-12 → 2026-08-13)

Yesterday's fix validated that endpoints returned correct data. Today, endpoints broke again with identical symptoms:
- `get_insulin_on_board()` → error: "devicestatus endpoint returned glucose entries"
- `get_recent_treatments()` → error: "treatments endpoint returned glucose entries"  
- `get_treatments_by_date()` → silent failure: returned empty array `[]`

All three were receiving SGV glucose entries instead of treatments/device status.

## Root Cause: Shell Environment Variable Override

**The Issue**:
```bash
NIGHTSCOUT_URL='https://cgms.davediabet.es/api/v1/entries.json?token=lunabeardoggo'
```

This was set in the shell environment. Docker Compose reads from the shell environment and those values **override** the `.env` file.

**Why This Caused Failures**:

The code in `nightscout_client.py:_url()` constructs URLs as:
```python
base = NIGHTSCOUT_URL.rstrip("/")
return f"{base}/api/v1/{path.lstrip('/')}"
```

With `NIGHTSCOUT_URL` set to the entries endpoint, it built invalid URLs like:
```
https://cgms.davediabet.es/api/v1/entries.json?token=.../api/v1/treatments.json
```

The API either rejected these or redirected to the entries endpoint, which is why glucose data was returned.

## Why Yesterday's Fix Didn't Prevent Regression

**Yesterday's Approach (c44dd12)**: Added validation checks that **detected** wrong data was being returned.

**What It Did NOT Do**: Fix the routing. The validation only reported symptoms, not the disease.

**Why**: The developer (likely) assumed the code was correct but data was being transformed somewhere. Adding validation was defensive but didn't address the root cause: misconfigured env vars.

## Why `get_treatments_by_date` Failed Silently

Looking at `nightscout_client.py:192-220`:

```python
def get_treatments_by_range(date_from, date_to, count=1000):
    params = {
        "find[created_at][$gte]": date_from,
        "find[created_at][$lte]": date_to,
        "count": str(count),
    }
    result = _get("treatments.json", params)  # <- Returns [] if no matches
    
    # Validation only runs if result is not empty:
    if result and isinstance(result[0], dict):  # <- Skips if result = []
        # ... validation checks ...
    
    return result  # <- Returns [] silently
```

**The Issue**: Empty arrays bypass validation. The code can't distinguish between:
1. **Valid**: No treatments in that date range (legitimate)
2. **Invalid**: Wrong endpoint called and returned empty instead of error (bug)

**Why Other Endpoints Threw Errors**: They check the first item's fields:
```python
if result and isinstance(result[0], dict):
    if 'sgv' in first and 'eventType' not in first:
        raise ValueError("...")  # <- Throws if SGV detected
```

But when the endpoint legitimately returned data with SGV (because it was hitting the wrong endpoint), they threw. When `get_treatments_by_date` returned empty, there was no first item to validate against.

## The Fix

1. **Unset the shell env var**:
   ```bash
   unset NIGHTSCOUT_URL
   ```

2. **Verified `.env` has the correct base URL** (not an endpoint):
   ```bash
   NIGHTSCOUT_URL=https://cgms.davediabet.es  # ✅ base URL only
   ```

3. **Rebuilt the Docker container**:
   ```bash
   docker compose down && docker compose up --build -d
   ```

## How to Prevent Future Regressions

### 1. Run `test_regression.py` After Every Restart
This script verifies:
- URL configuration is correct (base URL, not endpoint)
- Treatments endpoint returns treatment objects (not glucose)
- Treatments by date returns treatments (not empty due to wrong endpoint)
- Device status endpoint returns device data (not glucose)

```bash
export NIGHTSCOUT_URL=https://cgms.davediabet.es
export NIGHTSCOUT_TOKEN=lunabeardoggo
python test_regression.py
```

### 2. Improve Silent Failures in `get_treatments_by_date`

Add a heuristic check: if querying a recent 24-hour window returns empty, it's suspicious.

**Option A** (current): Print warning to stderr
**Option B** (stricter): Raise error on empty result in recent queries
**Option C** (recommended): Add a health check in the health endpoint

### 3. Lock Environment Variables in Docker Compose

Use `.env.local` instead of shell vars, or explicitly remove inherited vars:

```yaml
# docker-compose.yaml
environment:
  NIGHTSCOUT_URL: ${NIGHTSCOUT_URL}  # Only from .env, not shell
  # Force override (dangerous but explicit):
  # NIGHTSCOUT_URL: https://cgms.davediabet.es
```

### 4. Add Smoke Test to CI/CD

If deployed to Kubernetes or CI/CD, add a post-deployment health check:

```bash
# Run after deploy
python test_regression.py
```

## Lessons

1. **Env Vars Are Global**: Shell env vars override `.env` files. Always verify what the process actually sees.
2. **Validation Finds Symptoms, Not Causes**: Detecting wrong data is good, but fix the root cause.
3. **Silent Failures Hide Bugs**: Empty results can mask endpoint routing errors. Add heuristic checks.
4. **Test Against Real External APIs**: Unit tests with mocks won't catch this. Integration tests do.

## Testing Verification

```
✅ URL configuration: NIGHTSCOUT_URL=https://cgms.davediabet.es
✅ treatments endpoint: 20 treatments, first is Temp Basal
✅ treatments by date endpoint: 20 treatments in last 24h, first is Temp Basal
✅ device status endpoint: 5 device statuses, device=Trio
```

All endpoints now return correct data shapes.
