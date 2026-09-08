# R177-A09 — Agent capability completeness matrix (§12) — §19 closed-set classification

Legend: AC = ALREADY COVERED · CSE = COVERED BUT NEEDS STRONGER EVIDENCE · PC = PARTIALLY COVERED · M = MISSING · NN = NOT NECESSARY · D = DEFERRED · B = BLOCKED.
Evidence tiers: R176 probe = executed runtime evidence reused (not re-run); "read" = source read in R177; "test" = existing test suite.

| # | §12 item | what exists (anchor) | class | evidence / gap |
|---|---|---|---|---|
| 1 | Planning | `core/execution/graph_planner.py` (deterministic topologies single/pipeline/parallel; "planner PLANS, runtime RUNS"); agent loop proposes step-by-step | **PC** | planner exists and is tested but `WorkflowRuntimePort` has **no engine binding** (app.py:86 docstring); multi-node strategies refused at /v1/execute since FIX-03. Task-level planning = LLM proposal inside `AgentLoop` (bounded) |
| 2 | Decomposition | same as 1; `ExecutionGraphSpec`; pipeline via agent_node_mapping (10 §13.5) | **PC** | structural decomposition exists (graph spec, node mapping); no persisted task tree across runs |
| 3 | Repository understanding | A08 | **PC** | primitives AC; persisted repository model **M** (F-R177-05) |
| 4 | Context management | `core/context/composer.py` + `context_budget` seam | **AC** | deterministic, budgeted, gated (A06); R176 A4/A10 exercised |
| 5 | Working memory | `_RunState`/`AgentStep` in `core/execution/loop.py`; trace route | **AC** (per run) | per-run only — by design |
| 6 | Long-term memory | MemoryStorePort + MemoryItem | **PC** | store/composer real; **no runtime writer except GOLD** (F-R177-02/03) |
| 7 | Project memory | MemoryScope.PROJECT/WORKSPACE + projects/workspaces stores | **PC** | scope composes; no writer |
| 8 | Tool use | core/tools/* + core/engineering/tools.py; `/v1/agent-tools` | **AC** | R165 live run; R176 A5 laundering refusals; A08 |
| 9 | Skills | SkillRegistry, SkillResolver (AUTO 41 §16), import lifecycle 7 routes | **AC** | R176 A4/A6; skills import E2E from allowed source **UNVERIFIED** (R176 §20) |
| 10 | Execution | ExecutionService single/pipeline; async via outbox+worker; agent strategy | **AC** | R176 A4/A5/A7/A9 probes; FIX-03/05 in R176 B |
| 11 | Verification | verify-with-evidence in AgentLoop (STOP_VERIFICATION_FAILED); sourcechange verify; checkpoint seal | **AC** | R165; A08 |
| 12 | Testing | ws_run allowlist (pytest/ruff/python3); scenarios + regression-pack routes | **AC** | R165 live pytest via ws_run; admin scenarios routes (A04) |
| 13 | Evaluation | GraderType 7, EvaluationPolicyService, ladder | **PC** | deterministic graders composed; **model judge NOT composed** (G-A07-2); eval store in-memory (G-A07-4) |
| 14 | Recovery | stop reasons (max_steps, invalid_proposal, propose_failed, verification_failed, deadline, repeated_failure); worker retry/idempotency; checkpoint revert; admin/sourcechange rollback | **AC** | R176 A7 reliability probes (R-01..08) |
| 15 | Error handling | closed ErrorCode 11 + unified envelope everywhere | **AC** | R176 A5/A10/A12 (401/403/404/422/429/503 constancy) |
| 16 | Reasoning support | AgentRuntime.reason() through routing; constrained decoding schema; DEFAULT_REASONING_MAX_TOKENS | **AC** | R165/R173 live Groq ladder; provider-agnostic |
| 17 | Learning | A07 | **PC** | gates AC; evidence chain for promotion signals **PC** (G-A07-1); intake **M** (G-A07-3) |
| 18 | Knowledge management | GOLD memory + ask_learned/learned_keys | **PC** | promoted knowledge AC; intake M; observability PC (G-A07-5) |
| 19 | Policy enforcement | CapabilityFirewall + ToolCallGate + approval_policy default ALWAYS | **AC** | A05; frozen gate; tests |
| 20 | Permission boundaries | TenantPolicy grants; engineering tickets; payload binding; jail; denylist | **AC** | A05/A08; R176 A5 |
| 21 | Provider abstraction | ProviderRegistry/BindingRegistry/Router; remote gateway (ADR-0008); import-linter forbids provider libs in core | **AC** | R176 A9 (Groq 7/0/0, AssemblyAI 10/10); 13 contracts kept |
| 22 | Multi-tenant isolation | tenant_id on every store key; 20 §6 anti-enumeration; firewall per tenant | **AC** | R176 A5 20/20 attribution, 0 cross-reads; A12 falsifiers held |
| 23 | Observability | OpenTelemetry tracer/meter (apps/observability), audit events + /v1/admin/audit, agent trace/diagnosis, learning dashboard | **CSE** | wiring present; no executed probe of exported spans/metrics in R176/R177; audit read is admin-only |
| 24 | Reproducibility | request_hash on every Execution; idempotency (FIX-05); deterministic composer/planner; scenario replay route | **AC** | R176 A7/A12; FIX-05 |
| 25 | Durable state | 18 migrations; durable executions/outbox/idempotency/identity/sourcechange/bindings; **process-local**: queue, rate-limiter, usage, leases, evaluation store, memory (in env profile) | **PC** | honest envelope from R176 §21 unchanged; evaluation store in-memory even in durable profile (G-A07-4) |
| 26 | Human approval where required | five lifecycles + tickets + firewall REQUIRE_APPROVAL | **AC** (enforcement) / **M** (composition-level proposal record) | A05 §6 |

## Aggregate
AC 15 · PC 9 · CSE 1 · M 0 standalone (the MISSING items are sub-gaps inside PC rows: repository model, memory writers, structured
intake, proposal record) · NN 0 · D 0 · B 0. UI-related coverage is **DEFERRED** by directive §15/§3.9 and not assessed here.

## Confirmed gaps eligible for bounded landscape research (A10) — only these
1. Persisted repository model (row 3 / F-R177-05).
2. Composition-level capability-proposal record (row 26 / A05 §6).
3. Structured knowledge intake normalisation (row 17-18 / G-A07-3).
4. Evidence-bound promotion signals (row 17 / G-A07-1).
Not researched: memory writers/preferences (design is already fixed by 13 §6 — wiring, not pattern), Teacher (22 §10 already defines
the pattern), observability (verification task, not a pattern gap).
