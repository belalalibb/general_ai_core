# R179 findings ledger (every measurement that FAILED or contradicted the brief; a finding gets an entry, never an off-books fix)

Precedent: `evidence/r175_findings_ledger.md`. Severities: S1 release-blocking … S4 cosmetic.
Disposition of every row is mirrored in `docs/ai_orchestration_pack/R179_HANDOFF.md` §C.

| id | finding | evidence | severity | disposition |
|---|---|---|---|---|
| F-R179-01 | Durable profile: `POST /v1/execute` with any `conversation_id` answers constant 500. Root cause: `apps/composition/runtime.py` composes `InMemoryConversationStore()` for BOTH profiles while `executions.conversation_id` carries FK `fk_executions_conversation_id_conversations` (migration 0008) → `ForeignKeyViolationError` on the durable executions insert. Conversation continuity (4.4 P2) is therefore not merely non-durable — the conversational path is UNUSABLE on the durable profile. Discovered by the 4.4 probe on a real-alembic schema. | `evidence/r179/F01_execute_with_conversation_id_durable_500.txt`; probe `tests_live/r179/test_durability_measured_postgres.py` | S1 (durable-profile feature returns 500) | see HANDOFF §C |
