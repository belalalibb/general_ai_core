# QEVION R167-A — §5.0.7 Credentials manifest

No secret value appears in this file or anywhere in the repository. Fingerprint =
first 12 hex of `sha256("qevion-r167a-2026-09-03" + value)`; it identifies a credential
across this round only and cannot be reversed. Probes executed 2026-09-03 from the sandbox
with `urllib` (no platform code involved) [MEASURED].

| Logical id | Platform provider name | Fingerprint | Reachability (direct probe) | Models exposed | Bindable per application? | Spend ceiling |
|------------|------------------------|-------------|-----------------------------|----------------|---------------------------|---------------|
| GROQ_API_KEY | `groq` (`apps/composition/runtime.py` L199) | UNSET in this sandbox session (value not persisted after reset #5; earlier sessions: `400 organization_restricted`, `/v1/models` → `invalid_api_key`, see `evidence/tasks/15_developer_transcript.log` §9) | UNREACHABLE — not available | n/a | NO — process-wide env var, one credential per provider (see `evidence/provider_contract.md` item 2) | 0 |
| GSK_API_KEY | `genspark_llm` (`apps/composition/runtime.py` L200) | `2cd23619a46a` | `GET {OPENAI_BASE_URL}/models` → 200, list of 20+ ids; `POST /chat/completions` (gpt-5-nano, claude-sonnet-4-5) → **HTTP 200 whose assistant content is the string "Free-plan credits can't be used with the Genspark API / LLM proxy…"** — no inference is performed | gpt-5, gpt-5.1, gpt-5.2, gpt-5.4, gpt-5.4-mini, gpt-5.4-nano, … (listing only) | NO — same env-var mechanism | 0 (the endpoint does not bill; it refuses in-band) |
| OPENAI_API_KEY | not consumed by the platform (`grep -rn OPENAI_API_KEY apps/ core/ providers/` → none); sandbox tooling only | `70abed95c19e` (differs from GSK_API_KEY) | same proxy, same "Free-plan credits" in-band refusal | same | n/a | 0 |
| DATABASE_URL / GATEWAY_BASE_URL | durable + gateway hydration paths (`runtime.py` L718-760) | UNSET | n/a | n/a | n/a | n/a |

## §5.0.6 MODE decision

A credential counts as usable only if it completes at least one real inference. Neither
GROQ_API_KEY (absent / restricted org) nor GSK_API_KEY (HTTP 200 carrying a plan refusal
instead of a completion — see `evidence/failure_shapes/genspark_llm_200_plan_refusal.json`)
does so.

**MODE = OFFLINE-ENVELOPE.** [MEASURED]

Consequences per §5.0.7c: §4A, tenant isolation, authz on composition paths, credential
containment, atomicity, idempotency, config isolation, quota/cost paths, robustness, §17 and
the four model-independent categories are executed for real; §4B/§4D are executed via
test-only fault injection and tagged [INJECTED]; §4C is [PARTIAL] with two placeholder
credentials unless the contract makes it NOT EXECUTABLE; benchmarks, live delta and the
model-driven transcript are NOT PROBED; the gate reads "GATE NOT EVALUATED — OFFLINE ENVELOPE".

## §5.0.5 Spend ceiling

Ceiling: USD 0.00 external spend (no billable credential exists). Abort counter for the
round: 0 of 3 allowed environment aborts consumed at Phase 0 (five sandbox resets occurred
in R167-QEVION before this round; none in R167-A yet).

## §5.0.7b injection path

Decided after §4A (see `evidence/provider_contract.md`, item 2): credentials enter only via
process environment variables read at composition time. There is no per-application or
per-tenant credential binding surface (no request field, no admin route, no storage record).
Ledger outcome for §4C: **NOT EXECUTABLE — CONTRACT ABSENT** (outcome 3, architecture
limitation, handed to R168).
