# R160 — Platform evolution: agent intelligence, admin parity, UI execution

**Status:** IMPLEMENTED and VERIFIED on branch `feature/model-provider-skill-orchestration` (PR #12).
**Scope rule:** this document describes what the code DOES (evidence: file, test, or live probe).
Anything not backed by evidence is listed in §12 as *not implemented* — never implied.

Gate at the time of writing: `pytest` 2565 passed / 56 skipped (7 live-key tests deselected
in CI-less sandboxes), `ruff check` clean, `mypy --strict core/` clean, import-linter 12/12.

---

## 1. Shared agent runtime (`core/agent`)

One tool-using agent runtime serves BOTH the platform (`POST /v1/execute` with
`strategy: "agent"`) and the admin console's agent (`POST /v1/agent/converse`).

| Piece | Location | Evidence |
|---|---|---|
| Runtime loop, step budget, tool dispatch | `core/agent/runtime.py` | `tests/agent/test_runtime.py` |
| Authority chain ToolRegistry → CapabilityFirewall → DeviceRegistry | `core/agent/*`, composed once in `apps/composition/agent.py::build_agent` | `tests/composition/test_agent_composition_r160.py` |
| Offered catalog | `GET /v1/agent-tools` → `{strategy, max_steps, tools:[…describe()]}` | `tests/agent/test_execute_agent_http.py`; live: 3 source tools with `AGENT_SOURCE_ROOT` |
| Progressive disclosure | `AgentSurface.select(policy, skills)` — empty allow-list AND no skills ⇒ **no tools** (deny-by-default) | `apps/api/agent.py:77-…` |
| Source tools jail | `source_list / source_read / source_search` exist ONLY when `AGENT_SOURCE_ROOT` is a directory | `tests/composition/test_agent_source_seam.py`, live probe |

Admin parity: the console's "Platform agent catalog" panel reads the SAME
`GET /v1/agent-tools` — byte-identical to a tenant's view
(`TestAdminParityAgentCatalog`).

## 2. Verify / trace (admin agent)

`verify_result` and the trace read are the admin agent's evidence-cited reads;
claims without an evidence citation render as refusals in the UI
(`TestUIHonestyChecklist`). See `apps/admin_agent/` and
`docs/architecture/ADMIN_AGENT_UI_PRINCIPLES.md`.

## 3. Skills and tool intelligence

- `GET /v1/skills` — selectable skills with `requires_tools`.
- Skill tools are resolved through the same ToolRegistry; a skill never
  widens the firewall (a skill *names* tools, the firewall *admits* them).
- **External skill acquisition** (`apps/api/skills_import.py`, composed in
  `apps/composition/admin_console.py`): `POST /v1/admin/skills/import` →
  `scan → validate → review → approve → activate`, each a separate POST
  (`/v1/admin/skills/imports/{id}/{step}`), allowed sources enumerated by
  `GET /v1/admin/skills/imports` (`allowed_sources`). Provenance
  (`source_url`, `checksum`, `reviewed_by`, `local_version`) is carried on
  the import record. Pins: `TestExternalSkillAcquisition`.

## 4. Learning lifecycle over HTTP (22 §8)

Prefix `/v1/admin/learning` (admin-gated; routes absent when the lifecycle
service is not composed):

| Route | Body | Meaning |
|---|---|---|
| `GET /samples` | — | `{samples:[{id, source_execution_id, tenant_id, eligibility, sanitization_state, verification_level, dataset_id}]}` |
| `POST /samples` | `{knowledge_key, knowledge_value:obj, source_execution_id?}` | capture (enters PENDING) |
| `POST /samples/{id}/evaluate` | `{output:obj}` | grader output recorded |
| `POST /samples/{id}/sanitize` | `{passed:bool}` | explicit verdict |
| `POST /samples/{id}/admit` | `{privacy_policy_allows, tenant_user_policy_allows, sensitive_data_handled}` | three explicit booleans |
| `POST /samples/{id}/promote` | `{offline_eval_pass, regression_pass, security_eval_pass}` | three explicit booleans |
| `POST /learned` | `{keys:[]}` | GOLD knowledge read |
| `POST /ask` | `{key}` | one learned key |
| `POST /capability-retest` | `{probes:[1..200], baseline?}` | `{snapshot:{probes,found,missing,score,taken_at}, delta?:{probes,before,after,gained,lost,still_missing}}` |
| `GET /changes-since-review` / `POST /mark-reviewed` | — | observability |

**No verdict has a default.** The UI sends exactly these shapes
(`test_learning_verdicts_have_no_defaults`); the real lifecycle is driven
end-to-end over the composed runtime in
`test_learning_surface_drives_the_real_lifecycle`.

Contract enums rendered by the UI: `LearningEligibility`
(`eligible|ineligible|pending`), `SanitizationState`
(`pending|passed|failed`), `VerificationLevel`
(`RAW|EVALUATED|VALIDATED|VERIFIED|GOLD` — UPPERCASE; a lowercase alias
rendered a loud `UNKNOWN: RAW` badge live and was fixed in R160).

## 5. Provider onboarding (canonical gateway only)

`POST /v1/admin/providers/onboard` — body carries **references only**
(`credential_ref`, `route_token_ref`), never a secret value (20 §5;
`test_no_raw_secret_field_in_onboarding_form`). `discover: true` runs the
gateway `/v1/describe` auto-discovery. The route exists ONLY when
`GATEWAY_BASE_URL` (+ `GATEWAY_SECRET`) is configured — absent gateway ⇒
absent route (20 §4); the UI renders "route absent" honestly (verified live).

## 6. Hybrid identity mode (the R160 admin-reachability fix)

Before R160 the in-memory profile passed a fixed demo principal to
`create_app`, so EVERY `create_app`-owned `/v1/admin/*` route answered
403 to everyone (including `ADMIN_EMAILS` accounts) and `/v1/auth/*` was
not mounted — only the console's own routes honored sessions. RUN.md's
"ADMIN_EMAILS grants the admin surface" was true only on the durable profile.

`create_app(principal=…, auth=…)` now has three modes (`apps/api/app.py`):

| principal | auth | Behaviour |
|---|---|---|
| set | None | fixed principal (hermetic tests) |
| None | set | strict — every call authenticates (durable profile) |
| set | set | **HYBRID** — Bearer ⇒ real session (admin iff `email ∈ ADMIN_EMAILS`); no token ⇒ fixed principal (never admin); **bad token ⇒ 401** (a bad credential is a refusal, not anonymity) |

Neither ⇒ `ValueError` (loud, never a silent default). The auth router is
mounted whenever `auth` is given; in hybrid mode
`GET /v1/auth/session` without a token answers
`200 {user_id, tenant_id, email:null, is_admin:false, mode:"demo"}` so both
UIs PROBE the profile instead of assuming it. Pins:
`tests/api/test_aa1_api_seams.py::test_hybrid_identity_mode`,
`tests/composition/test_ui_app_pd2.py`, anonymous-401 console pins unchanged.

## 7. Read-models newly served by the runtime

- `GET /v1/admin/usage` — `AdminSurface.executions=store` (typed
  `ExecutionStorePort | None`; both in-memory and durable stores satisfy it).
- `GET /v1/admin/system` — `{profile: "in-memory"|"durable",
  identity_mode: "hybrid"|"auth", provider_keys:[…],
  admin_emails_configured:n, scope:"process"}` — process-local facts only
  (41 §49: no fleet claims).

## 8. Admin console surfaces (`ui/admin/`)

New rail items → sections → loaders (structural pin
`test_every_rail_surface_has_a_section_and_a_loader`):

- **Learning** — learned keys / ask; capture form; capability re-test with
  optional baseline delta; samples table with Evaluate / Sanitize ✓ / Sanitize ✗ /
  Admit / Promote (each an explicit confirm per verdict); changes-since-review;
  mark-reviewed.
- **Skills acquisition** — allowed sources; import form; imports table with the
  single next lifecycle step per row; selectable skills.
- **Provider onboarding** — refs-only form; providers table; honest "route absent"
  when the gateway is not composed.

Every `api("/v1/…")` path the console names is served by the composed default
profile — verified by a segment-wildcard matcher against `app.openapi()`
(`test_every_api_path_the_console_calls_is_served`; the one recorded exception
is the gateway-gated onboard route). Writes are EXACTLY the enumerated
sanctioned POST set (AA-3 four + R160 eight) — `test_write_paths_are_exactly_the_sanctioned_posts`.
Errors render the unified envelope verbatim (`errorText` → `code: message`).

## 9. Unified entrypoint

`python3 -m apps.cli {serve | check | test | routes | describe}`
(`apps/cli.py`, `tests/composition/test_cli_entrypoint.py`). `routes` and
`describe` compose the env-selected profile and print facts — no server needed.

## 10. Live verification record (Playwright, real server)

`ADMIN_EMAILS=admin@x.test AGENT_SOURCE_ROOT=$PWD python3 -m apps.main`; register →
verify (token from server console) → login in the `/admin/` form:

- Learning: capture → row `pending / pending / RAW`; Sanitize ✓ → `passed`;
  re-test `score 0 — found 0/2 · missing: …` (honest: nothing promoted).
- Skills: allowed sources rendered; unavailable note hidden; 0 selectable skills.
- Onboarding: providers `genspark_llm active`; POST → 404 → "Provider onboarding
  not composed in this profile (route absent)."
- System: `{profile:"in-memory", identity_mode:"hybrid", provider_keys:["genspark_llm"], admin_emails_configured:1, scope:"process"}`.
- Platform agent catalog: 3 tools. Only console error: the expected 404 above.

## 11. Scalability inventory (S1–S5) — unchanged posture

Process-local mutable state is limited to the injectable seams recorded in
`apps/api/app.py` (idempotency index, webhook subscriptions) plus the injected
stores. No distributed binding is claimed to exist.

## 12. Deliberately NOT implemented / supported-but-untestable here

- Real email delivery (MVP Phase 2 forbids it; token prints to the console).
- Gateway provider onboarding end-to-end (needs `GATEWAY_BASE_URL`; the route
  and its UI are present, the live path is *supported-but-untestable* in a
  sandbox without a gateway).
- Coding benchmark W2/W3 remain open (W1 closed).
- Distributed idempotency / subscription bindings (seams only).
- `/v1/admin/learning/dashboard` remains the structural placeholder it always
  was; the real lifecycle lives under `/v1/admin/learning/*`.
- Live provider usage positivity: the Genspark gateway reports all-zero usage for
  some models — the live test pins usage SHAPE, not positivity (recorded fact).
