# R177 — Capability Foundation Assessment (CFA)

Round: R177 (bounded, operator-authorized). Repository: `belalalibb/general_ai_core` main. Baseline HEAD at round start: **13be858d**.
Phase A was READ-ONLY on the product tree; every artefact lives under `evidence/r177/**`, `docs/r177/**`, `evidence/r177_state_ledger.md`
and appended entries in `final_docs_v3/60_DECISION_LOG.md`. Nothing under core/ apps/ ui/ infrastructure/ providers/ gateway-service/
engineering/verification/ or the canonical prompt was modified (KNOWN: `git diff --stat 13be858d -- core apps ui infrastructure providers
gateway-service engineering` → empty). This document does **not** declare QEVION complete; it classifies every investigated area with the
§19 closed set and states KNOWN vs INFERRED throughout.

## 1. Baseline reconciliation (A01) — `evidence/r177/A01_baseline/baseline_reconciliation.md`
All 13 rows of directive §2 CONFIRMED against git/ledger/evidence: HEAD 13be858d == origin/main, clean; R176 A0–A13 + B FIX-02..07 SHAs
present (bf5d0f9, ff38b07, bd4bdd9+eb44553, 005aa45, 4839b7b0, f44cc703); final gate artefact `pytest passed=3196 failed=0 errors=0
skipped=64`, ruff/format/mypy/import-linter PASS, `RESULT: FAIL` solely on the secret scan hit at canonical prompt line 132; gateway 194
passed. FIX-01 untouched — PENDING APPROVAL / OPERATOR-OWNED. **Divergences: none** for §2. Two divergences vs directive text elsewhere:
`CAPABILITY_IDS` has **17** ids (not 16; `dev.publish_modes`, R172 C7) and `create_app` has **37** parameters (not ~35). Repository wins.

Round operations: 4 sandbox resets; one erased two local-only commits while publication was blocked (no credential) — rewritten from the
same evidence and pushed; every later chunk was committed+pushed in one shell call. The R177 baseline gate re-run was started twice and
lost to resets both times; because the product tree is byte-identical to 13be858d, the R176 final-gate artefact is the pinned baseline.

## 2. Governance-constraint confirmation (A03) — `evidence/r177/A03_governance/governance_constraints.md`
All §3 items confirmed from `check_repo.sh` / `green_manifest.json`: forbidden filenames (:41), v3 pack = 20 (:50-54), 5 state header
fields (:56), secret-scan patterns + exceptions **5/5 full**, hardcoded budget tuple (:143), not_evaluated **2/2 full**, closed sets
(VerificationLevel 5, ErrorCode 11, CAPABILITY_IDS 17, FirewallDecision 4), import-linter 13, frozen trees (ui/, apps/admin_agent/,
core/tools/gate.py), pytest floor 3127/64.

**Secret-scan honesty (§3.4)**: of canonical prompt lines 132/133/134, ONLY line 132 (GitHub PAT shape) matches the gate patterns; lines
133 (Groq `gsk_` shape) and 134 (32-hex) do NOT. A green scan after a line-132-only redaction would not prove the file credential-free;
FIX-01 must redact all three (DEC-02). Values were never printed, copied or reconstructed in this round.

**F-R177-01 (S3, governance) — change-budget enforcement hole.** `check_repo.sh:143` iterates a hardcoded tuple
`("round_a","round_b","round_r169","round_r172","round_r173")`; `:144 if r not in cb: continue`. Any other manifest round is silently
ignored. Consequence (KNOWN): R176 Phase B changed six production files with no `round_r176` entry and thus no ceiling check — the gate's
"change budget within ceilings" PASS was true and irrelevant. Fix = R177-FIX-01 (needs DEC-05; `engineering/verification/*` edit).

## 3. Composition-surface map (A04) — `evidence/r177/A04_composition/`
`create_app(...)` exposes **37** parameters; three absent-seam postures coexist: mount-time gating (agent, admin, learning → true 404),
defaults-in-place (skills/roles registries, projects/workspaces, source_proposals/snapshots, idempotency_index → always present
in-process; the seam controls durability), response-shape gating (usage block absent, never faked). Published catalog
`GET /v1/admin/capabilities` = 17 ids with per-row state rule/seam/route. Env-composed profile = **79 routes** (57 admin, 5 agent, 5 auth,
4 execute, 3 webhooks, 2+2 workspaces/projects, 3 listing, 1 healthz; `routes_env_composed.json`). Operator-desired capabilities map
onto existing seams (table in evidence). Catalog completeness observation: agent runtime, source-change, skills import,
workspaces/projects and evaluation are mounted and exercised but have **no CAPABILITY_IDS row** (closed-set edit → R177-FIX-02).

## 4. Approval-and-policy map (A05) — `evidence/r177/A05_approval/approval_policy_map.md`
Enforcement of "Core policy > approval > application configuration, most-restrictive-wins" is **ALREADY COVERED**:
`CapabilityFirewall.decide` 6 ordered paths; `ToolCallGate` "both authorities must consent", tightening only;
`DEFAULT_APPROVAL_REQUIREMENT = ALWAYS`; `approval_state` closed to `"approved" | None`; R172 payload binding ties approval to the
argument hash. Recording is **PARTIALLY COVERED**: admin config lifecycle, sourcechange (approve{cited_hash}/reject{reason} →
APPROVAL_DECISION), skills import, learning promotion (approval_required=True / admin_approved=False defaults), engineering tickets
(issue/consume/refuse → APPROVAL_DECISION) each persist their own decision. **MISSING**: a persisted, auditable composition-level
*capability proposal* record (the §7 decision sheet). KNOWN: shipped TenantPolicies have empty `approval_gated_permissions` — firewall
REQUIRE_APPROVAL is exercised by tests, not by the composed app (CSE).
**DEC-01 verification**: memory/composer paths are governed by their own closed gates (sensitivity HIGH refused unless the *app* sets
`allow_high_sensitivity`; scope priority 13 §4; secret boundary guard; tenant-scoped keys) — not by the firewall vocabulary. No divergence;
no second precedence model exists. Confirmation appended to 60_DECISION_LOG (R177-DEC-01).
