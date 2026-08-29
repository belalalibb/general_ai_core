"""Route registry tests — revocation/disable without restart, anti-enumeration."""

from __future__ import annotations

from gateway.route_registry import RouteRegistry


def test_lookup_known_token() -> None:
    registry = RouteRegistry({"tok_a": "slug_a"})
    result = registry.lookup("tok_a")
    assert result.routable and result.slug == "slug_a"


def test_unknown_and_missing_tokens_unroutable() -> None:
    registry = RouteRegistry({"tok_a": "slug_a"})
    assert not registry.lookup("tok_b").routable
    assert not registry.lookup(None).routable
    assert not registry.lookup("").routable


def test_revocation_is_instant_no_restart() -> None:
    registry = RouteRegistry({"tok_a": "slug_a"})
    registry.revoke("tok_a")
    assert not registry.lookup("tok_a").routable


def test_disable_keeps_line_but_blocks_routing() -> None:
    registry = RouteRegistry({"tok_a": "slug_a"})
    registry.set_disabled("slug_a", True)
    result = registry.lookup("tok_a")
    assert result.disabled and not result.routable
    registry.set_disabled("slug_a", False)
    assert registry.lookup("tok_a").routable


def test_hot_reload_replaces_map_atomically() -> None:
    registry = RouteRegistry({"tok_a": "slug_a"})
    registry.reload({"tok_b": "slug_b"})
    assert not registry.lookup("tok_a").routable
    assert registry.lookup("tok_b").slug == "slug_b"
