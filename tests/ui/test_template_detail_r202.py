"""R202 guard — Templates + App Factory UX (UI-only; production ceiling 0).

Operator (verbatim anchors): "APPROVE R202. Confirm the proposed rulings: D1 = a, D2 = i, D3 = i,
D4 = i, D5 = i, D6 = i, D7 = yes, D8 = defer. Confirm the declared ui/app/app.js /v1/ ceiling
adjustment: 22 -> 23. ... Do not add TemplateOverride/model selection, project filtering, Command
template reads, template persistence, user/workspace templates, or App Factory code generation."

Pins (static; the real-browser proof lives in evidence/r202/):
- [D1 = a, D2 = i] loadTemplateDetail reads GET /v1/templates/{ref} through api() — exactly ONE
  such literal in ui/app/app.js; fired on the #ask-template change and after a restored choice;
  never at module load; not for the empty choice.
- [D3 = i, D6 = i] renderTemplateDetail renders the served StrategyTemplate verbatim (name,
  description, tags, skills, required_capabilities, strategy.stages[] key/kind/role/depends_on/
  instruction) and derives the stage model posture from the served model_policy (null -> auto).
  No model selector, no code-generation affordance, no provider names, no hardcoded template ref.
- [D4 = i] followEvents labels node rows 'kind · role' from the loaded detail (no new read).
- [D5 = i] Command reads no templates: command.js 12 /v1/ + one fetch(; templates href unchanged.
- counts: ui/app/app.js /v1/ == 23 (declared ceiling), fetch( 4; ui/admin/app.js 73; round_r202 0/0.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "ui" / "app"
COMMAND = APP / "command"
ADMIN = ROOT / "ui" / "admin"
MANIFEST = ROOT / "engineering" / "verification" / "green_manifest.json"
PROVIDER_WORDS = ("groq", "gsk", "openai", "anthropic", "genspark")
FORBIDDEN_AFFORDANCES = ("generate code", "build the app", "scaffold", "codegen", "code generation")
FABRICATED_STATES = ("thinking", "speaking", "listening", "energized", "processing", "reasoning")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", text)


def _body(js: str, name: str) -> str:
    marker = f"function {name}("
    assert marker in js, f"{name} is not defined"
    start = js.index(marker)
    i = js.index("{", js.index(")", start))
    depth = 0
    for j in range(i, len(js)):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i : j + 1]
    raise AssertionError(f"unbalanced braces in {name}")


def _app_raw() -> str:
    return _read(APP / "app.js")


def _app() -> str:
    return _strip(_app_raw())


def _html() -> str:
    return _read(APP / "index.html")


def _manifest() -> dict:
    return json.loads(_read(MANIFEST))


# ------------------------------------------------------------------ R202-A (D1 = a, D2 = i)


def test_detail_route_is_consumed_exactly_once_through_api() -> None:
    js = _app()
    assert js.count("/v1/templates/") == 1, "GET /v1/templates/{ref} must have exactly ONE consumer"
    body = _body(js, "loadTemplateDetail")
    assert "/v1/templates/" in body and "encodeURIComponent(" in body, "the ref is encoded"
    assert "api(" in body and "fetch(" not in body, "reads go through the ONE api() helper"
    assert "renderTemplateDetail(" in body
    assert "renderError(" in body, "a refused read renders the server body verbatim"


def test_detail_read_fires_on_choice_never_at_boot_never_for_none() -> None:
    js = _app()
    body = _body(js, "loadTemplateDetail")
    assert re.search(r"if\s*\(\s*!ref\s*\)", body), "empty choice -> panel cleared, NO request"
    wire = _body(js, "wireAsk")
    assert "loadTemplateDetail(" in wire, "the #ask-template change handler loads the detail"
    restore = _body(js, "restoreContext")
    assert "loadTemplateDetail(" in restore, "a restored choice loads its detail once"
    # the call must live inside function bodies only (never at module level)
    outside = re.sub(r"(?:async\s+)?function\s+\w+\([^)]*\)\s*\{.*?\n\}", "", js, flags=re.S)
    outside = re.sub(r"addEventListener\([^;]*?\{.*?\n\s*\}\);", "", outside, flags=re.S)
    assert "loadTemplateDetail(" not in outside, "must not fire at module load"
    assert "setInterval(" not in js and "setTimeout(" not in body


def test_render_uses_only_served_fields_and_derives_auto_posture() -> None:
    body = _body(_app(), "renderTemplateDetail")
    served = ("name", "description", "tags", "skills", "required_capabilities", "strategy",
              "stages")
    for field in served:
        assert field in body, field
    for field in ("key", "kind", "role", "depends_on", "instruction", "model_policy"):
        assert field in body, field
    assert "stagePolicyText(" in body, "the model cell goes through stagePolicyText()"
    policy = _body(_app(), "stagePolicyText")
    assert re.search(r"if\s*\(\s*!policy\s*\)", policy), "null policy is the AUTO branch"
    assert "auto" in policy.lower() and "router" in policy.lower(), (
        "null model_policy must be shown as the Router AUTO posture"
    )
    assert "<select" not in body and 'createElement("select")' not in body, "no model selector (D6)"
    low = body.lower()
    for word in PROVIDER_WORDS:
        assert not re.search(rf"[\"'`]{word}[\"'`]", body, flags=re.I), word
    for phrase in FORBIDDEN_AFFORDANCES:
        assert phrase not in low, phrase


def test_no_hardcoded_template_ref_or_fabricated_state() -> None:
    js = _app_raw()
    assert "app_factory" not in js.lower(), "hardcoded template id/ref"
    for state in FABRICATED_STATES:
        assert not re.search(rf"[\"'`]{state}[\"'`]", js), state


def test_panel_markup_present_and_wired() -> None:
    html = _html()
    for el in (
        'id="template-detail"',
        'id="template-detail-name"',
        'id="template-detail-description"',
        'id="template-detail-tags"',
        'id="template-detail-error"',
        'id="template-stages"',
    ):
        assert el in html, el
    assert re.search(r'id="template-detail"[^>]*\bhidden\b', html), "panel starts hidden"
    wired = re.findall(r"(href|src|action|data-[a-z-]+)=[\"'][^\"']*/v1/", html)
    assert wired == [], wired
    assert "/v1/" not in _read(APP / "styles.css")


# ------------------------------------------------------------------ R202-B (D4 = i)


def test_timeline_rows_carry_stage_kind_and_role_from_loaded_detail() -> None:
    js = _app()
    body = _body(js, "followEvents")
    assert "stageLabel(" in body, "node rows are labelled through stageLabel()"
    label = _body(js, "stageLabel")
    assert "templateDetail" in label and "kind" in label and "role" in label
    assert "api(" not in label and "fetch(" not in label and "/v1/" not in label


# ------------------------------------------------------------------ D5 = i, counts, ceiling


def test_command_reads_no_templates_and_href_unchanged() -> None:
    cmd = _read(COMMAND / "command.js")
    assert cmd.count("/v1/") == 12 and _strip(cmd).count("fetch(") == 1
    owner = 'templates: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false }'
    assert owner in cmd


def test_counts_and_declared_ceiling() -> None:
    raw = _app_raw()
    m = _manifest()
    ceiling = int(m["ui_workbench_static_check"]["v1_count_ceiling_app_js"])
    assert ceiling == 23, "operator-declared ceiling for R202"
    assert raw.count("/v1/") == 23, f"measured {raw.count('/v1/')}"
    assert raw.count("fetch(") == 4
    assert _read(ADMIN / "app.js").count("/v1/") == 73
    block = m["change_budget"]["round_r202"]
    assert int(block["ceiling"]) == 0 and int(block["changes_used"]) == 0
    assert any("R202-A" in i for i in block["items"])


def test_execute_wire_shape_unchanged() -> None:
    body = _body(_app(), "submitAsk")
    assert re.search(r"if\s*\(\s*templateRef\s*\)\s*body\.execution_strategy\s*=", body)
    assert "template_override" not in body and "model_policy" not in body, "D6: wire unchanged"
