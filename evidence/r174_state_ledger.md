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
