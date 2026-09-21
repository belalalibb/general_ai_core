"""R198-A (operator D2) — ADR-0014 is the AD-5 topology artefact, read as TEXT.

The artefact must describe the v1 production topology the repository actually
implements — never a topology the code does not have. Pins:
  * the document exists and carries the AD-5 ruling verbatim;
  * it names the three OPERATIONS §1 durable-profile startup steps in order
    (Postgres up → ``alembic upgrade head`` → ``apps.cli serve``);
  * it states ONE process = API + outbox relay + exec worker (apps/main.py lifespan);
  * every environment key it names in backticks is a key the runtime, the CLI, the
    API layer or the alembic env actually reads (no invented knobs);
  * it records the exclusions with their decision references (P-R188-04,
    no distributed worker, no token streaming) and the TLS-at-ingress posture
    (HSTS only behind TLS);
  * it does NOT claim "Production Ready" (operator D1: not while D-03 is open).
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs" / "architecture" / "ADR-0014_V1_PRODUCTION_TOPOLOGY.md"
OPERATIONS = ROOT / "docs" / "OPERATIONS.md"

AD5_VERBATIM = (
    "v1 production topology = durable single-server, single API process, "
    "external Postgres; multi-replica future."
)

_ENV_SOURCES = (
    ROOT / "apps" / "composition" / "runtime.py",
    ROOT / "apps" / "composition" / "database.py",
    ROOT / "apps" / "composition" / "secrets.py",
    ROOT / "apps" / "main.py",
    ROOT / "apps" / "cli.py",
    ROOT / "apps" / "api",
    ROOT / "infrastructure" / "db" / "migrations" / "env.py",
)
_ENV_READ = re.compile(
    r"(?:environ|env|os\.environ)(?:\.get)?\(?\[?\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']"
    r"|[A-Z_]*_ENV(?:_[A-Z_]+)?\s*=\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']"
    r"|[\"']([A-Z][A-Z0-9_]{3,})[\"']\s*(?:not\s+)?in\s+(?:environ|env)\b"
)


def _adr() -> str:
    assert ADR.is_file(), f"AD-5 artefact absent: {ADR.relative_to(ROOT)}"
    return ADR.read_text(encoding="utf-8")


def _env_keys_read_by_code() -> set[str]:
    keys: set[str] = set()
    for src in _ENV_SOURCES:
        files = sorted(src.glob("*.py")) if src.is_dir() else [src]
        for f in files:
            for m in _ENV_READ.finditer(f.read_text(encoding="utf-8")):
                keys.add(next(g for g in m.groups() if g))
    return keys


def test_artefact_exists_and_carries_the_ad5_ruling_verbatim() -> None:
    assert AD5_VERBATIM in _adr()
    assert "ADR-0014" in _adr()


def test_names_the_operations_durable_profile_steps_in_order() -> None:
    ops = OPERATIONS.read_text(encoding="utf-8")
    assert "`alembic upgrade head`" in ops and "`apps.cli serve`" in ops, "OPERATIONS §1 moved"
    text = _adr()
    i_pg = text.find("Postgres up")
    i_al = text.find("alembic upgrade head")
    i_sv = text.find("apps.cli serve")
    assert -1 < i_pg < i_al < i_sv, (
        "startup order must be Postgres up -> alembic upgrade head -> apps.cli serve"
    )


def test_states_one_process_with_relay_and_worker() -> None:
    text = _adr().lower()
    assert "one process" in text or "single api process" in text
    assert "outbox relay" in text and "worker" in text
    assert "apps/main.py" in text


def test_every_named_env_key_is_read_by_the_code() -> None:
    named = set(re.findall(r"`([A-Z][A-Z0-9_]{3,})`", _adr()))
    named -= {"ADR", "AD", "README", "UTF8", "HTTP", "HTTPS", "TLS", "SIGKILL", "GET", "POST"}
    assert named, "the artefact names no environment keys"
    read = _env_keys_read_by_code()
    invented = sorted(k for k in named if k not in read)
    assert invented == [], f"artefact names env keys the code never reads: {invented}"


def test_exclusions_carry_their_decision_references() -> None:
    text = _adr()
    assert "P-R188-04" in text, "multi-replica exclusion must cite P-R188-04"
    assert "no distributed worker" in text.lower()
    assert "no token streaming" in text.lower()
    assert "multi-replica" in text.lower()


def test_tls_at_ingress_and_hsts_posture() -> None:
    text = _adr()
    assert "`HSTS`" in text
    assert "ingress" in text.lower() or "reverse proxy" in text.lower()


def test_does_not_claim_production_ready() -> None:
    text = _adr()
    hits = [m.start() for m in re.finditer(r"production[- ]ready", text, flags=re.I)]
    for h in hits:
        window = text[max(0, h - 120) : h + 60].lower()
        assert "not" in window or "never" in window or "no " in window, (
            "the artefact must not claim Production Ready while D-03 is open (operator D1)"
        )
