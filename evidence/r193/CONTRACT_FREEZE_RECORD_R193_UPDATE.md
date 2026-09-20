# Contract Freeze Record — R193 update

Round: R193 — production composition of the governed REST-Git engineering path (P-R192-04), env-gated, read-first.
Baseline: `main = 7983590a`. Branch: `genspark_ai_developer_r193`.

## 1. Shape impact on the frozen contract set

**NONE.** `contract_freeze_derive.py --check` → `contract freeze baseline: MATCHES current tree` at 039a12c2 (after all three production edits).

| Touched file | Change | Frozen set touched? |
|---|---|---|
| `apps/composition/dev_bindings.py` (NEW) | env-gated composition root (`AGENT_DEV_STATE_DIR`); builds the C2 store, C3 trust registry, C8 transport, per-tenant `GitToolset` / `BoundProjectInspector`, 5 `AgentToolSpec`s | No — composition module; no route, no contract |
| `apps/composition/agent.py` | `build_agent(tool_registry=None, extra_tool_specs=())` | No — composition signature only |
| `apps/composition/runtime.py` | `RuntimeProfile.dev_bindings`; `dev = build_dev_bindings(...)`; `create_app(dev_bindings=...)` | No — the `/v1/dev` read route was already in the baseline as opt-in (IMPL-024); it is now *served* when the env var is set, unchanged in shape |

Served-route delta with `AGENT_DEV_STATE_DIR` unset: **none** (byte-identical default profile; pinned by `tests/api/test_dev_router_mount_r172.py` and `TestInertWhenUnset`). With the env var set: `GET /v1/dev/bindings/{binding_id}/publish-modes` (pre-existing IMPL-024 shape) becomes reachable — no new route, no new response shape.

## 2. Authorities reused (none duplicated)

`JsonBindingStore` / `RepoBindingRegistry.get(binding_id, tenant_id=)` (C2) · `JsonRemoteTrustStore` / `RemoteTrustRegistry` (C3) · `GitHubRestTransport` / `GITHUB_API_BASE` (C8) · `GitToolset` + `PERM_GIT_*` (R170–R172) · `BoundProjectInspector` (R192) · `workspace_root_refusal` / `PLATFORM_ROOT` (ADR-0009 §14) · `bind_run_tenant` / `current_run_tenant` (R177-FIX-06 `repo_map` precedent) · `ToolRegistry` · `AgentToolSpec` · `ApprovalRequirement.BEFORE_ACTION` for `git.commit` / `git.publish` · `SecretManagerPort.resolve` (the onboarding secret manager already composed in `runtime.py`).

## 3. Tenancy statement (verified by test, not asserted)

Every lookup is tenant-scoped from the admitted caller: handlers read `current_run_tenant()` and refuse (`ValueError: … no admitted tenant bound for this run`) when unbound; `RepoBindingRegistry.get(..., tenant_id=)` returns `binding_tenant_mismatch` for a foreign tenant with **no** secret resolution and **no** HTTP; untrusted remotes refuse with `remote_not_trusted` before any credential is touched. No admin-only path; no new isolation model; the same shared multi-tenant registry serves every tenant.

## 4. NOT claimed (deliberately absent)

- `/v1/dev` **write** routes (bind / grant / publish over HTTP) — absent.
- A trust-**grant** endpoint or CLI — absent (SHAPE decision, still P-R192-03).
- **Durable credential custody** — the composed secret manager is the existing in-memory onboarding manager; tokens are resolved per call and never stored by R193 code.
- Branch/PR cleanup primitive (C8 note) — still open.

## 5. Operator decisions still required (unchanged, re-checked)

- **P-R191-01** — served `/v1/templates`: still required; no route added.
- **P-R192-02** — App Factory binding_id UI/route: still required.
- **P-R192-03** — trust-grant operator act: still required (SHAPE).
- **P-R192-04** — production composition: **closed by R193** (env-gated).

## 6. Backward compatibility

Unset env ⇒ identical `RuntimeProfile` except the new `dev_bindings: None` field; identical served routes; identical agent catalog. `build_agent` new parameters default to prior behaviour (`ToolRegistry()` created internally; no extra specs).
