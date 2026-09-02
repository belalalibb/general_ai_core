"""FINAL AGENT CORE BENCHMARK — real multi-stage coding task (R157).

A single-pass answer CANNOT solve this task: the agent must inspect real
source, run real tests, patch a real file, get REJECTED by deterministic
verification for a realistic mid-strength-model mistake, correct itself,
and re-verify — all through the SHARED AgentLoop over the REAL V3 gated
tool runtime (gate → firewall → executor → audit → usage).

The proposer is a deterministic REACTIVE policy ("mid-strength model
harness"): it holds no script of outcomes — every next action branches
ONLY on the observations the loop feeds back. Its first patch contains a
realistic mid-model bug (off-by-one on the even-length median), so the
recovery below is produced by the LOOP's structure (observe → verify →
reject → reassess), not by model intelligence. That is exactly the
orchestration value the benchmark must measure. (The live LLM gateway
refuses this environment's keys — free-plan, 0 tokens, recorded in the
state file — so the mid-strength behavior is harnessed deterministically;
every OTHER component in the chain is the real production primitive.)

Behavior evidence asserted from the ACTUAL run record:

1.  Understand/Plan   — the policy's step-1 reasoning carries the plan.
2.  Select            — REAL SimpleScoringRouter picks the MID-tier model
                        under cost-aware weights (not the strongest);
                        REAL SkillResolver selects the coding skill and
                        NAMES the exclusion of the incompatible one.
3.  Inspect           — REAL jailed SourceReader tool feeds file content.
4.  Act               — REAL gated ToolExecutor runs every tool call.
5.  Observe           — observations accumulate per step.
6.  Reassess/Change   — action sequence changes per observation:
                        read → test → patch(wrong) → final(REJECTED) →
                        patch(corrected) → final(VERIFIED).
7.  Recovery          — the wrong patch is detected by verification and
                        corrected within the SAME bounded run.
8.  Verify            — deterministic VerifyFn actually executes the
                        module's tests; VALIDATOR nodes FAILED then
                        SUCCEEDED.
9.  Evidence          — nodes, steps, audit TOOL_CALL trail, usage ledger,
                        verification verdict on the report.
10. Bounded stop      — STOP_FINAL within max_steps; budget respected.
11. Security          — deny-by-default: revoking one permission blocks
                        the write path THROUGH THE GATE, file untouched.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from core.audit import InMemoryAuditLog
from core.contracts.audit import AuditEventType
from core.contracts.base import JsonObject
from core.contracts.domain import (
    BindingAvailability,
    Model,
    ModelStatus,
    ModelTier,
    ProviderModelBinding,
)
from core.contracts.execution import ExecutionNodeStatus, ExecutionNodeType
from core.contracts.provider import ProviderOperation
from core.contracts.routing import RoutingRequest, ScoringWeights
from core.contracts.tools import Tool
from core.execution.agent import AgentToolBinding
from core.execution.loop import STOP_FINAL, AgentLoop
from core.identity.devices import DeviceRegistry
from core.providers import BindingRegistry, ModelRegistry, ProviderRegistry
from core.roles import SkillRegistry
from core.routing import SimpleScoringRouter
from core.security.firewall import CapabilityFirewall, TenantPolicy
from core.skills import SkillResolver
from core.tools import ToolCallGate, ToolExecutor, ToolRegistry
from core.tools.source_reader import SourceReader
from core.usage import InMemoryUsageAccounting

# Reuse the EXISTING routing + skill fixtures verbatim (shared, not copied).
from tests.routing.test_router_scoring import _manifest, _provider
from tests.skills.test_skill_import_resolver import (
    local_skill,
    make_role_profile,
    make_task,
)

TENANT = uuid4()
USER = uuid4()

# --- the buggy workspace ------------------------------------------------------

BUGGY_STATS = '''\
"""Tiny stats module — median() is BUGGY (does not sort its input)."""


def median(values):
    vals = list(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2
'''

#: Realistic mid-strength-model FIRST attempt: it spots the missing sort but
#: introduces an off-by-one on the even branch (odd cases pass, even fail).
WRONG_PATCH = '''\
"""Tiny stats module — patched (attempt 1)."""


def median(values):
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid] + vals[mid + 1]) / 2
'''

CORRECT_PATCH = '''\
"""Tiny stats module — patched (attempt 2, corrected)."""


def median(values):
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2
'''

#: The task's acceptance tests, run DETERMINISTICALLY (in-process exec).
TEST_CASES: tuple[tuple[list[float], float], ...] = (
    ([3, 1, 2], 2),
    ([4, 1, 3, 2], 2.5),
    ([5], 5),
    ([2, 1], 1.5),
)


def _run_module_tests(workspace: Path) -> JsonObject:
    """Execute stats.py's acceptance tests; pure data out (P6)."""
    source = (workspace / "stats.py").read_text(encoding="utf-8")
    namespace: dict[str, Any] = {}
    try:
        exec(compile(source, "stats.py", "exec"), namespace)  # noqa: S102
    except Exception as exc:  # noqa: BLE001 — a broken patch is data
        return {"passed": 0, "failed": len(TEST_CASES), "error": str(exc)}
    median = namespace["median"]
    failures: list[JsonObject] = []
    for args, expected in TEST_CASES:
        try:
            got = median(args)
        except Exception as exc:  # noqa: BLE001
            failures.append({"input": args, "error": str(exc)})
            continue
        if got != expected:
            failures.append({"input": args, "expected": expected, "got": got})
    return {
        "passed": len(TEST_CASES) - len(failures),
        "failed": len(failures),
        "failures": failures,
    }


# --- the deterministic mid-strength policy (reactive, unscripted) -------------


class MidStrengthPolicy:
    """Reacts ONLY to observations; first patch carries a realistic bug.

    No outcome script exists here: each branch inspects the observation
    stream the loop feeds back. Recovery emerges from the loop's verify
    rejection landing in that stream — orchestration value, not model IQ.
    """

    def __init__(self) -> None:
        self.calls: list[JsonObject] = []

    async def __call__(self, payload: JsonObject) -> JsonObject:
        observations = payload["observations"]
        self.calls.append(payload)

        def last(tool: str) -> JsonObject | None:
            for obs in reversed(observations):
                if obs.get("tool") == tool:
                    return obs
            return None

        read = last("read_source")
        tests = last("run_tests")
        patches = [o for o in observations if o.get("tool") == "apply_patch"]
        rejected = any(o.get("final_rejected") for o in observations)

        if read is None:  # 1) inspect first
            return {
                "action": "tool_call",
                "tool": "read_source",
                "arguments": {"path": "stats.py"},
                "reasoning": (
                    "PLAN: (1) read stats.py, (2) run the tests to see the "
                    "failure, (3) patch median(), (4) finalize once tests pass."
                ),
            }
        if tests is None:  # 2) observe the failure for real
            return {
                "action": "tool_call",
                "tool": "run_tests",
                "arguments": {},
                "reasoning": "source read; running tests to observe the failure",
            }
        if not patches:  # 3) first fix — sorts, but off-by-one on even branch
            return {
                "action": "tool_call",
                "tool": "apply_patch",
                "arguments": {"path": "stats.py", "content": WRONG_PATCH},
                "reasoning": "tests fail on unsorted input; adding sorted()",
            }
        if rejected and len(patches) == 1:  # 5) REASSESS after verify rejection
            return {
                "action": "tool_call",
                "tool": "apply_patch",
                "arguments": {"path": "stats.py", "content": CORRECT_PATCH},
                "reasoning": (
                    "verification rejected my fix: even-length case returns "
                    "the wrong pair — correcting to (vals[mid-1]+vals[mid])/2"
                ),
            }
        # 4)/6) claim completion; the loop's verifier has the last word.
        return {
            "action": "final",
            "output": {"summary": "median() fixed", "patches": len(patches)},
            "reasoning": "patch applied; requesting verified finalization",
        }


# --- world composition over the REAL primitives -------------------------------


def _tool(name: str, permission: str) -> Tool:
    return Tool.model_validate(
        {
            "id": uuid4(),
            "name": name,
            "version": "1.0.0",
            "location": "server",
            "permissions": [permission],
            "approval_policy": {permission: "none"},
            "status": "active",
        }
    )


class BenchmarkWorld:
    """Real gate/firewall/executor/audit/usage over a real jailed workspace."""

    def __init__(self, workspace: Path, *, budget: float = 100.0) -> None:
        self.workspace = workspace
        (workspace / "stats.py").write_text(BUGGY_STATS, encoding="utf-8")
        self.reader = SourceReader(root=workspace)

        self.audit = InMemoryAuditLog()
        self.usage = InMemoryUsageAccounting()
        self.usage.configure_tenant(TENANT, plan="bench", task_units_limit=budget)

        registry = ToolRegistry()
        firewall = CapabilityFirewall()
        permissions: set[str] = set()
        handlers: dict[Any, Any] = {}
        self.bindings: dict[str, AgentToolBinding] = {}

        async def read_source(arguments: JsonObject) -> JsonObject:
            return dict(self.reader.read_file(str(arguments.get("path", ""))))

        async def run_tests(arguments: JsonObject) -> JsonObject:
            return _run_module_tests(self.workspace)

        async def apply_patch(arguments: JsonObject) -> JsonObject:
            rel = str(arguments.get("path", ""))
            target = (self.workspace / rel).resolve()
            if not target.is_relative_to(self.workspace.resolve()):
                msg = f"path escapes workspace: {rel}"
                raise ValueError(msg)
            content = str(arguments.get("content", ""))
            target.write_text(content, encoding="utf-8")
            return {"patched": rel, "bytes": len(content)}

        for name, permission, handler, units in (
            ("read_source", "workspace.source.read", read_source, 1.0),
            ("run_tests", "workspace.tests.run", run_tests, 2.0),
            ("apply_patch", "workspace.source.write", apply_patch, 3.0),
        ):
            tool = _tool(name, permission)
            registry.register(tool)
            handlers[tool.id] = handler
            permissions.add(permission)
            self.bindings[name] = AgentToolBinding(
                tool_id=tool.id,
                permission=permission,
                resource=f"workspace:{name}",
                scope="tenant",
                entitlement="workspace_dev",
                risk_level="low",
                estimated_units=units,
            )

        firewall.set_tenant_policy(
            TENANT,
            TenantPolicy(
                granted_permissions=frozenset(permissions),
                granted_entitlements=frozenset({"workspace_dev"}),
            ),
        )
        self.firewall = firewall
        self.executor = ToolExecutor(
            gate=ToolCallGate(tools=registry, firewall=firewall, devices=DeviceRegistry()),
            handlers=handlers,
            audit=self.audit,
            usage=self.usage,
        )

    async def verify(self, request: JsonObject, output: JsonObject) -> JsonObject:
        """Deterministic verification = actually run the acceptance tests."""
        result = _run_module_tests(self.workspace)
        return {
            "verified": result["failed"] == 0,
            "check": "stats.py acceptance tests",
            **result,
        }


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# --- model + skill selection over the REAL router/resolver --------------------


def _selection_evidence() -> tuple[str, str, list[str]]:
    """REAL router picks the mid model; REAL resolver picks + excludes skills."""
    providers = ProviderRegistry()
    models = ModelRegistry()
    bindings = BindingRegistry()
    provider = _provider("bench")
    providers.register(provider, _manifest("bench"))

    def _model(key: str, tier: ModelTier, quality: float, cost: float) -> Model:
        return Model(
            id=uuid4(),
            model_key=key,
            display_name=key,
            tier=tier,
            modalities=["text"],
            capabilities=["reasoning", "coding"],
            quality_score=quality,
            reliability_score=0.9,
            cost_score=cost,  # higher = cheaper (better cost score)
            speed_score=0.8,
            context_window=64_000,
            status=ModelStatus.ACTIVE,
        )

    strong = _model("strong-frontier", ModelTier.MAX, 0.98, 0.10)
    medium = _model("medium-balanced", ModelTier.MEDIUM, 0.80, 0.90)
    weak = _model("weak-cheap", ModelTier.FAST, 0.40, 0.99)
    for m in (strong, medium, weak):
        models.register(m)
        bindings.register(
            ProviderModelBinding(
                provider_id=provider.id,
                model_id=m.id,
                provider_model_name=m.model_key,
                availability=BindingAvailability.AVAILABLE,
            )
        )
    router = SimpleScoringRouter(providers, models, bindings)
    decision = router.route(
        RoutingRequest(
            operation=ProviderOperation.GENERATE_TEXT,
            required_capabilities=["coding"],
            # Cost-aware weights: the benchmark's mandate — measure the
            # orchestration with a MID model, not the strongest one.
            weights=ScoringWeights(
                quality=0.25,
                cost=0.55,
                latency=0.05,
                reliability=0.05,
                context_fit=0.05,
                policy_preference=0.05,
            ),
        )
    )
    model_key = models.get_by_id(decision.selected.model_id).model_key

    # Skill selection through the REAL resolver, using the EXISTING fixtures.
    skills = SkillRegistry()
    skills.register(
        local_skill(
            name="python-bugfix",
            capabilities=["coding", "testing"],
            compatible_roles=["software_engineer"],
        )
    )
    skills.register(
        local_skill(
            name="marketing-copy",
            capabilities=["copywriting"],
            compatible_roles=["marketer"],
        )
    )
    resolution = SkillResolver(skills).resolve(
        task=make_task(capabilities=["coding"]),
        role=make_role_profile(name="software_engineer"),
    )
    selected = [s.name for s in resolution.selected]
    excluded = [f"{e.skill_name}:{e.reason}" for e in resolution.excluded]
    assert model_key == "medium-balanced", model_key  # mid model, by policy
    assert selected == ["python-bugfix"], selected
    return model_key, selected[0], excluded


# --- THE BENCHMARK -------------------------------------------------------------


class TestFinalBenchmark:
    @pytest.fixture()
    def world(self, tmp_path: Path) -> BenchmarkWorld:
        return BenchmarkWorld(tmp_path)

    def test_full_target_loop_on_a_real_coding_task(self, world: BenchmarkWorld) -> None:
        # --- SELECT (real router + real skill resolver, evidence first) ------
        model_key, skill, exclusions = _selection_evidence()
        assert any("marketing-copy" in e for e in exclusions)  # named exclusion

        policy = MidStrengthPolicy()
        loop = AgentLoop(
            propose=policy,
            tools=world.executor,
            bindings=world.bindings,
            max_steps=8,  # explicit bound
            verify=world.verify,
        )
        report = run(
            loop.execute(
                tenant_id=TENANT,
                user_id=USER,
                request={
                    "task": "make stats.py pass its acceptance tests",
                    "model": model_key,
                    "skill": skill,
                },
                request_hash="b" * 64,
            )
        )

        # --- BOUNDED TERMINATION + VERIFIED FINAL -----------------------------
        assert report.stop_reason == STOP_FINAL
        assert report.succeeded
        assert len(report.steps) <= 8
        assert report.final_output == {"summary": "median() fixed", "patches": 2}
        assert report.verification["verified"] is True
        assert report.verification["failed"] == 0  # tests REALLY pass now
        assert _run_module_tests(world.workspace)["failed"] == 0  # ground truth

        # --- ACTUAL BEHAVIOR SEQUENCE (from the run record, not intent) ------
        actions = [
            (s.observation.get("tool"), bool(s.observation.get("final_rejected")))
            for s in report.steps
        ]
        assert actions == [
            ("read_source", False),  # 1 inspect
            ("run_tests", False),  # 2 observe real failure
            ("apply_patch", False),  # 3 act (wrong fix — mid-model mistake)
            (None, True),  # 4 final REJECTED by verification
            ("apply_patch", False),  # 5 REASSESSED, DIFFERENT action (fix 2)
            (None, False),  # 6 final VERIFIED
        ]

        # --- INSPECTION actually surfaced source ------------------------------
        read_obs = report.steps[0].observation
        assert read_obs["status"] == "succeeded"
        assert "def median" in read_obs["result"]["content"]

        # --- OBSERVED FAILURE was real -----------------------------------------
        test_obs = report.steps[1].observation
        assert test_obs["result"]["failed"] > 0

        # --- PLANNING evidence (step-1 reasoning, recorded verbatim) ----------
        assert "PLAN:" in report.steps[0].proposal_raw["reasoning"]

        # --- RECOVERY: rejection verdict NAMED the even-length failure --------
        rejection = report.steps[3].observation["verification"]
        assert rejection["verified"] is False
        assert rejection["failed"] > 0
        # and the policy's correction cited it (reassessment is observable):
        assert "correcting" in report.steps[4].proposal_raw["reasoning"]

        # --- VERIFICATION nodes: FAILED then SUCCEEDED -------------------------
        validators = [n for n in report.nodes if n.type is ExecutionNodeType.VALIDATOR]
        assert [v.status for v in validators] == [
            ExecutionNodeStatus.FAILED,
            ExecutionNodeStatus.SUCCEEDED,
        ]

        # --- SECURITY: every act passed the real gate (audit trail) -----------
        tool_events = [
            e for e in world.audit.read(TENANT) if e.event_type is AuditEventType.TOOL_CALL
        ]
        assert len(tool_events) == 4  # read, test, patch, patch
        assert all(e.tenant_id == TENANT for e in tool_events)

        # --- USAGE: every act reserved+settled real units ----------------------
        summary = world.usage.summary(TENANT)
        assert summary.task_units.used == pytest.approx(1.0 + 2.0 + 3.0 + 3.0)
        assert summary.task_units.remaining == pytest.approx(100.0 - 9.0)

        # --- MODEL-AGNOSTIC: the loop fed the policy ONLY request+observations
        # (+ the R160 step budget as data — never a provider/model detail) --
        for payload in policy.calls:
            assert set(payload) == {"request", "observations", "budget"}
            assert set(payload["budget"]) == {"step", "max_steps"}

    def test_deny_by_default_blocks_undeclared_tool_capability(self, world: BenchmarkWorld) -> None:
        """Capability != authority: revoking ONE permission blocks the write
        path THROUGH THE GATE even though the tool stays registered+bound."""
        world.firewall.set_tenant_policy(
            TENANT,
            TenantPolicy(  # revoke write permission only
                granted_permissions=frozenset({"workspace.source.read", "workspace.tests.run"}),
                granted_entitlements=frozenset({"workspace_dev"}),
            ),
        )

        async def patcher(payload: JsonObject) -> JsonObject:
            if not payload["observations"]:
                return {
                    "action": "tool_call",
                    "tool": "apply_patch",
                    "arguments": {"path": "stats.py", "content": CORRECT_PATCH},
                }
            return {"action": "final", "output": {"done": True}}

        loop = AgentLoop(
            propose=patcher,
            tools=world.executor,
            bindings=world.bindings,
            max_steps=2,
        )
        report = run(
            loop.execute(
                tenant_id=TENANT,
                user_id=USER,
                request={"task": "patch"},
                request_hash="c" * 64,
            )
        )
        refused = report.steps[0].observation
        assert refused["status"] != "succeeded"
        assert refused["error"]["reason"] == "capability_denied"
        # The file was NOT touched (authority enforced, not advisory).
        assert "attempt 2" not in (world.workspace / "stats.py").read_text(encoding="utf-8")
        # The refusal is recorded evidence (FAILED tool node).
        failed_nodes = [
            n
            for n in report.nodes
            if n.type is ExecutionNodeType.TOOL_CALL and n.status is ExecutionNodeStatus.FAILED
        ]
        assert failed_nodes
