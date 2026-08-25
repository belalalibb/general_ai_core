# 22 — Evaluation and Learning
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-009
SUPERSEDES:
  final_docs_v2/12_EVALUATION_LEARNING_SPEC.md
MIGRATION_TYPE: CARRY (verbatim)
DECISION_PRESERVATION: Evaluation pipeline, verification levels
(RAW|EVALUATED|VALIDATED|VERIFIED|GOLD), score vs confidence, grader types,
evaluation record, user visibility, learning lifecycle, training
eligibility, teacher model policy, promotion gates, and tests carried
unchanged. No decision changed.
RELATED_AUTHORITY:
  Verification levels in domain model: final_docs_v3/03_DOMAIN_MODEL.md
  Learning dashboard administration:   final_docs_v3/21_ADMIN_CONTROL_PLANE.md
```

---

## 1. Purpose

Evaluation verifies output quality. Learning improves the system only from verified, eligible, sanitized data.

---

## 2. Evaluation Pipeline

```text
Execution Trace
↓
Evaluation Policy
↓
Deterministic Graders
+ Model Graders
+ Pairwise / Counter Evaluation
↓
Aggregator
↓
Score + Confidence + Evidence
↓
Verification Level
```

---

## 3. Verification Levels

```text
RAW
EVALUATED
VALIDATED
VERIFIED
GOLD
```

Definitions:

| Level | Meaning |
|---|---|
| RAW | Generated but not evaluated |
| EVALUATED | Scored by one or more graders |
| VALIDATED | Passed required checks |
| VERIFIED | Has sufficient evidence/confidence |
| GOLD | Approved as high-quality reference sample |

---

## 4. Score vs Confidence

```text
Score = how good the output appears.
Confidence = how much we trust that judgment.
```

Never merge them into one number.

---

## 5. Grader Types

```text
deterministic
model_based
pairwise
counter_evaluation
skill_specific
role_specific
security
regression
human_calibrated
production_signal
```

---

## 6. Evaluation Record

```json
{
  "execution_id": "uuid",
  "level": "VALIDATED",
  "score": 0.86,
  "confidence": 0.78,
  "graders": [
    {
      "type": "deterministic",
      "name": "schema_validation",
      "passed": true
    },
    {
      "type": "model_based",
      "name": "code_review_judge",
      "score": 0.84,
      "confidence": 0.74
    }
  ],
  "evidence_ref": "object://evidence/uuid"
}
```

---

## 7. User Visibility

Default:

```text
User sees final result only.
Admin sees scores, confidence, evidence, traces.
```

Admin may enable or hide user-facing feedback UI.

---

## 8. Learning Lifecycle

```text
Raw Interaction
↓
Candidate Sample
↓
Privacy/Policy Check
↓
Sanitization
↓
Evaluation
↓
Verification
↓
Training Eligibility
↓
Dataset
↓
Teacher / Max Model Review
↓
Training
↓
Offline Evaluation
↓
Shadow
↓
Canary
↓
Promotion
↓
Rollback if needed
```

---

## 9. Training Eligibility

Data can enter training only if:

```text
privacy policy allows
tenant/user policy allows
sensitive data handled
quality level sufficient
deduplicated
sanitized
source trace exists
not poisoned
```

---

## 10. Teacher Model Policy

Max/teacher models are used selectively:

```text
high-value samples
uncertain samples
new task categories
calibration sets
canary evaluation
```

Not every request needs teacher review.

---

## 11. Promotion Gates

A trained model/policy is promoted only after:

```text
offline eval pass
regression pass
security eval pass
shadow performance acceptable
canary performance acceptable
rollback plan exists
admin approval where required
```

---

## 12. Tests

```text
evaluation record creation
score/confidence separation
failed deterministic check prevents verified level
feedback not treated as truth
training eligibility enforcement
sanitization removes secrets
shadow/canary promotion gate
rollback model version
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–12 (purpose, evaluation pipeline, verification levels, score vs confidence, grader types, evaluation record, user visibility, learning lifecycle, training eligibility, teacher model policy, promotion gates, tests) | v2 12 §1–12, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header and this
traceability section were added. No evaluation or learning rule was modified.
