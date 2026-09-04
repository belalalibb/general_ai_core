#!/usr/bin/env bash
# Repo governance verification — single verifier (stack-neutral core + Python gates).
# Same entry point locally and in CI. Exit 0 = PASS, non-zero = FAIL.
# R168 §6: reads engineering/verification/green_manifest.json (the only authority);
# pytest slices with counters and a floor gate; widened secret scan with declared
# per-line exceptions; NOT EVALUATED lines counted separately; change-budget guard.
# No or-true fallbacks: every check either passes or sets FAIL.
set -u
cd "$(dirname "$0")/../.." || exit 2

FAIL=0
note() { printf '%s\n' "$*"; }
fail() { FAIL=1; printf 'FAIL: %s\n' "$*"; }
pass() { printf 'PASS: %s\n' "$*"; }

MANIFEST="engineering/verification/green_manifest.json"
mf() { python3 -c "import json,sys;m=json.load(open('$MANIFEST'));exec(sys.argv[1])" "$1"; }

# 1. Governance structure
for f in \
  engineering/adr/ADR-TEMPLATE.md \
  engineering/adr/README.md \
  engineering/gates/GATE-TEMPLATE.md \
  engineering/decisions/README.md \
  engineering/verification/README.md \
  engineering/verification/green_manifest.json \
  docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md \
  docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md \
  docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md \
  docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
do
  [ -f "$f" ] && pass "exists: $f" || fail "missing: $f"
done
if ! python3 -c "import json;json.load(open('$MANIFEST'))" >/dev/null 2>&1; then
  fail "green manifest is not valid JSON: $MANIFEST"
  note "RESULT: FAIL"
  exit 1
fi

# 2. Single mutable state file — no legacy state scheme
for legacy in STATE.md PROGRESS.md HANDOFF.md NEXT_PLAN.md \
  FUTURE_IMPROVEMENTS.md ARCHITECTURE_GAPS.md; do
  if find . -path ./.git -prune -o -name "$legacy" -print | grep -q .; then
    fail "legacy state file present: $legacy (D10/D11 violation)"
  fi
done
[ "$FAIL" -eq 0 ] && pass "no legacy state files (D10/D11)"

# 3. Docs integrity — v3 pack complete (20 files) and state header fields
V3_COUNT=$(ls docs/ai_orchestration_pack/final_docs_v3/*.md 2>/dev/null | wc -l)
if [ "$V3_COUNT" -eq 20 ]; then
  pass "v3 pack complete: 20 documents"
else
  fail "v3 pack file count = $V3_COUNT (expected 20)"
fi
for field in STATE_REVISION RESUME_TOKEN CURRENT_TASK NEXT_TASK PHASE_2_STATUS; do
  grep -q "$field" docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md \
    && pass "state field present: $field" \
    || fail "state field missing: $field"
done

# 4a. pytest — declared slices, per-slice counters, floor gate (R168 §6.1)
GATE_MAX_SKIPPED=$(mf 'print(m["pytest"]["gate"]["max_skipped"])')
GATE_MIN_PASSED=$(mf 'print(m["pytest"]["gate"]["min_passed"])')
T_PASSED=0; T_FAILED=0; T_ERRORS=0; T_SKIPPED=0; T_SLICES=0
while IFS='|' read -r S_NAME S_SEL S_CEIL; do
  [ -n "$S_NAME" ] || continue
  T_SLICES=$((T_SLICES + 1))
  # shellcheck disable=SC2086
  S_LINE=$(timeout "$S_CEIL" python3 -m pytest $S_SEL -o addopts="" -q -p no:cacheprovider -W ignore::DeprecationWarning 2>&1 | tail -1)
  S_P=$(printf '%s' "$S_LINE" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+'); S_P=${S_P:-0}
  S_F=$(printf '%s' "$S_LINE" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+'); S_F=${S_F:-0}
  S_E=$(printf '%s' "$S_LINE" | grep -oE '[0-9]+ errors?' | grep -oE '[0-9]+'); S_E=${S_E:-0}
  S_S=$(printf '%s' "$S_LINE" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+'); S_S=${S_S:-0}
  if ! printf '%s' "$S_LINE" | grep -qE '[0-9]+ (passed|failed|skipped|errors?)'; then
    S_E=$((S_E + 1))
    fail "pytest slice $S_NAME: no summary line (timeout ${S_CEIL}s or crash): $S_LINE"
  fi
  note "pytest slice $S_NAME: passed=$S_P failed=$S_F errors=$S_E skipped=$S_S"
  T_PASSED=$((T_PASSED + S_P)); T_FAILED=$((T_FAILED + S_F))
  T_ERRORS=$((T_ERRORS + S_E)); T_SKIPPED=$((T_SKIPPED + S_S))
done < <(mf 'for s in m["pytest"]["slices"]: print(s["name"]+"|"+s["selection"]+"|"+str(s["time_ceiling_s"]))')
note "pytest coverage: slices ran = $T_SLICES; passed=$T_PASSED failed=$T_FAILED errors=$T_ERRORS skipped=$T_SKIPPED"
if [ "$T_FAILED" -eq 0 ] && [ "$T_ERRORS" -eq 0 ] && [ "$T_SKIPPED" -le "$GATE_MAX_SKIPPED" ] && [ "$T_PASSED" -ge "$GATE_MIN_PASSED" ]; then
  pass "pytest: passed=$T_PASSED (>= $GATE_MIN_PASSED) failed=0 errors=0 skipped=$T_SKIPPED (<= $GATE_MAX_SKIPPED)"
else
  fail "pytest gate: passed=$T_PASSED (floor $GATE_MIN_PASSED) failed=$T_FAILED errors=$T_ERRORS skipped=$T_SKIPPED (ceiling $GATE_MAX_SKIPPED)"
fi

# 4b. Static gates (ADR-0001: mypy / ruff / import-linter)
if python3 -m mypy >/dev/null 2>&1; then
  pass "mypy --strict (scope: pyproject.toml [tool.mypy].packages): clean"
else
  fail "mypy failed (run: python3 -m mypy)"
fi
if python3 -m ruff check . >/dev/null 2>&1; then
  pass "ruff: clean"
else
  fail "ruff failed (run: python3 -m ruff check .)"
fi
if lint-imports >/dev/null 2>&1; then
  pass "import-linter: architecture boundaries kept (40 §6.2)"
else
  fail "import-linter failed (run: lint-imports)"
fi

# 5. Secret scan — widened globs, declared per-line exceptions only (R168 §6.2)
SS_PATTERNS=$(mf 'print(m["secret_scan"]["patterns"])')
SS_INCLUDES=$(mf 'print(" ".join("--include="+g for g in m["secret_scan"]["include_globs"]))')
SS_EXCLUDES=$(mf 'print(" ".join("--exclude-dir="+d for d in m["secret_scan"]["exclude_dirs"]))')
EXC_N=$(mf 'print(len(m["secret_scan"]["exceptions"]))')
EXC_CEIL=$(mf 'print(m["secret_scan"]["exception_count_ceiling"])')
if [ "$EXC_N" -gt "$EXC_CEIL" ]; then
  fail "secret scan: exception list ($EXC_N) exceeds ceiling ($EXC_CEIL)"
fi
# shellcheck disable=SC2086
SS_HITS=$(grep -rEn "$SS_PATTERNS" $SS_INCLUDES $SS_EXCLUDES . 2>/dev/null | sed -E 's#^\./##' | cut -d: -f1,2)
SS_UNDECLARED=$(printf '%s\n' "$SS_HITS" | python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
allowed = {e["file"] + ":" + str(e["line"]) for e in m["secret_scan"]["exceptions"]}
for line in sys.stdin:
    line = line.strip()
    if line and line not in allowed:
        print(line)
' "$MANIFEST")
if [ -n "$SS_UNDECLARED" ]; then
  fail "possible secret detected outside the exception list:"
  printf '%s\n' "$SS_UNDECLARED" | sed 's/^/  /'
else
  pass "secret scan clean (declared exceptions: $EXC_N/$EXC_CEIL)"
fi
ENV_TRACKED=$(git ls-files | grep -E '(^|/)\.env($|\.)' | grep -vE '\.env\.example$')
if [ -n "$ENV_TRACKED" ]; then
  fail ".env file is git-tracked: $ENV_TRACKED"
else
  pass "no .env tracked"
fi

# 6. Production change budget — changes_used <= ceiling per round; log consistent (R168 §2)
BUDGET=$(mf '
cb = m["change_budget"]; roots = tuple(cb["counts_production_code_under"]); bad = []; parts = []
for r in ("round_a", "round_b", "round_r169"):
    if r not in cb: continue
    rd = cb[r]; used = rd["changes_used"]; ceil = rd["ceiling"]; log = rd["log"]
    rroots = tuple(rd.get("counts_production_code_under", roots))  # R169 §3: per-round roots
    parts.append(r + "=" + str(used) + "/" + str(ceil))
    if used > ceil: bad.append(r + " over ceiling")
    if used != len(log): bad.append(r + " changes_used != len(log)")
    items = {i.split(" ")[0] for i in rd["items"]}
    for e in log:
        if not e["file"].startswith(rroots): bad.append(r + " log file outside roots: " + e["file"])
        if e["item"] not in items: bad.append(r + " item not scheduled: " + e["item"])
print(("BAD " if bad else "OK ") + "; ".join(parts) + ((" | " + "; ".join(bad)) if bad else ""))
')
case "$BUDGET" in
  OK*) pass "change budget within ceilings: ${BUDGET#OK }" ;;
  *) fail "change budget exceeded or log/count mismatch: ${BUDGET#BAD }" ;;
esac

# 7. NOT EVALUATED — one line per item, closed reason set, counted separately (R168 §6.4)
NE_LINES=$(mf '
closed = set(m["not_evaluated_reason_closed_set"]); ceil = m["not_evaluated_count_ceiling"]
items = m["not_evaluated"]
for it in items:
    tag = "NOT EVALUATED: " if it["reason"] in closed else "BAD_REASON: "
    print(tag + it["item"] + " — " + it["reason"])
if len(items) > ceil: print("OVER_CEILING: " + str(len(items)) + " > " + str(ceil))
')
NE_COUNT=$(printf '%s\n' "$NE_LINES" | grep -c '^NOT EVALUATED:')
NE_BAD=$(printf '%s\n' "$NE_LINES" | grep -E '^(BAD_REASON|OVER_CEILING):')
printf '%s\n' "$NE_LINES" | grep '^NOT EVALUATED:'
if [ -n "$NE_BAD" ]; then
  fail "not_evaluated malformed (reason outside closed set or count > ceiling): $NE_BAD"
fi
note "SUMMARY: not_evaluated=$NE_COUNT (counted separately; never green, never FAIL)"

if [ "$FAIL" -eq 0 ]; then
  note "RESULT: PASS (all repo governance checks)"
  exit 0
else
  note "RESULT: FAIL"
  exit 1
fi
