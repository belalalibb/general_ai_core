"""R191-B — App Factory first vertical slice (RED first).

The slice: GitHub connection → repo inspection → project inventory → QEVION
capability inventory → skill inventory → strategy selection (a DATA template)
→ model policy → provider routing policy → application plan. Generation is
deferred by directive; nothing here writes code or opens PRs.

Boundaries proven here (R191 directive Parts 8/12/22):
* App Factory is a *capability* of the General Agent (registered in the ONE
  ``AgentCapabilityRegistry``), not a second engine/router/registry.
* Its strategy is a versioned DATA template registered in the ONE
  ``TemplateRegistry`` and executed by the ONE ``StrategyExecutor``.
* Inspection is read-only, bounded, and reaches GitHub only through httpx;
  tests use ``httpx.MockTransport`` — ZERO live calls.
* The token rides only the request header of the inspecting call; it never
  lands in the inventory, the plan, or any exception text.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from apps.agent_dev.git_tools import TransportError
from apps.agent_dev.project_inspector import GitHubProjectInspector
from core.agent.app_factory import (
    APP_FACTORY_CAPABILITY_NAME,
    APP_FACTORY_TEMPLATE,
    AppFactoryCapability,
    ProjectInventory,
    build_application_plan,
    qevion_inventory,
)
from core.agent.general import (
    AgentCapabilityRegistry,
    GeneralAgent,
    GeneralAgentRequest,
    PlanRefused,
)
from core.contracts.agent_template import TemplateOrigin, TemplateOverride
from core.contracts.model_policy import ExplicitModelPolicy
from core.contracts.skills import SkillStatus
from core.execution.strategy import StrategyExecutor
from core.execution.templates import TemplateRegistry
from core.roles.registry import SkillRegistry
from tests.api.test_node_mapping_and_auto_skills import make_skill
from tests.routing.test_r188_capacity_signals import World, _run

REMOTE = "https://github.com/acme/shop.git"
TOKEN = "ghp_TESTTOKEN_never_persisted"

_TREE = [
    {"path": "README.md", "type": "blob", "size": 10},
    {"path": "pyproject.toml", "type": "blob", "size": 200},
    {"path": "package.json", "type": "blob", "size": 90},
    {"path": "src", "type": "tree"},
    {"path": "src/app.py", "type": "blob", "size": 1000},
    {"path": "src/util.py", "type": "blob", "size": 300},
    {"path": "web/index.ts", "type": "blob", "size": 400},
    {"path": "web/App.tsx", "type": "blob", "size": 400},
    {"path": "Dockerfile", "type": "blob", "size": 50},
    {"path": "tests/test_app.py", "type": "blob", "size": 120},
]


def _github(
    *,
    ref_status: int = 200,
    tree_status: int = 200,
    tree: list[dict[str, Any]] | None = None,
    truncated: bool = False,
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path == "/repos/acme/shop/git/ref/heads/main":
            if ref_status != 200:
                return httpx.Response(ref_status, json={"message": "Not Found"})
            return httpx.Response(200, json={"object": {"sha": "c0ffee", "type": "commit"}})
        if path == "/repos/acme/shop/git/trees/c0ffee":
            if tree_status != 200:
                return httpx.Response(tree_status, json={"message": "boom"})
            return httpx.Response(
                200,
                json={
                    "sha": "c0ffee",
                    "tree": tree if tree is not None else _TREE,
                    "truncated": truncated,
                },
            )
        return httpx.Response(404, json={"message": f"unexpected {path}"})

    return httpx.MockTransport(handler), seen


def _inventory(**overrides: Any) -> ProjectInventory:
    base: dict[str, Any] = {
        "remote_url": REMOTE,
        "branch": "main",
        "head_sha": "c0ffee",
        "file_count": 9,
        "paths": ["README.md", "pyproject.toml", "src/app.py"],
        "languages": {"python": 3},
        "manifests": ["pyproject.toml"],
        "truncated": False,
    }
    base.update(overrides)
    return ProjectInventory.model_validate(base)


class TestInspectorIsReadOnlyAndBounded:
    def test_inspect_builds_bounded_inventory_from_ref_and_tree(self) -> None:
        transport, seen = _github()
        inspector = GitHubProjectInspector(transport=transport, max_paths=5)
        inv = _run(inspector.inspect(REMOTE, "main", token=TOKEN))
        assert inv.remote_url == REMOTE and inv.branch == "main" and inv.head_sha == "c0ffee"
        assert inv.file_count == 9  # blobs only, the "src" tree entry is not a file
        assert len(inv.paths) == 5 and inv.truncated is True  # bounded, and says so
        assert inv.languages == {
            "python": 3,
            "typescript": 2,
            "markdown": 1,
            "toml": 1,
            "json": 1,
            "dockerfile": 1,
        }
        assert inv.manifests == ["Dockerfile", "package.json", "pyproject.toml"]
        # exactly two GET calls, both authenticated per call, no mutation verbs
        assert [r.method for r in seen] == ["GET", "GET"]
        assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in seen)
        assert seen[1].url.params.get("recursive") == "1"
        # the token is NOT in the inventory
        assert TOKEN not in inv.model_dump_json()

    def test_inspect_refuses_non_github_remote_and_missing_branch_loudly(self) -> None:
        transport, seen = _github(ref_status=404)
        inspector = GitHubProjectInspector(transport=transport)
        with pytest.raises(TransportError, match="not a github.com"):
            _run(inspector.inspect("git@github.com:acme/shop.git", "main", token=TOKEN))
        assert seen == []  # refused BEFORE any network call
        with pytest.raises(TransportError, match="branch 'main' not found") as info:
            _run(inspector.inspect(REMOTE, "main", token=TOKEN))
        assert TOKEN not in str(info.value)

    def test_inspect_surfaces_tree_errors_without_the_token(self) -> None:
        transport, _ = _github(tree_status=500)
        inspector = GitHubProjectInspector(transport=transport)
        with pytest.raises(TransportError, match="http 500") as info:
            _run(inspector.inspect(REMOTE, "main", token=TOKEN))
        assert TOKEN not in str(info.value)

    def test_github_truncation_flag_is_propagated(self) -> None:
        transport, _ = _github(truncated=True)
        inv = _run(GitHubProjectInspector(transport=transport).inspect(REMOTE, "main", token=TOKEN))
        assert inv.truncated is True


class TestQevionInventoryUsesCoreRegistries:
    def test_inventory_is_read_through_existing_registries(self) -> None:
        world = World(["alpha", "beta"])
        skills = SkillRegistry()
        skills.register(make_skill(manifest_id="fastapi"))
        skills.register(make_skill(manifest_id="draft", status=SkillStatus.IMPORTED))
        caps = AgentCapabilityRegistry()
        caps.register(AppFactoryCapability(inspector=None).as_capability())
        inv = qevion_inventory(models=world.models, skills=skills, capabilities=caps)
        assert inv.models == ["shared-model"]
        assert inv.model_capabilities == {"shared-model": ["reasoning"]}
        assert inv.skills == ["fastapi"]  # selectable only — the ONE registry rule
        assert inv.capabilities == [f"{APP_FACTORY_CAPABILITY_NAME}@1"]


class TestAppFactoryIsACapabilityNotAnEngine:
    def test_template_is_data_and_system_owned(self) -> None:
        assert APP_FACTORY_TEMPLATE.id == "app_factory.plan"
        assert APP_FACTORY_TEMPLATE.origin is TemplateOrigin.SYSTEM
        assert APP_FACTORY_TEMPLATE.strategy.mode == "custom"
        assert [s.key for s in APP_FACTORY_TEMPLATE.strategy.stages] == [
            "inventory-summary",
            "architecture-plan",
            "review",
        ]
        stages = {s.key: s for s in APP_FACTORY_TEMPLATE.strategy.stages}
        assert stages["review"].kind == "review" and stages["review"].depends_on == [
            "architecture-plan"
        ]
        # a plain JSON round-trip proves "template is data" (no code inside)
        dumped = json.loads(APP_FACTORY_TEMPLATE.model_dump_json())
        assert dumped["strategy"]["stages"][0]["key"] == "inventory-summary"

    def test_slice_plans_through_the_general_agent_and_executes_via_the_one_executor(
        self,
    ) -> None:
        world = World(["alpha", "beta"])
        templates = TemplateRegistry()
        templates.register(APP_FACTORY_TEMPLATE)
        skills = SkillRegistry()
        skills.register(make_skill(manifest_id="fastapi"))
        caps = AgentCapabilityRegistry()
        inventory = _inventory()
        factory = AppFactoryCapability(inspector=None)
        caps.register(factory.as_capability())
        executor = StrategyExecutor(
            router=world.router,
            execution=world.service,
            templates=templates.as_strategy_mapping(),
            clock=lambda: world.now,
        )
        agent = GeneralAgent(
            executor=executor, templates=templates, skills=skills, capabilities=caps
        )
        plan = agent.plan(
            GeneralAgentRequest(
                ask="build an admin dashboard for this shop",
                capability=APP_FACTORY_CAPABILITY_NAME,
                skills=["fastapi"],
                # Part 9 chain: the runtime override on top of the template is EXPLICIT
                override=TemplateOverride(
                    model_policy_all=ExplicitModelPolicy(
                        type="explicit_model", model_id="shared-model"
                    )
                ),
                context={"project_inventory": inventory.model_dump(mode="json")},
            )
        )
        assert plan.capability == f"{APP_FACTORY_CAPABILITY_NAME}@1"
        assert plan.template_ref == "app_factory.plan@1"
        assert [s.key for s in plan.strategy.stages] == [
            "inventory-summary",
            "architecture-plan",
            "review",
        ]
        assert plan.skills == ["fastapi"]
        # the override is applied AND recorded per stage (Part 9 chain, no hidden rule)
        assert all(s.model_policy is not None for s in plan.strategy.stages)
        assert {(r.field, r.stage_key) for r in plan.overrides_applied} == {
            ("model_policy", "inventory-summary"),
            ("model_policy", "architecture-plan"),
            ("model_policy", "review"),
        }
        report = _run(
            agent.execute(
                plan,
                tenant_id=world.model.id,
                user_id=world.model.id,
                ask="build an admin dashboard for this shop",
                request_hash="h",
            )
        )
        assert report.succeeded and len(report.outcomes) == 3
        # provider routing policy honoured: every stage landed on a provider of the ONE model
        for outcome in report.outcomes:
            assert outcome.report is not None
            attempts = outcome.report.nodes[0].attempts
            assert {a.candidate.model_id for a in attempts} == {world.model.id}

    def test_application_plan_record_is_inspectable_and_defers_generation(self) -> None:
        world = World(["alpha"])
        skills = SkillRegistry()
        skills.register(make_skill(manifest_id="fastapi"))
        caps = AgentCapabilityRegistry()
        caps.register(AppFactoryCapability(inspector=None).as_capability())
        qinv = qevion_inventory(models=world.models, skills=skills, capabilities=caps)
        templates = TemplateRegistry()
        templates.register(APP_FACTORY_TEMPLATE)
        executor = StrategyExecutor(
            router=world.router,
            execution=world.service,
            templates=templates.as_strategy_mapping(),
            clock=lambda: world.now,
        )
        agent = GeneralAgent(
            executor=executor, templates=templates, skills=skills, capabilities=caps
        )
        plan = agent.plan(
            GeneralAgentRequest(
                ask="x",
                capability=APP_FACTORY_CAPABILITY_NAME,
                context={"project_inventory": _inventory().model_dump(mode="json")},
            )
        )
        app_plan = build_application_plan(
            ask="x", project=_inventory(), qevion=qinv, agent_plan=plan
        )
        assert app_plan.generation_deferred is True
        assert app_plan.project.head_sha == "c0ffee"
        assert app_plan.strategy_template == "app_factory.plan@1"
        assert app_plan.model_policy == "auto"  # nothing pinned -> AUTO, stated explicitly
        assert app_plan.provider_routing == "same-model-fallback-preferred"
        assert app_plan.qevion.capabilities == [f"{APP_FACTORY_CAPABILITY_NAME}@1"]
        assert "generation" not in {s.key for s in plan.strategy.stages}
        assert TOKEN not in app_plan.model_dump_json()

    def test_capability_refuses_when_no_inventory_and_no_inspector(self) -> None:
        caps = AgentCapabilityRegistry()
        caps.register(AppFactoryCapability(inspector=None).as_capability())
        world = World(["alpha"])
        templates = TemplateRegistry()
        templates.register(APP_FACTORY_TEMPLATE)
        executor = StrategyExecutor(
            router=world.router,
            execution=world.service,
            templates=templates.as_strategy_mapping(),
            clock=lambda: world.now,
        )
        agent = GeneralAgent(
            executor=executor, templates=templates, skills=SkillRegistry(), capabilities=caps
        )
        with pytest.raises(PlanRefused, match="project_inventory"):
            agent.plan(GeneralAgentRequest(ask="x", capability=APP_FACTORY_CAPABILITY_NAME))

    def test_capability_can_use_a_pre_inspected_inventory_port(self) -> None:
        class Port:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str]] = []

            def inspect(self, remote_url: str, branch: str) -> ProjectInventory:
                self.calls.append((remote_url, branch))
                return _inventory(remote_url=remote_url, branch=branch)

        port = Port()
        contribution = AppFactoryCapability(inspector=port).contribute(
            GeneralAgentRequest(
                ask="x",
                capability=APP_FACTORY_CAPABILITY_NAME,
                context={"remote_url": REMOTE, "branch": "dev"},
            )
        )
        assert port.calls == [(REMOTE, "dev")]
        assert contribution.template_ref == "app_factory.plan@1"
        assert any("dev" in n for n in contribution.notes)
        assert contribution.strategy is None  # the template is the strategy; no second engine


def test_no_live_network_in_this_module() -> None:
    """Belt-and-braces: the inspector must never build a client without a transport in tests."""
    inspector = GitHubProjectInspector(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(TransportError):
        asyncio.run(inspector.inspect(REMOTE, "main", token=TOKEN))
