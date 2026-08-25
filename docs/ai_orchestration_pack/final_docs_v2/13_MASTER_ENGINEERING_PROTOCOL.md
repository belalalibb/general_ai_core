# MASTER ENGINEERING PROTOCOL
**Version: 1.0 — Architecture Baseline**

---

# 0. Purpose

هذا البروتوكول هو **المرجع الهندسي الأعلى للمشروع**.

يحدد:

- المعمارية المعتمدة.
- حدود كل Module.
- العقود بين الـModules.
- قواعد الأمن.
- طريقة التنفيذ.
- الاختبارات.
- الـGit والتغييرات.
- الـState والاستئناف.
- الـRecovery.
- الـADR.
- الـPhase Gates.
- Definition of Done.

أي Implementation يجب أن تكون **متوافقة مع هذا البروتوكول**.

أي قرار جديد يتعارض معه **لا يُطبق مباشرة**؛ يجب أن يمر عبر Architecture Review وADR.

---

# 1. Core Engineering Principles

## 1.1 Contract First

لا تبدأ Implementation كبيرة قبل تحديد Contract واضح.

الـContract يحدد:

```text
Input
Output
Errors
Lifecycle
Version
Invariants
```

---

## 1.2 Extension Over Modification

إضافة:

```text
Provider
Model
Skill
Tool
Role
Execution Strategy
Benchmark
Evaluator
Credential Type
```

يجب أن تتم عبر:

```text
Registry
Plugin / Adapter
Contract
Configuration
```

وليس بتعديل Core logic كل مرة.

---

## 1.3 Policy Over Hardcoding

أي شيء يمثل Business Policy أو Runtime Policy يجب ألا يكون hardcoded.

يشمل:

```text
Model Tiers
Routing Weights
Fallback Rules
Task Costs
Plan Limits
Feature Availability
Skill Availability
Evaluation Thresholds
Learning Policies
Provider Preferences
```

السياسات تكون:

```text
Configurable
Versioned
Validated
Audited
Rollbackable
```

---

## 1.4 Security Invariants Are Not Configurable

ليس كل شيء يجب أن يكون editable من Admin.

لا يسمح للـAdmin Configuration بتغيير:

```text
Tenant isolation mechanisms
Secret storage guarantees
Cryptographic requirements
Core security boundaries
Authentication invariants
Authorization invariants
Audit integrity guarantees
```

**Configurable ≠ Everything.**

---

## 1.5 Model-Agnostic Core

الـCore لا يعتمد على Model معين.

---

## 1.6 Provider-Agnostic Core

الـCore لا يعتمد على Provider معين.

---

## 1.7 Execution-Agnostic Core

الـCore لا يفترض أن كل Task يتم تنفيذها بطريقة واحدة.

---

## 1.8 At-Least-Once + Idempotency

لا نعتمد على ضمان `Exactly Once` على مستوى النظام بالكامل.

القاعدة:

```text
At-Least-Once Delivery
+
Idempotent Operations
+
Durable State
+
Leases/Fencing where required
```

---

## 1.9 Evidence Before Confidence

لا نحول:

```text
Observation
```

إلى:

```text
Fact
```

بدون Evidence.

---

## 1.10 Verified Learning Only

لا تدخل البيانات في Verified/GOLD Dataset لمجرد أنها تبدو جيدة.

يجب أن توجد:

```text
Evidence
Evaluation
Verification
Eligibility
Sanitization
Governance
```

---

# 2. System Vision

النظام عبارة عن:

> **Model-Agnostic AI Orchestration Platform**

يمكن لأي مشروع خارجي استخدامه:

```text
IDE
Marketing
Automation
Research
Support
Future Products
```

من خلال API موحدة.

---

# 3. High-Level Architecture

```text
                           PUBLIC / ADMIN API
                                  │
                         Identity / Authentication
                                  │
                           Authorization Layer
                                  │
                         Capability Firewall
                                  │
                                 CORE
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        │                         │                         │
      Router                Personal Context          Control Plane
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  │
                          Execution Planner
                                  │
                         Durable Workflow Runtime
                                  │
             ┌────────────────────┼────────────────────┐
             │                    │                    │
          Models                Skills               Tools
             │                    │                    │
             └────────────────────┼────────────────────┘
                                  │
                               Providers
                                  │
                    ┌─────────────┴─────────────┐
                    │                           │
             Platform Credentials        User Credentials
                    │
                 Accounts
                    │
               Account Pools
                                  │
                         Evaluation / Verification
                                  │
                         Verified Intelligence
                                  │
                       Learning / Model Evolution
```

---

# 4. Module Boundaries

## 4.1 Public API

مسؤول عن:

```text
Transport
Authentication entry
Validation
Versioning
Idempotency entry
Response formatting
Streaming
Webhook interface
```

لا يعرف Provider implementation.

---

## 4.2 Identity

مسؤول عن:

```text
Users
Authentication
Sessions
Email verification
Credentials for platform identity
```

لا يقرر صلاحيات Feature من تلقاء نفسه.

---

## 4.3 Authorization

مسؤول عن:

```text
Roles
Permissions
Entitlements
Policies
Scopes
```

القرار النهائي:

```text
ALLOW
DENY
ALLOW_WITH_LIMIT
```

---

## 4.4 Tenant Isolation

مسؤول عن:

```text
Tenant Context
Ownership
Scope enforcement
Data access boundaries
```

ويعمل عبر:

```text
Application Enforcement
+
Repository/Data Access Enforcement
+
Database Enforcement where applicable
```

---

## 4.5 Core

مسؤول عن orchestration عالي المستوى.

لا يجوز له:

```text
Direct Provider HTTP
Direct Secret Access
Direct Browser Control
Direct Account Cookie Management
```

---

# 5. Model System

## 5.1 Model Registry

Source of model metadata.

يشمل:

```text
model_id
provider
tier
capabilities
modalities
quality
speed
cost
reliability
availability
benchmark data
production signals
```

---

## 5.2 Model Selection

يدعم:

```text
AUTO
TIER
EXPLICIT_MODEL
```

---

## 5.3 Explicit Model

عند تحديد Model صراحة:

```text
لا يستبدل تلقائيًا
```

إلا ضمن Fallback Policy المسموح بها.

إذا فشلت كل Providers لنفس Model:

```text
Same-Tier Auto Fallback
```

---

# 6. Provider System

## 6.1 Provider Independence

كل Provider وحدة مستقلة.

---

## 6.2 Provider Contract

يجب أن يغطي حسب قدرة الـProvider:

```text
Authentication
Account lifecycle
Models
Capabilities
Generation
Assets
Files
Health
Errors
Limits
Agent module if supported
```

---

## 6.3 Provider Files

الـProvider الحالي يمكن أن يحتوي implementation مختلفة، لكن الـCore لا يتعامل معها مباشرة.

---

## 6.4 Provider Inventory

قبل Migration:

```text
Analyze
Discover
Organize
Document
Verify
```

Current code = Reference.

---

# 7. Accounts & Credentials

## 7.1 Ownership Separation

```text
Platform Managed
User Managed
```

ولا يتم خلط الاثنين في نفس Account Pool.

---

## 7.2 Platform Account Pool

يتحكم في:

```text
Selection
Usage
Cooldown
Health
Lease
Fencing
Lifecycle
Refresh
```

---

## 7.3 User Credentials

المستخدم يستطيع إضافة credentials الخاصة به للـProviders المسموح بها.

السياسات:

```text
platform_only
user_only
prefer_user
auto
```

---

## 7.4 Secret Storage

الـSecrets لا تخزن plaintext في DB أو Logs.

يتم تخزين:

```text
credential_ref
```

في metadata، والـsecret داخل Secret Manager/KMS-backed system.

---

# 8. Rate Limits

Rate limits Provider-specific.

يمكن أن تعتمد على:

```text
Requests
Tokens
Concurrency
Time
Account
Model
Endpoint
Server headers
```

ولا يتم فرض abstraction تكسر Provider behavior.

---

# 9. Provider / Account Health

فصل تام بين:

```text
Provider Health
Account Health
Credential Health
Model Health
```

---

# 10. Routing Engine

## 10.1 Role

الـRouter يقرر:

```text
What should happen?
Which strategy?
Which candidates?
Which resources?
```

ولا ينفذ الطلب.

---

## 10.2 Pipeline

```text
Request Validation
↓
Task Analysis
↓
Context Resolution
↓
Role Resolution
↓
Capability Resolution
↓
Skill Requirements
↓
Execution Strategy
↓
Hard Eligibility
↓
Scoring
↓
Resource Selection
↓
Execution Plan
```

---

## 10.3 Router Strategy

النظام:

```text
Policy-Driven
Hybrid
Dynamic
Replaceable
```

---

## 10.4 Bootstrap Router

الـRouter نفسه لا يجوز أن يحتاج Full Router لاختيار نفسه.

يتم استخدام:

```text
Bootstrap Routing Policy
```

لمنع recursion.

---

# 11. Execution System

## 11.1 Execution Graph

كل مهمة قد تكون:

```text
Single
Parallel
Pipeline
Debate
Review/Judge
Map/Reduce
Agent
Hybrid
```

---

## 11.2 Node Contract

كل Node قد يحتوي:

```text
role
model_policy
skills
input_source
output_schema
retry_policy
timeout
evaluation_policy
```

---

## 11.3 Auto vs Explicit

الـCore يدعم:

```text
Auto Graph
Explicit Graph
```

---

## 11.4 Workflow Ownership

Durable Workflow Runtime هو المسؤول عن:

```text
Workflow State
Node progression
Workflow lifecycle
Workflow retries
Timeouts
Recovery
```

لا نبني Workflow Engine جديد داخل Core.

---

# 12. Async Execution Fabric

## 12.1 Durable Truth

PostgreSQL + durable workflow state.

---

## 12.2 Fast/Background Jobs

Redis Streams.

---

## 12.3 Outbox

أي عملية تحتاج DB state + Event publication:

```text
DB Transaction
↓
Outbox
↓
Publisher
↓
Message Bus
```

---

## 12.4 Idempotency

كل عملية يمكن تنفيذها أكثر من مرة يجب أن تكون logically idempotent عندما يلزم.

---

## 12.5 Leases + Fencing

تستخدم فقط عند وجود Exclusive Resource.

مثل:

```text
Provider Account
Credential Resource
Exclusive Device Tool
```

ليست لكل Job.

---

## 12.6 Backpressure

يجب دعم:

```text
Admission Control
Queue Limits
Tenant Concurrency
Provider Concurrency
Fair Scheduling
Priority
Adaptive Scaling
```

---

## 12.7 Retry

الـRetry يجب أن يكون Error-aware.

```text
Retryable
Non-Retryable
Retry-After
Provider Failover
```

---

## 12.8 Dead Letter

المهام التي تفشل نهائيًا تنتقل إلى:

```text
DLQ / Recovery Flow
```

ولا يوجد infinite retry.

---

# 13. Personal Context Engine

## 13.1 Components

```text
Conversation State
User Profile
Project / Workspace Context
Learned Preferences
Retriever
Context Composer
```

---

## 13.2 Memory Evidence

كل Learned Preference له:

```text
source
confidence
evidence_count
scope
last_seen
```

---

## 13.3 Memory Scope

```text
Global
User
Workspace
Project
Conversation
Role
```

الأكثر تخصيصًا له أولوية عند التعارض.

---

## 13.4 Context Composer

لا يرسل كل التاريخ.

يجمع:

```text
Current Conversation
Relevant Preferences
Relevant Project Context
Relevant Past Decisions
```

فقط.

---

# 14. Role System

## 14.1 Role Types

```text
System Roles
Custom Roles
```

---

## 14.2 Role Profile

```text
Identity
Objective
Required Capabilities
Preferred Skills
Behavior Policies
Output Contract
Runtime Override
```

---

## 14.3 Role Rules

Role لا يختار Model مباشرة.

Role لا يمنح Security Permission.

Custom Role لا يستطيع تجاوز Platform Policy.

---

## 14.4 Role Versioning

كل Role لها:

```text
version
scope
status
```

---

# 15. Skill System

## 15.1 Skill Definition

الـSkill:

> Versioned, Importable, Composable Instruction / Workflow / Tool-enabled Module.

---

## 15.2 Skill Types

```text
Instruction Skill
Workflow Skill
Tool-Enabled Skill
```

---

## 15.3 Invocation

```text
User-invoked
Model-invoked
Both
```

---

## 15.4 External Skill Sources

المراجع:

```text
https://github.com/mattpocock/skills
https://www.aihero.dev/skills-wayfinder
https://github.com/amElnagdy/review-skills
```

هذه مصادر Reference/Import وليست Core dependency.

---

## 15.5 Skill Import Lifecycle

```text
Imported
↓
Scanned
↓
Validated
↓
Reviewed
↓
Approved
↓
Active
```

---

## 15.6 Local Copies

أي Skill خارجية يجب أن تكون لها Local Version.

مع:

```text
source
source_version
checksum
imported_at
local_version
provenance
```

---

# 16. Tool Fabric

## 16.1 Tool vs Skill

```text
Skill = What / How
Tool = Means of Execution
```

---

## 16.2 Tool Locations

كل Tool تعلن:

```text
server
client
hybrid
```

---

## 16.3 Client Tools

مثل:

```text
Browser
Local Files
Terminal
Local Project
IDE
Local Network Resources
```

تعمل محليًا على جهاز المستخدم.

---

## 16.4 Server Tools

مثل:

```text
GitHub API
Cloud APIs
Search APIs
Database Services
```

حسب طبيعة الاستخدام.

---

## 16.5 Device Trust

Local client يجب أن يملك:

```text
device_id
status
paired state
permissions
revoke state
```

ويجب أن يكون Device قابلًا للإلغاء.

---

# 17. Evaluation & Verification

## 17.1 Evaluation Fabric

```text
Execution Trace
↓
Evaluation Policy
↓
Deterministic Graders
+
Model Graders
+
Optional Counter-Evaluation
↓
Aggregator
↓
Confidence + Evidence
↓
Verification
```

---

## 17.2 Evaluation Levels

```text
RAW
EVALUATED
VALIDATED
VERIFIED
GOLD
```

---

## 17.3 Grader Types

```text
Deterministic
Model-based
Pairwise
Skill-specific
Role-specific
Counter-evaluation
Human calibration
Regression
Production
```

---

## 17.4 Score ≠ Confidence

يجب حفظ الاثنين منفصلين.

---

## 17.5 User Visibility

التقييم الداخلي افتراضي.

المستخدم العادي يرى النتيجة النهائية.

الأدمن يستطيع رؤية:

```text
Scores
Confidence
Evidence
Trace
Graders
Verification
```

---

# 18. Learning & Model Evolution

## 18.1 Learning Lifecycle

```text
Verified Data
↓
Dataset
↓
Teacher / Max
↓
Training
↓
Evaluation
↓
Shadow
↓
Canary
↓
Production
```

---

## 18.2 Teacher Policy

Max Models تستخدم بشكل انتقائي، وليس مع كل Request.

---

## 18.3 User Feedback

User Feedback:

```text
Learning Signal
```

وليس حقيقة مطلقة.

---

## 18.4 Learning Dashboard

الأدمن يرى:

```text
Verified Samples
Gold Samples
Task Coverage
Specialists
Accuracy
Cost Reduction
Escalation Rate
Teacher Agreement
Training State
Canary State
```

---

## 18.5 User Evaluation Visibility

Admin-controlled.

يمكن للأدمن إخفاء الـUI للمستخدم دون تعطيل جمع الـinternal signal.

---

## 18.6 Training Eligibility

وجود بيانات في النظام لا يعني أنها Training eligible.

يجب أن توجد:

```text
training_eligible
```

مع Privacy/Governance requirements.

---

# 19. Plans / Usage

## 19.1 Universal Task Units

الوحدة الأساسية:

```text
Simple = 1
Medium = 2
Complex = 3
```

لكن الأرقام Configurable.

---

## 19.2 Plan

الـPlan يحدد:

```text
task_units
entitlements
feature access
limits
```

---

## 19.3 Billing Flow

```text
Estimate
↓
Reserve
↓
Execute
↓
Settle
```

---

## 19.4 Cost Snapshot

عند بداية التنفيذ يتم إنشاء:

```text
Authoritative Cost Snapshot
```

ولا تتغير تكلفة User Task بسبب internal fallback/retries.

---

# 20. Authorization

المعمارية:

```text
RBAC
+
Entitlements
+
Policy Engine
+
Optional Scope Overrides
+
Capability Firewall
```

---

## 20.1 Global Permissions

الـdefault المستخدم يحصل على صلاحيات عامة، وليس Project-specific.

---

## 20.2 Scope

يمكن إضافة:

```text
Global
Workspace
Project
Conversation
```

عند الحاجة فقط.

---

## 20.3 Deny by Default

Unknown capability = DENY.

---

# 21. Authentication

## Initial Method

```text
Gmail
+
Password
+
Email Verification Code
```

---

## Password

```text
Argon2id
Unique Salt
Strong password policy
Compromised password checks
```

---

## Sessions

```text
TLS
Secure
HttpOnly
SameSite
Rotation
Re-authentication
```

---

## Email Verification

```text
One-time
Short-lived
Single-use
Attempt-limited
Rate-limited
Resend cooldown
```

---

## Future Upgrade Path

Architecture must allow:

```text
Passkeys
MFA
TOTP
```

بدون تغيير Core Auth boundaries.

---

# 22. Multi-Tenancy

## Model

```text
Platform
↓
Tenant
↓
User
↓
Optional Workspace
↓
Project
```

كل مستخدم له Tenant منطقي افتراضيًا.

---

## Isolation Model

Hybrid / Bridge.

```text
Shared Infrastructure
+
Strict Tenant Isolation
```

---

## Data Enforcement

```text
Application
+
Data Access Layer
+
Database Enforcement
```

---

# 23. Storage

## PostgreSQL

Main Source of Truth.

---

## pgvector

Semantic Retrieval مبدئيًا.

---

## Redis

```text
Cache
Runtime
Locks
Leases
Rate limits
Streams
Short-lived state
```

ليس Source of Truth.

---

## Object Storage

```text
Images
Audio
Video
Files
Datasets
Large Artifacts
Model Artifacts
```

---

## Secrets Manager

```text
Provider Credentials
User API Keys
Refresh Tokens
Other Secrets
```

---

# 24. Observability

## Standard

OpenTelemetry.

---

## Data Types

```text
Logs
Metrics
Traces
Audit
Execution Records
Evaluation Evidence
```

---

## Sampling

Adaptive.

```text
Normal → reduced
Error → full
Slow → full
High-value → full
Debug → full
```

---

## Security Audit

Security-sensitive events:

```text
Append-only
Protected
Long retention
Tamper-evident where necessary
```

ليس كل log يحتاج hash chain.

---

# 25. Admin Control Plane

كل شيء قابل للإدارة يكون:

```text
Configuration-driven
Versioned
Validated
Audited
Rollbackable
```

---

## Admin controls

```text
Users
Tenants
Plans
Providers
Models
Routing
Execution
Roles
Skills
Tools
Evaluation
Learning
Security
Audit
Observability
Feature Flags
System Settings
```

---

## Config Lifecycle

```text
Draft
↓
Validate
↓
Preview
↓
Publish
↓
Version
↓
Monitor
↓
Rollback
```

---

## Admin Limits

Admin cannot disable core security invariants.

---

# 26. Public API

## Main endpoint

```text
POST /v1/execute
```

---

## Supporting

```text
GET /v1/executions/{id}
GET /v1/models
GET /v1/skills
GET /v1/usage
POST /v1/webhooks
```

---

## API Features

```text
API Keys
Scopes
Idempotency
Sync
Async
Streaming
Webhooks
Unified Errors
Versioning
```

---

## API Principle

Public API exposes:

```text
Task
Execution
Result
Usage
Status
```

ولا exposes internal implementation.

---

# 27. Security Fabric

```text
Edge Security
↓
Identity/Auth
↓
Authorization
↓
Capability Firewall
↓
Data Boundary
↓
Tool/Agent Sandbox
↓
Output Validation
↓
Audit / Detection / Response
```

---

# 28. AI Security Rules

يجب حماية من:

```text
Prompt Injection
Indirect Prompt Injection
Sensitive Information Disclosure
Excessive Agency
Tool Abuse
SSRF
Command Injection
Path Traversal
Malicious Skills
Supply Chain
Data Poisoning
Improper Output Handling
Unbounded Consumption
Cross-tenant Context Leakage
Secret Leakage
```

---

# 29. Capability Firewall

أي Model/Agent/Skill لا يملك direct authority.

قبل أي action:

```text
Identity
+
Permission
+
Entitlement
+
Resource
+
Scope
+
Policy
+
Approval
```

ثم:

```text
ALLOW
DENY
ALLOW_WITH_LIMIT
```

---

# 30. Production Architecture

## Initial

```text
Single Region
+
Multi-AZ
```

---

## API

Stateless + horizontally scalable.

---

## Database

```text
Primary
+
HA Standby
+
Backups
+
PITR
```

---

## Redis

HA.

---

## Workers

Autoscaled.

---

## Region Failure

Initial:

```text
DR Region
```

وليس Active/Active.

---

## Future

Multi-Region Active/Active فقط إذا requirements تستدعيها.

---

# 31. Deployment Philosophy

```text
Architecture stable
Deployment topology flexible
```

نبدأ:

```text
Modular Monolith
+
Workers
+
Workflow Runtime
```

ولا نبدأ Microservices بالكامل.

---

# 32. Kafka Policy

Kafka ليس default.

يمكن إدخاله لاحقًا عندما تصبح:

```text
Event throughput
Replay
Partitioning
Consumer scale
```

تبرر التعقيد.

---

# 33. Testing Architecture

لا يوجد اعتماد على Unit Tests فقط.

يجب وجود:

```text
Unit
Integration
Contract
Provider
Router
Execution
Security
Tenant Isolation
Quota
Concurrency
Load
Stress
Soak
Chaos
Evaluation Regression
Model Regression
E2E
```

---

# 34. Architecture Tests

يجب فحص الحدود:

```text
Core cannot import Provider internals
Router cannot execute HTTP
Model Registry cannot execute requests
Skill cannot bypass Tool Gateway
Memory cannot access Secrets
UI cannot access DB directly
```

---

# 35. Engineering Governance

كل Feature جديدة:

```text
Contract
Implementation
Tests
Security
Observability
Documentation
Rollback
```

---

# 36. Definition of Done

Feature لا تعتبر Done إلا عند:

```text
Code
+
Tests
+
Security
+
Observability
+
Documentation
+
Compatibility
+
Rollback
```

---

# 37. ADR Protocol

أي قرار معماري مهم:

```text
Context
Alternatives
Decision
Reason
Consequences
Status
```

لو تغير:

```text
Supersedes ADR-X
```

ولا يسمح بتغيير معماري significant بدون ADR.

---

# 38. Git Safety Protocol

قبل أي Mutation مهمة:

```text
Inspect
Plan
Modify
Verify
Test
Update State
Commit when approved
```

---

## ممنوع

```text
blind overwrite
force reset
destructive cleanup
assuming previous command succeeded
```

إلا بتفويض صريح وبـverification.

---

# 39. Project State System

الهيكل الإلزامي:

```text
engineering/
├── STATE.md
├── PROGRESS.md
├── DECISIONS.md
├── ACTIVE_TASK.md
├── BLOCKERS.md
├── VERIFY.md
├── RECOVERY.md
├── ADR/
└── HANDOFF/
```

---

## STATE.md

الحالة الحالية الفعلية.

---

## PROGRESS.md

ما تم إنجازه Verified.

---

## DECISIONS.md

القرارات المعتمدة.

---

## ACTIVE_TASK.md

المهمة الحالية فقط.

---

## BLOCKERS.md

ما يمنع التقدم.

---

## VERIFY.md

نتائج التحقق الفعلية.

---

## RECOVERY.md

تعليمات الاستئناف.

---

# 40. Resume Protocol

عند بدء أي Session جديدة:

```text
1. Read ENGINEERING_PROTOCOL.
2. Read STATE.
3. Read PROGRESS.
4. Read ACTIVE_TASK.
5. Read DECISIONS.
6. Read BLOCKERS.
7. Inspect Git status.
8. Inspect actual filesystem.
9. Compare documented state vs actual state.
10. Identify last verified state.
11. Run targeted verification.
12. Resume only from verified state.
```

---

## Critical Rule

**Never assume interrupted work succeeded.**

يجب التحقق من الواقع الفعلي.

---

# 41. Session Handoff

قبل إنهاء Session:

```text
Current Phase
Current Task
Completed
Verified
Unverified
Changed Files
Tests
Git State
Known Risks
Next Action
```

---

# 42. Phase Gates

المراحل:

```text
G0 Governance
G1 Contracts
G2 Identity/Security
G3 Storage
G4 Providers
G5 Models
G6 Accounts
G7 Router
G8 Execution
G9 Memory
G10 Roles
G11 Skills
G12 Tools
G13 Evaluation
G14 Billing
G15 Learning
G16 Public API
G17 Admin
G18 Observability
G19 Hardening
G20 Production
G21 Final Validation
```

كل Gate له:

```text
Entry Criteria
Tasks
Tests
Exit Criteria
Artifacts
Risks
```

---

# 43. Implementation Order

```text
Governance
↓
Contracts
↓
Identity/Security
↓
Storage
↓
Providers
↓
Models
↓
Accounts/Credentials
↓
Router
↓
Execution
↓
Memory
↓
Roles
↓
Skills
↓
Tools
↓
Evaluation
↓
Usage/Plans
↓
Learning
↓
Public API
↓
Admin
↓
Observability
↓
Hardening
↓
Production
↓
Final Validation
```

---

# 44. Change Management

أي تعديل على Architecture:

```text
Current Decision
↓
Problem/Evidence
↓
Impact Analysis
↓
Alternatives
↓
ADR
↓
Approval
↓
Migration Plan
↓
Implementation
↓
Verification
```

---

# 45. Recovery From Failure

لو حصل:

```text
Session interruption
Process crash
Partial mutation
Unexpected Git change
Test failure
Build failure
```

لا نستمر مباشرة.

نرجع:

```text
Known State
↓
Reality Check
↓
Reconcile
↓
Repair
↓
Verify
↓
Resume
```

---

# 46. Final Engineering Rule

> **Reality beats documentation.**

لو:

```text
STATE.md
```

يقول حاجة، لكن filesystem يقول حاجة أخرى:

**filesystem + Git + tests هم الحقيقة التشغيلية.**

ثم نصلح documentation.

---

# 47. Final Architecture Invariants

هذه أهم قواعد المشروع، ويجب ألا تُكسر:

```text
1. Core remains provider-agnostic.
2. Model is separate from Provider.
3. Provider is separate from Account.
4. Platform Credentials are separate from User Credentials.
5. Router decides; Execution executes.
6. Workflow Runtime owns workflow state.
7. Memory is not Verified Intelligence.
8. User Preference is not Truth.
9. Skill is not automatically a Tool.
10. Tool is never trusted by default.
11. LLM is not a Security Authority.
12. Security boundaries are enforced outside the LLM.
13. Training data requires eligibility and verification.
14. Admin configuration cannot break security invariants.
15. All important configuration is versioned.
16. At-least-once + idempotency is the reliability model.
17. Tenant isolation is enforced at multiple layers.
18. Secrets never enter normal logs.
19. Public API hides internal implementation.
20. Significant architecture changes require ADR.
21. Interrupted work must be verified before resume.
22. New extensibility must prefer registries/contracts over Core modification.
```

---

# 48. Final Project Philosophy

المشروع لا يجب أن يكون:

> **أكثر نظام ممكن تعقيدًا.**

بل:

> **أكثر نظام ممكن قدرةً، مع أقل قدر ضروري من التعقيد.**

لذلك:

```text
Strong Contracts
+
Simple Runtime Boundaries
+
Configurable Policies
+
Replaceable Implementations
+
Strict Security
+
Measured Evolution
```

---

# 49. Final Engineering Standard

أي مهندس أو AI يعمل على المشروع يجب أن يسأل قبل أي تغيير:

```text
هل هذا يخالف Contract؟
هل يكسر Boundary؟
هل يحتاج Config بدل Hardcode؟
هل يحتاج ADR؟
هل يؤثر على Security؟
هل يؤثر على Tenant Isolation؟
هل يوجد Test؟
هل يوجد Rollback؟
هل يمكن استبدال implementation لاحقًا؟
هل تم تحديث State؟
```

إذا لم يستطع الإجابة، **لا يبدأ التغيير**.

---

# 50. Final Resume Command

يجب أن يكون لدينا Resume Prompt ثابت في المشروع:

```text
RESUME PROJECT

You are continuing an existing engineered system.

Do not assume the previous session completed anything.

Read:
1. MASTER_ENGINEERING_PROTOCOL
2. STATE.md
3. PROGRESS.md
4. ACTIVE_TASK.md
5. DECISIONS.md
6. BLOCKERS.md
7. VERIFY.md
8. RECOVERY.md

Then inspect:
- actual filesystem
- git status
- relevant tests
- recent changes

Reconcile documented state with actual state.

Identify the last VERIFIED completed step.

Do not trust unverified claims.

Do not repeat completed work unless verification shows it is incomplete.

Do not modify architecture decisions silently.

If a new architectural decision is necessary:
STOP → document alternatives → create/update ADR → verify impact → then continue.

Continue only from the last verified state.

After every meaningful mutation:
- verify the result
- run relevant tests
- update STATE
- update PROGRESS
- record important decisions
- maintain recovery information

Never assume an interrupted operation succeeded.
Never overwrite unrelated work.
Never bypass security, testing, or phase gates.
```

---

## الحكم النهائي

بهذا البروتوكول أصبح عندنا **ثلاث طبقات واضحة**:

```text
MASTER ENGINEERING PROTOCOL
        ↓
MASTER ARCHITECTURE
        ↓
IMPLEMENTATION PLAN
```

والـResume System مستقل ومبني داخل البروتوكول نفسه، وليس مجرد Prompt محفوظ.

**المرحلة التالية المنطقية الآن ليست إضافة Architecture جديدة.**

هي أن نحول البروتوكول ده إلى **MASTER IMPLEMENTATION PLAN**: كل Phase بالتفصيل، الملفات/Modules التي ستُنشأ، Dependencies، Entry/Exit Criteria، Tests المطلوبة، وما الذي يجب أن يظل ممنوعًا في كل مرحلة. وبعدها نخرج منه **الـMaster Build Prompt** النهائي + **Resume Prompt** المختصر الثابت.