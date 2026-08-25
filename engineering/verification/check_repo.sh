#!/usr/bin/env bash
# Repo governance verification — Phase 0 (stack-neutral).
# Same entry point locally and in CI. Exit 0 = PASS, non-zero = FAIL.
set -u
cd "$(dirname "$0")/../.." || exit 2

FAIL=0
note() { printf '%s\n' "$*"; }
fail() { FAIL=1; printf 'FAIL: %s\n' "$*"; }
pass() { printf 'PASS: %s\n' "$*"; }

# 1. Governance structure
for f in \
  engineering/adr/ADR-TEMPLATE.md \
  engineering/adr/README.md \
  engineering/gates/GATE-TEMPLATE.md \
  engineering/decisions/README.md \
  engineering/verification/README.md \
  docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md \
  docs/ai_orchestration_pack/final_docs_v3/00_INDEX.md \
  docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md \
  docs/ai_orchestration_pack/final_docs_v3/41_IMPLEMENTATION_PLAN_AND_MVP.md
do
  [ -f "$f" ] && pass "exists: $f" || fail "missing: $f"
done

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

# 4. Secret scan (obvious patterns only; case-sensitive prefixes)
if grep -rEn 'AKIA[0-9A-Z]{16}|-----BEGIN (RSA|EC|OPENSSH) PRIVATE KEY-----|xox[bap]-[0-9A-Za-z-]{10,}|ghp_[0-9A-Za-z]{36}|sk-[A-Za-z0-9]{40,}' \
     --include='*.md' --include='*.sh' --include='*.yml' --include='*.yaml' \
     --include='*.json' --include='*.txt' . --exclude-dir=.git >/dev/null 2>&1; then
  fail "possible secret detected (run the grep above to inspect)"
else
  pass "secret scan clean"
fi

if [ "$FAIL" -eq 0 ]; then
  note "RESULT: PASS (all repo governance checks)"
  exit 0
else
  note "RESULT: FAIL"
  exit 1
fi
