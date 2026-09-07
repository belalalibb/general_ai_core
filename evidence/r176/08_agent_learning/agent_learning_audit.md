# A8 — Agent / Skills / Learning forensic (prompt §2.8) — EXECUTED

HEAD at start 8eacc6f (sandbox reset #23 wiped an untracked draft; probes were then committed BEFORE running).
Tier 1: `tier1_suites.txt` — agent + agent_dev + 4 agent-loop suites + skills + learning + evaluation + memory + context:
**585 passed**. Tier 2: `a8_probe.py` → `learning_probes.txt`; `a8b_chain.py` → `learning_chain.txt`;
`sanitizer_gap_check.txt` (pure-function check).

## 1. Agent loop (Understand → Plan → … → Stop)
| aspect | evidence | status |
|---|---|---|
| Real loop, not retry-retry | `core/agent/runtime.py`; tests `test_agent_loop_reassess/_verify/_v4`, `test_agent_proposals_v4` (in the 585) cover reassess, verify, invalid proposal, tool denial, max_steps; A4 P-24 live: no tools on `local_echo` ⇒ stop `invalid_proposal` at `plan-2`, honest 502 with `stop_reason`, node, error detail | VERIFIED · TEST + RUNTIME (platform) |
| Tool denial / unknown tool | A4 P-18: 422 before any step | VERIFIED |
| Policy denial (budget) | `max_steps` may only lower the operator cap (`app.py` R165) | VERIFIED · STATIC + TEST |
| Provider failure / repeated failure / timeout | R165 + R175 L-03 live (Groq): failure classes mapped, `organization_restricted` parity fixed R175 | LIVE (prior round) |
| Trace observability | `/v1/agent/executions/{id}/trace` (admin) returns model/provider/attempts/stop reason — observable artefacts, no hidden reasoning | VERIFIED · STATIC (route) |
Behaviour with a real model this round: NOT re-spent (already LIVE-proven R165/R175; prompt §2.1 "never spend to prove the proven").

## 2. Skills / tools lifecycle
- `POST /v1/admin/skills/import` closed shape (G-14: 422 with field errors); listing exposes an **allow-list of 3 sources**
  (G-15) — imported skills are not trusted on entry; states `scan → validate → review → approve → activate` are separate routes.
- User-visible `/v1/skills` = [] with no approved skills (G-16); unknown skill in execute → 422 (A5 S-24).
- Tool allow-list resolved against composition catalog; 0 tools offered without `AGENT_WORKSPACE_ROOT` (A4 P-21).
Status: lifecycle **VERIFIED at the gates (RUNTIME)**; end-to-end import from an allowed source not exercised (network + P2).

## 3. Learning trust chain — poisoning test EXECUTED
Sample carrying a **Groq-shaped secret** (`gsk_` + 28 chars) + a prompt-injection sentence, captured as external knowledge:
| step | result |
|---|---|
| capture | 201 `eligibility: pending`, `sanitization_state: pending`, `verification_level: RAW` |
| promote / admit straight from RAW | refused (acts need verdict bodies; without them 422 — G-02/03) |
| **scan** | **`clean: true`** — the sanitizer has no `gsk_` pattern (gap, see F-R176-09) |
| sanitize `passed=true` (reviewer act) | accepted (`sanitization_state: passed`) because scan was clean |
| evaluate | `verification_level: VALIDATED` |
| **admit** (privacy+tenant policy true) | **`admitted:false` — "not eligible for training; failed: ['sensitive_data_handled', 'not_poisoned']"** — the eligibility gate caught it independently |
| promote | `promoted:false` — "must pass training eligibility before promotion (22 §8)" |
| GOLD listing / `learning/ask` / execute `gold_blocks` | `keys: []` · `found:false` · `gold_blocks` absent/0 · secret string never echoed in any response (G-09b/10b/11b/12b all False) |
Control sample with an `sk-` token: scan → `opaque_provider_token` finding (fingerprint only, no echo); sanitize `passed=true` → **REFUSED**
("machine scan reports findings; passed=true refused"); admit refused; never GOLD.
Cross-tenant: other tenant's execute shows `gold_blocks: 0`, no marker (G-12); non-admin cannot list samples (403).

Verdict: **poisoned or secret-bearing knowledge did not reach GOLD, retrieval, or another tenant** — VERIFIED · RUNTIME. Deny-by-default
holds at two independent layers (sanitizer report → reviewer act refusal; eligibility gate → admit refusal).

**F-R176-09 — sanitizer pattern coverage gap (S3, defence-in-depth).** `core/learning/sanitizer.py` `_VALUE_PATTERNS` lacks Groq
(`gsk_`), Anthropic (`sk-ant-`), Google (`AIza`), Slack `xox[abp]-` beyond `xoxb`, generic `api[_-]?key\s*[:=]`; the repo's own
`check_repo.sh` secret scan already knows `gsk_` (it caught the prompt commit in A0). The same vocabulary is documented as
"mirrors the memory screen" (`core/memory/memory.py`) — so the memory write screen has the same gap. Impact bounded by the
eligibility gate above (which is *why* this is S3 not S2). Classification: **SHOULD FIX BEFORE EXTERNAL CONSUMPTION**.
Proposed **FIX-06** (not executed): add the missing patterns to `_VALUE_PATTERNS` (single source consumed by both screens), extend
`tests/learning/test_sanitizer_r161.py` failing-first with the `gsk_` case; no contract change; blast radius: sanitizer + memory
screen + 1 test file; the `SECRET_LABELS` closed set grows (UI enumerates it — check `ui/admin`).

Prompt injection (`IGNORE ALL PREVIOUS INSTRUCTIONS`) is not detected by any scanner (by design: sanitizer is credential-only);
poisoning defence for injected *instructions* relies on evaluation + eligibility (`not_poisoned` check) — that check refused the
sample here, but its heuristics were not characterised. NOT PROBED (P2): what `not_poisoned` actually keys on.

## 4. Evaluation
`evaluate` act raised `verification_level RAW → VALIDATED` through the existing grader; graders (pairwise/skill/role/counter, R088)
covered by `tests/evaluation` (in the 585). Head-to-head quality claims: none possible without a real model → A11.

## 5. Coverage
P0 learning-poisoning: executed (2 samples, 2 tenants). P1: agent gates (RUNTIME), skills gates (RUNTIME), sanitizer (unit).
NOT PROBED (P2): skills import from allowed source end-to-end; `not_poisoned` heuristic; agent loop with real model this round.
