# R173 §1.5 — §6 seven exercises re-run + §5 denylist blast radius

Recorder: `evidence/r173/tools/run_exercises_e1_e7.py` (HTTP facts only; every line scanned
against every secret-shaped env value + the two session tokens before write).
Measurer: `evidence/r173/tools/denylist_blast_radius.py` (read-only over `git ls-files`).

## Reset note
A sandbox reset landed between the §1.5 ledger row (`4548d48`) and this closure: deps, `/tmp/r173/*`
(tokens, servers) and the UNCOMMITTED harness were lost. Origin/main was intact at `4548d48`;
nothing committed was redone. Harness recreated and committed BEFORE the first run; each
artefact committed before the next step.

## Compositions exercised
| mode | port | env | providers (runtime_started) | bare `/v1/execute` probe |
|---|---|---|---|---|
| hermetic | 8173 | §1.4 29-name unset list + `ADMIN_EMAILS=ops@r173.local AGENT_SOURCE_ROOT=/home/user/webapp PROVIDER_MAX_RETRIES=0` | `["local_echo"]` | (E3 evidence) `succeeded` |
| live | 8174 | same list **minus `GSK_API_KEY`** (platform-injected) | `["genspark_llm"]` | 403 `entitlement_exceeded`, `provider_error_category=quota_exceeded`, 204 ms |

Tokens per composition: admin (`ops@r173.local`, `is_admin`) and non-admin (`user@r173.local`)
via register → console-token verify → login. Agent turns are posted as ADMIN because
`/v1/agent/executions/*/trace` is admin-gated (`apps/admin_agent/http.py::_admit`) — the first
draft posted them as the non-admin user and got trace 404 (tenant-scoped, correct), so the harness
was corrected; that is a harness fix, not a platform finding.

## E1–E7 verdicts (`e1_e7_hermetic_local_echo.jsonl`, `e1_e7_live_genspark_llm.jsonl`)
| # | claim under test | hermetic (local_echo) | live (genspark_llm) |
|---|---|---|---|
| E1 | agent turn, `tools.allowed=[source_list,source_read]` | INERT — 502 `invalid_proposal` @ plan-2 (echo emits no proposal); record 200 `failed`; trace 200 stages `[plan-1, plan-2]`; **0 act stages** | INERT — 502 `propose_failed`: `ReasoningFailed … quota_exceeded/plan_refusal_200`; record 200 `failed`; trace `[plan-1, plan-2]`; 0 act |
| E2 | agent turn, NO tools | INERT (same shape); 0 act | INERT (same shape); 0 act |
| E3 | exercisable → exercise `execute.sync` → unknown id | **PASS** — 4 exercisable; `{capability_id, result:{exercised:true, evidence:{status:succeeded}}}`; unknown ⇒ 404 `validation_error` | **PASS** — `exercised:true`, evidence `status:failed` (honest under plan refusal — exercise ran, upstream refused); unknown ⇒ 404 |
| E4 | console auth boundary | **PASS** — anon and garbage bearer ⇒ byte-identical 401 `unauthenticated`/"Authentication failed."; non-admin ⇒ 403 `unauthorized`; admin system+audit 200 | **PASS** |
| E5 | existence oracle | **PASS** — unknown uuid ⇒ 404 on record/trace/diagnosis; malformed id ⇒ 404 on trace/diagnosis ("Unknown execution id."), 422 on `/v1/executions/<malformed>` (see F-15.3) | **PASS** |
| E6 | unknown tool name up front | **PASS** — 422 `validation_error`, `field=tools.allowed`, `unknown=[shell_exec]`, no execution created | **PASS** |
| E7 | composed source reader denylist | **PASS with F-15.2** — `.env .ENV .e\u200bnv .git/config secrets.pem id_rsa.key ../../etc/passwd` all `SourceReadRefused`; `core/agent/runtime.py` admitted; **also admitted:** `engineering/verification/green_manifest.json`, `core/providers/accounts.py`, `infrastructure/security/password.py` (`reader_patterns=13`) | same |

E1/E2 are INERT, not FAIL: in neither composition can the reasoning model produce a proposal
(hermetic: echo; live: the injected GSK plan refuses inference with HTTP 200 `plan_refusal_200`,
typed `quota_exceeded`, no tokens consumed). The STRUCTURAL claim holds in both: a turn never
produced an act stage without a proposal, and every failed turn left a record + trace that agree
(`failed` / `[plan-1, plan-2]`). The R148 live PASS for E1/E2 (real completion) is **not
reproduced** in R173 — NOT EVALUATED, not regression.

## Findings
- **F-15.2 (E7, §5)** — `apps/composition/runtime.py::_source_reader` builds `SourceReader(root=path)`
  with `DEFAULT_DENIED_PATTERNS` (13). The R172 hardened `DENIED_PATH_PATTERNS` (64) is wired only in
  `apps/agent_dev/surface.py:367`. Normalisation (`is_denied`) is shared, so unicode/case evasions are
  refused under both. Difference is the pattern set only: under the platform agent, the gate file
  `green_manifest.json`, `core/providers/accounts.py`, `infrastructure/security/password.py` are
  readable. Owner decision (R172 C1 kept hardened patterns for the dev surface; runtime never switched).
- **F-15.3 (E5)** — `GET /v1/executions/<malformed>` ⇒ 422 "execution id must be a UUID." while the
  agent readers ⇒ 404. Not an oracle (a shape check reveals nothing about stored ids); consistency nit.
  Agent side pinned by `tests/admin_agent/test_aa2_admin_agent.py::test_unknown_and_malformed_ids_404`.

## §5 denylist blast radius — three forms over 870 tracked files (`../16_denylist_blast_radius/`)
| form | patterns | composed by | tracked denied | what |
|---|---|---|---|---|
| A `DEFAULT_DENIED_PATTERNS` | 13 | runtime (platform agent) | **4** | all via `*credentials*`: `gateway-service/gateway/credentials.py`, migration `0012_credentials.py`, proposal `_credentials.py`, `evidence/credentials_manifest.md` — source/docs by NAME, none a secret |
| B `DENIED_PATH_PATTERNS` | 64 | agent_dev surface only | **18** = A + 14 | +10 `engineering/verification/*` (verifier `check_repo.sh`, both manifests, 7 docs), +3 `*password*` (argon2 hasher, its test, ADR-0005), +1 `*accounts*` (`core/providers/accounts.py`) |
| C `is_denied(path, B)` | 64 + normalisation | the check both readers run | 18 | **0** normalisation-only hits (ASCII tree ⇒ C == B) |

All 18 form-B denials are ordinary source/test/doc files (`.py` 6, `.md` 9, `.json` 2, `.sh` 1) —
zero tracked files are credential material, which is the expected shape of a clean repo. 59 of 64
hardened patterns hit **zero** tracked files; they exist for untracked material (`.ssh`, `.aws`, `id_*`,
key stores, `.env*`). The whole cost of B on this tree is 14 files: under B the dev agent cannot read
or edit the verifier, the gate manifest, the password hasher or the provider accounts module
(recorded in R172 C1 as intentional fail-closed). Under A (what the platform agent has) the cost is 4
files and the gate file is readable.

## Not evaluated in §1.5
Real model completion through the agent (E1/E2 PASS as in R148); Groq keys 5/6 through the agent
path (they succeed on `allam-2-7b` via bare `/v1/execute` — §1.2b — but were not exported into
these compositions; a `GROQ_API_KEY=<key 5|6>` composition is the §1.6 candidate).
