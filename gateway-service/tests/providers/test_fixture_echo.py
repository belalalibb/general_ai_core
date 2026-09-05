"""Hermetic fixture_echo tests — the R174 §7 collision partner.

Proves: canonical success shape with the MARKER · schema policing ·
DEFINITION <-> HANDLERS parity · the declared model name is EXACTLY the one
AssemblyAI declares (the collision is intentional and pinned) · registration
is opt-in only (default app composition never registers it).
"""

from __future__ import annotations

import pytest

from gateway.contracts import (
    CredentialMode,
    ErrorCategory,
    GatewayOperation,
    ProviderContext,
)
from providers.assemblyai.definition import DEFINITION as ASSEMBLYAI_DEFINITION
from providers.fixture_echo.adapter import FIXTURE_ECHO_MARKER, HANDLERS, generate_text
from providers.fixture_echo.definition import COLLIDING_MODEL_NAME, DEFINITION


def _context(payload: dict[str, object] | None = None) -> ProviderContext:
    return ProviderContext(
        operation=GatewayOperation.GENERATE_TEXT,
        model=COLLIDING_MODEL_NAME,
        request_id="req_fx",
        tenant_id="ten_fx",
        credential_mode=CredentialMode.PLATFORM,
        credential_value=None,
        payload=payload
        if payload is not None
        else {"messages": [{"role": "user", "content": "say hi"}]},
        timeout_ms=1000,
    )


class TestCollisionIsPinned:
    def test_declares_exactly_assemblyais_model_name(self) -> None:
        aai_names = {m["name"] for m in ASSEMBLYAI_DEFINITION["models"]}  # type: ignore[index]
        fx_names = {m["name"] for m in DEFINITION["models"]}  # type: ignore[index]
        assert fx_names == {COLLIDING_MODEL_NAME}
        assert COLLIDING_MODEL_NAME in aai_names

    def test_platform_mode_no_key_no_health(self) -> None:
        assert DEFINITION["credential_mode"] == "platform"
        assert DEFINITION["health_supported"] is False

    def test_handlers_parity_with_definition(self) -> None:
        assert {op.value for op in HANDLERS} == set(DEFINITION["operations"])  # type: ignore[arg-type]


class TestFacade:
    async def test_success_is_canonical_and_carries_marker(self) -> None:
        result = await generate_text(_context())
        assert result.succeeded is True
        assert result.error is None
        assert result.output is not None
        assert set(result.output) == {"text", "finish_reason"}
        assert result.output["finish_reason"] == "stop"
        assert result.output["text"].startswith(FIXTURE_ECHO_MARKER)
        assert f"model={COLLIDING_MODEL_NAME}" in result.output["text"]
        assert "echo=say hi" in result.output["text"]
        assert result.usage is not None and result.usage.units == 1

    async def test_ignores_credential_value_entirely(self) -> None:
        ctx = _context().model_copy(update={"credential_value": "SHOULD-NEVER-APPEAR"})
        result = await generate_text(ctx)
        assert "SHOULD-NEVER-APPEAR" not in result.model_dump_json()

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"messages": []},
            {"messages": [{"role": "user", "content": ""}]},
            {"messages": [{"role": "user"}]},
            {"messages": ["not-a-dict"]},
        ],
    )
    async def test_bad_messages_is_bad_request(self, payload: dict[str, object]) -> None:
        result = await generate_text(_context(payload))
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST

    async def test_extra_payload_keys_rejected(self) -> None:
        result = await generate_text(
            _context({"messages": [{"role": "user", "content": "x"}], "tools": []})
        )
        assert result.succeeded is False
        assert result.error is not None
        assert result.error.category is ErrorCategory.BAD_REQUEST
        assert result.error.provider_code == "schema_extra_keys"


class TestRegistrationIsOptIn:
    def test_default_composition_does_not_register_fixture(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app import register_live_providers
        from gateway.provider_registry import ProviderRegistry

        monkeypatch.delenv("GW_ENABLE_FIXTURE_ECHO", raising=False)
        registry = ProviderRegistry()
        register_live_providers(registry)
        registry.eager_verify_all()
        assert registry.get("fixture_echo") is None
        assert registry.get("assemblyai") is not None
        assert registry.get("groq") is not None

    def test_opt_in_registers_fixture_alongside_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app import register_live_providers
        from gateway.provider_registry import ProviderRegistry

        monkeypatch.setenv("GW_ENABLE_FIXTURE_ECHO", "1")
        registry = ProviderRegistry()
        register_live_providers(registry)
        registry.eager_verify_all()
        fx = registry.get("fixture_echo")
        aai = registry.get("assemblyai")
        assert fx is not None and aai is not None
        # The collision is real: both slugs declare the same model name.
        assert {m.name for m in fx.definition.models} & {m.name for m in aai.definition.models} == {
            COLLIDING_MODEL_NAME
        }
