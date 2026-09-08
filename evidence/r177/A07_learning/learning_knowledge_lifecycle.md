# R177-A07 — Learning & knowledge lifecycle assessment (§9) at HEAD

## 1. Real implementation (KNOWN)
| §9 element | Code | Observed behaviour |
|---|---|---|
| Trust ladder | `core/contracts/evaluation.py:64-68` RAW→EVALUATED→VALIDATED→VERIFIED→GOLD | closed; `core/evaluation/policy.py:320-345` derives the level: any failed deterministic check caps at EVALUATED; no judge confidence caps at VALIDATED; VERIFIED needs all checks passed + a judgment confidence; GOLD only via `promote_to_gold` |
| TrainingEligibilityGate | `core/learning/gates.py` (22 §9: privacy_policy_allows, tenant_user_policy_allows, sensitive_data_handled, quality_level_sufficient, deduplicated, sanitized, source_trace_exists, not_poisoned) | deny-by-default; refuses naming every failed condition (R176 A8 probed: poisoning refused at the FIRST gate) |
| PromotionGate | `gates.py:132-139` PromotionSignals (offline_eval_pass, regression_pass, security_eval_pass, shadow_performance_acceptable, canary_performance_acceptable, rollback_plan_exists, approval_required=**True**, admin_approved=**False**) | `promote_to_gold` (lifecycle.py:466) requires prior eligibility pass, runs the gate, writes GOLD MemoryItem `source=learning.gold` only after the substrate accepted it, audits TRAINING_DATASET_PROMOTED |
| Lifecycle service | `core/learning/lifecycle.py` capture_from_execution / capture_external / sanitize / mark_sanitized / derived_signals / resolve_signals / evaluate / set_verification_level / admit_to_training / promote_to_gold / ask_learned / learned_keys / capability_snapshot / capability_delta | composed once at `apps/api/app.py:2085-2090` with `EvaluationPolicyService(store=InMemoryEvaluationStore())`, `knowledge=memory`, `audit=admin.audit`, `TrainingEligibilityGate(minimum_level=RAW)` |
| Sanitizer | `core/learning/sanitizer.py` `sanitize_knowledge()` (FIX-06 widened); memory write guard shares `_VALUE_PATTERNS` | one vocabulary (R176 B-06 verified) |
| Admin surface | 12 routes `/v1/admin/learning/*` (A04) | samples CRUD-ish, scan, sanitize, evaluate, admit, promote, ask, learned, dashboard, changes-since-review, mark-reviewed, capability-retest |

## 2. Gaps and observations (evidence-backed)
- **G-A07-1 — PromotionSignals are caller-asserted booleans.** `apps/api/admin.py:212-232` accepts `offline_eval_pass`, `regression_pass`,
  `security_eval_pass`, `shadow_…`, `canary_…`, `rollback_plan_exists`, `admin_approved` **from the request body**. The gate checks the
  booleans; nothing in the repository *produces* them from executed evaluations (no scenario/regression-pack result is bound to a
  sample). ⇒ PromotionGate is a correct policy engine over unverified inputs. Class: **COVERED BUT NEEDS STRONGER EVIDENCE** (the gate)
  / **PARTIALLY COVERED** (the evidence chain). Mature pattern: promotion decisions consume recorded evaluation artefacts by id
  (offline eval run id, regression pack run id) rather than a flag. Minimum compatible addition: optional `evidence_refs` on the
  promote request resolved against the evaluation store / scenario runs, with `admin_approved` staying a human act. No closed-set change.
- **G-A07-2 — Teacher role: ModelJudgePort is optional and NOT composed.** `EvaluationPolicyService(store=…, judge: ModelJudgePort |
  None = None)` (policy.py:206-222); app.py:2086 composes it **without** a judge. Consequence (KNOWN from policy.py:333-337): no sample
  can exceed **VALIDATED** through `evaluate()` in the shipped profile; VERIFIED needs a judgment confidence. `set_verification_level`
  exists as an admin override. ⇒ "Teacher disabled" is the CURRENT state and the pipeline still runs end-to-end: deterministic graders +
  both gates + admin approval → GOLD is reachable (promotion requires eligibility ≥ minimum_level=RAW, not VERIFIED). This answers §9's
  "what happens when Teacher is disabled": nothing breaks; the ceiling is VALIDATED via evaluation, GOLD via human-approved promotion.
  Class: **PARTIALLY COVERED** — role exists as a seam; 22 §10 selective policy (high-value/uncertain/new-category/calibration/canary)
  has no selector; teacher_agreement field is unused by any gate.
- **G-A07-3 — Intake normalisation is absent.** Knowledge enters only via `capture_from_execution` or `capture_external(knowledge_key,
  knowledge_value: JsonObject)` (admin.py:635). No CSV/Excel/JSON-file/upload/API-pull adapter exists (grep csv|xlsx|openpyxl|pandas over
  core/apps/providers → 0). Class: **MISSING** for structured/bulk intake; **ALREADY COVERED** for the trust boundary itself (every
  external item is RAW, sanitized, gated). Any normaliser must live in providers/ or apps/composition/ and feed `capture_external`.
- **G-A07-4 — Evaluation store is process-memory in the composed app** (`InMemoryEvaluationStore()` at app.py:2086) even in the
  durable profile; evaluation records do not survive restart. Class: **PARTIALLY COVERED** (durability envelope stated honestly in R176).
- **G-A07-5 — Observability of "what it learned"** (§10): `learned_keys`, `ask_learned`, dashboard, changes-since-review,
  capability-retest (before/after over a probe set) exist and are admin-only. Missing: a per-tenant "what is uncertain / proposed /
  passed review" view is derivable from sample states but not exposed as one surface. Class: **PARTIALLY COVERED** (data present,
  surface partial).
- Sanitizer/poisoning: **ALREADY COVERED** (R176 A8 + B-06 runtime rerun).

## 3. Teacher — minimum design if a gap is confirmed (NOT proposed for implementation here)
Teacher = (a) a `ModelJudgePort` binding (existing seam; provider-agnostic via the routing/execution service — `AdapterModelJudge`),
(b) a selection policy object over 22 §10 criteria deciding WHEN the judge runs, (c) unchanged gates. Disabled ⇒ (a) None, (b) never
selects; deterministic graders, eligibility and promotion gates run unchanged. Replaceable (port), configurable (policy data),
vendor-independent (goes through routing). No new contract term is required; "teacher" stays documentary.
