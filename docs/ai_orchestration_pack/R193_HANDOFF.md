# R193 HANDOFF — production composition of the governed REST-Git engineering path (P-R192-04)

## 1. Authority
Operator "APPROVE R193" on the R192→next-round proposal. Declared in `60_DECISION_LOG.md` R193-DEC-01 BEFORE any production commit. Baseline `main 7983590a`.

## 2. Boundaries
Additive, env-gated (`AGENT_DEV_STATE_DIR`). Reuse ONLY: `JsonBindingStore`, `JsonRemoteTrustStore`, `RepoBindingRegistry`, `RemoteTrustRegistry`, `GitToolset`, `GitHubRestTransport`, `BoundProjectInspector`, `SecretManagerPort`, `CapabilityFirewall`/`ToolCallGate`, `create_app(dev_bindings=)`, `apps.api.run_context`. No Core change. No `/v1/dev` write route. No trust-grant endpoint. No admin-only execution. No new isolation model — tenant scope from the admitted caller at every lookup.

## 3. Slice
`round_r193` ceiling 3: `apps/composition/dev_bindings.py` (NEW), `apps/composition/runtime.py`, `apps/composition/agent.py`.

## 4. Proof plan
RED `tests/composition/test_r193_dev_bindings_composition.py` (i–vii in DEC-01) → implement → GREEN → regression → freeze `--check` → fresh-clone gate + gateway → ratchet → PR → post-merge gate → records.

## 5. Stop conditions
Fourth production file → STOP. Any served-route SHAPE change → STOP + proposal. Freeze re-derive not MATCHES → STOP. A requirement for per-tenant durable credential custody → STOP (out of scope; NOT claimed).

## 6. Ledger
`evidence/r193_state_ledger.md`.

## 7. Closure (2026-09-20)
- **Result:** R193 CLOSED (R193-DEC-02). PR #44 merged by merge commit → `main 04952844`; records-only closure PR follows.
- **Production:** 3/3 files (`apps/composition/dev_bindings.py` NEW, `agent.py`, `runtime.py`); Core untouched; freeze `--check` MATCHES.
- **Gates:** gate of record 9ae8b6b6 PASS 3837/0/0/64 + gateway 194; post-merge 04952844 PASS 3837/0/0/64 + gateway 194; `min_passed` 3826 → 3837.
- **Operating the seam:** set `AGENT_DEV_STATE_DIR=<dir outside the platform root>` (optionally `AGENT_DEV_GITHUB_API` for GHE). Bindings and trust grants are registered through the existing `RepoBindingRegistry` / `RemoteTrustRegistry` authorities on `RuntimeProfile.dev_bindings` / the composed trust store — no HTTP write route and no grant endpoint exist (P-R192-03).
- **Next:** STOP on main. Open decisions P-R191-01, P-R192-02, P-R192-03 remain operator-owned.
