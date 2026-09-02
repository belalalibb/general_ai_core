# R165 — live Groq proof: the agent edits, tests, commits and pushes real code

**Result: PASS.** One `POST /v1/execute` against a live Groq provider (free
tier) drove a 32-stage agent run that fixed a planted bug, added a
function, wrote tests, ran `pytest` (7 passed), committed and pushed to a
bare remote — all through the platform's ticketed engineering tools, with
every mutating act audited. Wall clock: 617 s (rate-limit dominated).

## Reproduce

```sh
bash docs/benchmarks/r165-live-groq/mk_target.sh              # fresh /tmp/r165/ws + bare remote
GROQ_API_KEY=... ADMIN_EMAILS=ops@example.com \
  AGENT_WORKSPACE_ROOT=/tmp/r165/ws AGENT_WORKSPACE_COMMANDS=python3,pytest \
  AGENT_MAX_STEPS=32 AGENT_DEADLINE_MS=1800000 PROVIDER_MAX_RETRIES=4 \
  AGENT_REASONING_MAX_TOKENS=3072 python3 -m apps.main
bash docs/benchmarks/r165-live-groq/identity.sh               # ops login -> /tmp/r165/ops.tok
# grant workspace.write/exec + git.write, issue a 14-use ticket (see chat log), then:
python3 docs/benchmarks/r165-live-groq/task_ledger.py <ticket-id> > task.json
curl -X POST :8000/v1/execute -H "Authorization: Bearer $(cat /tmp/r165/ops.tok)" -d @task.json
```

## Evidence (`evidence/`)

| file | shows |
|---|---|
| `execute_response.json` | HTTP 200, `final.answer` + evidence step indexes |
| `trace.json` | 32 stages, all `succeeded`: 6 reads/lists → 5 `ws_write` → `ws_run` → `git_commit` → `git_push` → verify → final |
| `agent_commit.patch` | the model's commit `181ebb1`: correct `frac.ljust(2, "0")` fix, `format_totals`, 2 test files |
| `pytest_after.txt` | `7 passed` in the target repo |
| `remote_refs.txt` | `refs/heads/main` on the bare remote == the agent's commit |
| `audit_events.json` | 14 `tool_call` (each with `gate_decision`), 9 `approval_decision` (ticket issue + consumption); ticket ended with 6/14 uses left |
| `provider_errors_histogram.txt` | 62×429 (TPM) survived via Retry-After parking; 15×400 `param=response_format` failed over; 2 constrained-decoding failures retried |

## What the live run forced us to fix (all on `main`, each with tests)

1. **Explicit model + widening fallback scope now reaches other models**
   (`core/routing/router.py`). Groq caps each model separately; an
   exhausted `gpt-oss-120b` must hand off to `gpt-oss-20b` / `qwen3.8-27b`.
2. **400 `param=response_format` is `unsupported_capability`, not
   `bad_request`** (`providers/real/groq/adapter.py`) — `allam-2-7b` has no
   constrained decoding; the *candidate* is wrong, not the request.
3. **Proposal schema is discriminated on `action`**
   (`core/execution/agent.py`) — the flat schema let the decoder emit a
   `tool_call` with no `arguments`; two in a row stopped the run.
4. **Fixture bug was fake** (`mk_target.sh`) — `parse_money` was already
   correct, so the brief pushed the model into *breaking* working code.
   The planted bug is now real (`int(frac or 0)` → `12.5` = 1205 cents).

## Caveats

- Free tier: ~1 model step / 40 s. Not a latency benchmark.
- Every proposal was still validated by the strict R095 parser; the schema
  only shapes decoding, it does not relax acceptance.
