# MCP Nightscout

FastMCP server providing tools for diabetes type 1 management via Nightscout API.

## Key files
- `src/server.py` — MCP tools + auth middleware + health endpoint
- `src/nightscout_client.py` — HTTP client for Nightscout REST API v1
- `src/log_filter.py` + `src/log_config.yaml` — JSON logging, filters /health
- `tests/test_auth.py` — auth middleware tests (pytest-asyncio)

## Stack
- Python 3.12, FastMCP, httpx, uvicorn
- Docker → GitLab CI → Kubernetes (deploy/ templates)

## Environment variables
- `NIGHTSCOUT_URL` — Nightscout instance base URL
- `NIGHTSCOUT_API_SECRET` — API secret (hashed SHA1)
- `NIGHTSCOUT_TOKEN` — readable token (alternative to api-secret)
- `NIGHTSCOUT_TIMEOUT` — request timeout (default 30s)
- `MCP_AUTH_TOKEN` — MCP server auth token (optional for local dev)

## Adding a new tool
1. If it needs a new API call, add it to `nightscout_client.py`
2. Add `@mcp.tool()` function in `server.py` with clear docstring
3. Run `docker compose up --build` to test locally

## 2. Coding Practices (Clean Code)
- **SOLID & Modular:** Use Clean Code principles. E.g. keep functions small and focused on one task.
- **No Redundancy:** Avoid "huge texts" for small clarifications. Keep code self-documenting.
- **Formatting**: 
  - Black for Python (max line length 79).

## 3. Testing

### Unit Test Writing Guidelines

#### 1. Structure Every Test with Given-When-Then comments
- Given: set up preconditions and test data.
- When: execute one behavior/action under test.
- Then: assert the observable outcome.
- If action and expectation are tightly coupled (for example exception checks), a combined When/Then block is acceptable.

#### 2. Name Tests as Readable Behavior Statements
- Use names that describe scenario plus expected outcome.
- Recommended pattern: scenario_expected_result.
- Prefer descriptive names over generic names like test1 or shouldWork.
- A reader should understand what the test proves without reading the full body.

#### 3. Keep One Behavior per Test
- Each test should validate one rule or behavior.
- Avoid mixing unrelated assertions in one test.
- Split into multiple tests if multiple behaviors need verification.

#### 4. Use Parameterized Tests for Variations
- If the same behavior must hold for multiple inputs, use parameterized tests.
- Avoid duplicating nearly identical test methods.
- Keep test intent clear while reducing repetition.

#### 5. Test Observable Behavior, Not Implementation Details
- Assert outputs, state changes, side effects, and error behavior visible to consumers.
- Avoid coupling tests to internals that may change during refactoring.

#### 6. Cover Happy Paths and Edge/Error Paths
Use the **ZOMBIES** checklist to ensure complete coverage:
- **Z**ero — empty input, no data, missing fields
- **O**ne — single element / minimal valid input
- **M**any — multiple elements, typical realistic input
- **B**oundaries — exact boundary values (e.g. sgv=70, sgv=180)
- **I**nterfaces — correct return shape and field names
- **E**xceptions — invalid input, API errors, unexpected data
- **S**imple scenarios first, then progressively more complex

#### 7. Keep Tests Focused and Maintainable
- Use minimal setup.
- Avoid unnecessary dependencies.
- Prefer clear arrange data and explicit assertions over clever abstractions.

#### 8. No Logic in Tests
- Tests should not contain `if`, `elif`, or `else` — a test with
  branching can itself contain bugs, defeating its purpose.
- `for` and `while` loops are acceptable for building test data,
  but not for selecting which assertions to run.
- Move branching into parametrized inputs instead:

  ```python
  # ❌ Wrong — logic inside test body
  def test_tir(sgv, zone):
      day = compute(sgv)
      if zone == "low":
          assert day["tir_low_pct"] == 100.0
      elif zone == "in_range":
          assert day["tir_pct"] == 100.0

  # ✅ Correct — expected values in parametrize, no logic in body
  @pytest.mark.parametrize("sgv,expected_tir,expected_low", [
      (69,  0.0,   100.0),
      (70,  100.0, 0.0),
  ])
  def test_tir(sgv, expected_tir, expected_low):
      day = compute(sgv)
      assert day["tir_pct"] == expected_tir
      assert day["tir_low_pct"] == expected_low
  ```

#### Example Naming Patterns
- test_initially_there_are_no_active_loans
- test_borrowing_an_already_borrowed_item_is_not_allowed
- test_get_items_returns_only_items_for_the_requested_owner
- test_quality_of_normal_items_decreases_by_1_every_day_before_sell_by_day
- test_quality_of_conjured_items_decreases_by_4_every_day_past_sell_by_day
- test_adding_items_makes_them_accessible_by_index_starting_from_0
- test_adding_duplicate_items_moves_them_to_the_head
- test_arabic_numbers_less_than_1_have_no_roman_representation
- test_opening_account_with_initial_balance_adds_it_to_repository

## 4. Development Workflow

### Branching Strategy & Naming
Maintain a clean repository history. Every branch (except chores) should reference a Feature-ID or Issue-ID.

| Prefix | Pattern | Example |
| :--- | :--- | :--- |
| **`feat/`** | `feat/ID-description` | `feat/8-wiso-checklist-sidebar` |
| **`refactor/`** | `refactor/ID-description` | `refactor/8-api-response-optimization` |
| **`fix/`** | `fix/ID-description` | `fix/12-vin-validation-error` |
| **`docs/`** | `docs/ID-description` | `docs/8-update-ui-requirements` |
| **`test/`** | `test/ID-description` | `test/5-backend-pdf-tests` |

### Commits & Commit Messages
 
- **Atomic Commits:** Commit small, functional changes (e.g., "feat: add VIN validation logic").
- **Conventional Commits:** 
  - Use prefixes like `feat:`, `fix:`, `docs:`, `refactor:`.
  - Put issue ID into the scope. E.g. `feat(#123): add VIN validation logic`.
- Create a commit message that clearly describes the change
- If necessary, include a more detailed description in the commit body, but keep it concise.

