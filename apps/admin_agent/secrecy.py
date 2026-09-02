"""R4-forbidden content scrubbing — AA-2 acceptance criterion 4.

R165: the ONE scrubber lives in ``core.security.scrub`` so the public API
(``apps.api``) can scrub agent failure causes without importing the admin
agent (which itself imports ``apps.api`` — a cycle). This module keeps the
historical import path for the admin agent and its tests.
"""

from __future__ import annotations

from core.security.scrub import scrub_json, scrub_object, scrub_text

__all__ = ["scrub_json", "scrub_object", "scrub_text"]
