# 09 — Skill & Tool Specification

```text
STATUS: SUPERSEDED — NOT AUTHORITATIVE (T-DOC-008)
AUTHORITATIVE SUCCESSOR:
docs/ai_orchestration_pack/final_docs_v3/14_SKILLS_AND_TOOLS.md
This file is retained as V2 baseline material only. Do not edit; do not cite as authority.
```

---

## 1. Definitions

```text
Skill = instruction/workflow/capability module that guides how work is done.
Tool = external or local capability used to execute actions.
```

Skill is not automatically a Tool. Tool is never trusted by default.

---

## 2. Skill Manifest

```yaml
id: code_review
name: Code Review
version: 1.0.0
type: instruction
source: local
status: active

capabilities:
  - coding
  - reasoning

inputs:
  schema: null

outputs:
  format: markdown

requires_tools:
  optional:
    - github.read
  required: []

permissions_requested: []

runtime:
  invocation: user_or_model
  compatible_roles:
    - software_engineer
    - reviewer
```

---

## 3. Skill Import Lifecycle

```text
imported
↓
scanned
↓
validated
↓
reviewed
↓
approved
↓
active
```

External sources are references, not runtime dependencies.

Every imported skill becomes a local version with:

```text
source_url
source_version
checksum
imported_at
reviewed_by
local_version
```

---

## 4. Tool Manifest

```yaml
id: github
name: GitHub
version: 1.0.0
location: server
status: active

permissions:
  - github.repo.read
  - github.branch.create
  - github.commit.create
  - github.pr.create
  - github.pr.merge

input_schema: {}
output_schema: {}

credentials:
  supported_owners:
    - platform
    - user

approval_policy:
  github.repo.read: none
  github.commit.create: before_action
  github.pr.merge: always

sandbox_policy:
  network: restricted
  filesystem: none
```

---

## 5. Tool Locations

```text
server: runs on platform backend
client: runs on user's device/browser/IDE/local runtime
hybrid: coordinated between server and client
```

Examples:

```text
GitHub API → server
Browser automation → client/hybrid
Local filesystem → client
Terminal → client
Database service → server
```

---

## 6. Client Runtime

Client tools require:

```text
device pairing
device trust state
permission grants
revocation
heartbeat
operation audit
```

Device states:

```text
paired
trusted
revoked
expired
compromised
```

---

## 7. Capability Firewall Check

Every tool call must pass:

```text
identity
tenant
permission
entitlement
resource ownership
scope
approval policy
tool sandbox policy
rate limit
audit
```

---

## 8. GitHub Tool Permissions

```text
github.repo.read
github.issue.read
github.issue.write
github.branch.create
github.commit.create
github.pr.create
github.pr.review
github.pr.merge
```

Default write operations require approval.

---

## 9. Forbidden

```text
Skill grants security permissions.
Tool executes without Capability Firewall.
Client tool runs on server by assumption.
Tool logs secrets.
Imported skill becomes active without review.
LLM decides final permission.
```

---

## 10. Tests

```text
skill manifest validation
skill import checksum
malicious skill blocked
tool permission denied by default
tool approval flow
client device revoked
github write requires approval
skill cannot bypass tool policy
```

---

## 11. Provider-Agent Tool Use

Some provider-agent models may have their own provider-side tools.

These tools are not automatically trusted.

They must be classified as:

```text
provider_internal_tool
platform_tool
hybrid_tool
unknown_tool
```

Rules:

```text
unknown provider-side tools default to DENY or disabled mode
provider-side write tools require explicit admin policy
platform tools still use Capability Firewall
provider agent tool traces must be recorded where available
```
