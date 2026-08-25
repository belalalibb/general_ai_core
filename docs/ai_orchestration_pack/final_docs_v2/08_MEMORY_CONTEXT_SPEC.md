# 08 — Memory & Context Specification

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
