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
from core.contracts.base import JsonObject
from core.contracts.execute import ToolsPolicy
from core.contracts.skills import Skill

AGENT_STRATEGY = "agent"


class AgentToolsRejected(ValueError):
    """The request named a tool the deployment does not offer."""

    def __init__(self, unknown: Sequence[str]) -> None:
        self.unknown = list(unknown)
        super().__init__(f"unknown agent tools: {', '.join(self.unknown)}")


@dataclass(frozen=True)
class AgentToolSelection:
    """What ONE agent run may see, and why (skill → tool intelligence).

    ``tools``          the disclosed specs, allow-list order then skill order.
    ``by_skill``       tool name → skill names whose manifest required it
                       (disclosure the caller did not spell out by hand).
    ``unavailable``    skill name → required tool names this deployment does
                       NOT offer — a named gap (never silently dropped, never
                       invented). Rides the task as data so the model knows.
    """

    tools: tuple[AgentToolSpec, ...] = ()
    by_skill: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    unavailable: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def describe(self) -> JsonObject:
        return {
            "disclosed": [spec.name for spec in self.tools],
            "by_skill": {k: list(v) for k, v in self.by_skill.items()},
            "unavailable": {k: list(v) for k, v in self.unavailable.items()},
        }


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
        """Allow-list-only selection (see :meth:`select`)."""
        return list(self.select(policy).tools)

    def select(
        self, policy: ToolsPolicy | None, skills: Sequence[Skill] = ()
    ) -> AgentToolSelection:
        """Select the tools this run may see (progressive disclosure).

        - ``tools`` absent / empty allow-list AND no skills ⇒ NO tools
          (pure-answer run; never "all tools" — deny-by-default).
        - unknown allow-list names ⇒ :class:`AgentToolsRejected` (loud).
        - admitted SKILLS disclose their manifest's ``requires_tools`` when
          the catalog offers them (03 §8: a skill can require tools but
          never bypass tool permissions — the firewall still decides per
          call); required tools the deployment lacks are a NAMED gap.
        - ``denied`` overrides everything; order = allow-list, then skills.
        """
        allowed = list(policy.allowed) if policy is not None else []
        denied = set(policy.denied) if policy is not None else set()
        unknown = [name for name in allowed if name not in self.catalog]
        if unknown:
            raise AgentToolsRejected(unknown)
        selected: list[AgentToolSpec] = []
        seen: set[str] = set()
        for name in allowed:
            if name in denied or name in seen:
                continue
            seen.add(name)
            selected.append(self.catalog[name])
        by_skill: dict[str, list[str]] = {}
        unavailable: dict[str, list[str]] = {}
        for skill in skills:
            for name in skill.manifest.requires_tools.required:
                if name in denied:
                    continue
                if name not in self.catalog:
                    unavailable.setdefault(skill.name, []).append(name)
                    continue
                by_skill.setdefault(name, []).append(skill.name)
                if name not in seen:
                    seen.add(name)
                    selected.append(self.catalog[name])
        return AgentToolSelection(
            tools=tuple(selected),
            by_skill={k: tuple(v) for k, v in by_skill.items()},
            unavailable={k: tuple(v) for k, v in unavailable.items()},
        )
