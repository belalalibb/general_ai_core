"""R160 — the SHARED agent surface composed into the real runtime profile.

Pins:
- the profile always composes an agent (strategy=agent is offered, never a
  silent "unavailable" on the default deployment);
- without AGENT_SOURCE_ROOT the catalog is EMPTY (pure-answer agent runs);
  with it, exactly the three read-only source tools are offered, over the
  ONE composed ToolRegistry;
- the demo tenant holds the read-only policy; a tenant that appears via the
  identity seam (register) is granted the SAME policy — one derivation;
- the composed source tools work through the runtime's authority chain and
  refuse escapes (jail) as recorded FAILED observations, never exceptions;
- the hermetic echo provider cannot drive an agent turn: the run stops
  ``invalid_proposal`` and the API answers a unified ``execution_failed``
  carrying the execution id — honest, never a fabricated success.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import httpx

from apps.composition.agent import (
    AGENT_TOOLS_ENTITLEMENT,
    READ_ONLY_AGENT_POLICY,
    SOURCE_READ_PERMISSION,
)
from apps.composition.runtime import RuntimeProfile, build_runtime_profile
from core.contracts.security import ActorKind, FirewallDecision, FirewallDecisionInput


def _profile(**env: str) -> RuntimeProfile:
    return build_runtime_profile(environ=env)


def _decision(profile: RuntimeProfile, tenant_id) -> FirewallDecision:
    assert profile.agent is not None
    return profile.agent.firewall.decide(
        FirewallDecisionInput(
            actor=ActorKind.USER,
            tenant_id=tenant_id,
            permission=SOURCE_READ_PERMISSION,
            resource="source:root",
            scope="tenant",
            entitlement=AGENT_TOOLS_ENTITLEMENT,
            approval_state=None,
            risk_level="low",
        )
    )


class TestCatalog:
    def test_default_profile_offers_agent_with_empty_catalog(self) -> None:
        profile = _profile()
        assert profile.agent is not None
        assert profile.agent.surface.offered() == []
        assert profile.agent.tool_registry.list_all() == []

    def test_source_root_offers_three_read_only_tools(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("x = 1\n")
        profile = _profile(AGENT_SOURCE_ROOT=str(tmp_path))
        assert profile.agent is not None
        names = [entry["name"] for entry in profile.agent.surface.offered()]
        assert names == ["source_list", "source_read", "source_search"]
        assert all(
            e["permission"] == SOURCE_READ_PERMISSION for e in profile.agent.surface.offered()
        )
        # Registered in the ONE composed registry (not a private one).
        assert {t.name for t in profile.agent.tool_registry.list_all()} == set(names)


class TestTenantGrants:
    def test_demo_tenant_holds_read_only_policy(self) -> None:
        profile = _profile()
        assert profile.demo_principal is not None
        assert _decision(profile, profile.demo_principal.tenant_id) is FirewallDecision.ALLOW
        assert _decision(profile, uuid4()) is FirewallDecision.DENY

    def test_registering_tenant_is_granted_via_identity_seam(self) -> None:
        profile = _profile()
        assert profile.identity is not None
        user = profile.identity.register("r160@example.com", "Sup3r-secret-pw!", "en")
        assert _decision(profile, user.tenant_id) is FirewallDecision.ALLOW

    def test_policy_is_read_only(self) -> None:
        assert READ_ONLY_AGENT_POLICY.granted_permissions == frozenset({SOURCE_READ_PERMISSION})
        assert READ_ONLY_AGENT_POLICY.approval_gated_permissions == frozenset()


class TestSourceToolsThroughRuntime:
    def test_read_and_jail_refusal_are_observations(self, tmp_path: Path) -> None:
        (tmp_path / "README.md").write_text("hello r160\n")
        profile = _profile(AGENT_SOURCE_ROOT=str(tmp_path))
        assert profile.agent is not None and profile.demo_principal is not None
        specs = profile.agent.surface.resolve(
            type("P", (), {"allowed": ["source_read"], "denied": []})()  # ToolsPolicy shape
        )
        read = specs[0]
        ok = asyncio.run(read.handler({"path": "README.md"}))
        assert ok["content"] == "hello r160\n" and ok["truncated"] is False
        # Jail escape → typed refusal surfaced as a ValueError the executor
        # records as status=failed (never an unhandled exception).
        try:
            asyncio.run(read.handler({"path": "../../etc/passwd"}))
        except ValueError as exc:
            assert "refused" in str(exc)
        else:  # pragma: no cover - defensive
            raise AssertionError("jail escape was not refused")


class TestEchoProfileHonesty:
    def test_echo_provider_cannot_drive_agent_turn_and_says_so(self) -> None:
        profile = _profile()

        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=profile.app), base_url="http://t"
            ) as client:
                response = await client.post(
                    "/v1/execute",
                    json={"ask": "inspect", "execution_policy": {"strategy": "agent"}},
                )
            assert response.status_code == 502, response.text
            error = response.json()["error"]
            assert error["code"] == "execution_failed"
            assert "execution_id" in error["details"]

        asyncio.run(scenario())
