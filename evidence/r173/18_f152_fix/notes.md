# R173 F-15.2 — runtime source reader composes the hardened denylist (APPROVED, applied)

Change (one line + comment): `apps/composition/runtime.py::_source_reader`
`SourceReader(root=path)` → `SourceReader(root=path, denied_patterns=DENIED_PATH_PATTERNS)`
(import `core.tools.denied_paths.DENIED_PATH_PATTERNS`). Fix commit `51d00fd692a8`.

Pin: `tests/composition/test_agent_source_seam.py::test_runtime_reader_composes_hardened_denylist`
(mirrors the dev-surface pin in `tests/tools/test_denied_paths_r172.py:148`).

## Before / after (`before.json` @ e712919633db, `after.json` @ 51d00fd692a8; probe = `tools/f152_probe.py`)
| probe | before (13) | after (64) |
|---|---|---|
| `.env`, `.git/config`, `id_rsa.key`, `../../etc/passwd` | refused | refused |
| `core/agent/runtime.py` | admitted | admitted |
| `engineering/verification/green_manifest.json` | **admitted** | refused |
| `engineering/verification/check_repo.sh` | **admitted** | refused |
| `core/providers/accounts.py` | **admitted** | refused |
| `infrastructure/security/password.py` | **admitted** | refused |

Blast radius on the tracked tree moves from form A (4 files) to form B (18 files) — exactly the
§1.5 measurement (`../16_denylist_blast_radius/`); zero credential material either way, so the
cost is that the platform agent can no longer READ the verifier, the gate manifests, the argon2
hasher, the provider accounts module and 9 verification docs. That is the R172 C1 intent
(fail-closed on the agent's own gate) now applied uniformly to both surfaces.

## Gate
Hermetic verifier (`verifier_tail.txt`, same unset list as §1.4): all slices green;
execution-composition-infra 380 → 381 (the new pin). `not_evaluated=2` unchanged from baseline.
