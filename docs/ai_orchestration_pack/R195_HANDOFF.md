# R195 HANDOFF — governed dev-binding registration + remote trust (AD-1) · durable dev credential custody (AD-2)

## 1. Status
CLOSED 2026-09-20 — PR #48 → `main 16048078`; closure PR records-only. Base `main 26e24f1e`. Branch `r195_governed_dev_bindings`. Authority: `60_DECISION_LOG.md` R195-DEC-01 (operator "APPROVE R195", D1–D4 accepted).

## 2. Scope (ceiling 4 production files)
| Item | File | Purpose |
|---|---|---|
| R195-A | `core/contracts/admin.py` | `AdminAction` +3 (`REGISTER_REPO_BINDING`, `GRANT_REMOTE_TRUST`, `REVOKE_REMOTE_TRUST`) → `AdminArea.TOOLS` |
| R195-B | `core/admin/service.py` | Protocol seams + validate/preview/snapshot/apply/restore branches |
| R195-C | `apps/agent_dev/git_tools.py` | `RepoBindingRegistry.remove(binding_id, *, tenant_id)` for rollback |
| R195-D | `apps/composition/runtime.py` | Vault custody when `VAULT_ADDR`+`VAULT_TOKEN`; seams handed to `AdminConfigService` |

Excluded: N-9 (D4), any `/v1/dev` write route, any new area, any UI change, R196+ (AD-3…).

## 3. How an operator uses it (after merge)
1. Seed the tenant's GitHub token in Vault under `<VAULT_MOUNT>/<tenant_id>/<suffix>` with field `value`; the `credential_ref` is `vault:<suffix>`. (Vault refs minted by `store()` use a UUID suffix; hand-seeded suffixes are accepted by `_path`.)
2. `POST /v1/admin/changes {"action":"register_repo_binding","payload":{"binding":{RepoBinding JSON incl. tenant_id, remote_url https://…, branch, local_root, credential_ref}}}` → `/validate` → `/preview` → `/publish`.
3. `POST /v1/admin/changes {"action":"grant_remote_trust","payload":{"target_tenant_id":"…","remote_url":"https://…","note":"…"}}` → validate → publish. Revoke symmetric with `revoke_remote_trust`.
4. Rollback via `/rollback` removes the binding / restores the prior trust state (never silently deletes a trust row).

## 4. Invariants
Shared multi-tenant; secrets never in payloads (R176 FIX-04); core pure (Protocols); no route/freeze delta; absent seams fail validation loudly; in-memory profile byte-identical without Vault.

## 5. Evidence (filled at closure)
`evidence/r195/{red_r195.txt, green_r195.txt, regression_<sha>.txt, gate_head_<sha>.txt, gateway_head_<sha>.txt, gate_merge_<sha>.txt, gateway_merge_<sha>.txt, CONTRACT_FREEZE_RECORD_R195_UPDATE.md}`; ledger `evidence/r195_state_ledger.md`.

## 6. Next decision gate
After closure: R196 (AD-3 templates) requires its own proposal + `APPROVE R196`. D-03 remains operator-owned and unclaimed.
