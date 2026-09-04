"""R169 A5/A6 contract tests: RepoBinding and PublishMode (contracts-first, INV-1/INV-2)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from core.contracts.publish_mode import (
    DEFAULT_ALLOWED_MODES,
    DEFAULT_PUBLISH_MODE,
    PUBLISH_MODE_LABELS,
    REASON_DIRECT_PUSH_NOT_ENABLED,
    REASON_MODE_NOT_IN_BINDING,
    PublishMode,
    PublishModesResponse,
    publish_mode_options,
)
from core.contracts.repo_binding import (
    GitPublishRequest,
    GitRefusal,
    GitRefusalCode,
    RepoBinding,
)


def _binding(**overrides: object) -> RepoBinding:
    base: dict[str, object] = {
        "tenant_id": uuid4(),
        "remote_url": "https://github.com/example/repo.git",
        "branch": "main",
        "local_root": "/tmp/repo",
        "credential_ref": "credref_abc",
    }
    base.update(overrides)
    return RepoBinding.model_validate(base)


class TestPublishMode:
    def test_default_is_pull_request(self) -> None:
        assert DEFAULT_PUBLISH_MODE is PublishMode.PULL_REQUEST

    def test_default_allowed_excludes_direct_push(self) -> None:
        assert PublishMode.DIRECT_PUSH not in DEFAULT_ALLOWED_MODES
        assert set(DEFAULT_ALLOWED_MODES) == {
            PublishMode.DRY_RUN,
            PublishMode.LOCAL_COMMIT_ONLY,
            PublishMode.PULL_REQUEST,
        }

    def test_enum_is_closed_with_four_members(self) -> None:
        assert len(PublishMode) == 4
        assert set(PUBLISH_MODE_LABELS) == set(PublishMode)

    def test_options_enumerate_every_mode_in_order(self) -> None:
        options = publish_mode_options(frozenset(DEFAULT_ALLOWED_MODES))
        assert [o.id for o in options] == list(PublishMode)
        labels = [o.label for o in options]
        assert labels == ["Dry run", "Local commit only", "Pull request", "Direct push"]

    def test_direct_push_non_selectable_has_binding_reason(self) -> None:
        options = {o.id: o for o in publish_mode_options(frozenset(DEFAULT_ALLOWED_MODES))}
        assert options[PublishMode.DIRECT_PUSH].selectable is False
        assert options[PublishMode.DIRECT_PUSH].reason == REASON_DIRECT_PUSH_NOT_ENABLED
        for mode in DEFAULT_ALLOWED_MODES:
            assert options[mode].selectable is True
            assert options[mode].reason is None

    def test_other_disallowed_mode_has_generic_reason(self) -> None:
        options = {o.id: o for o in publish_mode_options(frozenset({PublishMode.DRY_RUN}))}
        assert options[PublishMode.PULL_REQUEST].selectable is False
        assert options[PublishMode.PULL_REQUEST].reason == REASON_MODE_NOT_IN_BINDING

    def test_direct_push_selectable_when_enabled(self) -> None:
        options = {o.id: o for o in publish_mode_options(frozenset(PublishMode))}
        assert options[PublishMode.DIRECT_PUSH].selectable is True
        assert options[PublishMode.DIRECT_PUSH].reason is None

    def test_response_default_and_json_shape(self) -> None:
        resp = PublishModesResponse(
            binding_id="b1", modes=publish_mode_options(frozenset(DEFAULT_ALLOWED_MODES))
        )
        data = resp.model_dump(mode="json")
        assert data["default"] == "pull_request"
        assert {"id", "label", "description", "selectable", "reason"} <= set(data["modes"][0])


class TestRepoBinding:
    def test_defaults(self) -> None:
        b = _binding()
        assert b.allowed_modes == frozenset(DEFAULT_ALLOWED_MODES)
        assert b.mode_allowed(PublishMode.PULL_REQUEST) is True
        assert b.mode_allowed(PublishMode.DIRECT_PUSH) is False

    def test_direct_push_opt_in_per_binding(self) -> None:
        b = _binding(allowed_modes=list(PublishMode))
        assert b.mode_allowed(PublishMode.DIRECT_PUSH) is True

    def test_rejects_non_https_remote(self) -> None:
        with pytest.raises(ValidationError):
            _binding(remote_url="git@github.com:example/repo.git")
        with pytest.raises(ValidationError):
            _binding(remote_url="http://github.com/example/repo.git")

    def test_credential_ref_is_opaque_and_required(self) -> None:
        with pytest.raises(ValidationError):
            _binding(credential_ref="")
        assert "token" not in RepoBinding.model_fields

    def test_publish_request_defaults_to_pull_request(self) -> None:
        req = GitPublishRequest(binding_id=uuid4())
        assert req.mode is PublishMode.PULL_REQUEST

    def test_refusal_is_typed_data(self) -> None:
        r = GitRefusal(
            code=GitRefusalCode.REMOTE_REJECTED_PROTECTED_BRANCH,
            reason="protected",
            suggested_mode=PublishMode.PULL_REQUEST,
        )
        data = r.model_dump(mode="json")
        assert data["ok"] is False
        assert data["code"] == "remote_rejected_protected_branch"
        assert data["suggested_mode"] == "pull_request"

    def test_refusal_codes_are_snake_case_values(self) -> None:
        for code in GitRefusalCode:
            assert code.value == code.name.lower()
