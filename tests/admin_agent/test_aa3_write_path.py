"""AA-3 acceptance suite — governed write path (R2) + NTF-1 + SKL-1.

Covers the four doc C §5 acceptance criteria:

1. An Agent-drafted change is INDISTINGUISHABLE in lifecycle from a
   form-drafted one — same records, same audit (TestCriterion1SameLifecycle).
2. Publish is impossible without the explicit UI act — proven by test that
   the Agent's tool registry contains NO publish tool
   (TestCriterion2NoPublishTool).
3. Rollback UX renders backend denials verbatim — RollbackUnavailable
   surfaces word-for-word over HTTP and the UI pipes it through renderError
   (TestCriterion3VerbatimRollbackDenial).
4. Every notification links to its evidence record; ZERO notifications
   exist without a backing record (TestCriterion4NotificationsEvidence).

Plus SKL-1: the skill-import review pipeline surfaced verbatim over HTTP
(TestSkillImportSurface) and auth walls on every new route
(TestNewRoutesAuth).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI

from apps.api import create_app
from apps.api.notifications import NotificationCategory
from apps.composition.admin_console import UI_DIR, attach_admin_console
from core.admin.errors import ChangeNotFound
from core.contracts.admin import AdminAction
from core.contracts.audit import AuditEvent, AuditEventType
from core.roles.errors import SkillNotRegistered
from core.skills.importing import content_checksum
from tests.admin_agent.test_aa2_admin_agent import (
    ADMIN_EMAIL,
    USER_EMAIL,
    AgentWorld,
    _client,
    _login,
    _provider_error,
    _reasoning,
    bearer,
    openapi_ops,
    run,
)

# The RollbackUnavailable message, verbatim from core/admin/service.py —
# criterion 3 asserts the HTTP body carries EXACTLY this string.
ROLLBACK_DENIAL = (
    "rollback unavailable: no prior plan configuration exists for this "
    "tenant; restoring would invent a version that never was (21 §8)"
)


async def _admin_post(
    world: AgentWorld, path: str, body: dict[str, Any] | None = None
) -> Any:
    token = await _login(world.app, ADMIN_EMAIL)
    async with _client(world.app) as c:
        return await c.post(path, headers=bearer(token), json=body or {})


async def _admin_get(world: AgentWorld, path: str) -> Any:
    token = await _login(world.app, ADMIN_EMAIL)
    async with _client(world.app) as c:
        return await c.get(path, headers=bearer(token))


# --- criterion 1: agent-drafted == form-drafted --------------------------------------


class TestCriterion1SameLifecycle:
    def test_agent_draft_and_form_draft_are_the_same_record_shape(self) -> None:
        """Same service, same ConfigChange — only id/created_at differ."""
        world = AgentWorld(
            [
                _reasoning(
                    tool_calls=[
                        {
                            "tool": "draft_change",
                            "arguments": {
                                "action": "disable_model",
                                "payload": {"model_key": "model-a"},
                            },
                        }
                    ]
                )
            ]
        )
        world.grant_budget(100)
        admin = world.admin_principal()
        answer = run(world.service.converse(admin, "disable model-a"))
        drafted = next(c for c in answer.tool_calls if c.tool == "draft_change")
        assert drafted.ok is True
        assert drafted.result is not None
        assert drafted.result["state"] == "draft"

        async def form_draft() -> None:
            response = await _admin_post(
                world,
                "/v1/admin/changes",
                {"action": "disable_model", "payload": {"model_key": "model-a"}},
            )
            assert response.status_code == 201, response.text

        run(form_draft())

        records = world.surface.admin.service.list_changes(admin.tenant_id)
        assert len(records) == 2
        agent_record, form_record = records
        exclude = {"id", "created_at"}
        assert agent_record.model_dump(exclude=exclude) == form_record.model_dump(
            exclude=exclude
        )

    def test_agent_drafted_change_progresses_through_the_same_http_lifecycle(
        self,
    ) -> None:
        """Validate/preview/publish an AGENT-drafted change over the SAME
        HTTP routes a form-drafted change uses — same states, same audit."""
        world = AgentWorld()
        admin = world.admin_principal()
        # Draft through the agent DISPATCHER (the same object converse uses).
        record = run(
            world.dispatcher.dispatch(
                admin,
                "draft_change",
                {"action": "disable_model", "payload": {"model_key": "model-a"}},
            )
        )
        assert record.ok is True and record.result is not None
        change_id = record.result["change_id"]

        async def lifecycle() -> None:
            for step, expected_state in (
                ("validate", "validated"),
                ("preview", "validated"),
                ("publish", "published"),
            ):
                response = await _admin_post(
                    world, f"/v1/admin/changes/{change_id}/{step}"
                )
                assert response.status_code == 200, (step, response.text)
                assert response.json()["state"] == expected_state

        run(lifecycle())
        # Same audit trail: ADMIN_CONFIG_PUBLISHED names THIS change.
        events = world.audit.read(
            admin.tenant_id, event_type=AuditEventType.ADMIN_CONFIG_PUBLISHED
        )
        assert any(e.details.get("change_id") == change_id for e in events)

    def test_agent_validate_and_preview_tools_hit_the_same_service(self) -> None:
        """Agent-side validate/preview produce the SAME state transitions."""
        world = AgentWorld()
        admin = world.admin_principal()
        drafted = run(
            world.dispatcher.dispatch(
                admin,
                "draft_change",
                {"action": "disable_model", "payload": {"model_key": "model-a"}},
            )
        )
        assert drafted.result is not None
        change_id = drafted.result["change_id"]
        validated = run(
            world.dispatcher.dispatch(
                admin, "validate_change", {"change_id": change_id}
            )
        )
        assert validated.result is not None
        assert validated.result["state"] == "validated"
        assert validated.result["validation_result"] == "passed"
        previewed = run(
            world.dispatcher.dispatch(
                admin, "preview_change", {"change_id": change_id}
            )
        )
        assert previewed.result is not None
        assert "impact_preview" in previewed.result
        # The record the HTTP surface reads is the SAME one.
        record = world.surface.admin.service.get(admin.tenant_id, UUID(change_id))
        assert record.state.value == "validated"
        assert record.impact_preview is not None

    def test_agent_lifecycle_tool_denials_are_the_core_messages(self) -> None:
        world = AgentWorld()
        admin = world.admin_principal()
        # Unknown / foreign id: anti-enumeration answer.
        unknown = run(
            world.dispatcher.dispatch(
                admin, "validate_change", {"change_id": str(uuid4())}
            )
        )
        assert unknown.result is not None
        assert unknown.result["error"] == "unknown change id"
        # Out-of-order: validate twice → the core refusal, verbatim.
        drafted = run(
            world.dispatcher.dispatch(
                admin,
                "draft_change",
                {"action": "disable_model", "payload": {"model_key": "model-a"}},
            )
        )
        assert drafted.result is not None
        change_id = drafted.result["change_id"]
        run(world.dispatcher.dispatch(admin, "validate_change", {"change_id": change_id}))
        again = run(
            world.dispatcher.dispatch(admin, "validate_change", {"change_id": change_id})
        )
        assert again.result is not None
        assert again.result["error"] == (
            "invalid lifecycle transition: expected draft, found validated"
        )


# --- criterion 2: publish impossible without the UI act --------------------------------


class TestCriterion2NoPublishTool:
    def test_registry_contains_no_publish_and_no_rollback_tool(self) -> None:
        """Doc C §5, verbatim: 'proven by test that the Agent's tool
        registry contains no publish tool'."""
        world = AgentWorld()
        names = set(world.registry.names())
        assert "publish_change" not in names
        assert "rollback_change" not in names
        for name in names:
            assert "publish" not in name
            assert "rollback" not in name

    def test_injected_publish_proposal_is_refused_while_draft_succeeds(self) -> None:
        world = AgentWorld(
            [
                _reasoning(
                    tool_calls=[
                        {"tool": "publish_change", "arguments": {"change_id": "x"}},
                        {
                            "tool": "draft_change",
                            "arguments": {
                                "action": "disable_model",
                                "payload": {"model_key": "model-a"},
                            },
                        },
                    ]
                )
            ]
        )
        world.grant_budget(100)
        answer = run(world.service.converse(world.admin_principal(), "publish it all"))
        by_tool = {c.tool: c for c in answer.tool_calls}
        assert by_tool["publish_change"].ok is False
        assert by_tool["publish_change"].refusal is not None
        assert by_tool["draft_change"].ok is True


# --- criterion 3: rollback denials verbatim ---------------------------------------------


class TestCriterion3VerbatimRollbackDenial:
    def test_rollback_unavailable_surfaces_verbatim_over_http(self) -> None:
        """First-ever SET_PLAN for a tenant: publish OK, rollback DENIED —
        the HTTP body carries the core message word-for-word."""
        world = AgentWorld()

        async def flow() -> None:
            draft = await _admin_post(
                world,
                "/v1/admin/changes",
                {
                    "action": "set_plan",
                    "payload": {
                        "target_tenant_id": str(uuid4()),
                        "plan": "pro",
                        "task_units_limit": 10,
                    },
                },
            )
            assert draft.status_code == 201, draft.text
            change_id = draft.json()["id"]
            for step in ("validate", "preview", "publish"):
                response = await _admin_post(
                    world, f"/v1/admin/changes/{change_id}/{step}"
                )
                assert response.status_code == 200, (step, response.text)
            rollback = await _admin_post(
                world, f"/v1/admin/changes/{change_id}/rollback"
            )
            assert rollback.status_code == 409
            error = rollback.json()["error"]
            assert error["code"] == "validation_error"
            assert error["message"] == ROLLBACK_DENIAL

        run(flow())

    def test_ui_lifecycle_act_renders_denials_verbatim(self) -> None:
        """The Changes surface pipes lifecycle failures through renderError
        (the verbatim unified-error renderer) — never a friendly rewrite."""
        code = (UI_DIR / "app.js").read_text(encoding="utf-8")
        assert "async function lifecycleAct" in code
        assert "renderError(errorBox, result.body)" in code
        # And renderError itself shows code + message verbatim.
        assert "`${payload.error.code}: ${payload.error.message}`" in code


# --- criterion 4: notifications = derived evidence ---------------------------------------


class TestCriterion4NotificationsEvidence:
    def _world_with_all_six_categories(self) -> AgentWorld:
        """One source record per category, through EXISTING machinery only."""
        world = AgentWorld(
            [
                {"content": "pong"},  # SUCCESS: a succeeded R1 execution
                _provider_error(),  # ERROR: a failed R1 execution
            ]
        )
        world.grant_budget(100)
        admin = world.admin_principal()
        run(world.dispatcher.dispatch(admin, "run_test_execution", {}))
        run(world.dispatcher.dispatch(admin, "run_test_execution", {}))
        service = world.surface.admin.service
        # INFO: a change awaiting publish.
        info_change = service.draft(
            tenant_id=admin.tenant_id,
            actor_id=admin.user_id,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        service.validate(admin.tenant_id, info_change.id)
        # WARNING: a rejected change.
        warn_change = service.draft(
            tenant_id=admin.tenant_id,
            actor_id=admin.user_id,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "ghost-9"},
        )
        service.validate(admin.tenant_id, warn_change.id)
        # CHANGE: a published change (audit ADMIN_CONFIG_PUBLISHED).
        pub_change = service.draft(
            tenant_id=admin.tenant_id,
            actor_id=admin.user_id,
            action=AdminAction.DISABLE_MODEL,
            payload={"model_key": "model-a"},
        )
        service.validate(admin.tenant_id, pub_change.id)
        service.preview(admin.tenant_id, pub_change.id)
        service.publish(admin.tenant_id, pub_change.id)
        # SECURITY: a permission-denied audit event.
        world.audit.append(
            AuditEvent(
                tenant_id=admin.tenant_id,
                event_type=AuditEventType.PERMISSION_DENIED,
                actor_id=admin.user_id,
                details={"surface": "test"},
            )
        )
        return world

    def test_all_six_categories_derive_from_their_record_types(self) -> None:
        world = self._world_with_all_six_categories()

        async def check() -> None:
            response = await _admin_get(world, "/v1/admin/notifications")
            assert response.status_code == 200
            rows = response.json()["notifications"]
            categories = {row["category"] for row in rows}
            assert categories == {member.value for member in NotificationCategory}

        run(check())

    def test_every_notification_links_to_a_resolvable_record(self) -> None:
        """Criterion 4: evidence {kind, ref} on EVERY row, and each ref
        resolves against the actual backing store — zero orphans."""
        world = self._world_with_all_six_categories()
        admin = world.admin_principal()

        async def check() -> None:
            response = await _admin_get(world, "/v1/admin/notifications")
            rows = response.json()["notifications"]
            assert rows, "expected derived notifications"
            audit_ids = {str(e.id) for e in world.audit.read(admin.tenant_id)}
            for row in rows:
                evidence = row["evidence"]
                assert set(evidence.keys()) == {"kind", "ref"}
                kind, ref = evidence["kind"], evidence["ref"]
                if kind == "audit_event":
                    assert ref in audit_ids, row
                elif kind == "execution":
                    world.store.get(admin.tenant_id, UUID(ref))  # raises if absent
                elif kind == "config_change":
                    world.surface.admin.service.get(admin.tenant_id, UUID(ref))
                else:
                    raise AssertionError(f"unknown evidence kind: {kind}")

        run(check())

    def test_no_create_path_exists_on_the_notification_service(self) -> None:
        """Derive-on-read is structural: NOTHING can mint a notification."""
        from apps.api.notifications import NotificationService

        public_methods = {
            name
            for name in dir(NotificationService)
            if not name.startswith("_")
            and callable(getattr(NotificationService, name))
        }
        assert public_methods == {"list", "ack"}

    def test_ack_marks_read_and_unread_count_drops(self) -> None:
        world = self._world_with_all_six_categories()

        async def check() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                first = await c.get("/v1/admin/notifications", headers=bearer(token))
                rows = first.json()["notifications"]
                unread_before = first.json()["unread"]
                assert unread_before == len(rows)
                target = rows[0]["id"]
                ack = await c.post(
                    f"/v1/admin/notifications/{target}/ack", headers=bearer(token)
                )
                assert ack.status_code == 200
                assert ack.json() == {"acknowledged": target}
                second = await c.get("/v1/admin/notifications", headers=bearer(token))
                assert second.json()["unread"] == unread_before - 1
                acked_row = next(
                    r for r in second.json()["notifications"] if r["id"] == target
                )
                assert acked_row["read"] is True

        run(check())

    def test_ack_of_underivable_id_is_404(self) -> None:
        """No phantom acks: an id with no backing record is refused."""
        world = AgentWorld()

        async def check() -> None:
            response = await _admin_post(
                world, f"/v1/admin/notifications/audit:{uuid4()}/ack"
            )
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "validation_error"

        run(check())


# --- SKL-1: skill-import review surface -----------------------------------------------


def _manifest_dict(name: str = "review_helper") -> dict[str, Any]:
    return {
        "id": name,
        "name": name,
        "version": "1.0.0",
        "type": "instruction",
        "source": "imported",
        "status": "imported",
    }


def _import_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "manifest": _manifest_dict(),
        "content": "Perform careful code reviews.",
        "source_url": "https://github.com/mattpocock/skills/tree/main/review",
        "source_version": "abc123",
    }
    body.update(overrides)
    return body


class TestSkillImportSurface:
    def test_full_pipeline_import_to_active_registers_the_skill(self) -> None:
        world = AgentWorld()
        admin = world.admin_principal()

        async def flow() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                headers = bearer(token)
                imported = await c.post(
                    "/v1/admin/skills/import", headers=headers, json=_import_body()
                )
                assert imported.status_code == 201, imported.text
                skill_id = imported.json()["skill_id"]
                assert imported.json()["status"] == "imported"
                assert imported.json()["source"] == "imported"
                # checksum recorded from content, not caller-claimed.
                assert imported.json()["provenance"]["checksum"] == content_checksum(
                    "Perform careful code reviews."
                )

                scanned = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/scan",
                    headers=headers,
                    json={"findings": []},
                )
                assert scanned.status_code == 200
                assert scanned.json()["status"] == "scanned"

                validated = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/validate", headers=headers
                )
                assert validated.status_code == 200
                assert validated.json()["status"] == "validated"

                reviewed = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/review", headers=headers
                )
                assert reviewed.status_code == 200
                assert reviewed.json()["status"] == "reviewed"
                # Reviewer = the authenticated principal, never claimed.
                assert reviewed.json()["provenance"]["reviewed_by"] == str(
                    admin.user_id
                )

                approved = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/approve", headers=headers
                )
                assert approved.status_code == 200
                assert approved.json()["status"] == "approved"

                active = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/activate", headers=headers
                )
                assert active.status_code == 200
                assert active.json()["status"] == "active"
                assert active.json()["source"] == "local"  # 41 §16 Local Version

                # Registered into the EXISTING SkillRegistry.
                registered = world.skill_registry.get(UUID(skill_id))
                assert registered.status.value == "active"
                # And gone from the pending review list.
                remaining = await c.get("/v1/admin/skills/imports", headers=headers)
                assert remaining.json()["imports"] == []

        run(flow())

    def test_out_of_order_step_refused_with_core_message_verbatim(self) -> None:
        world = AgentWorld()

        async def flow() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                headers = bearer(token)
                imported = await c.post(
                    "/v1/admin/skills/import", headers=headers, json=_import_body()
                )
                skill_id = imported.json()["skill_id"]
                response = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/approve", headers=headers
                )
                assert response.status_code == 409
                message = response.json()["error"]["message"]
                assert "cannot approve from status=imported" in message

        run(flow())

    def test_scan_findings_block_the_skill(self) -> None:
        world = AgentWorld()

        async def flow() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                headers = bearer(token)
                imported = await c.post(
                    "/v1/admin/skills/import", headers=headers, json=_import_body()
                )
                skill_id = imported.json()["skill_id"]
                response = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/scan",
                    headers=headers,
                    json={"findings": ["exfiltrates credentials"]},
                )
                assert response.status_code == 409
                message = response.json()["error"]["message"]
                assert "scan blocked skill" in message
                assert "exfiltrates credentials" in message

        run(flow())

    def test_unknown_source_refused_422(self) -> None:
        world = AgentWorld()

        async def check() -> None:
            response = await _admin_post(
                world,
                "/v1/admin/skills/import",
                _import_body(source_url="https://evil.example/skills"),
            )
            assert response.status_code == 422
            assert "unknown import source" in response.json()["error"]["message"]

        run(check())

    def test_checksum_mismatch_refused_422(self) -> None:
        world = AgentWorld()

        async def check() -> None:
            response = await _admin_post(
                world,
                "/v1/admin/skills/import",
                _import_body(expected_checksum="0" * 64),
            )
            assert response.status_code == 422
            assert "checksum mismatch" in response.json()["error"]["message"]

        run(check())

    def test_unknown_and_malformed_ids_are_the_same_404(self) -> None:
        world = AgentWorld()

        async def check() -> None:
            for skill_id in (str(uuid4()), "not-a-uuid"):
                response = await _admin_post(
                    world, f"/v1/admin/skills/imports/{skill_id}/validate"
                )
                assert response.status_code == 404, skill_id
                error = response.json()["error"]
                assert error["code"] == "validation_error"
                assert error["message"] == "Unknown skill import id."

        run(check())

    def test_pending_imports_are_tenant_scoped(self) -> None:
        world = AgentWorld()
        foreign_tenant = uuid4()

        async def flow() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                imported = await c.post(
                    "/v1/admin/skills/import",
                    headers=bearer(token),
                    json=_import_body(),
                )
                skill_id = imported.json()["skill_id"]
            # The holding area answers nothing for a foreign tenant.
            assert world.skill_review.get(foreign_tenant, UUID(skill_id)) is None
            assert world.skill_review.list(foreign_tenant) == []

        run(flow())

    def test_activation_never_skips_review(self) -> None:
        """14 §9 forbidden: 'Imported skill becomes active without review'."""
        world = AgentWorld()

        async def flow() -> None:
            token = await _login(world.app, ADMIN_EMAIL)
            async with _client(world.app) as c:
                headers = bearer(token)
                imported = await c.post(
                    "/v1/admin/skills/import", headers=headers, json=_import_body()
                )
                skill_id = imported.json()["skill_id"]
                response = await c.post(
                    f"/v1/admin/skills/imports/{skill_id}/activate", headers=headers
                )
                assert response.status_code == 409
                assert "cannot activate from status=imported" in (
                    response.json()["error"]["message"]
                )
            # And nothing reached the registry.
            try:
                world.skill_registry.get(UUID(skill_id))
                raise AssertionError("skill must not be registered")
            except SkillNotRegistered:
                pass

        run(flow())

    def test_skills_routes_absent_entirely_without_the_seam(self) -> None:
        """20 §4 posture: no seam ⇒ no route exists at all."""
        world = AgentWorld()
        app: FastAPI = create_app(
            router=world.world.router,
            execution_service=world.execution_service,
            store=world.store,
            auth=world.auth,
        )
        attach_admin_console(app, surface=world.surface, auth=world.auth, ui=False)
        assert not [op for op in openapi_ops(app) if "/v1/admin/skills" in op]


# --- auth walls on every new route -------------------------------------------------------


class TestNewRoutesAuth:
    NEW_ROUTES = [
        ("GET", "/v1/admin/notifications"),
        ("POST", f"/v1/admin/notifications/audit:{uuid4()}/ack"),
        ("GET", "/v1/admin/skills/imports"),
        ("POST", "/v1/admin/skills/import"),
        ("POST", f"/v1/admin/skills/imports/{uuid4()}/scan"),
        ("POST", f"/v1/admin/skills/imports/{uuid4()}/validate"),
        ("POST", f"/v1/admin/skills/imports/{uuid4()}/review"),
        ("POST", f"/v1/admin/skills/imports/{uuid4()}/approve"),
        ("POST", f"/v1/admin/skills/imports/{uuid4()}/activate"),
    ]

    def _body_for(self, method: str, path: str) -> dict[str, Any] | None:
        if method != "POST":
            return None
        if path.endswith("/import"):
            return _import_body()
        if path.endswith("/scan"):
            return {"findings": []}
        return {}

    def test_anonymous_401_on_all_new_routes(self) -> None:
        world = AgentWorld()

        async def check() -> None:
            async with _client(world.app) as c:
                for method, path in self.NEW_ROUTES:
                    kwargs: dict[str, Any] = {}
                    body = self._body_for(method, path)
                    if body is not None:
                        kwargs["json"] = body
                    response = await c.request(method, path, **kwargs)
                    assert response.status_code == 401, (method, path)
                    assert response.json()["error"]["code"] == "unauthenticated"

        run(check())

    def test_non_admin_403_on_all_new_routes(self) -> None:
        world = AgentWorld()

        async def check() -> None:
            token = await _login(world.app, USER_EMAIL)
            async with _client(world.app) as c:
                for method, path in self.NEW_ROUTES:
                    kwargs: dict[str, Any] = {"headers": bearer(token)}
                    body = self._body_for(method, path)
                    if body is not None:
                        kwargs["json"] = body
                    response = await c.request(method, path, **kwargs)
                    assert response.status_code == 403, (method, path)
                    assert response.json()["error"]["code"] == "unauthorized"

        run(check())

    def test_cross_tenant_change_ids_are_unknown(self) -> None:
        """Agent R2 lifecycle tools never confirm foreign records exist."""
        world = AgentWorld()
        admin = world.admin_principal()
        drafted = run(
            world.dispatcher.dispatch(
                admin,
                "draft_change",
                {"action": "disable_model", "payload": {"model_key": "model-a"}},
            )
        )
        assert drafted.result is not None
        change_id = drafted.result["change_id"]
        # A DIFFERENT tenant asking about the same id gets the same
        # answer as an absent id — via the service directly.
        try:
            world.surface.admin.service.get(uuid4(), UUID(change_id))
            raise AssertionError("foreign tenant must not resolve the change")
        except ChangeNotFound:
            pass
