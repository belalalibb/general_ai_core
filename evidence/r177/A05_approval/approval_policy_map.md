# R177-A05 — Approval-and-policy map (what already enforces "propose → explain → approve/reject → Core enforces → recorded")

All rows are KNOWN (read from source at HEAD 13be858d) unless marked INFERRED.

## 1. Enforcement — `core/security/firewall.py` `CapabilityFirewall.decide()` (deterministic, deny-by-default)
Ordered paths (firewall.py:23-27, code :76-93):
1. tenant has no policy record → **DENY**
2. `permission ∉ granted_permissions` → **DENY**
3. `entitlement ∉ granted_entitlements` → **DENY**
4. `permission ∈ approval_gated_permissions and approval_state != "approved"` → **REQUIRE_APPROVAL**
5. `permission ∈ limited_permissions` → **ALLOW_WITH_LIMIT**
6. else **ALLOW**
Invariant (:30): `approval_state == "approved"` never bypasses grant checks (approved-but-ungranted stays DENY).
`TenantPolicy` (core/contracts/security.py:56-59): four frozensets — granted_permissions, granted_entitlements, approval_gated_permissions,
limited_permissions; `FirewallDecisionInput.approval_state: Literal["approved"] | None` (:91) — **closed**.

## 2. Composition of authorities — `core/tools/gate.py` `ToolCallGate` (FROZEN tree, r173)
Order: (1-3) manifest/tool-shape/permission checks → DENY naming the check (:117-136); (4) firewall verdict; DENY → `firewall_deny` (:142);
(5) tool `approval_policy.get(permission, ApprovalRequirement.ALWAYS)`; anything but NONE without `approval_state=="approved"` →
REQUIRE_APPROVAL `tool_approval_required:<level>` (:144-149); (6) firewall REQUIRE_APPROVAL → `firewall_requires_approval` (:151-154).
Docstring :34-38: "tightening only, never loosening … most-restrictive-wins; both authorities must consent".
`core/contracts/tools.py`: `ApprovalRequirement = {none, before_action, always}` (:58-63, closed); `DEFAULT_APPROVAL_REQUIREMENT = ALWAYS`
(:101) — an unlisted permission resolves to the MOST restrictive requirement (41 §1 rule 9).
**Conclusion**: the operator's model "Core policy > approval > application configuration, most-restrictive-wins" is the EXISTING semantics.

## 3. Where approval_state comes from at runtime (KNOWN)
- `core/execution/loop.py:588-599`: the agent loop builds `FirewallDecisionInput(... approval_state=binding.approval_state ...)` from the
  **tool binding** (`core/execution/agent.py:150 approval_state: Literal["approved"] | None = None`) — i.e. composition DATA, default None.
- `apps/agent_dev/surface.py:192` builds the same input for the dev surface, and (R172 C6) adds **payload binding**: approval is tied to
  the sha256 of the canonical call arguments (`core/contracts/approval_binding.py`, `core/tools/payload_binding.py`) — refusals
  `approval_hash_required | approval_payload_mismatch | payload_not_canonicalisable`. Opt-in per composition (`payload_binding=True`).
- Runtime tenant policies are composition data: `apps/composition/agent.py:56 READ_ONLY_AGENT_POLICY` (granted `source.read` +
  entitlement `agent.tools`; **no** approval_gated / limited sets); `apps/composition/engineering.py:_merge/grant_engineering_reads/
  grant_engineering_writes` add engineering permissions (unknown names refused). ⇒ In the shipped profile **no permission is
  approval-gated at the firewall**; approval gating today is exercised through (a) the tool `approval_policy` default ALWAYS, (b) the
  engineering **AuthorizationLedger** tickets, (c) the sourcechange / skills / admin lifecycles below.

## 4. Decision recording / auditability
- `core/contracts/audit.py` `AuditEventType` (13 values) includes `APPROVAL_DECISION`, `TOOL_CALL`, `PERMISSION_DENIED`,
  `ADMIN_CONFIG_PUBLISHED/ROLLED_BACK`, `SECURITY_POLICY_CHANGED`, `TRAINING_DATASET_PROMOTED`, `CROSS_TENANT_ACCESS_DENIED`.
  `AuditEvent` = id, tenant_id, event_type, actor_id (None = system), occurred_at, details, admin_change.
- `APPROVAL_DECISION` is emitted by exactly **2** modules: `core/sourcechange/workflow.py` ("every human act appends an APPROVAL_DECISION
  audit row") and `core/engineering/authorization.py` (ticket issue / consume / refuse). `TOOL_CALL` by 4 modules.
- Read surface: `GET /v1/admin/audit` (admin-only).

## 5. Lifecycle patterns already implementing propose→explain→approve/reject→apply
| pattern | states / verbs | explanation carried | approve/reject record | code |
|---|---|---|---|---|
| admin config change | draft → validate → preview (impact_preview only after preview) → publish → rollback | impact_preview (diff, affected tenants) | AuditEvent ADMIN_CONFIG_PUBLISHED / ROLLED_BACK with `admin_change` | core/admin/*, apps/api/admin.py; routes /v1/admin/changes/* |
| source change (ADR-0009) | snapshot → propose(add/modify/delete) → verify → approve{cited_hash} → reject{reason} → apply → rollback | proposal content_sha256, verification report | `ApprovalRecord(approver_id, approved_patch_hash)`; APPROVAL_DECISION rows | core/sourcechange/workflow.py:198-222 |
| skills import | import → scan → validate → review → approve → activate; `allowed_sources` enumerated; 6 provenance fields | scan/validate reports | lifecycle state + audit | core/skills/importing.py:132; routes /v1/admin/skills/imports/* |
| learning promotion | admit_to_training (TrainingEligibilityGate) → promote_to_gold (PromotionGate) | every failed condition named | `PromotionSignals.approval_required=True`, `admin_approved=False` defaults (core/learning/gates.py:138-139); TRAINING_DATASET_PROMOTED | core/learning/lifecycle.py |
| engineering writes | admin issues ticket → consume (one use burned) → refuse | ticket scope, TTL ceiling | AuthorizationLedger → APPROVAL_DECISION act=issue/consume/refuse | core/engineering/authorization.py |
| tool call | manifest → firewall → approval_policy → execute | refusal names the failed check | TOOL_CALL / PERMISSION_DENIED audit | core/tools/gate.py, core/tools/executor.py |

## 6. What is genuinely missing (evidence-backed)
1. **No generic "capability proposal" record.** The five lifecycles above each persist THEIR decision; there is no persisted object for
   "the Agent proposed enabling capability X for application Y; operator approved/rejected with reason", i.e. the §7 decision sheet has
   no storage or route. Enforcement is complete; **the recording/explanation surface for composition-level proposals is absent**
   (INFERRED from: no contract/route mentions "proposal" outside sourcechange; `grep -rn "capability.*propos"` over core/apps → 0 hits).
2. **Firewall approval gating is unused in the shipped profile** (all runtime TenantPolicy values have empty `approval_gated_permissions`).
   Not a defect — composition data — but it means REQUIRE_APPROVAL via the firewall is exercised only by tests, not by the composed app
   (COVERED BUT NEEDS STRONGER EVIDENCE for the runtime path).
3. **Memory/knowledge/personalization paths do not pass through the firewall at all**: `core/memory/*`, `core/context/composer.py` gate
   on MemorySensitivity (`allow_high_sensitivity`, default False, composer.py:167), scope priority (13 §4), confidence, and the secret
   boundary guard (memory.py:54-66) — all deny-by-default, tenant-scoped by key `(tenant_id, user_id, scope, key)` — but there is no
   TenantPolicy permission for "read memory type T" or "write preference". ⇒ For **DEC-01**: the most-restrictive semantics hold
   *within* memory (sensitivity/scope gates cannot be loosened by request data — `allow_high_sensitivity` is a composer-input, set by
   the app, never by the caller: app.py builds ContextComposeRequest without it → False), but memory is governed by its own closed
   gates, not by the firewall vocabulary. No divergence found; no second precedence model exists. Minimum alignment, if ever wanted,
   is composition DATA (a TenantPolicy permission consulted by the composer) — not a new model.

## 7. Answer to the A05 question
Enforcement of "Core policy > approval > app configuration, most-restrictive-wins" is **ALREADY COVERED** (firewall + gate + closed
defaults + payload binding). Recording is **PARTIALLY COVERED**: complete for source changes, admin config, skills, learning promotion,
engineering tickets; **MISSING** for composition-level capability proposals (the §7 decision sheet as a persisted, auditable object).
