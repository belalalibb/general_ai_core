# R174 state ledger (checkpoint discipline: one row appended BEFORE each item; recoverable from this file alone)

Question: are external providers wired correctly into the core? Proof: AssemblyAI LLM gateway, real key,
through the WHOLE chain (gateway-service provider → canonical contract → RemoteGatewayAdapter → core port).
Hard condition: zero AssemblyAI-specific lines in core/. Deliberate check: two providers, same model name, no collision.

| item | intended change | HEAD at start |
|---|---|---|
| §0 | sandbox reset #4 recovered (venv rebuilt, creds restored, HEAD==origin/main c94217c); this ledger created | c94217c |
| §1 | READ: AssemblyAI LLM gateway reference (web) + repo external-provider reference (contract, runbook, example, template, existing real provider) → reconciliation note in evidence/r174/01_read/ | c94217c |
| §2 | Direct upstream probe (key form raw vs Bearer, error body shape, cheapest model) — 3 calls max, key only in env var, evidence with key redacted → evidence/r174/02_upstream_probe/ | 5830ed0 |
| §3 | gateway-service/providers/assemblyai/ (definition, adapter, _upstream, __init__) copied from groq's shape; hermetic tests gateway-service/tests/providers/test_assemblyai.py; ONE registration line in gateway-service/app.py (same line Groq has — F-1); zero lines in core/ apps/ providers/real/ | 732624c |
| §3′ | sandbox reset #5 wiped the untracked §3 files (ledger row survived, work did not) — rebuilt from groq's shape + §2 evidence, 57 hermetic tests, gateway suite 179/179, pushed as b131345. Lesson applied: commit+push every file the moment it exists | 3d1ede4 |
| §4 | Live E2E through the GATEWAY process only (uvicorn :8800, GW_ASSEMBLYAI_API_KEY in env, route_map token→assemblyai): one success on qwen3.5-4b-32k-fast, one unknown-model → model_unavailable; ≤3 paid calls; request/response captured key-redacted → evidence/r174/04_gateway_live/. Then F-2/F-3 probing of the platform→gateway link | b131345 |
| §4′ | sandbox reset #6 wiped local 59077a0 + gateway process + key env; commit restored byte-identical from the uploaded git bundle (fast-forward on 9c689e7), pushed. Lesson held: the bundle upload was the only thing that saved §4 | 9c689e7 |
| §5 | PLATFORM→GATEWAY link (the last link). (a) F-3 live: build the REAL runtime profile (apps.composition) with an onboarded gateway provider using `route_token_ref` and show whether the route token can resolve at all (predicted SecretNotFound); (b) F-2 live: onboard a `user_key` gateway definition through the real composition path (predicted ValueError); (c) if (a) has a legitimate seam, drive ONE paid call platform→gateway→AssemblyAI via RemoteGatewayAdapter → core port, envelope built by the platform; (d) collision check: groq + assemblyai both declaring the same model name, route by provider not by model name. Evidence → evidence/r174/05_platform_link/. Key must be re-supplied (lost in reset #6) for (c) only | 59077a0 |
