"""R196-B (AD-3): read-only ``GET /v1/templates`` + ``GET /v1/templates/{ref}``.

- absent seam ⇒ routes absent (404) and ``templates.listing`` INERT (20 §4)
- bound ⇒ list serves ACTIVE SYSTEM templates only (USER-origin and DISABLED
  excluded), ref-ordered; detail serves the FULL template (operator D3) for
  ``id`` and ``id@version``; unknown / inactive / non-system ⇒ 404
  ``validation_error`` (the existing unknown-resource convention)
- tenant-authenticated like /v1/skills (operator D4): tokenless ⇒ 401
- ``strategy_templates`` and ``templates`` together ⇒ ValueError (one source)
- the executor consumes the SAME registry (template mode resolves)
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from apps.api import create_app
from apps.api.capabilities import CAPABILITY_IDS
from core.agent.app_factory import APP_FACTORY_TEMPLATE
from core.contracts.agent_template import StrategyTemplate, TemplateOrigin, TemplateStatus
from core.contracts.execution_strategy import ExecutionStrategySpec, StageKind, StrategyStage
from core.execution.service import ExecutionService
from core.execution.templates import TemplateRegistry
from core.routing.router import SimpleScoringRouter
from tests.api.test_execute_api import World


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _no_sleep(_seconds: float) -> None:
    return None


def _app(world: World, **kwargs: Any) -> FastAPI:
    router = SimpleScoringRouter(world.providers, world.models, world.bindings)
    service = ExecutionService(
        adapters={world.provider.id: world.adapter},
        credential_refs={world.provider.id: f"secret-ref://{world.provider.id}"},
        bindings=world.bindings,
        max_retries_per_candidate=0,
        usage=world.usage,
        sleeper=_no_sleep,
    )
    return create_app(
        router=router,
        execution_service=service,
        store=world.store,
        principal=world.principal,
        **kwargs,
    )


async def _get(app: FastAPI, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers or {})


def _template(
    template_id: str,
    version: str,
    *,
    origin: TemplateOrigin = TemplateOrigin.SYSTEM,
    status: TemplateStatus = TemplateStatus.ACTIVE,
) -> StrategyTemplate:
    return StrategyTemplate(
        id=template_id,
        version=version,
        name=f"{template_id} {version}",
        origin=origin,
        status=status,
        strategy=ExecutionStrategySpec(
            mode="custom",
            stages=[StrategyStage(key="only", kind=StageKind.GENERATE, instruction="do it")],
        ),
    )


def _registry() -> TemplateRegistry:
    registry = TemplateRegistry()
    registry.register(APP_FACTORY_TEMPLATE)
    registry.register(_template("coding.default", "1"))
    registry.register(_template("coding.default", "2", status=TemplateStatus.DISABLED))
    registry.register(_template("tenant.private", "1", origin=TemplateOrigin.USER))
    return registry


def _states(app: FastAPI) -> dict[str, str]:
    return {row.id: row.state.value for row in app.state.capability_catalog}


class TestAbsentSeam:
    def test_routes_absent_and_capability_inert(self) -> None:
        app = _app(World())
        assert run(_get(app, "/v1/templates")).status_code == 404
        assert run(_get(app, "/v1/templates/app_factory.plan")).status_code == 404
        assert "templates.listing" in CAPABILITY_IDS
        assert _states(app)["templates.listing"] == "inert"

    def test_two_template_sources_is_a_composition_error(self) -> None:
        with pytest.raises(ValueError, match="templates"):
            _app(World(), templates=_registry(), strategy_templates={})


class TestList:
    def test_lists_active_system_templates_ref_ordered(self) -> None:
        app = _app(World(), templates=_registry())
        r = run(_get(app, "/v1/templates"))
        assert r.status_code == 200, r.text
        rows = r.json()["templates"]
        assert [row["ref"] for row in rows] == [APP_FACTORY_TEMPLATE.ref, "coding.default@1"]
        assert all(row["origin"] == "system" and row["status"] == "active" for row in rows)
        assert "strategy" not in rows[0]
        assert rows[0]["stage_count"] == 3
        assert _states(app)["templates.listing"] == "available"


class TestDetail:
    def test_full_template_by_id_and_by_ref(self) -> None:
        app = _app(World(), templates=_registry())
        by_id = run(_get(app, "/v1/templates/app_factory.plan"))
        by_ref = run(_get(app, f"/v1/templates/{APP_FACTORY_TEMPLATE.ref}"))
        assert by_id.status_code == by_ref.status_code == 200
        assert by_id.json() == by_ref.json()
        assert StrategyTemplate.model_validate(by_id.json()) == APP_FACTORY_TEMPLATE
        assert by_id.json()["strategy"]["stages"][0]["key"] == "inventory-summary"

    @pytest.mark.parametrize(
        "ref",
        ["ghost", "coding.default@2", "coding.default@9", "tenant.private", "tenant.private@1"],
        ids=["unknown", "disabled-version", "unknown-version", "user-origin", "user-origin-ref"],
    )
    def test_unknown_inactive_or_non_system_is_404_validation_error(self, ref: str) -> None:
        app = _app(World(), templates=_registry())
        r = run(_get(app, f"/v1/templates/{ref}"))
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "validation_error"


class TestExecutorSharesRegistry:
    def test_template_mode_resolves_through_the_bound_registry(self) -> None:
        app = _app(World(), templates=_registry())
        executor = app.state.strategy_executor
        resolved = executor.resolve(
            ExecutionStrategySpec(mode="template", template_id="app_factory.plan")
        )
        assert resolved.mode == "custom" and len(resolved.stages) == 3
