#!/usr/bin/env python3
"""Contract Freeze Baseline — DERIVATION (R189, R189-DEC-01).

Derives ``contract_freeze_baseline.json`` from the LIVE contract objects of
the current tree (pydantic models, enums, frozen dataclasses, closed-set
constants) and from the LIVE FastAPI route table. Nothing here is a
hand-maintained roster: the module list below names WHICH modules are frozen
(the freeze decision); everything inside them is read by introspection, and
the served surface is read from the SAME app factory the platform serves.

Rules (Contract Freeze semantics, R189):
- ADDITIVE-ONLY AFTER FREEZE. The guard (tests/verification/
  test_contract_freeze_baseline.py) FAILS on any removal, rename, type or
  requiredness change of a frozen field, any enum-member change, any closed-set
  constant change, any served /v1 route removal. ADDITIONS are admitted only by
  re-deriving this baseline inside an explicitly declared round (``frozen_at``).
- No new served contract: this is a repository artifact + guard machinery.

Usage:
    python engineering/verification/contract_freeze_derive.py            # print JSON
    python engineering/verification/contract_freeze_derive.py --write [--round=rNNN]
    python engineering/verification/contract_freeze_derive.py --check    # exit 1 on drift
"""

from __future__ import annotations

import dataclasses
import enum
import importlib
import json
import sys
from pathlib import Path
from typing import Any, get_type_hints
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "engineering" / "verification" / "contract_freeze_baseline.json"

#: The FROZEN module set (the decision). Everything inside is introspected.
FROZEN_MODULES: tuple[str, ...] = (
    "core.contracts.provider",  # provider errors, request/response, manifest, health, rate limits
    "core.contracts.domain",  # Model / Provider / Binding entities
    "core.contracts.routing",  # RoutingRequest / RoutingDecision / ExclusionRecord
    "core.contracts.model_policy",  # ModelPolicy / NodeModelPolicy unions, FallbackScope
    "core.contracts.execute",  # ExecuteRequest, sync/async/stream events, webhooks
    "core.contracts.execution",  # Execution / ExecutionNode
    "core.contracts.execution_strategy",  # ExecutionStrategySpec (R188 C1)
    "core.contracts.model_listing",  # GET /v1/models rows
    "core.contracts.usage",  # usage ledger / budget / summary
    "core.contracts.learning",  # learning sample states
    "core.contracts.evaluation",  # verification levels, graders, evaluation records
    "core.contracts.errors",  # error envelope
    "core.learning.gates",  # 22 §9 / §11 condition sets + signals (no feedback field)
    "core.routing.capacity",  # resource-signal read vocabulary (R188 A1)
    "apps.api.provider_onboarding",  # admin onboarding request (P-R188-01)
)

#: Closed-set constants frozen by NAME (module-level values).
FROZEN_CONSTANTS: dict[str, tuple[str, ...]] = {
    "core.learning.gates": ("TRAINING_ELIGIBILITY_CONDITIONS", "PROMOTION_CONDITIONS"),
    "core.routing.capacity": (
        "DEFAULT_COOLDOWN_MS",
        "DEFAULT_UNAVAILABLE_MS",
        "RPM_WINDOW_SECONDS",
    ),
    "core.contracts.execution_strategy": ("MAX_STAGES", "MAX_PARALLEL"),
    "core.contracts.evaluation": ("VERIFICATION_LEVEL_ORDER",),
}


def _annotation(obj: Any) -> str:
    if isinstance(obj, type):
        return obj.__qualname__
    text = obj if isinstance(obj, str) else repr(obj)
    return text.replace("typing.", "")


def _jsonable(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    try:
        json.dumps(value)
    except TypeError:
        return repr(value)
    return value


def _pydantic_model(cls: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for name, info in cls.model_fields.items():
        if info.is_required():
            default: Any = "<required>"
        elif info.default_factory is not None:
            default = f"<factory:{getattr(info.default_factory, '__name__', 'factory')}>"
        else:
            default = _jsonable(info.default)
        fields[name] = {
            "annotation": _annotation(info.annotation),
            "required": info.is_required(),
            "default": default,
            "alias": info.alias,
        }
    config = getattr(cls, "model_config", {}) or {}
    return {
        "kind": "pydantic_model",
        "fields": fields,
        "extra": config.get("extra"),
        "frozen": config.get("frozen"),
    }


def _enum(cls: type[enum.Enum]) -> dict[str, Any]:
    return {"kind": "enum", "members": {m.name: m.value for m in cls}}


def _dataclass(cls: type) -> dict[str, Any]:
    hints = get_type_hints(cls)
    fields: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.default is not dataclasses.MISSING:
            default: Any = _jsonable(f.default)
        elif f.default_factory is not dataclasses.MISSING:
            default = "<factory>"
        else:
            default = "<required>"
        fields[f.name] = {"annotation": _annotation(hints.get(f.name, f.type)), "default": default}
    params = getattr(cls, "__dataclass_params__", None)
    return {"kind": "dataclass", "fields": fields, "frozen": bool(params and params.frozen)}


def _module_unions(mod: Any) -> dict[str, Any]:
    """Annotated discriminated unions declared at module level."""
    out: dict[str, Any] = {}
    for name, value in vars(mod).items():
        if name.startswith("_") or isinstance(value, type):
            continue
        text = repr(value)
        if "Annotated[" in text and "discriminator" in text:
            out[name] = {"kind": "discriminated_union", "annotation": _annotation(value)}
    return out


def _module_contracts(module_name: str) -> dict[str, Any]:
    mod = importlib.import_module(module_name)
    entries: dict[str, Any] = {}
    for name, obj in sorted(vars(mod).items()):
        if not isinstance(obj, type) or obj.__module__ != module_name or name.startswith("_"):
            continue
        if issubclass(obj, enum.Enum):
            entries[name] = _enum(obj)
        elif hasattr(obj, "model_fields"):
            entries[name] = _pydantic_model(obj)
        elif dataclasses.is_dataclass(obj):
            entries[name] = _dataclass(obj)
        elif issubclass(obj, Exception):
            entries[name] = {"kind": "exception", "bases": [b.__name__ for b in obj.__bases__]}
    entries.update(_module_unions(mod))
    constants: dict[str, Any] = {}
    for const in FROZEN_CONSTANTS.get(module_name, ()):
        value = getattr(mod, const)
        if isinstance(value, (tuple, list, frozenset, set)):
            value = [_jsonable(v) for v in value]
        constants[const] = value
    return {"contracts": entries, "constants": constants}


def _served_routes() -> list[dict[str, Any]]:
    """The served /v1 surface, read from the SAME app factory the platform serves.

    Hermetic composition (in-memory registries, no env, no provider call) with
    the optional seams bound so every conditionally mounted family is present.
    """
    from apps.api.admin import AdminSurface
    from apps.api.app import Principal, create_app
    from core.admin.service import AdminConfigService
    from core.audit.memory import InMemoryAuditLog
    from core.evaluation.memory import InMemoryEvaluationStore
    from core.execution.service import ExecutionService
    from core.providers.registry import BindingRegistry, ModelRegistry, ProviderRegistry
    from core.routing.router import SimpleScoringRouter
    from core.usage.memory import InMemoryUsageAccounting

    providers, models, bindings = ProviderRegistry(), ModelRegistry(), BindingRegistry()
    router = SimpleScoringRouter(providers, models, bindings)
    usage = InMemoryUsageAccounting()
    admin_service = AdminConfigService(
        providers=providers,
        models=models,
        usage=usage,
        routing=router,
        audit_log=InMemoryAuditLog(),
    )
    admin = AdminSurface(
        service=admin_service,
        providers=providers,
        models=models,
        usage=usage,
        routing=router,
        evaluations=InMemoryEvaluationStore(),
    )
    app = create_app(
        router=router,
        execution_service=ExecutionService(adapters={}, credential_refs={}, bindings=bindings),
        principal=Principal(tenant_id=uuid4(), user_id=uuid4(), is_admin=True),
        models=models,
        bindings=bindings,
        providers=providers,
        usage=usage,
        admin=admin,
        webhooks=True,
    )
    # The OpenAPI document is the served route truth (included routers are
    # flattened there; ``app.routes`` holds lazy router wrappers).
    paths = app.openapi()["paths"]
    rows: list[dict[str, Any]] = [
        {"path": path, "methods": sorted(m.upper() for m in ops if m != "head")}
        for path, ops in paths.items()
        if path.startswith("/v1/")
    ]
    rows.sort(key=lambda r: r["path"])
    return rows


def derive() -> dict[str, Any]:
    from core.routing.capacity import ResourceSignalBoard

    board = ResourceSignalBoard()
    board.record_attempt(provider_id=uuid4(), model_id=uuid4())
    (row,) = board.snapshot()
    return {
        "schema": "qevion.contract_freeze_baseline/1",
        "rule": (
            "ADDITIVE-ONLY AFTER FREEZE: removals, renames, type/requiredness changes, "
            "enum/closed-set changes and served-route removals FAIL the guard; additions "
            "are admitted only by re-deriving this baseline in an explicitly declared round."
        ),
        "derived_by": "engineering/verification/contract_freeze_derive.py",
        "frozen_modules": list(FROZEN_MODULES),
        "modules": {name: _module_contracts(name) for name in FROZEN_MODULES},
        "resource_signal_snapshot": {
            "keys": sorted(row.keys()),
            "states": ["available", "unavailable", "cooldown", "limited"],
        },
        "served_routes_v1": _served_routes(),
    }


def strip_volatile(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "frozen_at"}


def main(argv: list[str]) -> int:
    current = derive()
    if "--write" in argv:
        frozen_at: dict[str, Any] = {
            "round": "r189",
            "note": "baseline derived at the R189 gate of record",
        }
        if BASELINE.exists():
            frozen_at = json.loads(BASELINE.read_text()).get("frozen_at", frozen_at)
        for arg in argv:
            if arg.startswith("--round="):
                frozen_at = {"round": arg.split("=", 1)[1], "note": "re-derived by declared round"}
        BASELINE.write_text(json.dumps({**current, "frozen_at": frozen_at}, indent=2) + "\n")
        print(f"wrote {BASELINE.relative_to(ROOT)}")
        return 0
    if "--check" in argv:
        committed = strip_volatile(json.loads(BASELINE.read_text()))
        if committed == current:
            print("contract freeze baseline: MATCHES current tree")
            return 0
        print("contract freeze baseline: DRIFT detected (run the guard test for details)")
        return 1
    print(json.dumps(current, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
