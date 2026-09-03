# QEVION — Platform Capability Evolution: Final Report (§18)

Round R167-QEVION. Tags per §12; untagged = invalid.

## 1. Mandate and judging criterion

Increase *reliable task completion per unit added complexity* on the existing platform, every change measured against a committed baseline. The sandbox reset six times during the round; §1A applied each time (HEAD verified against origin, environment restored, nothing recreated, no secret committed) [VERIFIED `git log`/`git status` per session].

## 2. Baseline (before)

`python3 evidence/baseline_tasks.py` → `evidence/baseline_before.json`: **8/11 PASS**, 6 verified completions, 0 unverified successes, 28 model calls [MEASURED]. All three failing rows were one seam: a provider fault on ONE reasoning step ended the whole run (`propose_failed`), and under AUTO policy a registered backup provider was never tried [OBSERVED code:core/routing/router.py:_resolve_fallback_scope pre-change]. Full suite at start: 2683 passed / 64 skipped [VERIFIED exit 0].

## 3. Domain discovery and benchmark

Seven domains mapped; three selected (coding, ops console, artifact/data) because each is reachable with existing tools, so a failed row indicts the platform rather than a missing integration. Competitor seams from public docs only: LangGraph persistence/interrupt [SOURCED docs.langchain.com/oss/python/langgraph/persistence 2026-09-03], OpenAI Agents SDK guardrails/tracing/sessions [SOURCED openai.github.io/openai-agents-python/guardrails/ 2026-09-03], LiteLLM retries→fallback [SOURCED docs.litellm.ai/docs/proxy/reliability 2026-09-03]. Run **persistence/resume** is the one seam where a competitor's documented capability is clearly ahead. Table: `evidence/benchmark.md`.

## 4. Gap matrix and selection

G1 loop dies on provider fault (Platform primitive) — accepted. G2 silent caller gets no failover route (Platform primitive) — accepted. G3 no resume of a bounded-failure run — rejected this round (est. 300–500 LOC, one consumer, work already preserved in the record). G4 richer capability metadata — rejected (two-consumer rule fails; per-tool metadata already exists via `GET /v1/agent-tools`). G5–G7 retrieval/browser/daemon control — Integration/Tool, out of budget. G8 error taxonomy — already present. G9 surfaced live (§6) and was accepted.

## 5. Changes shipped (3 of ≤7; one commit each; tests green)

1. **`168c7fd` loop — bounded recovery at the propose seam.** `DEFAULT_MAX_PROPOSE_FAILURES=2`; a fault becomes an observation (`nothing_happened: true`), consumes one step, the run continues; two consecutive faults still stop as `propose_failed`. Admin agent opts out (`max_propose_failures=1`) to keep its single-turn semantics. Two consumers: API agent runtime and admin agent [OBSERVED code:core/execution/loop.py, apps/admin_agent/service.py]. Three pins added/updated [VERIFIED pytest exit 0].
2. **`cf37e69` router — silent-caller default `same_model_different_provider`.** 8 LOC + pin test + 11 §8 doc aligned [OBSERVED code:core/routing/router.py]. Opt-out unchanged (`allow_fallback=false` / `fallback_scope=none`) [VERIFIED tests/routing 59 passed].
3. **`ae295f6` groq — HTTP 400 `organization_restricted` → `invalid_credential`.** Found live (§6). As `bad_request` it forbade both retry and failover [OBSERVED code:providers/real/groq/adapter.py:_normalize_http_response]. Pin test added [VERIFIED].

## 6. Measured after

Same harness after Changes 1–2: **11/11 PASS**; verified completions 6→9; model calls 28→30 (exactly one re-proposal per recovered fault; the failover row recovers with zero extra calls); prompt chars +7.5%, confined to rows 5–6; rows 1–4 and 8–11 byte-identical [MEASURED before→after, evidence/baseline.md]. No amplification on healthy paths.

Live (Phase 6, `evidence/tasks/*.log`, real HTTP against `python3 -m apps.main` bound to Groq): the operator's Groq **organization is restricted** — direct probe `400 organization_restricted`; `/v1/models` `invalid_api_key` [VERIFIED curl; 15_developer_transcript.log §9]. The alternate provider (genspark_llm) returns a "free-plan credits can't be used" message inside a 200 [VERIFIED curl]. Consequently:
- Model-dependent categories 01–07, 10 and the execute step of 12: **NOT VERIFIED live**. Each fails in 130–260 ms with `502 execution_failed`, `stop_reason=propose_failed`, cause `invalid_credential/organization_restricted`; record and trace remain readable [VERIFIED logs]. Fast honest failure is RECOVER-boundary behaviour, not completion.
- Model-independent categories **PASS live**: 08 authz denial (`ws_write` without `workspace.write` → file untouched), 09 no fabricated file content, 11 Admin op (capabilities / exercise / system / audit all 200), 13 capability registration proof — option **(b)**: closed set, 16 rows, each with an `evidence` seam; no runtime registration API by design [VERIFIED logs].
- Failover cannot rescue a single restricted account; harness rows 5–7 prove the mechanism with a scripted second provider [MEASURED].

## 7. Core/app boundary and genericity (§10)

`core/` owns loop, routing, execution, gate/firewall, evidence verification, engineering tools; `apps/` owns composition, HTTP contracts, Admin, admin agent. All three changes landed in core/providers with no app-layer branching [OBSERVED git diff]. import-linter boundaries hold [VERIFIED check_repo.sh PASS].

Genericity check (≤300 words). An *ops console* app would compose `build_agent` with a different tool set — allow-listed `ws_run` commands such as `systemctl status` or `journalctl`, read-only config paths — and a different `TenantPolicy`. Nothing in the loop, router, gate or verifier references coding; the `ws_run` exit-code `verify_result` rule generalises to any command. The capability catalog stays the same closed set unless the composition root adds a row. What would NOT transfer: long-running process control (no lifecycle model — G7) and resume of a budget-exhausted run (G3). Those are honest gaps, not coding-specific assumptions [INFERRED from code reading; not executed].

## 8. Admin L1/L2/L3 and developer transcript (§15)

L1 catalog: `GET /v1/admin/capabilities` — 16 rows, states {available, inert, unavailable}, `evidence` per row; UI badges derive from these enums [VERIFIED 13_capability_registration.log]. L2 drill-down: `GET /v1/executions/{id}`, `/v1/agent/executions/{id}/trace` (stages; attempts with model/provider/error_category), `/diagnosis` [VERIFIED transcript §7]. L3 act: `POST /v1/admin/capabilities/{id}/exercise` for the server-declared exercisable subset; a non-exercisable id returns 404 [VERIFIED transcript §11]. Transcript: 17 real calls — session → system → capabilities → tools → engineering status (root, commands, grants, tickets) → models/providers → execute → record/trace/diagnosis → audit → induced-failure attribution → continue → exercise → list [VERIFIED 15_developer_transcript.log: 15×200, 2×502]. Metadata gap: capability rows lack inputs/permissions/verification-method; tool rows carry them (`describe()`), so L1 legibility is tool-level, not capability-level [OBSERVED].

## 9. Security invariants and scale red-team

Re-verified: gate before handler (08 live; baseline row 11), no fabricated evidence (09 live; row 9), no secrets in repo (check_repo secret scan PASS; logs redact bearer/token) [VERIFIED]. Red-team on Change 1: recovery consumes `max_steps` slots, so a flapping provider cannot extend a run beyond its step budget; two consecutive faults stop the run; per-step retries stay bounded by `PROVIDER_MAX_RETRIES`. Per-run call ceiling = `max_steps × (1 + max_retries) × |fallback route|`; unchanged by Change 1, at most `+|providers|` per step by Change 2 [INFERRED from code; harness shows +2 calls over 11 tasks, MEASURED]. Change 3 widens failover only for a non-retryable credential category — no retry storm [OBSERVED].

## 10. Learning seams (§17)

`core/learning/{lifecycle,gates,sanitizer}.py` and `/v1/admin/learning/*` exist and sit in the closed catalog (`learning.lifecycle`) [OBSERVED]. Not exercised this round; no measured-learning claim is made. The new propose-fault observations and `propose_faults` summary field are signals a learning consumer could read [INFERRED].

## 11. Gate decision (§20) and stop condition (§19)

(a) baseline measured ✔; (b) changes measured 8→11/11 ✔; (c) tests green, gate PASS ✔ [VERIFIED 2687 passed / 64 skipped; check_repo.sh PASS]; (d) docs match code ✔ (11 §8 updated; OPERATIONS still accurate); (e) git clean and pushed ✔; (f) **live 13-category validation ✘** — 9 categories unverified live because the provider account is restricted; (g) §15 transcript ✔, but its execute steps show honest failure, not completion.

**The §20 sentence is NOT emitted.** Failed condition: (f). To close it: supply a working provider key and run `python3 evidence/tasks/run_live.py`; the same runner and assertions apply and no code change is expected.

Pre-existing, out of scope: `ruff format --check` lists 33 files at both `4072348` and HEAD; `check_repo.sh` does not run it [VERIFIED].
