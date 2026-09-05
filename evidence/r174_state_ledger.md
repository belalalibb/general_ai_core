# R174 state ledger (checkpoint discipline: one row appended BEFORE each item; recoverable from this file alone)

Question: are external providers wired correctly into the core? Proof: AssemblyAI LLM gateway, real key,
through the WHOLE chain (gateway-service provider → canonical contract → RemoteGatewayAdapter → core port).
Hard condition: zero AssemblyAI-specific lines in core/. Deliberate check: two providers, same model name, no collision.

| item | intended change | HEAD at start |
|---|---|---|
| §0 | sandbox reset #4 recovered (venv rebuilt, creds restored, HEAD==origin/main c94217c); this ledger created | c94217c |
| §1 | READ: AssemblyAI LLM gateway reference (web) + repo external-provider reference (contract, runbook, example, template, existing real provider) → reconciliation note in evidence/r174/01_read/ | c94217c |
