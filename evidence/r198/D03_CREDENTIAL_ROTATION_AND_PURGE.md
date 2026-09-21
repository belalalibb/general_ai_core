# D-03 — credential rotation + history purge: measured state and operator evidence slot (R198-D)

**Ruling (verbatim):** "credential rotation + history purge required before public deployment; never claim completion
without evidence." Operator D4 (R198): history-purge path; **engineering performs no rewrite unless the required
operator-controlled procedure/evidence is available**; rewritten SHAs invalidate prior commit references (acknowledged).
Operator D5: legacy branches carrying the leaked blobs are removed only through that procedure, after the historical
record is preserved; no publicly reachable ref to the leaked commits may remain afterwards.

**Status at R198 close: OPERATOR-OWNED-OPEN.** Nothing below is claimed as done. "Production Ready" is not claimed.

## 1. Measured state (read-only, 2026-09-21, `main fbdd1f0b`; secrets masked)

| # | fact | how measured |
|---|---|---|
| 1 | Working tree carries **no** credential literal (`ghp_`, `gsk_`, `sk-`, `AKIA` patterns) | `grep -rI` over the tree excluding `.git/.venv`; gate secret scan clean (5/5 declared exceptions) |
| 2 | History carries the R177 canonical-prompt leak: commit **`521d8850`** added `GITHUB_TOKEN=ghp_RD…`, `GROQ_API_KEY=gsk_LM…`, `GW_ASSEMBLYAI_API_KEY=512fc6…` to `docs/ai_orchestration_pack/QEVION_FINAL_CLOSURE_EXAMINATION_PROMPT.md`; commit **`28989b04`** (2026-09-09, "r177(B-D2/DEC-02): redact the three exposed credential literals … rotation") redacted the **tree only** | `git log --all -p \| grep -c 'ghp_[A-Za-z0-9]{30,}'` = 2 (the add and the removal); `git log --all -S ghp_` |
| 3 | GitHub secret-scanning **alert #1 — Groq API Key — state `open`, `publicly_leaked: true`, validity `unknown`**, created 2026-09-07 | `GET /repos/…/secret-scanning/alerts?state=open` |
| 4 | Secret-scanning **alert #2 — GitHub PAT — `resolved` with resolution `used_in_tests`** (2026-09-07). This is a *dismissal*, not a revocation proof | `…/secret-scanning/alerts?state=resolved` |
| 5 | Repository visibility: **PUBLIC** | `GET /repos/belalalibb/general_ai_core` → `private: false` |
| 6 | The five legacy branches (`feature/platform-capability-assessment`, `genspark_ai_developer`, `r178_decisions_verified_units`, `r178_p01_subject_verified_units`, `r178_verified_units`) all descend from history containing `521d8850`; all are diverged from `main` (+1/−1061, +4/−627, +8..16/−461) | `GET /compare/main...<branch>`; `git merge-base` |
| 7 | The token used by the engineering session (`ghp_KgC00y…`) is a **different** token from the leaked one (`ghp_RDofZG…`). This is **not** evidence that the leaked token was revoked | prefix comparison only; never stored |
| 8 | Other historical secret-pattern hits (23) are test fixtures / manifest pattern strings / a `.pytest_cache` blob — not live credentials; listed for completeness, not claimed as clean without operator review | `git log --all -p \| grep -E 'gsk_…\|sk-…\|AKIA…'` file list |

## 2. Operator evidence checklist (fill in; each line needs an artefact path or a verifiable API state)

| # | required evidence | how to prove | artefact / state | done |
|---|---|---|---|---|
| E1 | Groq key `gsk_LM…` **revoked** at the provider | Groq console screenshot/export **or** alert #1 → `validity: inactive` / resolved as `revoked` | | ☐ |
| E2 | GitHub PAT `ghp_RD…` **revoked** | GitHub → Settings → Developer settings → token list (absent) **or** alert #2 re-resolved as `revoked` (not `used_in_tests`) | | ☐ |
| E3 | AssemblyAI key `512fc6…` **revoked** | provider console proof | | ☐ |
| E4 | Any credential ever pasted into a chat/prompt that reached the repository is rotated (the engineering session PAT included, at the operator's discretion) | token list / rotation note | | ☐ |
| E5 | **Historical record preserved** before rewrite: `git bundle create qevion_pre_purge_<date>.bundle --all` stored off-repository (private), plus the ledger/pointer SHA map | bundle path + sha256 | | ☐ |
| E6 | **History purge executed** (operator-controlled): `git filter-repo --replace-text <expressions>` (or `--path` rewrite of the prompt file's history) on a fresh mirror clone, covering `main` **and** the five legacy branches (or their deletion first — D5), then `git push --force --mirror`, followed by GitHub support request to purge cached views / run GC | filter-repo report; `git log --all -S ghp_ \| wc -l` = 0 on the mirror; support ticket id | | ☐ |
| E7 | **No publicly reachable ref to the leaked commits**: legacy branches deleted (D5), no tags pointing into the old history (`r185-ui-live-freeze`, `r186-close`, `r186-close-records` re-pointed or removed), PR #… "files changed" views confirmed purged by GitHub support | `GET /branches`, `GET /tags`; support confirmation | | ☐ |
| E8 | **SHA invalidation acknowledged and mapped**: every sha cited in `evidence/*_state_ledger.md`, `PROJECT_EXECUTION_STATE.md` pointers and `60_DECISION_LOG.md` refers to the pre-purge history; the bundle (E5) is the lookup | one-line acknowledgment + bundle reference in R199 records | | ☐ |
| E9 | Secret-scanning: alert #1 closed with a real resolution (`revoked`), no new alerts after the force-push | `…/secret-scanning/alerts?state=open` = [] | | ☐ |

## 3. What engineering will and will not do
- WILL (on instruction, in a later records round): verify E1–E9 by API where possible, store the artefacts under
  `evidence/r19x/d03/`, flip the register row to `ACCEPTED-AS-MEASURED`, and re-baseline pointers on the rewritten history.
- WILL NOT: rewrite history, force-push, or delete the legacy branches on its own initiative (D4/D5); claim rotation
  from a token-prefix difference; dismiss alerts.
