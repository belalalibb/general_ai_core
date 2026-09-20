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
