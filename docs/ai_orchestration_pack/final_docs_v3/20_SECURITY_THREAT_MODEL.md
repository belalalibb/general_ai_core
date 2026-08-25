# 20 — Security Threat Model
## AI Orchestration Platform

```text
STATUS: AUTHORITATIVE (V3)
CREATED_BY_TASK: T-DOC-009
SUPERSEDES:
  final_docs_v2/10_SECURITY_THREAT_MODEL.md
MIGRATION_TYPE: CARRY (verbatim)
DECISION_PRESERVATION: Security position, trust boundaries, threats and
mitigations, Capability Firewall (deny-by-default), secrets rules, tenant
isolation, AI-specific output validation, approval requirements, audit
events, security tests, and provider-agent security risks carried
unchanged. No decision changed.
RELATED_AUTHORITY:
  Tool-level firewall checks:    final_docs_v3/14_SKILLS_AND_TOOLS.md
  Provider-agent orchestration:  final_docs_v3/12_EXECUTION_GRAPH_AND_AGENT_MODE.md
```

---

## 1. Security Position

The LLM is untrusted for authority decisions.

Security boundaries must be enforced by deterministic platform code, not prompts.

---

## 2. Trust Boundaries

```text
User Browser / External Client
↓
Public API Boundary
↓
Identity / Session Boundary
↓
Tenant Boundary
↓
Authorization / Entitlement Boundary
↓
Capability Firewall
↓
Tool / Provider Boundary
↓
Secrets Boundary
↓
Data / Storage Boundary
```

---

## 3. Threats and Mitigations

| Threat | Example | Mitigation |
|---|---|---|
| Prompt Injection | User tells model to ignore policies | Policies enforced outside LLM |
| Indirect Injection | Web page instructs agent to leak secrets | Content isolation + tool permission checks |
| Secret Leakage | Provider key appears in logs | Secret manager + redaction + no plaintext logs |
| Cross-Tenant Leakage | Memory from user A used for B | tenant filters at app/data/db layers |
| Tool Abuse | Agent merges PR without approval | Capability Firewall + approval gates |
| SSRF | Tool fetches internal metadata URL | network allowlists/denylists |
| Command Injection | Terminal tool executes unsafe command | sandbox + approval + command policy |
| Malicious Skills | Imported skill contains unsafe instructions | scan/validate/review/approve lifecycle |
| Data Poisoning | Bad outputs enter training | verification + eligibility + sanitization |
| Unbounded Spend | Agent loops using max models | cost budgets + quotas + backpressure |
| Account Abuse | Provider account overused | leases + rate limits + cooldown |
| Admin Misconfig | Admin disables security | security invariants non-configurable |

---

## 4. Capability Firewall

Required decision inputs:

```json
{
  "actor": "user_or_system",
  "tenant_id": "uuid",
  "permission": "github.pr.create",
  "resource": "repo:owner/name",
  "scope": "project",
  "entitlement": "github_write",
  "approval_state": "approved|null",
  "risk_level": "medium"
}
```

Output:

```text
ALLOW
DENY
ALLOW_WITH_LIMIT
REQUIRE_APPROVAL
```

---

## 5. Secrets Rules

```text
Secrets stored only in Secret Manager/KMS-backed system.
DB stores credential_ref only.
No secrets in logs.
No secrets in prompts unless explicitly required and scoped.
No secrets in evaluation evidence.
No secrets in training data.
```

---

## 6. Tenant Isolation Rules

Enforced at:

```text
API request context
service/repository layer
database query filters
optional row-level security
audit verification
```

Every tenant-scoped table must include tenant_id where applicable.

---

## 7. AI-Specific Output Validation

Validate before using model output for:

```text
tool calls
code execution
SQL queries
file paths
URLs
permissions
configuration changes
training samples
```

---

## 8. Approval Required For

```text
external write actions
financially expensive tasks
credential use beyond read-only
local filesystem mutation
terminal execution
PR merge
publishing admin config
training promotion
```

---

## 9. Audit Events

Must audit:

```text
login/logout
credential create/revoke
provider account use
permission denied
tool call
approval decision
admin config publish/rollback
security policy change
training dataset promotion
cross-tenant access denial
```

---

## 10. Security Tests

```text
authentication
authorization
IDOR
tenant isolation
prompt injection
tool abuse
SSRF
path traversal
secret redaction
malicious skill import
admin invariant protection
provider credential isolation
```

---

## 11. Provider-Agent Security Risks

Provider-agent models introduce additional risks because some execution state or tool behavior may be managed by the provider.

Risks:

```text
opaque provider-side tool use
provider-managed thread/run state leakage
reduced step-level observability
unexpected provider-side actions
harder cost prediction
provider agent ignoring platform intent
```

Mitigations:

```text
provider-agent capability must be explicitly declared
provider-agent usage must be policy-controlled
provider-side tools default to disabled unless approved
all provider-agent runs must be tenant-scoped
platform tools still require Capability Firewall
provider-agent outputs must pass evaluation/output validation
sensitive tasks may require platform-native Execution Graph instead
```

---

# V2 → V3 TRACEABILITY

| V3 Section | V2 Source |
|---|---|
| 1–11 (security position, trust boundaries, threats/mitigations, Capability Firewall, secrets rules, tenant isolation, AI output validation, approvals, audit events, security tests, provider-agent security risks) | v2 10 §1–11, carried verbatim |

CARRY migration: content unchanged; only the V3 authority header and this
traceability section were added. Capability Firewall and deny-by-default
rules were not modified.
