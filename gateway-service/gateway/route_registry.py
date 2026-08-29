"""Route registry — route_token -> internal slug. Reloadable WITHOUT restart.

5-layer identity model (ADR-0008): the route_token is an opaque platform-
issued CREDENTIAL (not a name); the slug is gateway-private and NEVER
crosses the boundary. No derivation exists between layers.

Anti-enumeration: lookups distinguish nothing externally — unknown,
revoked and disabled tokens all yield the same uniform 404 body
(``contracts.UNKNOWN_ROUTE_BODY``). The distinction here is internal only.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteLookup:
    """Internal lookup result — NEVER serialized to the wire."""

    slug: str | None  # None => unknown/revoked
    disabled: bool = False

    @property
    def routable(self) -> bool:
        return self.slug is not None and not self.disabled


class RouteRegistry:
    """Thread-safe, hot-reloadable token->slug map.

    Revocation = removing the map line (instant uniform 404). Disabling a
    provider keeps the line but marks the slug disabled. Both take effect
    without restart via ``reload``/``set_disabled``.
    """

    def __init__(
        self,
        route_map: dict[str, str],
        disabled_slugs: frozenset[str] = frozenset(),
    ) -> None:
        self._lock = threading.Lock()
        self._validate(route_map)
        self._route_map = dict(route_map)
        self._disabled = set(disabled_slugs)

    @staticmethod
    def _validate(route_map: dict[str, str]) -> None:
        for token, slug in route_map.items():
            if not token or not slug:
                msg = "route map entries must have non-empty token and slug"
                raise ValueError(msg)

    def lookup(self, route_token: str | None) -> RouteLookup:
        if not route_token:
            return RouteLookup(slug=None)
        with self._lock:
            slug = self._route_map.get(route_token)
            if slug is None:
                return RouteLookup(slug=None)
            return RouteLookup(slug=slug, disabled=slug in self._disabled)

    def reload(self, route_map: dict[str, str]) -> None:
        """Replace the whole map atomically — no restart required."""

        self._validate(route_map)
        with self._lock:
            self._route_map = dict(route_map)

    def revoke(self, route_token: str) -> None:
        with self._lock:
            self._route_map.pop(route_token, None)

    def set_disabled(self, slug: str, disabled: bool) -> None:
        with self._lock:
            if disabled:
                self._disabled.add(slug)
            else:
                self._disabled.discard(slug)
