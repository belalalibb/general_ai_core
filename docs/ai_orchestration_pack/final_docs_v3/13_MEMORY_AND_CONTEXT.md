# 13 — Memory and Context
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-008
SUPERSEDES:
  final_docs_v2/08_MEMORY_CONTEXT_SPEC.md
MIGRATION_TYPE: CARRY (verbatim)
DECISION_PRESERVATION: Memory types, memory item contract, scope priority,
context composer, learning preferences, memory safety, visibility,
retrieval rules, and tests carried unchanged. No decision changed.
RELATED_AUTHORITY:
  Domain entities (MemoryItem etc.): final_docs_v3/03_DOMAIN_MODEL.md
  Execution graph consuming context:  final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md
```

---

## 1. Purpose

Memory makes the system feel personalized without becoming unsafe, noisy, or incorrect.

Memory must be evidence-based, scoped, and revocable.

---

## 2. Memory Types

```text
Conversation Memory
Episodic Memory
Semantic/User Memory
Project Memory
Working Context
Verified Intelligence
```

Important:

```text
Memory ≠ Training Data
User Preference ≠ Truth
```

---

## 3. Memory Item Contract

```json
{
  "key": "preferred_language",
  "value": "ar",
  "scope": "user",
  "source": "conversation",
  "confidence": 0.92,
  "evidence_count": 12,
  "last_seen": "iso-date",
  "expires_at": null,
  "sensitivity": "low"
}
```

---

## 4. Scope Priority

When memory conflicts:

```text
Conversation > Project > Workspace > User > Tenant > Global
```

More specific scope wins unless low confidence.

---

## 5. Context Composer

Context Composer selects only relevant context.

Inputs:

```text
current request
conversation state
project context
user preferences
relevant past decisions
role requirements
skill requirements
security policy
context budget
```

Output:

```json
{
  "context_blocks": [
    {
      "type": "preference",
      "content": "User prefers Arabic.",
      "source": "memory:123",
      "confidence": 0.92
    }
  ],
  "excluded": [
    {
      "reason": "irrelevant",
      "memory_id": "abc"
    }
  ]
}
```

---

## 6. Learning Preferences

A preference can be learned when:

```text
repeated evidence exists
no contradiction dominates
scope is clear
sensitivity is acceptable
user/admin policy allows memory
```

Do not infer sensitive attributes unnecessarily.

---

## 7. Memory Safety

Forbidden:

```text
cross-tenant memory leakage
using one user's memory for another
storing secrets as memory
blindly trusting model-generated memory
training on memory without eligibility
```

---

## 8. Memory Visibility

Users should eventually be able to:

```text
view key preferences
edit preferences
delete preferences
disable memory where allowed
```

Admin can configure memory policies but cannot break tenant isolation.

---

## 9. Retrieval Rules

Retrieve by:

```text
scope
semantic similarity
recency
confidence
role/task relevance
security classification
```

Do not include low-confidence memory unless marked as uncertain.

---

## 10. Tests

```text
scope conflict resolution
tenant isolation
preference confidence update
irrelevant memory excluded
secret not stored
memory deletion respected
context budget respected
project memory overrides user memory
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–10 (purpose, memory types, memory item contract, scope priority, context composer, learning preferences, memory safety, visibility, retrieval rules, tests) | v2 08 §1–10, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header and this
traceability section were added. No memory rule or contract was modified.
