# R173 state ledger (checkpoint discipline: one row appended BEFORE each item)

| item | intended change | HEAD at start |
|---|---|---|
| §1.1 | host facts (Linux sandbox — directive premise refuted) + tracked pre-commit scanner + canary + OPERATIONS §14 | 3c0f357 |
| §1.2 | credential presence table (5 directive + 5 platform names, count 10), token scope, build_runtime_profile signature + derived hermetic unset list | e875bfc |
| §1.2b | tests_live/r173 recorder (asserts against ALL present secret names) + probe keys 5,6 via execute path | 3b69cfd |
| §1.3 | probe keys 1,4 via same /v1/execute harness (expected negative posture) | b08a06d |
| §1.4 | hermetic baseline verifier (derived unset list incl. GSK_API_KEY) + skips + guards + routes snapshot | 137d402 |
| §1.5 | §6 seven exercises re-run + §5 denylist blast-radius (three forms) — DONE: E3–E7 PASS ×2 compositions, E1/E2 INERT (no proposal-capable provider), F-15.2 runtime reader = 13-pattern set, F-15.3 422/404 nit; blast radius A=4 B=18 C=18 of 870 | 5e43f2f |
| §1.6 | APPROVED — Groq ladder key5→8 in order, first HTTP 200 THROUGH THE AGENT PATH wins, winner composed as GROQ_API_KEY, E1/E2 real completion (or NOT EVALUATED + 4 typed errors); F-15.2 APPROVED one-line fix `runtime.py::_source_reader` → hardened set with before/after; F-15.3 accepted nit → CLOSURE.md; R148 live E1/E2 stays NOT EVALUATED. Standing authority granted from here (record decisions in rows). | 3e935cb |
| §1.7 | CLOSURE — round_r173 budget entry (ceiling 1, used 1 = F-15.2) + check_repo round tuple; pytest floor 3126→3127; hermetic verifier at fixed HEAD; evidence/r173/CLOSURE.md (secret sweep, frozen trees, F-15.3 accepted nit, E1/E2 NOT EVALUATED); push + ls-remote. NOTE: first closure attempt (e169011..b4a698b) was lost to a sandbox reset that re-cloned at 211c442 — redone here. | 211c442 |
