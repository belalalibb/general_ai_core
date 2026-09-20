"""R192 G2 (H1/H2) — pin the canonical layering discovered in the R192 review.

Verified facts this guard turns into tests:
* ``GeneralAgent`` COMPOSES the two execution authorities (StrategyExecutor for
  model stages; AgentRuntime for tool loops) and owns none of them: it never
  imports a Router, ExecutionService, ToolCallGate, ToolExecutor, or provider
  adapter, and never reaches GitHub/httpx.
* ``core.agent.app_factory`` owns no engine either — it contributes DATA
  (template ref + notes) and reads existing registries.
* The App Factory template contains no generation/tool stage: generation is a
  TOOL class action owned by ``AgentRuntime`` + firewall chain (H7 map).
* ``POST /v1/execute`` refuses ``execution_strategy`` together with
  ``execution_policy.strategy=agent`` — the two authorities are never stacked
  on one request (already pinned upstream; re-asserted here by source).
"""

from __future__ import annotations

import ast
from pathlib import Path

import core.agent.app_factory as app_factory
import core.agent.general as general
from core.agent.general import GeneralAgent
from core.contracts.execution_strategy import StageKind

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_IMPORT_PREFIXES = (
    "core.routing",
    "core.providers.adapters",
    "core.tools.gate",
    "core.tools.executor",
    "apps.",
    "httpx",
)


def _imports(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class TestGeneralAgentOwnsNoAuthority:
    def test_general_and_app_factory_import_no_router_execution_tool_or_transport(
        self,
    ) -> None:
        for module in (general, app_factory):
            assert module.__file__ is not None
            offending = {
                name
                for name in _imports(Path(module.__file__))
                if name.startswith(FORBIDDEN_IMPORT_PREFIXES) or name == "core.execution.service"
            }
            assert offending == set(), f"{module.__name__} imports an authority: {offending}"

    def test_general_agent_exposes_only_plan_and_execute(self) -> None:
        public = {n for n in dir(GeneralAgent) if not n.startswith("_")}
        assert public == {"PLATFORM_AUTHORITY", "plan", "execute"}

    def test_platform_authority_names_the_deterministic_controls(self) -> None:
        assert set(GeneralAgent.PLATFORM_AUTHORITY) >= {
            "authorization",
            "capability_firewall",
            "tool_approval",
            "tenant_isolation",
            "routing",
            "audit",
        }


class TestAppFactoryTemplateHasNoToolStage:
    def test_template_stage_kinds_are_model_only(self) -> None:
        kinds = {s.kind for s in app_factory.APP_FACTORY_TEMPLATE.strategy.stages}
        assert kinds <= {StageKind.GENERATE, StageKind.REVIEW, StageKind.RETEST}
        assert not any("generat" in s.key for s in app_factory.APP_FACTORY_TEMPLATE.strategy.stages)

    def test_application_plan_defers_generation_by_type(self) -> None:
        field = app_factory.ApplicationPlan.model_fields["generation_deferred"]
        assert field.default is True


class TestExecuteNeverStacksTheTwoAuthorities:
    def test_api_source_refuses_strategy_plus_agent(self) -> None:
        src = (ROOT / "apps" / "api" / "app.py").read_text(encoding="utf-8")
        assert "execution_strategy cannot be combined with execution_policy.strategy=agent" in src
