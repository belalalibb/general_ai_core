"""Admin control-plane contracts — config lifecycle (MVP Phase 7 slice 3).

T-IMPL-031 (41 §46 "admin models/providers/plans/routing"). Spec anchors
(21_ADMIN_CONTROL_PLANE.md), re-read before coding per the task ruling:

- 21 §1: everything configurable must be versioned / validated /
  previewable / audited / rollbackable — those five properties ARE the
  shape of this module: :class:`ConfigChange` carries validation_result +
  impact_preview; versions and rollback targets are per-area monotonic
  identities managed by the admin service; auditing lands through the
  EXISTING audit seam (core/contracts/audit.py AdminChangeRecord, 21 §8).
- 21 §2: the full admin-module list is carried VERBATIM as the closed
  :class:`AdminArea` set (21 values, nothing added or dropped).
  ``MVP_ACTIVE_ADMIN_AREAS`` marks the FOUR areas 41 §46 names for the MVP
  ("admin models/providers/plans/routing") — the R049 pattern from
  ``MVP_ACTIVE_GRADER_TYPES``: the rest are representable but inert;
  naming them is denied loudly, never silently accepted.
- 21 §3: configuration lifecycle Draft → Validate → Preview Impact →
  Publish → Observe → Rollback. States here: DRAFT / VALIDATED / REJECTED
  / PUBLISHED / ROLLED_BACK. "Preview Impact" is an ACT on a validated
  draft (it produces ``impact_preview``, 21 §8), not a distinct state;
  "Observe" is runtime behavior of the published config, not a state.
- 21 §4 control matrix: admin can control models enable/disable + weights,
  providers enable/disable, plan units/limits, routing weights — and
  CANNOT break deny-by-default security / tenant isolation / accounting
  integrity. Structurally honored: the closed :class:`AdminAction` set
  contains ONLY control-matrix "can control" verbs; there is no action
  that touches a "cannot break" column, and non-MVP areas (Security, ...)
  have no actions at all this phase.

EXACT SLICE SCOPE (recorded per the task ruling): model enable/disable,
provider enable/disable, plan configuration (21 §5 units/limits via the
EXISTING usage seam), routing scoring weights (21 §6 weights via the
EXISTING router default-weights seam). NOT in this slice: model tiers,
provider accounts, model-control levels (21 §10), provider-agent
administration (21 §11–§12), skills/tools/learning/security admin — all
representable in :class:`AdminArea` but with no active actions.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel, JsonObject, utc_now

# --- Closed admin-module set (21 §2, verbatim) ---------------------------------


class AdminArea(StrEnum):
    """Admin modules (21 §2) — closed set, carried verbatim (21 values)."""

    OVERVIEW = "overview"
    USERS = "users"
    TENANTS = "tenants"
    PLANS = "plans"
    PROVIDERS = "providers"
    PROVIDER_ACCOUNTS = "provider_accounts"
    USER_CREDENTIALS_POLICY = "user_credentials_policy"
    MODELS = "models"
    MODEL_TIERS = "model_tiers"
    ROUTING_POLICIES = "routing_policies"
    EXECUTION_POLICIES = "execution_policies"
    ROLES = "roles"
    SKILLS = "skills"
    TOOLS = "tools"
    EVALUATION = "evaluation"
    LEARNING = "learning"
    SECURITY = "security"
    AUDIT = "audit"
    OBSERVABILITY = "observability"
    FEATURE_FLAGS = "feature_flags"
    SYSTEM_SETTINGS = "system_settings"


# Areas with ACTIVE admin actions in MVP Phase 7 (41 §46 verbatim:
# "admin models/providers/plans/routing"). Everything else is representable
# but inert — naming it raises InactiveAdminArea, never a silent no-op.
MVP_ACTIVE_ADMIN_AREAS: frozenset[AdminArea] = frozenset(
    {
        AdminArea.MODELS,
        AdminArea.PROVIDERS,
        AdminArea.PLANS,
        AdminArea.ROUTING_POLICIES,
    }
)


# --- Lifecycle (21 §3) ----------------------------------------------------------


class ConfigLifecycleState(StrEnum):
    """21 §3 lifecycle as data. REJECTED = validation failed (terminal)."""

    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PUBLISHED = "published"
    ROLLED_BACK = "rolled_back"


# --- Actions (21 §4 "Admin Can Control" column, MVP subset) ---------------------


class AdminAction(StrEnum):
    """Closed action set — ONLY control-matrix "can control" verbs.

    Deny-by-default (20 §4): an action string outside this set never
    parses; an action used under the wrong area is rejected at validation.
    """

    ENABLE_MODEL = "enable_model"
    DISABLE_MODEL = "disable_model"
    ENABLE_PROVIDER = "enable_provider"
    DISABLE_PROVIDER = "disable_provider"
    SET_PLAN = "set_plan"
    SET_ROUTING_WEIGHTS = "set_routing_weights"


# Each action belongs to EXACTLY ONE area (mismatch = invalid change).
ACTION_AREA: dict[AdminAction, AdminArea] = {
    AdminAction.ENABLE_MODEL: AdminArea.MODELS,
    AdminAction.DISABLE_MODEL: AdminArea.MODELS,
    AdminAction.ENABLE_PROVIDER: AdminArea.PROVIDERS,
    AdminAction.DISABLE_PROVIDER: AdminArea.PROVIDERS,
    AdminAction.SET_PLAN: AdminArea.PLANS,
    AdminAction.SET_ROUTING_WEIGHTS: AdminArea.ROUTING_POLICIES,
}


# --- The change record -----------------------------------------------------------


class ConfigChange(ContractModel):
    """One config-lifecycle item (21 §1 properties as fields).

    Frozen like every contract: the admin service advances lifecycle state
    by REPLACING the stored instance (``model_copy``), so no historical
    state is ever mutated in place. ``tenant_id`` scopes visibility of the
    change record itself (20 §6); ``actor_id`` is the 21 §8 "who".
    """

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    actor_id: UUID
    area: AdminArea
    action: AdminAction
    payload: JsonObject = Field(default_factory=dict)
    state: ConfigLifecycleState = ConfigLifecycleState.DRAFT
    created_at: datetime = Field(default_factory=utc_now)
    validation_result: BoundedStr | None = None
    impact_preview: BoundedStr | None = None
    published_version: BoundedStr | None = None


# --- API request/read shapes (T-IMPL-032, MVP Phase 7 slice 4) -------------------


class AdminDraftRequest(ContractModel):
    """POST /v1/admin/changes body: the action + its payload, nothing more.

    The area is DERIVED from the action (ACTION_AREA) and tenant/actor come
    from the authenticated principal — clients never claim identity fields.
    """

    action: AdminAction
    payload: JsonObject = Field(default_factory=dict)


class LearningDashboard(ContractModel):
    """21 §7 learning-dashboard read model — PLACEHOLDER in MVP Phase 7.

    Field-for-field from the 21 §7 admin view list (verified samples, gold
    samples, dataset coverage, task coverage, specialist models, accuracy
    trends, cost reduction, teacher agreement, canary status, promotion
    history, rollback actions). R049 boundary (a): NO learning machinery
    exists in this phase, so the surface serves HONEST empty/zero values
    with an EXPLICIT placeholder marker — fabricated metrics would fake a
    lifecycle (22 §8–§11) that was never built. ``placeholder`` is a
    Literal[True]: this shape structurally CANNOT claim to be real data;
    when the learning lifecycle lands, a non-placeholder variant replaces
    it consciously (contract change, not silent flag flip).
    """

    placeholder: Literal[True] = True
    verified_samples: Annotated[int, Field(ge=0)] = 0
    gold_samples: Annotated[int, Field(ge=0)] = 0
    dataset_coverage: JsonObject = Field(default_factory=dict)
    task_coverage: JsonObject = Field(default_factory=dict)
    specialist_models: tuple[BoundedStr, ...] = ()
    accuracy_trends: tuple[JsonObject, ...] = ()
    cost_reduction: float | None = None
    teacher_agreement: float | None = None
    canary_status: BoundedStr | None = None
    promotion_history: tuple[JsonObject, ...] = ()
    rollback_actions: tuple[JsonObject, ...] = ()
