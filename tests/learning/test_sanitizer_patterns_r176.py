"""R176 FIX-06 (F-R176-09): the credential-value patterns shared by the
learning sanitizer and the memory write screen must recognise the provider
key shapes the platform actually routes to — the repo's own gate
(``check_repo.sh``) already knows ``gsk_``; the sanitizer did not (A8:
``clean: true`` for a Groq-shaped secret). Fails on the parent commit.

Also pins ONE vocabulary: the memory screen must consume the sanitizer's
table, not keep a drifting copy.
"""

from __future__ import annotations

import pytest

from core.learning.sanitizer import SECRET_LABELS, sanitize_knowledge

_SHAPES: list[tuple[str, str, str]] = [
    ("groq", "gsk_" + "F" * 28, "groq_api_key"),
    ("groq_repo_fixture", "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123", "groq_api_key"),
    ("anthropic", "sk-ant-api03-" + "a" * 40, "anthropic_api_key"),
    ("google", "AIza" + "B" * 35, "google_api_key"),
    ("slack_bot", "xoxb-" + "1" * 12 + "-" + "a" * 24, "opaque_provider_token"),
    ("slack_app", "xoxp-" + "1" * 12 + "-" + "a" * 24, "opaque_provider_token"),
    ("github_fine_grained", "github_pat_" + "A" * 22 + "_" + "b" * 59, "github_pat"),
    ("openai_project", "sk-proj-" + "c" * 48, "opaque_provider_token"),
    ("generic_assignment", "api_key = " + "Z" * 32, "generic_api_key_assignment"),
    ("generic_colon", "apiKey: " + "y" * 24, "generic_api_key_assignment"),
]


@pytest.mark.parametrize("name,secret,label", _SHAPES, ids=[s[0] for s in _SHAPES])
def test_provider_key_shapes_are_findings(name: str, secret: str, label: str) -> None:
    report = sanitize_knowledge("note", {"text": f"the key is {secret} ok"})
    assert not report.clean, name
    labels = {f.label for f in report.findings}
    assert label in labels, (name, labels)
    assert label in SECRET_LABELS
    for f in report.findings:
        assert secret not in f.fingerprint and secret not in f.path


@pytest.mark.parametrize(
    "benign",
    [
        "the sky is blue",
        "model gsk-quick is fast",
        "use api_key rotation weekly",
        "AIzaWhatever",
        "https://example.com/sk-shop",
    ],
)
def test_benign_text_stays_clean(benign: str) -> None:
    assert sanitize_knowledge("note", {"text": benign}).clean


def test_memory_screen_uses_the_same_pattern_table() -> None:
    """One vocabulary, two enforcement points (sanitizer docstring)."""
    from core.learning import sanitizer
    from core.memory import memory

    assert memory._SECRET_VALUE_PATTERNS is sanitizer._VALUE_PATTERNS
