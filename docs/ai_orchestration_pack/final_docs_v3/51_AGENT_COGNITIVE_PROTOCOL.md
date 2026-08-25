# 51 — Agent Cognitive Protocol
## For Maximum Reasoning, Decision Quality, and Execution Discipline

```text
STATUS: AUTHORITATIVE (V3)
AUTHORED_BY_TASK: T-DOC-012
SOURCE (V2, now SUPERSEDED):
- final_docs_v2/19_AGENT_COGNITIVE_OPERATING_PROTOCOL.md (CARRY)
AUTHORITY SWITCH: final_docs_v3/00_INDEX.md (MIGRATION STATUS table)
RELATED AUTHORITATIVE DOCS:
- final_docs_v3/50_AGENT_EXECUTION_PROMPT.md        (the build prompt that invokes this protocol)
- final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md  (how to resume safely)
- final_docs_v3/40_ENGINEERING_PROTOCOL.md          (engineering rules and gates)
CARRY NOTE: All tiers, modes, checklists, rules, and output contracts carried
verbatim. The §1 purpose narrative is normalized from Arabic to English with
identical meaning (recorded in the traceability ledger). No decision changed.
```

Resume / Handoff:
Project execution state is controlled by docs/ai_orchestration_pack/PROJECT_EXECUTION_STATE.md.
Do not infer project progress from this document.
Resume only from the authorized task recorded in the project state file.

---

## 1. Purpose

This protocol does not only explain what the Agent builds — it defines **how the Agent must think before building**.

Its goal is to force the Agent or engineer to:

```text
Understand the task deeply
Choose the appropriate level of thinking
Compare alternatives when needed
Attack its own decision before adopting it
Prevent lazy execution
Prevent overengineering
Prove success with evidence
```

This document is used on top of all other documents; it does not replace them.

---

## 2. Core Cognitive Rule

Before acting, classify the task.

```text
Wrong behavior:
Start coding immediately for every task.

Correct behavior:
Classify → choose reasoning mode → decide → implement → verify.
```

---

## 3. Task Classification

Every task must be classified into one of these tiers:

| Tier | Meaning | Required Thinking |
|---|---|---|
| S — Simple | Local, low-risk, obvious implementation | Direct execution + tests |
| M — Design-Sensitive | Affects contracts, APIs, data model, provider behavior, routing, memory, evaluation | Options + tradeoff + red-team + validation |
| L — Architecture-Sensitive | Affects core invariants, security boundaries, extensibility, workflow runtime, tenant isolation, credentials | ADR + impact analysis + approval gate |
| R — Risk/Security-Sensitive | Touches auth, secrets, tools, permissions, training data, tenant boundaries, local execution | Threat model + deny-by-default + security tests |
| U — Unclear/Blocked | Missing information changes the design materially | Ask targeted questions or document assumptions |

---

## 4. Mode Selection Policy

### 4.1 Simple Mode

Use for small changes that do not affect architecture.

Required output before implementation:

```text
Task ID
Objective
Files expected
Acceptance criteria
Verification command
```

Then implement, test, commit.

---

### 4.2 Deep Design Mode

Use when a task affects:

```text
API contracts
Provider contracts
Model routing
Execution graph
Memory/context
Skill/tool manifests
Evaluation/learning
Admin policies
Data model
```

Required before implementation:

```text
Problem framing
Assumptions
2-3 viable options
Decision criteria
Tradeoff matrix
Preferred option
Red-team findings
Validation plan
Rollback/migration impact
```

---

### 4.3 Architecture Gate Mode

Use when the task may change a non-breakable invariant.

Required:

```text
STOP
Identify affected invariant
Create/update ADR
List alternatives
Analyze compatibility
Analyze migration impact
Define tests
Get approval if human approval is required
Only then implement
```

The Agent must not silently change architecture.

---

### 4.4 Security / Risk Mode

Use for anything involving:

```text
Authentication
Authorization
Tenant isolation
Secrets
Credentials
Provider accounts
Tools
Client runtime
Terminal/filesystem/browser
Training data
Audit integrity
Admin security settings
```

Required:

```text
Threats
Abuse cases
Deny-by-default behavior
Permission checks
Approval gates
Audit events
Security tests
Secret leakage checks
```

---

### 4.5 Clarification Mode

Ask questions only if missing information can materially change architecture or implementation.

Max questions:

```text
3 questions at once
```

If not blocking, make explicit assumptions and continue.

---

## 5. Decision Forcing Contract

For every non-trivial decision, produce this structure before implementation:

```md
## Decision Point
What is being decided?

## Context
Why does this matter now?

## Constraints
Architecture invariants, security rules, existing docs, project state.

## Options
A. ...
B. ...
C. ...

## Evaluation Criteria
- correctness
- security
- extensibility
- simplicity
- operational reliability
- cost/performance
- migration impact
- testability

## Tradeoff Matrix
| Option | Pros | Cons | Risks | Fit |
|---|---|---|---|---|

## Red-Team Findings
How could this decision fail or be abused?

## Final Decision
Chosen option and why.

## Rejected Alternatives
Why not the other options?

## Validation Plan
What proves the decision works?

## Rollback / Migration Plan
How to reverse or migrate if wrong?
```

---

## 6. Red-Team Checklist

Before approving a design or implementation, attack it:

```text
Can this leak tenant data?
Can this expose secrets?
Can a model bypass permissions?
Can a skill invoke a tool without approval?
Can provider-specific logic enter Core?
Can routing silently choose an unauthorized model?
Can retries double-charge the user?
Can fallback change user intent?
Can unverified memory become truth?
Can bad data enter training?
Can admin config disable a security invariant?
Can interrupted work be mistaken as complete?
Can this become overengineered?
Can a simpler design satisfy the same goal?
```

Each real risk must have a mitigation or explicit accepted risk.

---

## 7. Compression Gate

After producing any design, ask:

```text
What can be removed without reducing outcome quality?
What is overengineering for the current phase?
What belongs in MVP vs later?
What should become a policy instead of hardcode?
What should be documented as future improvement instead of implemented now?
```

Delete or postpone anything without immediate execution value.

---

## 8. Evidence Rule

The Agent must never claim success without evidence.

Valid evidence:

```text
passing tests
schema validation
contract tests
security test output
command logs
created artifacts
migration output
commit hash
trace/audit sample
manual verification note with exact steps
```

Invalid evidence:

```text
I think it works
Implemented successfully
No visible errors
Looks good
```

---

## 9. Completion Language Rules

The Agent may say:

```text
Implemented and verified
```

only if tests/verification passed.

The Agent may say:

```text
Committed
```

only if commit hash is shown and `git status` verified.

The Agent must say:

```text
Unverified
```

if tests were not run or failed.

---

## 10. Anti-Laziness Rules

The Agent must not:

```text
skip reading relevant files
implement broad tasks without decomposition
claim architecture compliance without checking invariants
ignore failing tests
hide partial work
invent provider capabilities
invent external API behavior
write placeholders as final implementation
hardcode policies that should be configurable
create documentation instead of required code/tests
```

---

## 11. Anti-Overengineering Rules

The Agent must not:

```text
introduce microservices before justified
introduce Kafka before throughput/replay requires it
build custom workflow engine if durable runtime is intended
add abstractions without at least two clear implementations or future need
build full UI before contracts stabilize
implement future improvements during MVP unless blocking
```

---

## 12. Reasoning Depth Budget

Use proportional reasoning.

```text
S task: concise reasoning, execute quickly.
M task: design comparison required.
L/R task: full decision forcing + ADR/security analysis.
```

Heavy reasoning for trivial tasks is a failure. Shallow reasoning for critical tasks is a failure.

---

## 13. Implementation Quality Gate

Before committing, verify:

```text
1. Does it satisfy the task objective?
2. Does it preserve architecture invariants?
3. Are contracts updated and versioned if needed?
4. Are tests added or updated?
5. Are security implications addressed?
6. Are errors handled?
7. Is observability/audit added where needed?
8. Is documentation/state updated?
9. Is scope controlled?
10. Is the next micro-task clear?
```

---

## 14. Required Output by Task Tier

### S — Simple

```text
TASK RESULT
Status:
Task ID:
Implementation:
Tests:
Commit:
Next:
```

### M — Design-Sensitive

```text
DESIGN RESULT
Decision Point:
Options Considered:
Tradeoffs:
Red-Team Findings:
Decision:
Validation Plan:

TASK RESULT
Status:
Implementation:
Tests:
Commit:
Next:
```

### L/R — Architecture or Security Sensitive

```text
GATE RESULT
Affected Invariants:
ADR:
Threats/Risks:
Mitigations:
Approval Needed:
Validation Plan:

TASK RESULT
Status:
Implementation:
Tests:
Commit:
Next:
```

---

## 15. Final Cognitive Standard

The Agent succeeds when it behaves like:

```text
Architect before changing architecture.
Security engineer before touching authority/secrets/tools.
Product engineer before expanding scope.
Reliability engineer before async/retry/workflow changes.
QA gatekeeper before claiming done.
```

The goal is not maximum text. The goal is maximum correct outcome with the minimum necessary complexity.

---

## Traceability (V2 → V3) Ledger

```text
v2 19 §1 (Purpose, Arabic narrative) → §1 (normalized to English; identical meaning;
        the seven forcing goals carried one-to-one)
v2 19 §2..§15                        → §2..§15 CARRIED VERBATIM
        (tier table, mode selection policy, decision forcing contract,
         red-team checklist, compression gate, evidence rule, completion
         language rules, anti-laziness rules, anti-overengineering rules,
         reasoning depth budget, implementation quality gate, per-tier
         output contracts, final cognitive standard)

Additions (structure only, no rule change):
- Authority/status banner (migration bookkeeping).
- Static Resume/Handoff pointer per D10/D11 (progress lives only in
  PROJECT_EXECUTION_STATE.md).

No decision, rule, checklist item, or output contract was dropped,
weakened, or changed.
```
