# Evidence — Phase 2 (domain discovery + bounded benchmark), Phase 3 (gap matrix), Phase 4 (selection)

Tags per §12. Competitor claims are what their public docs SAY, not what was measured here; none was run in this sandbox.

## Phase 2a — domain map (one line each)

| domain | what a task looks like | reachable with the current tool set? |
|---|---|---|
| Coding / repo engineering | read, run tests, patch, re-run, cite | yes — `ws_*`, `git_*`, `ws_run` [OBSERVED code:core/engineering/tools.py:L267-375] |
| Ops / runbook console | inspect state, act with a gated command, verify observable | yes with `ws_run` + allow-listed commands; no long-running process control |
| Knowledge Q&A over a corpus | search, read, answer with citations | partial — `ws_search/ws_read`, `source.*` only; no retrieval index |
| Data extraction / transformation | read file → produce artifact | yes — `ws_read` + `ws_write` (row 4) |
| Customer-facing chat | multi-turn conversation persistence | `conversations.persistence` exists; no agent-turn continuation seam |
| Browser / web automation | navigate, fill, extract | no tool; out of scope for this round |
| Long-running / scheduled jobs | pause, resume, checkpoint | `execute.async` + progress SSE exist; no agent-run resume [MEASURED baseline row 10] |

Selected for the benchmark (3): **coding**, **ops console**, **artifact/data**. Reason: each is reachable without a new integration, so a failed row indicts the platform, not a missing tool.

## Phase 2b — bounded benchmark (what the 11-row harness measures, and how competitors describe the same seams)

| seam | Qevion (measured this round) | LangGraph (docs) | OpenAI Agents SDK (docs) | LiteLLM (docs) |
|---|---|---|---|---|
| Provider fault mid-run | run survives one fault, bounded at 2 consecutive; 11/11 after change [MEASURED evidence/baseline_after.json] | not a framework concern; delegated to the model client | Runner performs the tool loop; retries are the model client's | "If a call fails after `num_retries`, LiteLLM falls back to another model group" [SOURCED https://docs.litellm.ai/docs/proxy/reliability 2026-09-03] |
| Same-model provider failover, silent caller | default `same_model_different_provider` [VERIFIED tests/routing::test_silent_caller_default_scope_is_same_model_different_provider] | n/a | n/a | fallback lists are operator-configured per model group [SOURCED https://docs.litellm.ai/docs/routing 2026-09-03] |
| Verification before success | verifier refuses invented evidence; `verify_result` per tool; row 9 never reports success [MEASURED] | none built in; user-written nodes | "guardrails" on input/output, tripwire semantics [SOURCED https://openai.github.io/openai-agents-python/guardrails/ 2026-09-03] | none |
| Pause/resume of an agent run | **absent** (row 10 `resumable_primitive_exists=False`) [MEASURED] | checkpointer persists thread state; `interrupt` pauses, resume later [SOURCED https://docs.langchain.com/oss/python/langgraph/persistence 2026-09-03] | "sessions … resumable approval flows" [SOURCED https://developers.openai.com/api/docs/guides/agents 2026-09-03] | n/a |
| Tool admission / authz | ToolCallGate + CapabilityFirewall before every handler; row 11 `handler_ran=False` [MEASURED] | user-written | tool guardrails; "handoffs bypass tool guardrails" [SOURCED same guardrails page] | proxy key/model permissions [UNVERIFIED-RECALL] |
| Trace / record | ExecutionRecord with nodes, evidence ids, reasoning ids in `cost_snapshot` [OBSERVED core/agent/runtime.py agent_execution_report] | checkpoints per super-step [SOURCED persistence page] | "built-in tracing … LLM generations, tool calls, handoffs, guardrails" [SOURCED https://github.com/openai/openai-agents-python/blob/main/docs/tracing.md 2026-09-03] | request logs [UNVERIFIED-RECALL] |
| Capability catalog with honest states | 16 closed ids × {available, inert, unavailable} + exercise endpoint [OBSERVED apps/api/capabilities.py:L58-92] | none | none | `/model/info` [UNVERIFIED-RECALL] |

Honest reading: the frameworks above are libraries; Qevion is a hosted control plane. The only seam where a competitor's documented capability is clearly ahead is **run persistence/resume** (LangGraph, Agents SDK). For every other seam **no head-to-head was executed**: only Qevion's column is measured, the competitor columns are documentation readings. No domain in this table is LEADING or HIGHLY COMPETITIVE; the honest label for each is **UNRANKED — competitor not executed** (R167-A §7.3 downgrade, 2026-09-03; the earlier wording "parity-or-better by construction claim" is withdrawn).

## Phase 3 — gap matrix

| gap | evidence | source type | leverage (tasks unblocked / complexity) | decision |
|---|---|---|---|---|
| G1 provider fault kills the run | rows 5–6 FAIL before | Platform primitive (loop) | 2 rows / ~60 LOC | **accepted → Change 1** (shipped `168c7fd`) |
| G2 silent caller gets no failover route | row 7 FAIL before | Platform primitive (router) | 1 row / ~8 LOC + test | **accepted → Change 2** (shipped `cf37e69`) |
| G3 no resume of a bounded-failure run | row 10 extras | Platform primitive | 1 row / est. 300–500 LOC (record→seed state, idempotency, new stop-reason semantics, storage, API field) | **rejected this round** — highest complexity per row; the record already preserves work and the caller can re-issue the ask with a `conversation_id`; would need ≥2 consumers (API + Admin) to justify. Recorded as next-round candidate. |
| G4 capability metadata lacks inputs/permissions/verification-method | Phase 1 forensics | Application-specific (Admin) | 0 tasks; improves §15 L1/L2 legibility | **rejected** — two-consumer rule fails (only Admin would read it); tool metadata already exists per tool via `GET /v1/agent-tools` (`describe()` = name/description/arguments/permission/risk) [OBSERVED core/agent/runtime.py:L153-160] |
| G5 retrieval index for corpus Q&A | domain map | Integration | many tasks / large | **rejected** — new integration, not a platform gap; out of the ≤7 budget by size |
| G6 browser automation | domain map | Tool/Skill | many / large | **rejected** — new tool family; not in scope |
| G7 long-running process control (ops) | domain map | Tool/Skill | some / medium | **rejected** — `ws_run` covers bounded commands; daemons need a lifecycle model that does not exist and should not be improvised |
| G8 provider error taxonomy already routes correctly (bad_request request-indicting, 5xx retryable, outage route-indicting) | rows 5–7 after | — | — | **Unnecessary** (already present) |

## Phase 4 — selection

Accepted (implemented, one commit each, tests green, ≤500 LOC):
1. Change 1 — bounded RECOVER at the propose seam (`core/execution/loop.py`, `apps/admin_agent/service.py` opt-out, tests). Two consumers: agent runtime (API) and admin agent (explicit single-shot posture) — both exercise the parameter.
2. Change 2 — router silent-caller default `same_model_different_provider` (`core/routing/router.py`, pin test, 11 §8 doc). Two consumers: agent `reason()` and plain `execute.sync` both route through `_resolve_fallback_scope`.

Rejected with reason: G3 (complexity/leverage), G4 (two-consumer rule), G5–G7 (integrations/tools, not platform gaps), G8 (already present).

Stop condition for implementation: no remaining gap with leverage ≥ that of G1/G2 fits the budget without inventing a consumer. Further changes this round would add complexity without a measured row that flips. [INFERRED from the matrix above]
