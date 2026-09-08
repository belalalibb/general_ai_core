# Memory types → `MemoryItem` convention (R177-FIX-05)

Status: **pinned by test** `tests/memory/test_memory_type_convention_r177.py`.
Authority: `final_docs_v3/13_MEMORY_AND_CONTEXT.md` §2 (the six types) and §3 (the item
contract). This document adds **no contract field and no enum** — a `MemoryType` enum was
considered and explicitly deferred (decision log `R177-DEFER-01`). A memory's "type" is the
combination **`scope` × `source` × `user_id` presence** on the existing `MemoryItem`
(`core/contracts/memory.py`).

## 1. Source vocabulary (closed by test, extended only with a test-pinned edit)

| `source` value | meaning | writer |
|---|---|---|
| `learning.gold` | promoted GOLD knowledge (`VerificationLevel.GOLD`) | `core/learning/lifecycle.py` `promote_to_gold` (`GOLD_KNOWLEDGE_SOURCE`) |
| `preference` | learned user preference that passed `PreferenceLearningGate` (13 §6) | R177-FIX-04 seam (optional; absent ⇒ no writer) |
| `episode` | episodic / relationship memory distilled from a conversation | reserved — no runtime writer yet (would be an optional seam; needs approval) |
| `repo.map` | compact ranked repository map of a project (discovery artefact) | R177-FIX-06 tool (optional; absent ⇒ no writer) |

Rules:

- Runtime writers MUST use one of the values above (the test walks every
  `MemoryItem(...)` construction under `core/` and `apps/` and resolves the `source` argument).
- Composer provenance labels (`request`, `memory:<id>`, `message:<id>`, `role:<id>`, `local`) are
  `ContextBlock.source` values, **not** `MemoryItem.source` values, and are out of scope here.
- No writer may emit `MemoryItem` with `sensitivity=high` unless the composer caller opts in
  (`allow_high_sensitivity`, default False) — unchanged from 13 §7.

## 2. Type mapping (13 §2 → item shape)

| 13 §2 type | `scope` | `source` | `user_id` | `expires_at` | status |
|---|---|---|---|---|---|
| Conversation Memory | — (not a `MemoryItem`; `Conversation`/`Message` via `ConversationStorePort`) | — | — | — | COVERED |
| Working Context | — (not stored; `ComposedContext` per request, `core/context/composer.py`) | — | — | — | COVERED |
| Verified Intelligence | `tenant` | `learning.gold` | `None` (tenant-shared) | `None` | COVERED (runtime writer exists) |
| Semantic/User Memory | `tenant` | `preference` | set (user-owned) | optional | PARTIAL — writer = FIX-04 seam |
| Project Memory | `project` (or `workspace`) | `repo.map` \| `preference` | `None` | optional | PARTIAL — writer = FIX-06 tool |
| Episodic Memory | `tenant` | `episode` | set (user-owned) | **required** (episodes decay) | RESERVED — vocabulary only, no writer |

Invariants (13 §7, unchanged): tenant isolation is by `tenant_id`; a user-owned item
(`user_id` set) is never composed for another user; `Memory ≠ Training Data`;
`User Preference ≠ Truth` (preferences never raise `VerificationLevel`).

## 3. Why not an enum

A `MemoryType` field would be a new closed set (blast radius: contract, store schemas,
migration, composer ranking, admin UI) for a property that is already fully determined by
existing fields. The convention above is machine-checked without touching the contract.
Revisit only through the decision log.
