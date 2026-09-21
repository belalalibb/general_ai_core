"""R196-C (AD-3 "compose the existing built-in template registry").

The runtime profile composes ONE ``TemplateRegistry`` holding the ONE built-in
system template (``APP_FACTORY_TEMPLATE``), serves it on ``GET /v1/templates``
(tenant-authenticated — operator D4) and lets ``/v1/execute``
``mode="template"`` resolve it (operator D5; R191-C deferred proof).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import httpx

from apps.composition.runtime import DEV_DEMO_PRINCIPAL_ENV, build_runtime_profile
from core.agent.app_factory import APP_FACTORY_TEMPLATE
from core.contracts.agent_template import TemplateOrigin
from core.contracts.execution_strategy import ExecutionStrategySpec
from tests.security.test_r194_security_headers import ADMIN_EMAIL, USER_EMAIL, _session


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


async def _get(app: Any, path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path, headers=headers or {})


class TestBuiltInRegistryComposed:
    def test_profile_exposes_exactly_the_built_in_template(self) -> None:
        profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})
        assert profile.templates is not None
        assert [t.ref for t in profile.templates.list()] == [APP_FACTORY_TEMPLATE.ref]
        assert profile.templates.list(origin=TemplateOrigin.SYSTEM)[0] == APP_FACTORY_TEMPLATE
        r = run(_get(profile.app, "/v1/templates"))
        assert r.status_code == 200, r.text
        assert [row["ref"] for row in r.json()["templates"]] == [APP_FACTORY_TEMPLATE.ref]
        states = {row.id: row.state.value for row in profile.app.state.capability_catalog}
        assert states["templates.listing"] == "available"

    def test_reads_are_tenant_authenticated(self) -> None:
        profile = build_runtime_profile(environ={"ADMIN_EMAILS": ADMIN_EMAIL})
        anonymous = run(_get(profile.app, "/v1/templates"))
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "unauthenticated"
        user = _session(profile, USER_EMAIL)
        ok = run(_get(profile.app, "/v1/templates", {"Authorization": f"Bearer {user}"}))
        assert ok.status_code == 200
        detail = run(
            _get(
                profile.app,
                "/v1/templates/app_factory.plan",
                {"Authorization": f"Bearer {user}"},
            )
        )
        assert detail.status_code == 200 and detail.json()["id"] == "app_factory.plan"

    def test_template_mode_resolves_in_the_composed_executor(self) -> None:
        profile = build_runtime_profile(environ={DEV_DEMO_PRINCIPAL_ENV: "1"})
        resolved = profile.app.state.strategy_executor.resolve(
            ExecutionStrategySpec(mode="template", template_id="app_factory.plan")
        )
        assert resolved.mode == "custom"
        assert [s.key for s in resolved.stages] == ["inventory-summary", "architecture-plan", "review"]
