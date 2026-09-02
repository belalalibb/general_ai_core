"""Public agent seam for ``POST /v1/execute`` (``execution_policy.strategy = "agent"``).

The API owns NO agent logic: it resolves the caller's ``tools`` policy
against the composition-declared catalog and hands the run to the SHARED
``core.agent.AgentRuntime`` (the same runtime the Admin agent and any future
external app consume). Authority stays where it already lives — the ONE
Capability Firewall decides per tenant at dispatch time; the catalog only
names what the deployment is *able* to offer (20 §4: unknown ⇒ deny).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from core.agent import AgentRuntime, AgentToolSpec
from core.contracts.execute import ToolsPolicy

AGENT_STRATEGY = "agent"


class AgentToolsRejected(ValueError):
    """The request named a tool the deployment does not offer."""

    def __init__(self, unknown: Sequence[str]) -> None:
        self.unknown = list(unknown)
        super().__init__(f"unknown agent tools: {', '.join(self.unknown)}")


@dataclass(frozen=True)
class AgentSurface:
    """Composition-declared agent capability: runtime + offered tool catalog."""

    runtime: AgentRuntime
    catalog: Mapping[str, AgentToolSpec] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, spec in self.catalog.items():
            if name != spec.name:
                msg = f"catalog key {name!r} != tool name {spec.name!r}"
                raise ValueError(msg)

    def offered(self) -> list[dict[str, object]]:
        """Data view of the catalog (what a client may request by name)."""
        return [self.catalog[name].describe() for name in sorted(self.catalog)]

    def resolve(self, policy: ToolsPolicy | None) -> list[AgentToolSpec]:
        """Select the tools this run may see (progressive disclosure).

        - ``tools`` absent / empty allow-list ⇒ NO tools (pure-answer run;
          never "all tools" — deny-by-default).
        - unknown names ⇒ :class:`AgentToolsRejected` (loud, never dropped).
        - ``denied`` overrides ``allowed``; order = allow-list order, deduped.
        """
        if policy is None or not policy.allowed:
            return []
        unknown = [name for name in policy.allowed if name not in self.catalog]
        if unknown:
            raise AgentToolsRejected(unknown)
        denied = set(policy.denied)
        selected: list[AgentToolSpec] = []
        seen: set[str] = set()
        for name in policy.allowed:
            if name in denied or name in seen:
                continue
            seen.add(name)
            selected.append(self.catalog[name])
        return selected
