# R173 — CLOSURE (§1.7)

Round span: `3c0f357` (R172 closure) .. this HEAD. Ledger: `evidence/r173_state_ledger.md`
(one row per item; §1.7 row appended twice — the first closure attempt `e169011..b4a698b` was
lost to a sandbox reset that re-cloned the repo at `211c442`, so closure was redone from there).

## Verifier (hermetic, fixed HEAD `2b54b87`)
`evidence/r173/19_closure/check_repo_final.txt` — `RESULT: PASS`, exit 0.
- pytest: **passed=3127 failed=0 errors=0 skipped=64**; floor raised 3126 → **3127** (met exactly);
  +1 = the F-15.2 pin `tests/composition/test_agent_source_seam.py::test_runtime_reader_composes_hardened_denylist`.
- unset list: 32 names = §1.4 derived list + `GROQ_API_KEY_7 GROQ_API_KEY_8 GW_GROQ_API_KEY`;
  still-set count proven **0** inside the same env before check_repo ran.
- budget: `round_a=4/5; round_b=4/5; round_r169=5/6; round_r172=8/8; round_r173=1/1`.
- mypy --strict clean; ruff clean; import-linter kept; secret scan 5/5 declared; no .env tracked;
  not_evaluated=2 (unchanged from baseline).
- venv had to be recreated (`pip install -e ".[dev]"`) after the reset; no code change involved.

## Production change budget — round_r173
`change_budget.round_r173`: ceiling 1, used 1 = **F-15.2** `apps/composition/runtime.py` +6/-1
(`_source_reader` composes `DENIED_PATH_PATTERNS` (64) instead of the 13-pattern primitive default;
before/after in `18_f152_fix/`). `git diff --stat 3c0f357..HEAD -- core/ apps/ infrastructure/`
= exactly that one file. `check_repo.sh` round tuple extended with `"round_r173"`.

## Frozen trees
`git diff --stat 3c0f357..HEAD -- ui/ apps/admin_agent/ core/tools/gate.py` → **0 lines**.
UI byte sizes unchanged from the R172 closure:
```
79351 ui/admin/app.js   32385 ui/admin/index.html   16392 ui/admin/styles.css
28395 ui/app/app.js     11686 ui/app/index.html     19604 ui/app/styles.css
```
Files touched this round (`git diff --name-only 3c0f357..HEAD | wc -l`): 38.

## Secret sweep over `git log -p 3c0f357..HEAD`
- strict `gsk_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}` → **0**
- loose `gsk_|ghp_` → **35**, all self-referential (breakdown sums to 35):
  - 14 recorder JSONL `"first4": "gsk_"` (tests_live/r173 recorder writes prefix only)
  - 9 credential/probe table `first4` columns (`| gsk_ |`, `| ghp_ |`)
  - 5 scanner/helper regex character classes (`{20,}` / `{36}`)
  - 7 prose / canary labels (pre-commit canary transcript, OPERATIONS §14, docstrings)
- no real key value appears in any commit of this round. `/tmp` holds no r173 artefacts
  (probe-key file purged at §1.6 close; sweep scratch removed).
- Exposure note (§1.2 credential_table): the classic PAT used for pushes has scope `repo`
  (all repos of the account) — recorded, not remediated in this round.

## Findings disposition
- **F-15.2** — FIXED (approved one-line change, pinned, verifier green). Blast radius moved
  A(4) → B(18) of 870 tracked files, zero credential material either way (`16_denylist_blast_radius/`).
- **F-15.3** — **accepted nit**: `GET /v1/executions/<malformed>` → 422 "execution id must be a UUID."
  while agent trace/diagnosis readers → 404. Not an oracle (shape check reveals nothing about
  stored ids); consistency only. No budget spent; carried as a note, not a defect.
- **Groq ladder (§1.6)** — EXHAUSTED: keys 5→8 all `invalid_credential / organization_restricted`
  (upstream HTTP 400) through the agent path; nothing composed as `GROQ_API_KEY`.

## Not evaluated (unchanged count = 2)
- browser live-suite (no browser in sandbox) — missing dependency
- real two-account provider round-trip — credential unavailable
- **E1/E2 real completion**: NOT EVALUATED in R173 — no proposal-capable provider (all 8 Groq keys
  organization_restricted; §1.5 INERT structural claim is the only E1/E2 evidence). R148 live E1/E2
  PASS is NOT carried forward (owner decision 4).

## Final state
HEAD == origin/main asserted by the closure push (git ls-remote line appended below).
git ls-remote origin refs/heads/main -> 2d95833a1a8bc4e83e6161cdecbd25a34b00156e	refs/heads/main (local HEAD before this line: 2d95833a1a8bc4e83e6161cdecbd25a34b00156e)
