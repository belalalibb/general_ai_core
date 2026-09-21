"""R196-A (AD-3): template read models — a SUMMARY list entry and its envelope.

Additive to the non-frozen ``core.contracts.agent_template`` module. The list
entry is a projection of ``StrategyTemplate`` (no strategy body — the detail
route serves the full template, operator D3); ``TemplatesListResponse`` is the
envelope of ``GET /v1/templates``.
"""

from __future__ import annotations

from core.agent.app_factory import APP_FACTORY_TEMPLATE
from core.contracts.agent_template import (
    StrategyTemplate,
    TemplateListEntry,
    TemplateOrigin,
    TemplatesListResponse,
    TemplateStatus,
)


class TestTemplateListEntry:
    def test_projection_field_for_field(self) -> None:
        entry = TemplateListEntry.from_template(APP_FACTORY_TEMPLATE)
        t = APP_FACTORY_TEMPLATE
        assert entry.ref == t.ref == f"{t.id}@{t.version}"
        assert (entry.id, entry.version, entry.name) == (t.id, t.version, t.name)
        assert entry.origin is TemplateOrigin.SYSTEM
        assert entry.status is TemplateStatus.ACTIVE
        assert entry.description == t.description
        assert entry.tags == t.tags
        assert entry.stage_count == len(t.strategy.stages) == 3
        assert entry.stage_keys == [s.key for s in t.strategy.stages]
        assert entry.skills == t.skills
        assert entry.required_capabilities == t.required_capabilities

    def test_list_entry_carries_no_strategy_body(self) -> None:
        payload = TemplateListEntry.from_template(APP_FACTORY_TEMPLATE).model_dump(mode="json")
        assert "strategy" not in payload
        assert "instruction" not in str(payload)

    def test_envelope_round_trips(self) -> None:
        response = TemplatesListResponse(
            templates=[TemplateListEntry.from_template(APP_FACTORY_TEMPLATE)]
        )
        again = TemplatesListResponse.model_validate_json(response.model_dump_json())
        assert again == response
        # the detail shape IS the template contract (D3) — data round-trips whole
        assert StrategyTemplate.model_validate_json(APP_FACTORY_TEMPLATE.model_dump_json()) == (
            APP_FACTORY_TEMPLATE
        )
