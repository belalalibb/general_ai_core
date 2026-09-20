"""Template registry — declarative templates → runtime ExecutionStrategySpec (R191).

Authority: R191-DEC-01 (Part 5 Template system, Part 6 UI-manageable
configuration, Part 12 override model, Part 23 Q version semantics).

Recorded decisions:
- ONE strategy engine. This registry never executes anything; it PRODUCES an
  :class:`ExecutionStrategySpec` and exposes a read-only ``Mapping`` view so
  the EXISTING :class:`~core.execution.strategy.StrategyExecutor` consumes
  templates through its unchanged ``templates=`` seam (``mode="template"``).
- Identity ``(id, version)`` is immutable: registering the same pair twice is
  refused; a NEW version is a NEW record; older versions stay byte-identical.
- ``system`` ids are reserved: a non-system origin cannot register under an
  id that a system template owns (a user template must not shadow a built-in).
- Lifecycle: ``get(id)`` returns the LATEST ACTIVE version; disabled/archived
  records remain listable (``include_inactive=True``) but never selectable.
- Overrides are explicit and inspectable: :meth:`materialize` returns the
  runtime spec AND the list of :class:`OverrideRecord`s describing exactly
  what changed. An override naming an unknown stage is refused loudly.
- In-memory only in R191 (durability recorded as deferred, not pretended).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping

from core.contracts.agent_template import (
    OverrideRecord,
    StrategyTemplate,
    TemplateOrigin,
    TemplateOverride,
    TemplateStatus,
)
from core.contracts.execution_strategy import ExecutionStrategySpec


class TemplateError(Exception):
    """Base class for template registry refusals."""


class DuplicateTemplate(TemplateError):
    """Same ``(id, version)`` registered twice, or a system id shadowed."""


class TemplateNotFound(TemplateError):
    """No template (or no ACTIVE template) for the reference."""


class OverrideRejected(TemplateError):
    """An override referenced a stage the template does not have."""


def _version_key(version: str) -> tuple[tuple[int, str], ...]:
    """Natural ordering for versions like ``1``, ``1.2``, ``2.0.1``, ``1a``."""
    parts: list[tuple[int, str]] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        rest = piece[len(digits) :]
        parts.append((int(digits) if digits else -1, rest))
    return tuple(parts)


class _StrategyView(Mapping[str, ExecutionStrategySpec]):
    """Live read-only ``Mapping`` the EXISTING StrategyExecutor consumes.

    Keys: ``"<id>"`` (latest ACTIVE version) and ``"<id>@<version>"`` (pinned,
    ACTIVE only). Nothing is copied: a later registration is visible at once.
    """

    def __init__(self, registry: TemplateRegistry) -> None:
        self._registry = registry

    def __getitem__(self, key: str) -> ExecutionStrategySpec:
        template = self._registry.resolve_ref(key)
        if template is None:
            raise KeyError(key)
        return template.strategy

    def __iter__(self) -> Iterator[str]:
        return iter(self._registry.strategy_keys())

    def __len__(self) -> int:
        return len(self._registry.strategy_keys())

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self._registry.resolve_ref(key) is not None


class TemplateRegistry:
    """Versioned, origin-labelled registry of declarative strategy templates."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict[str, StrategyTemplate]] = {}

    # -- lifecycle -----------------------------------------------------------------

    def register(self, template: StrategyTemplate) -> StrategyTemplate:
        versions = self._by_id.setdefault(template.id, {})
        if template.version in versions:
            msg = f"template already registered: {template.ref}"
            raise DuplicateTemplate(msg)
        owners = {t.origin for t in versions.values()}
        if owners and template.origin is not TemplateOrigin.SYSTEM and TemplateOrigin.SYSTEM in owners:
            msg = f"template id {template.id!r} is owned by a system template; choose another id"
            raise DuplicateTemplate(msg)
        if owners and template.origin is TemplateOrigin.SYSTEM and TemplateOrigin.SYSTEM not in owners:
            msg = f"template id {template.id!r} is owned by a non-system template"
            raise DuplicateTemplate(msg)
        versions[template.version] = template
        return template

    def get(self, template_id: str, *, version: str | None = None) -> StrategyTemplate:
        versions = self._by_id.get(template_id)
        if not versions:
            msg = f"unknown template {template_id!r}"
            raise TemplateNotFound(msg)
        if version is not None:
            found = versions.get(version)
            if found is None:
                msg = f"unknown template version {template_id}@{version}"
                raise TemplateNotFound(msg)
            return found
        active = [t for t in versions.values() if t.status is TemplateStatus.ACTIVE]
        if not active:
            msg = f"no active version of template {template_id!r}"
            raise TemplateNotFound(msg)
        return max(active, key=lambda t: _version_key(t.version))

    def resolve_ref(self, ref: str) -> StrategyTemplate | None:
        """``"<id>"`` or ``"<id>@<version>"`` → ACTIVE template, else ``None``."""
        template_id, _, version = ref.partition("@")
        try:
            template = self.get(template_id, version=version or None)
        except TemplateNotFound:
            return None
        return template if template.status is TemplateStatus.ACTIVE else None

    def list(
        self, *, origin: TemplateOrigin | None = None, include_inactive: bool = False
    ) -> list[StrategyTemplate]:
        out: list[StrategyTemplate] = []
        for template_id in sorted(self._by_id):
            for version in sorted(self._by_id[template_id], key=_version_key):
                template = self._by_id[template_id][version]
                if origin is not None and template.origin is not origin:
                    continue
                if not include_inactive and template.status is not TemplateStatus.ACTIVE:
                    continue
                out.append(template)
        return out

    def strategy_keys(self) -> list[str]:
        keys: list[str] = []
        for template in self.list():
            keys.append(template.ref)
        for template_id in sorted(self._by_id):
            if self.resolve_ref(template_id) is not None:
                keys.append(template_id)
        return keys

    def as_strategy_mapping(self) -> Mapping[str, ExecutionStrategySpec]:
        """The seam the EXISTING ``StrategyExecutor(templates=...)`` consumes."""
        return _StrategyView(self)

    # -- overrides -----------------------------------------------------------------

    def materialize(
        self, ref: str, *, override: TemplateOverride | None = None
    ) -> tuple[ExecutionStrategySpec, list[OverrideRecord]]:
        """Template (+ explicit override) → runtime strategy + inspectable trail."""
        template = self.resolve_ref(ref)
        if template is None:
            msg = f"unknown or inactive template {ref!r}"
            raise TemplateNotFound(msg)
        return apply_override(template.strategy, override)


def apply_override(
    strategy: ExecutionStrategySpec, override: TemplateOverride | None
) -> tuple[ExecutionStrategySpec, list[OverrideRecord]]:
    """Pure, additive override application (Part 12) — no hidden priority rules.

    Precedence is explicit: a per-stage policy wins over ``model_policy_all``
    for that stage; both are recorded.
    """
    if override is None or override.is_empty:
        return strategy, []
    known = {stage.key for stage in strategy.stages}
    unknown = sorted(set(override.stage_model_policies) - known)
    if unknown:
        msg = f"override names unknown stage(s): {unknown}"
        raise OverrideRejected(msg)
    records: list[OverrideRecord] = []
    stages = []
    for stage in strategy.stages:
        policy = stage.model_policy
        if override.model_policy_all is not None:
            policy = override.model_policy_all
            records.append(
                OverrideRecord(
                    field="model_policy",
                    stage_key=stage.key,
                    detail=f"model_policy_all -> {policy.type}",
                )
            )
        if stage.key in override.stage_model_policies:
            policy = override.stage_model_policies[stage.key]
            records.append(
                OverrideRecord(
                    field="model_policy",
                    stage_key=stage.key,
                    detail=f"stage_model_policies -> {policy.type}",
                )
            )
        stages.append(stage.model_copy(update={"model_policy": policy}))
    update: dict[str, object] = {"stages": stages}
    if override.max_parallel is not None and override.max_parallel != strategy.max_parallel:
        update["max_parallel"] = override.max_parallel
        records.append(
            OverrideRecord(
                field="max_parallel",
                detail=f"{strategy.max_parallel} -> {override.max_parallel}",
            )
        )
    return ExecutionStrategySpec.model_validate(
        {**strategy.model_dump(), **{k: (v if k != "stages" else [s.model_dump() for s in stages]) for k, v in update.items()}}
    ), records
