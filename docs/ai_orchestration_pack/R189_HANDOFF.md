# R189 HANDOFF — Contract Freeze Preparation

## 1. Authority
Operator directive "QEVION — R189 EXECUTION DIRECTIVE · Contract Freeze Preparation" (2026-09-19). Declared in `60_DECISION_LOG.md` R189-DEC-01 BEFORE any production commit.

## 2. Boundaries
Stabilization + disposition. ZERO new capabilities except the operator-approved P-R188-01 additive field. ZERO new served endpoint. ZERO provider calls. ZERO App Factory. Additive-only after freeze. Repository wins over the directive; disagreements recorded in R189-DEC-01.

## 3. Slice
1. P-R188-01 `model_key_prefix` on `GatewayOnboardRequest` (≤ 2 production files, `round_r189` ceiling 2).
2. Contract Freeze Baseline: derived `engineering/verification/contract_freeze_baseline.json` + guard `tests/verification/test_contract_freeze_baseline.py` (distinct from "port conformance").
3. Dispositions A (modality_limits) / B (admin_fallback_chain) / C (account pool / lease / fencing); R188 audit artifact `evidence/r188/audit_routing_a99e2545.md`; §E/§F reference replacement; P-R188-03/04 NO recorded.

## 4. Proof plan
RED→GREEN for (1) and (2); deliberate mutation FAIL → revert PASS; fresh-clone gate + gateway; D-03 stays NOT EVALUATED.

## 5. Stop conditions
Material decision outside boundary → PROPOSAL block; third production file needed → STOP and name the next round.

## 6. Ledger
`evidence/r189_state_ledger.md`.
