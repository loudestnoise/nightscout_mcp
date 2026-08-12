# Testing MCP Nightscout Fixes in Claude.ai

## Step 1: Rebuild Docker with Latest Code

```bash
cd /home/dave/mcp-nightscout

# Stop running containers
docker compose down

# Rebuild with latest code (this will pull in the validation fixes)
docker compose up --build -d

# Verify it's running
docker ps | grep mcp_nightscout
```

After rebuild, the server should be running on `http://localhost:8000` with the new validation code.

## Step 2: Test Each Tool in Claude.ai

Open Claude.ai and test each of the previously broken tools. Here's what to test:

### Test 1: `server_status`

**In Claude.ai, type:**
```
Use the server_status MCP tool to get the Nightscout server version and status.
```

**Expected Result:**
- Should return a JSON object with fields like:
  - `status`: "ok"
  - `version`: "15.0.7"
  - `settings`: {...}
  - Other server configuration

**❌ Wrong Result:** If you see an error or a list of glucose entries (with `sgv` fields), the validation caught the bug. The error message will explain what's wrong.

---

### Test 2: `get_recent_treatments`

**In Claude.ai, type:**
```
What treatments have I had in the last 24 hours? Use get_recent_treatments to show me the last 10.
```

**Expected Result:**
- Should return a list of treatment objects with fields like:
  - `eventType`: "Bolus", "Temp Basal", "Carb Correction", etc.
  - `insulin`: amount in units (if bolus)
  - `carbs`: amount in grams (if carb entry)
  - `created_at`: timestamp
  - `_id`: treatment ID

**Example of correct response:**
```json
[
  {
    "eventType": "Bolus",
    "insulin": 2.5,
    "created_at": "2026-08-12T14:30:00Z"
  },
  {
    "eventType": "Carb Correction",
    "carbs": 15,
    "created_at": "2026-08-12T13:00:00Z"
  }
]
```

**❌ Wrong Result:** If you see glucose entries with `sgv` field instead, the validation caught it.

---

### Test 3: `get_treatments_by_date`

**In Claude.ai, type:**
```
Show me all treatments from August 10, 2026.
```

**Expected Result:**
- Should return treatments (eventType, insulin, carbs, etc.) from that date
- NOT glucose entries

**❌ Wrong Result:** Glucose entries with `sgv` field = validation caught an error

---

### Test 4: `get_latest_device_status`

**In Claude.ai, type:**
```
What's my current pump/loop status? What's my IOB and COB?
```

**Expected Result:**
- Should return device status with fields like:
  - `device`: "Trio" (your pump name)
  - `loop`: Loop algorithm data
  - `iob`: Insulin on board
  - `cob`: Carbs on board
  - `pump`: Pump status

**Example of correct response:**
```json
{
  "device": "Trio",
  "loop": {
    "iob": {
      "iob": 2.5,
      "bolusiob": 3.0
    },
    "cob": {
      "cob": 0
    }
  }
}
```

**❌ Wrong Result:** Glucose entries with `sgv` field = validation caught an error

---

## Step 3: Interpret Results

### ✅ If All Tests Pass:
Congratulations! The tools are working correctly. The validation fixes either:
1. Fixed the underlying issue, or
2. Confirmed the endpoints were already working correctly

### ❌ If You See Errors:

The error messages will indicate what went wrong. Examples:

**Error: "treatments endpoint returned glucose entries instead of treatments"**
- This means the endpoint returned glucose data instead of treatments
- The error message will show the actual data received
- Possible causes:
  - Wrong endpoint being called
  - Proxy/middleware transforming response
  - Environment variable misconfiguration

**Error: "get_server_status returned a list instead of dict"**
- The status endpoint returned a list instead of a dict
- Same possible causes as above

**Any error with actual data shown:**
- Copy the error message
- This data tells us exactly what endpoint returned what

## Step 4: If Tests Fail

If you see validation errors:

1. **Copy the full error message** (it contains valuable debugging info)
2. **Share it** - the error will show:
   - What was expected
   - What was actually received
   - The actual data from Nightscout

3. **Check Docker logs:**
   ```bash
   docker logs mcp_nightscout | tail -50
   ```

4. **Verify environment variables:**
   ```bash
   cat .env
   ```
   - `NIGHTSCOUT_URL` should be `https://cgms.davediabet.es`
   - `NIGHTSCOUT_TOKEN` should be set to your token
   - `MCP_AUTH_TOKEN` should be your auth token

5. **Test endpoints directly:**
   ```bash
   curl -s "https://cgms.davediabet.es/api/v1/treatments.json?count=1&token=YOUR_TOKEN" | python -m json.tool
   ```

## Summary

| Tool | Expected Data | Wrong Sign | Status |
|------|---|---|---|
| `server_status` | Dict with version/settings | Error about "list instead of dict" | ? |
| `get_recent_treatments` | List with eventType field | Error about "glucose entries" | ? |
| `get_treatments_by_date` | List with eventType field | Error about "glucose entries" | ? |
| `get_latest_device_status` | List with device/loop/pump fields | Error about "glucose entries" | ? |

After testing, come back with:
- ✅ "All tests passed!" or
- ❌ The error message you received

This will tell us exactly what's happening.
