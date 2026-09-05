# R173 state ledger (checkpoint discipline: one row appended BEFORE each item)

| item | intended change | HEAD at start |
|---|---|---|
| §1.1 | host facts (Linux sandbox — directive premise refuted) + tracked pre-commit scanner + canary + OPERATIONS §14 | 3c0f357 |
| §1.2 | credential presence table (5 directive + 5 platform names, count 10), token scope, build_runtime_profile signature + derived hermetic unset list | e875bfc |
| §1.2b | tests_live/r173 recorder (asserts against ALL present secret names) + probe keys 5,6 via execute path | 3b69cfd |
| §1.3 | probe keys 1,4 via same /v1/execute harness (expected negative posture) | b08a06d |
| §1.4 | hermetic baseline verifier (derived unset list incl. GSK_API_KEY) + skips + guards + routes snapshot | 137d402 |
| §1.5 | §6 seven exercises re-run + §5 denylist blast-radius (three forms) | 5e43f2f |
