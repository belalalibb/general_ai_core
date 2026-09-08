# R177-A10 — Bounded landscape research (§5) — CONFIRMED gaps only

Evidence tier: **Level 3/5 (external, non-proof about our code)**. One web search per gap, 2026-09-08. Patterns extracted; nothing copied.
Time-box respected: 4 searches, no follow-up browsing.

## Gap 1 — Persisted repository model (F-R177-05)
- Sources (2026-09-08): aider.chat/docs/repomap.html; aider.chat/2023/10/22/repomap.html; agentpatterns.ai "Repository Map Pattern";
  arXiv 2603.27277 "Codebase-Memory: Tree-Sitter-Based Knowledge Graphs" (Mar 2026).
- **Pattern**: a *compact, ranked* map — files as nodes, symbol definitions/references as edges, importance ranking (PageRank-style),
  fitted into a token budget by binary search — computed from parsers (tree-sitter), NOT by reading whole files into context. Aider's
  map is stateless/live-computed; "Codebase-Memory" persists it as a graph.
- **Operational lesson**: the map is a *context-selection* artefact, not a truth store; it must be cheap to recompute and must degrade
  to "unknown" for unparsed files.
- **QEVION minimum**: no graph DB, no tree-sitter dependency in core/. Discovery = an OPTIONAL agent tool (apps/composition or
  providers-side adapter) that writes MemoryItems `scope=project, source="repo.map"` (entries: path, kind, top symbols, confidence,
  evidence_count) through the existing MemoryStorePort; the composer already budget-fits project-scope items (13 §4/§5). Ranking may
  start as import-degree from the existing bounded reader; tree-sitter, if ever, lives outside core/ (import-linter). Fits existing
  guarantees: jail/denylist apply to the reader; tenant scoping via MemoryItem keys; no execution authority implied.
- Re-evaluate over time: parser/ranking choice (vendor-neutral); whether models with very large context make the map less necessary.

## Gap 2 — Composition-level capability-proposal record (A05 §6.1)
- Sources (2026-09-08): martinfowler.com/bliki/ArchitectureDecisionRecord.html (updated Mar 2026); Nygard ADR template
  (joelparkerhenderson/architecture-decision-record); ctaverna.github.io/adr; hidekazu-konishi.com ADR operations (May 2026).
- **Pattern**: a decision record with a closed status ladder (proposed → accepted | rejected; later deprecated/superseded), immutable
  once accepted (a changed conclusion = a NEW record referencing the old one), sections Context / Decision / Consequences.
- **QEVION minimum**: the §7 decision sheet IS an ADR-shaped record. Two options, both without a new subsystem: (a) **documentary**:
  append each sheet + ruling to `final_docs_v3/60_DECISION_LOG.md` (append-only, already the repo's ADR-like log) — zero code;
  (b) **runtime**: reuse the admin change lifecycle (draft → validate → preview → publish) with a new draft *kind* `capability_proposal`
  whose publish records an `APPROVAL_DECISION` AuditEvent — the record then lives in the audit trail read by `/v1/admin/audit`.
  (b) touches core/contracts/admin.py (closed change kinds → approval) and is the only path that makes decisions *machine-readable* for
  later sessions. Recommend (a) now, (b) as a proposal (R177-FIX-03).
- Re-evaluate: whether proposals need their own read route or the audit trail suffices.

## Gap 3 — Structured knowledge intake normalisation (G-A07-3)
- Sources (2026-09-08): greatexpectations.io (GX Core); conduktor.io glossary "Great Expectations" (Jul 2026); devblogs.microsoft.com
  ISE "Data Validations with Great Expectations" (Apr 2025).
- **Pattern**: declare *expectations* (schema, nullability, ranges, uniqueness) as data; validate every batch BEFORE it enters the
  trusted zone; produce a validation *report* per batch; failed batches are quarantined, never silently dropped or promoted.
- **QEVION minimum**: an intake adapter (CSV/JSON first; Excel via an optional dependency) OUTSIDE core/ that (1) parses to rows,
  (2) validates against a declared expectation set (composition data), (3) emits ONE `capture_external(knowledge_key, knowledge_value)`
  per admitted row (or per batch summary) — each item lands **RAW** and goes through the existing sanitize → eligibility → evaluate →
  promote chain unchanged. Quarantine = the validation report + refused rows recorded as a learning sample report, not as knowledge.
  Trust boundary unchanged; no promotion shortcut.
- Re-evaluate: format list; whether expectation sets belong to the admin config lifecycle.

## Gap 4 — Evidence-bound promotion signals (G-A07-1)
- Sources (2026-09-08): mlflow.org/docs/latest/ml/model-registry (stages, aliases, tags); mlflow.org articles "gated promotion … through
  defined checkpoints" (Aug 2026); Databricks workspace model registry (Jul 2026); oneuptime.com "model approval workflows" (Jan 2026).
- **Pattern**: promotion between stages is gated on *recorded* artefacts — evaluation run ids, metrics, tags — and an explicit human
  approval; the gate reads the registry, it does not accept "passed=true" from the requester.
- **QEVION minimum**: keep `PromotionSignals` and `PromotionGate` unchanged; make the admin promote route *derive* `offline_eval_pass`,
  `regression_pass`, `security_eval_pass` from referenced artefacts already in the repo (evaluation record id → `EvaluationPolicyService`
  store; regression-pack / scenario run id → scenarios store) when `evidence_refs` are supplied, and refuse caller-asserted `True` for
  those three when refs are absent (composition policy flag, default strict). `admin_approved` stays a human act. No closed-set change;
  one contract field addition on the admin request model (additive), failing-first test: caller-asserted `offline_eval_pass=True`
  without evidence ⇒ refused naming the condition.
- Re-evaluate: shadow/canary signals still have no producer in QEVION (no serving tier) — keep them caller-asserted but labelled UNVERIFIED
  in the sample report until a producer exists.
