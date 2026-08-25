# 04 — API Contracts

---

## 1. Public API Principles

The API exposes tasks and results, not internal implementation.

It must support:

```text
Versioning
Authentication
Idempotency
Sync / Async
Streaming
Webhooks
Unified errors
Tenant isolation
```

---

## 2. Main Endpoint

```http
POST /v1/execute
```

### Request

```json
{
  "ask": "راجع الكود ده أو ابنِ بوست تسويقي لمنتج كذا",
  "mode": "auto",
  "conversation_id": "optional-uuid",
  "project_id": "optional-uuid",
  "role": {
    "type": "system",
    "id": "senior_software_architect"
  },
  "model_policy": {
    "type": "auto",
    "tier": "medium",
    "explicit_model_id": null,
    "allow_fallback": true,
    "fallback_scope": "same_tier"
  },
  "execution_policy": {
    "strategy": "auto",
    "async": false,
    "stream": false,
    "max_cost_units": 3,
    "approval_required_for_tools": true
  },
  "tools": {
    "allowed": ["github", "browser"],
    "denied": [],
    "approval_mode": "before_write"
  },
  "context": {
    "attachments": [],
    "metadata": {},
    "language": "ar"
  },
  "output": {
    "format": "markdown",
    "language": "ar",
    "schema": null
  },
  "webhook_url": null
}
```

### Required Fields

```text
ask
```

Everything else has policy-driven defaults.

---

## 3. Response — Sync Success

```json
{
  "execution_id": "uuid",
  "status": "succeeded",
  "result": {
    "type": "message",
    "content": "final answer",
    "format": "markdown",
    "artifacts": []
  },
  "usage": {
    "units_reserved": 2,
    "units_settled": 2,
    "details": {}
  },
  "evaluation": {
    "visible": false,
    "level": "EVALUATED",
    "summary": null
  }
}
```

---

## 4. Response — Async Accepted

```json
{
  "execution_id": "uuid",
  "status": "queued",
  "poll_url": "/v1/executions/uuid"
}
```

---

## 5. Execution Status

```http
GET /v1/executions/{id}
```

```json
{
  "execution_id": "uuid",
  "status": "running",
  "progress": {
    "current_stage": "review",
    "percent": 65
  },
  "result": null,
  "error": null
}
```

---

## 6. Models Endpoint

```http
GET /v1/models
```

```json
{
  "models": [
    {
      "id": "model_uuid",
      "name": "example-max",
      "tier": "max",
      "modalities": ["text", "vision"],
      "capabilities": ["reasoning", "coding"],
      "availability": "available"
    }
  ]
}
```

---

## 7. Skills Endpoint

```http
GET /v1/skills
```

```json
{
  "skills": [
    {
      "id": "code_review",
      "version": "1.0.0",
      "status": "active",
      "requires_tools": ["github"]
    }
  ]
}
```

---

## 8. Usage Endpoint

```http
GET /v1/usage
```

```json
{
  "plan": "pro",
  "task_units": {
    "limit": 100,
    "used": 37,
    "remaining": 63
  },
  "modality_limits": {
    "image_generation": {
      "limit": 20,
      "used": 4
    }
  }
}
```

---

## 9. Unified Error Format

```json
{
  "error": {
    "code": "capability_denied",
    "message": "This tool is not allowed for the current user or plan.",
    "retryable": false,
    "details": {
      "capability": "github.pr.merge"
    },
    "trace_id": "trace-id"
  }
}
```

### Error Categories

```text
validation_error
unauthenticated
unauthorized
entitlement_exceeded
capability_denied
provider_unavailable
model_unavailable
tool_approval_required
rate_limited
execution_failed
internal_error
```

---

## 10. Idempotency

Clients should send:

```http
Idempotency-Key: unique-client-key
```

Same tenant + same idempotency key should not create duplicate executions.

---

## 11. Streaming

Streaming response events:

```json
{"type":"execution_started","execution_id":"uuid"}
{"type":"node_started","node":"planner"}
{"type":"delta","content":"partial text"}
{"type":"node_completed","node":"reviewer"}
{"type":"final","result":{}}
{"type":"error","error":{}}
```

---

## 12. Webhooks

Webhook event types:

```text
execution.queued
execution.started
execution.waiting_approval
execution.succeeded
execution.failed
execution.cancelled
```

Webhook payload:

```json
{
  "event": "execution.succeeded",
  "execution_id": "uuid",
  "tenant_id": "uuid",
  "timestamp": "iso-date",
  "data": {}
}
```

---

## 13. Advanced Model Control Contract

The API must support full user/developer control over model selection while preserving security, entitlement, availability, and provider/account constraints.

Supported model policy types:

```text
auto
tier
explicit_model
explicit_models
agent_node_mapping
```

---

### 13.1 Model Policy — Auto

The Router chooses the best eligible model/provider/account.

```json
{
  "model_policy": {
    "type": "auto",
    "allow_fallback": true,
    "fallback_scope": "same_tier"
  }
}
```

---

### 13.2 Model Policy — Tier

The user constrains selection to a tier.

```json
{
  "model_policy": {
    "type": "tier",
    "tier": "medium",
    "allow_fallback": true,
    "fallback_scope": "same_tier"
  }
}
```

Allowed tiers are admin-configurable, for example:

```text
fast
medium
max
custom
```

---

### 13.3 Model Policy — Explicit Model

The user selects one model.

```json
{
  "model_policy": {
    "type": "explicit_model",
    "model_id": "model_coding_strong",
    "provider_id": null,
    "allow_fallback": false,
    "fallback_scope": "none"
  }
}
```

Rules:

```text
1. User explicit model choice has priority over Router preference.
2. Router must still verify entitlement, availability, policy, provider health, and credentials.
3. If provider_id is null, Router may choose any eligible provider serving the selected model.
4. If provider_id is set, Router must use that provider unless unavailable and fallback is allowed.
5. If allow_fallback=false and the model/provider is unavailable, return a clear error.
```

---

### 13.4 Model Policy — Explicit Models

The user selects a list of models and a strategy.

```json
{
  "model_policy": {
    "type": "explicit_models",
    "models": [
      {"model_id": "model_a", "provider_id": null},
      {"model_id": "model_b", "provider_id": null},
      {"model_id": "model_c", "provider_id": "provider_x"}
    ],
    "selection_strategy": "parallel_compare",
    "judge_policy": {
      "type": "tier",
      "tier": "max"
    },
    "allow_partial": true,
    "allow_fallback": true,
    "fallback_scope": "same_model_different_provider"
  }
}
```

Supported selection strategies:

```text
fallback_chain        Try models in order until one succeeds.
parallel_compare      Send to multiple models, evaluate outputs, return best/aggregated result.
best_of_n             Generate N alternatives and select best by evaluator.
debate                Multiple models critique/argue, then judge/finalizer produces answer.
specialist_roles      Assign models to roles such as planner, coder, reviewer, judge.
```

---

### 13.5 Agent Node Model Mapping

In Agent Mode, the client may specify model policies per execution node or role.

```json
{
  "mode": "agent",
  "agent_policy": {
    "workflow": "code_review_and_patch",
    "default_model_policy": {
      "type": "tier",
      "tier": "medium"
    },
    "node_model_policies": {
      "planner": {
        "type": "tier",
        "tier": "medium"
      },
      "code_analyzer": {
        "type": "explicit_model",
        "model_id": "model_coding_strong",
        "allow_fallback": true,
        "fallback_scope": "same_model_different_provider"
      },
      "patch_generator": {
        "type": "explicit_model",
        "model_id": "model_coding_fast"
      },
      "security_reviewer": {
        "type": "tier",
        "tier": "max"
      },
      "final_judge": {
        "type": "explicit_models",
        "models": [
          {"model_id": "judge_a"},
          {"model_id": "judge_b"}
        ],
        "selection_strategy": "parallel_compare"
      }
    }
  }
}
```

Rules:

```text
1. Node-level policy overrides request-level model_policy.
2. Missing node policy falls back to agent_policy.default_model_policy.
3. Missing default falls back to request model_policy.
4. Missing request model_policy falls back to Router auto policy.
5. Every selected model must pass entitlement, security, availability, and provider/account checks.
```

---

### 13.6 Model Control Error Codes

```text
model_not_allowed
model_not_found
model_unavailable
provider_not_allowed
provider_unavailable
explicit_model_fallback_disabled
model_strategy_not_allowed
node_model_policy_invalid
judge_model_required
parallel_model_limit_exceeded
```

Example:

```json
{
  "error": {
    "code": "explicit_model_fallback_disabled",
    "message": "The selected model is unavailable and fallback is disabled.",
    "retryable": false,
    "details": {
      "model_id": "model_coding_strong"
    }
  }
}
```
