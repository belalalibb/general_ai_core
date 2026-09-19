# R190 HANDOFF — P-R189-01 Logical Model Identity Across Providers

## 1. Authority
Operator directive "QEVION — R190 EXECUTION DIRECTIVE · P-R189-01". Declared in `final_docs_v3/60_DECISION_LOG.md` R190-DEC-01 BEFORE any production commit. Baseline `main c9730d9d`.

## 2. Boundaries
ONE logical Model + MANY ProviderModelBindings + ONE router + ONE execution path + same-model fallback. No aliases, no second registry, no provider-specific routing branch. Freeze ADDITIVE-ONLY; contract SHAPE expected unchanged. App Factory out of scope. F-CS1-04 operator-owned. Zero provider calls.

## 3. Slice
`round_r190` ceiling 2: `core/providers/onboarding.py` (step-12 reuse of an existing Model under an explicit prefix; rollback removes only what this onboarding created) + `apps/composition/provider_onboarding.py` (hydration idempotent Model registration).

## 4. Proof plan
RED on the current tree (duplicate-key refusal; hydration DuplicateRegistration) → implement → GREEN A–J (one Model, two bindings, no duplicate Model, first provider intact, failed second onboarding leaves state intact, model-only routing sees both, explicit provider+model, same-model fallback, cooled provider excluded, old payload unchanged) → regression → fresh-clone gate + gateway → ratchet → PR → post-merge gate → freeze record update → closure.

## 5. Stop conditions
Third production file needed → STOP and record. Contract SHAPE change needed → PROPOSAL block, stop that expansion. Tenant-ownership rule needed → PROPOSAL, not invented.

## 6. Ledger
`evidence/r190_state_ledger.md`.
