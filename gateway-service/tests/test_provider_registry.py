"""Provider registry tests — eager validation, OPEN-2, parity, duplicates."""

from __future__ import annotations

import pytest

from gateway.provider_registry import ProviderRegistry
from providers._example.definition import DEFINITION as EXAMPLE_DEFINITION


def _register_example(registry: ProviderRegistry, slug: str = "example_mock"):
    return registry.register(
        slug=slug,
        raw_definition=dict(EXAMPLE_DEFINITION),
        facade_module="providers._example.adapter",
    )


def test_register_and_lazy_handlers_parity_ok() -> None:
    registry = ProviderRegistry()
    provider = _register_example(registry)
    handlers = provider.handlers()  # lazy import + parity check
    assert {op.value for op in handlers} == {"generate_text"}


def test_duplicate_slug_is_startup_error() -> None:
    registry = ProviderRegistry()
    _register_example(registry)
    with pytest.raises(ValueError, match="duplicate provider slug"):
        _register_example(registry)


def test_excluded_operation_rejected_at_registration() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    definition["operations"] = ["generate_text", "run_provider_agent"]
    with pytest.raises(ValueError, match="OPEN-2"):
        registry.register("x", definition, "providers._example.adapter")


def test_declared_without_handler_fails_parity() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    # analyze_vision is declared but the example facade has no handler for it.
    definition["operations"] = ["generate_text", "analyze_vision"]
    provider = registry.register("y", definition, "providers._example.adapter")
    with pytest.raises(ValueError, match="parity"):
        provider.handlers()


def test_invalid_definition_fails_eagerly() -> None:
    registry = ProviderRegistry()
    definition = dict(EXAMPLE_DEFINITION)
    definition["definition_version"] = "not-semver"
    with pytest.raises(Exception):  # noqa: B017 — any validation failure is loud
        registry.register("z", definition, "providers._example.adapter")


def test_unregistered_slug_lookup_is_none() -> None:
    assert ProviderRegistry().get("ghost") is None
