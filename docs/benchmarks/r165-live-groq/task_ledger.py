#!/usr/bin/env python3
"""Build the R165 live engineering brief (ledger repo) as an /v1/execute body.

usage: python3 task_ledger.py <authorization_id> [model_key] > task.json
"""

import json
import sys

ticket = sys.argv[1]
model = sys.argv[2] if len(sys.argv) > 2 else "openai/gpt-oss-120b"
ask = (
    "You are working in a Python repo (package `ledger`, tests under `tests/`). "
    "Your Admin-issued authorization_id for privileged tools (ws_write, ws_run, "
    f"git_commit, git_push) is: {ticket} — pass it verbatim as the "
    "`authorization_id` argument.\n"
    "TASK:\n"
    "(1) Read ledger/money.py and find the bug in parse_money: '12.5 USD' must parse "
    "to 1250 cents but a single fractional digit is currently mishandled — fix it.\n"
    "(2) Add a function `format_totals(ledger) -> str` to ledger/report.py that returns "
    "one line per currency 'CUR: <amount>' (use Money.__str__), sorted by currency code.\n"
    "(3) Add tests for both: create tests/test_report.py and extend tests/test_money.py.\n"
    "(4) Run the test suite with ws_run (executable python3, args ['-m','pytest','-q']) "
    "and make sure it passes; if it fails, read the output, fix, and re-run.\n"
    "(5) Commit all changes with git_commit message 'fix(money): parse single fractional "
    "digit; feat(report): format_totals' and push with git_push to branch main.\n"
    "(6) Finalize with an answer summarizing what changed, the test result line, and the "
    "commit hash. Cite the succeeded steps as evidence."
)
print(
    json.dumps(
        {
            "ask": ask,
            "execution_policy": {"strategy": "agent", "max_steps": 28, "deadline_ms": 1800000},
            # Groq free tier: per-model TPM (8k) and TPD (200k) caps. When the
            # explicit model answers a Retry-After the platform will not park
            # on, the run fails over to the next eligible Groq model (each
            # has its own quota) instead of dying — 11 §8 max_escalation.
            "model_policy": {
                "type": "explicit_model",
                "model_id": model,
                "allow_fallback": True,
                "fallback_scope": "max_escalation",
            },
            "tools": {
                "allowed": [
                    "ws_read",
                    "ws_list",
                    "ws_search",
                    "ws_write",
                    "ws_run",
                    "git_status",
                    "git_diff",
                    "git_commit",
                    "git_push",
                    "git_log",
                ]
            },
        }
    )
)
