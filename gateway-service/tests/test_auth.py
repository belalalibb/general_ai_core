"""Auth tests — dual-accept rotation, constant-time compare semantics."""

from __future__ import annotations

import pytest

from gateway.auth import AuthOutcome, auth_error_body, authenticate
from gateway.config import GatewayConfig
from tests.conftest import SECRET_V6, SECRET_V7


@pytest.fixture()
def config() -> GatewayConfig:
    return GatewayConfig(
        secrets_by_version={7: SECRET_V7, 6: SECRET_V6},
        current_secret_version=7,
    )


def test_current_secret_accepted(config: GatewayConfig) -> None:
    assert authenticate(config, SECRET_V7, "7").outcome is AuthOutcome.OK


def test_previous_secret_accepted_dual_window(config: GatewayConfig) -> None:
    # OPEN-7: during rotation both current and previous versions work.
    assert authenticate(config, SECRET_V6, "6").outcome is AuthOutcome.OK


def test_wrong_secret_rejected(config: GatewayConfig) -> None:
    result = authenticate(config, "wrong-value-entirely!", "7")
    assert result.outcome is AuthOutcome.WRONG_SECRET
    body = auth_error_body(result)
    assert body["error"]["category"] == "invalid_credential"  # type: ignore[index]
    assert body["error"]["retryable"] is False  # type: ignore[index]


def test_stale_version_is_retryable_auth_expired(config: GatewayConfig) -> None:
    result = authenticate(config, SECRET_V7, "5")
    assert result.outcome is AuthOutcome.STALE_VERSION
    body = auth_error_body(result)
    assert body["error"]["category"] == "auth_expired"  # type: ignore[index]
    assert body["error"]["retryable"] is True  # type: ignore[index]
    assert "current is 7" in body["error"]["message"]  # type: ignore[index]


def test_missing_headers_rejected(config: GatewayConfig) -> None:
    assert authenticate(config, None, None).outcome is AuthOutcome.MISSING
    assert authenticate(config, SECRET_V7, None).outcome is AuthOutcome.MISSING
    assert authenticate(config, None, "7").outcome is AuthOutcome.MISSING
    assert authenticate(config, SECRET_V7, "seven").outcome is AuthOutcome.MISSING


def test_auth_errors_never_leak_secret_values(config: GatewayConfig) -> None:
    for result in (
        authenticate(config, "wrong", "7"),
        authenticate(config, SECRET_V7, "5"),
        authenticate(config, None, None),
    ):
        rendered = str(auth_error_body(result))
        assert SECRET_V7 not in rendered
        assert SECRET_V6 not in rendered


def test_config_misconfiguration_fails_loud() -> None:
    with pytest.raises(ValueError):
        GatewayConfig(secrets_by_version={}, current_secret_version=1)
    with pytest.raises(ValueError):
        GatewayConfig(secrets_by_version={1: SECRET_V7}, current_secret_version=2)
    with pytest.raises(ValueError):
        GatewayConfig(secrets_by_version={1: "short"}, current_secret_version=1)
