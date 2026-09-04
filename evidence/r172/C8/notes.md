# C8 — live transport proof: REST-only GitHub transport + env-gated live suite (IMPL-025, budget 8/8)

## What changed
- `apps/agent_dev/github_transport.py` NEW (+345): `GitHubRestTransport` implements the R169
  `GitTransportPort` over the GitHub Git Data / Pulls REST API with httpx — **no subprocess, no
  shell, no hooks, no local `.git`**. `commit()` stages a content-addressed in-memory snapshot of
  the jailed paths (no token, no network); `push()` uploads blobs → tree → commit and creates/moves
  `refs/heads/<branch>` (non-force); `open_pull_request()` posts to `/pulls` and returns `html_url`.
  Token rides only the `Authorization` header inside the call; never stored, never in results/repr.
  `parse_github_remote` admits only `https://github.com/{owner}/{repo}[.git][/]`.
- Error mapping: 422 whose message names a pull-request/protected rule → `ProtectedBranchRejected`
  (GitToolset → `remote_rejected_protected_branch` + `suggested_mode=pull_request`); other 4xx →
  `RemoteRejected`; network / malformed / missing ref → `TransportError`; nothing staged →
  `NothingToCommit`.
- `tests/agent_dev/test_github_transport_r172.py` NEW — 25 hermetic tests on `httpx.MockTransport`.
- `tests_live/r172/test_live_transport.py` NEW — 13 live tests, env-gated, OUTSIDE `testpaths`
  and every manifest slice (verifier never collects it; skip budget untouched).
- `evidence/r172/live_transport.txt` — one complete live run (model/latency/status/tokens/codes only).

## Why a REST transport (owner-facing decision)
Before C8 the port had only a test fake ("live git transport NOT EVALUATED" since R169). A `git`
CLI transport would violate the R172 no-subprocess rule and would need a checkout the sandbox
does not have per binding. The Git Data API gives the same four primitives (fetch head, commit,
push branch, open PR) as pure HTTPS with typed error bodies — which is exactly what the refusal
codes need. Trade-off recorded: no local history/merge; `commit()` is a staging snapshot, so
`status.head` is the snapshot id, not a git SHA on the remote until `push()` succeeds.

## Live results (2026-09-04)
- **GitHub** (throwaway repo, main protected PR-only): fetch/status OK (380 ms); PULL_REQUEST publish
  → real PR `https://github.com/belalalibb/r172-live-transport-throwaway-48b263/pull/2` (3.4 s);
  DIRECT_PUSH not allowed → `publish_mode_not_allowed` + `suggested_mode=pull_request`, remote head
  unchanged; DIRECT_PUSH allowed but branch protected → GitHub 422 "Changes must be made through a
  pull request." → `remote_rejected_protected_branch` + `suggested_mode=pull_request`, remote head
  unchanged; untrusted binding → `remote_not_trusted` on fetch AND publish with `secrets.resolve`
  called **0** times; credential absent from trace / repr / binding dumps.
- **Groq**: all four supplied keys answer HTTP 400 `organization_restricted` (account-level block)
  on `/models` and `/chat/completions`; adapter types it `invalid_credential` / `retryable=false`
  (route-indicting). **No real completion could be obtained with these keys — recorded honestly,
  not over-claimed.** Bogus key → 401 `invalid_api_key` → `invalid_credential`; `timeout_ms=1` →
  `timeout` / retryable; 429 NOT observed in a 6-call burst (restriction short-circuits first).
  Adapter performs no retry/backoff itself — retries live in `ExecutionService` (finding).

## Findings
- GitHub Git Data API protected-branch signal is HTTP 422 with message
  "Changes must be made through a pull request." (not 403) — mapped by message markers.
- `GroqAdapter`'s pooled client is bound to the loop that created it; live harness must run
  `generate()`+`aclose()` in ONE `asyncio.run` (first live attempt: "Event loop is closed" — test-side).
- Groq keys supplied for R172 are organization-restricted; a real completion needs an unblocked key.

## Not done / open
- `GitHubRestTransport` is NOT wired into `apps/composition/runtime.py` (no production composition
  builds a `GitToolset` yet — C2 store / C3 trust registry / C7 dev seam likewise). Owner decision.
- Only github.com remotes; GitHub Enterprise base URLs would need `base_url=` plumbing.
- No `delete branch` / `close PR` cleanup primitive — throwaway repo keeps PR #1/#2 as evidence.

## Verification
- fail-first: `evidence/r172/C8/fail_first.txt` (ModuleNotFoundError at 6d09e56).
- after-fix: `evidence/r172/C8/after_fix.txt`; live: `evidence/r172/live_transport.txt`.
