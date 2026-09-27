/* INTELLIGENCE — P15 Skills · P16 Learning · P17 Sample detail · P18 Scenarios ·
   P19 Evaluation · P20 Context Lab. Users see the served skills list; admin
   surfaces are server-gated (403 rendered verbatim). Lifecycle buttons appear
   for the served transitions; the server refuses what it refuses. */

import { h, clear, section, pageHeader, badge, loading, empty, errorPanel, forbidden, kv, button, field, input, select, dataList, advancedPanel, json, renderValue, announce, unavailable, lifecycleStrip, shortId } from "../components.js";

/* Ordered lifecycle vocabularies are CONTRACT enums (core/contracts/evaluation.py
   VerificationLevel; skills import steps are the served route names). */
const VERIFICATION_LEVELS = ["RAW", "EVALUATED", "VALIDATED", "VERIFIED", "GOLD"];
const SAMPLE_STEPS = ["evaluate", "scan", "sanitize", "admit", "promote"];
const SKILL_IMPORT_STEPS = ["scan", "validate", "review", "approve", "activate"];

export function registerIntelligence({ api, router, main, isAdmin, isAdvanced }) {
  function tabs(active) {
    const items = [["skills", "Skills"]];
    if (isAdmin()) items.push(["learning", "Learning"], ["scenarios", "Scenarios"], ["context-lab", "Context Lab"]);
    return h("div", { class: "tabs-inline", role: "tablist" }, ...items.map(([k, label]) => h("a", { role: "tab", href: `#/intel/${k}`, "aria-selected": active === k ? "true" : "false", text: label })));
  }

  function gate(box, r, retry) {
    if (r.status === 403) {
      box.append(forbidden(r.body, r.status));
      return false;
    }
    if (r.status === 404) {
      box.append(unavailable("Not served by this process.", r.body && r.body.detail));
      return false;
    }
    if (!r.ok) {
      box.append(errorPanel(r.body, { status: r.status, onRetry: retry }));
      return false;
    }
    return true;
  }

  /* ----------------------------------------------------------------- P15 Skills */
  async function skillsPage() {
    const m = clear(main());
    m.append(pageHeader("Skills", { crumb: "Intelligence" }), tabs("skills"));
    const box = section("Served skills", loading("skills"));
    m.append(box);
    const r = await api.work.skills();
    clear(box).append(h("h2", { text: "Served skills" }));
    if (gate(box, r, skillsPage)) {
      const list = (r.body && r.body.skills) || [];
      box.append(list.length ? dataList([{ label: "skill", render: (s) => h("span", {}, h("strong", { text: s.name || s.key || s.id }), s.status ? badge(s.status) : null) }, { label: "description", render: (s) => renderValue(s.description) }, { label: "version", render: (s) => renderValue(s.version) }], list) : empty("No skills served."));
    }
    if (!isAdmin()) return;
    const imports = section("Imports (admin lifecycle)", loading("imports"));
    m.append(imports);
    const ir = await api.admin.skillImports();
    clear(imports).append(h("h2", { text: "Imports (admin lifecycle)" }));
    if (gate(imports, ir, skillsPage)) {
      const rows = (ir.body && (ir.body.imports || ir.body.skills)) || (Array.isArray(ir.body) ? ir.body : []);
      if (!rows.length) imports.append(empty("No skill imports."));
      rows.forEach((row) => {
        const id = row.skill_id || row.id;
        const card = h("article", { class: "card sub" }, h("div", { class: "row" }, h("strong", { class: "mono", text: id }), badge(row.status || row.state)), kv(Object.entries(row).filter(([k]) => !["skill_id", "id"].includes(k)).slice(0, 8)));
        const actions = h("div", { class: "actions" });
        SKILL_IMPORT_STEPS.forEach((step) =>
          actions.append(
            button(step, async () => {
              const res = await api.admin.skillImportStep(id, step, {});
              if (!res.ok) card.append(errorPanel(res.body, { status: res.status }));
              else {
                announce(`${step} done`);
                skillsPage();
              }
            }),
          ),
        );
        card.append(actions, advancedPanel("Record", json(row)));
        imports.append(card);
      });
      const src = input({ type: "text", placeholder: "source (as the server expects)" });
      const err = h("div");
      const form = h("form", { class: "stack", novalidate: true }, field("Import skill from source", src), err, h("div", { class: "actions" }, button("Import", null, { primary: true, type: "submit" })));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        clear(err);
        const res = await api.admin.importSkill({ source: src.value.trim() });
        if (!res.ok) err.append(errorPanel(res.body, { status: res.status }));
        else skillsPage();
      });
      imports.append(form, h("p", { class: "muted small", text: "Enable/disable a skill is a Change (Control · Changes)." }));
    }
  }
  router.route("/intel/skills", skillsPage);

  /* --------------------------------------------------------------- P16 Learning */
  async function learningPage() {
    const m = clear(main());
    m.append(pageHeader("Learning", { crumb: "Intelligence", actions: [button("Refresh", learningPage)] }), tabs("learning"));
    const dash = section("Lifecycle", loading("dashboard"));
    m.append(dash);
    const d = await api.admin.learningDashboard();
    clear(dash).append(h("h2", { text: "Lifecycle" }));
    if (!gate(dash, d, learningPage)) return;
    const b = d.body || {};
    dash.append(h("p", { class: "muted small", text: `measured_at ${b.measured_at || "—"} · placeholder ${b.placeholder === true ? "yes" : "no"}` }));
    const stages = [
      ["Experience (runs)", "→ capture a run as a sample from Run Detail · Advanced"],
      ["Samples", `${b.samples_total ?? "—"} total · by level ${JSON.stringify(b.samples_by_level || {})}`],
      ["Evaluate → Scan → Sanitize → Admit", `${b.evaluations_recorded ?? "—"} evaluations recorded · ${b.verified_samples ?? "—"} verified · ${b.eligible_samples ?? "—"} eligible`],
      ["Replay (scenarios)", "see Scenarios"],
      ["Promote → GOLD", `${b.gold_samples ?? "—"} gold · ${(b.promotion_history || []).length} promotions · ${(b.rollback_actions || []).length} rollbacks`],
      ["Learned keys", `${(b.learned_keys || []).length}`],
    ];
    dash.append(h("ol", { class: "lifecycle-map" }, ...stages.map(([k, v]) => h("li", {}, h("strong", { text: k }), h("span", { class: "muted", text: ` ${v}` })))));
    if (b.deferred) dash.append(advancedPanel("Deferred (unmeasured) metrics — named by the server", json(b.deferred)));
    dash.append(advancedPanel("Raw dashboard", json(b)));

    const samplesBox = section("Samples", loading("samples"));
    m.append(samplesBox);
    const s = await api.admin.learningSamples();
    clear(samplesBox).append(h("h2", { text: "Samples" }));
    if (gate(samplesBox, s, learningPage)) {
      const rows = (s.body && s.body.samples) || (Array.isArray(s.body) ? s.body : []);
      const level = select([{ value: "", label: "level: all" }, ...VERIFICATION_LEVELS.map((l) => ({ value: l, label: `level: ${l}` }))], { "aria-label": "level filter" });
      const list = h("div");
      const render = () => {
        clear(list);
        const filtered = rows.filter((x) => !level.value || x.verification_level === level.value).slice(0, 50);
        list.append(
          dataList(
            [
              { label: "sample", render: (x) => h("span", { class: "mono", text: shortId(x.id) }) },
              { label: "level", render: (x) => badge(x.verification_level, "level") },
              { label: "eligibility", render: (x) => badge(x.eligibility) },
              { label: "sanitization", render: (x) => badge(x.sanitization_state) },
              { label: "source run", render: (x) => h("a", { href: `#/runs/${x.source_execution_id}`, class: "mono", text: shortId(x.source_execution_id) }) },
            ],
            filtered,
            { onRow: (x) => router.navigate(`/intel/learning/${x.id}`), emptyText: "No samples.", limitNote: rows.length > 50 ? "showing 50 — filter by level to narrow" : null },
          ),
        );
      };
      level.addEventListener("change", render);
      const capture = input({ type: "text", placeholder: "execution id to capture" });
      const err = h("div");
      const form = h("form", { class: "row", novalidate: true }, capture, button("Capture", null, { primary: true, type: "submit" }));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        clear(err);
        const c = await api.admin.captureSample(capture.value.trim());
        if (!c.ok) err.append(errorPanel(c.body, { status: c.status }));
        else router.navigate(`/intel/learning/${c.body.id || c.body.sample_id}`);
      });
      samplesBox.append(h("div", { class: "filters" }, level), list, form, err);
      render();
    }

    const askBox = section("Ask learning");
    const q = input({ type: "text", placeholder: "question about what was learned" });
    const out = h("div");
    const askForm = h("form", { class: "row", novalidate: true }, q, button("Ask", null, { primary: true, type: "submit" }));
    askForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out).append(loading());
      const a = await api.admin.learningAsk(q.value.trim());
      clear(out);
      if (!a.ok) out.append(errorPanel(a.body, { status: a.status }));
      else out.append(json(a.body));
    });
    askBox.append(askForm, out);
    m.append(askBox);

    const review = section("Review", loading("changes since review"));
    m.append(review);
    const [csr, learned] = await Promise.all([api.admin.changesSinceReview(), api.admin.learned()]);
    clear(review).append(h("h2", { text: "Review" }));
    if (csr.ok) {
      review.append(
        kv([["changes since review", Array.isArray(csr.body && csr.body.changes) ? csr.body.changes.length : renderValue(csr.body)]]),
        advancedPanel("Changes since review", json(csr.body)),
        button("Mark reviewed", async () => {
          const r = await api.admin.markReviewed();
          if (!r.ok) review.append(errorPanel(r.body, { status: r.status }));
          else learningPage();
        }),
      );
    } else review.append(errorPanel(csr.body, { status: csr.status }));
    if (learned.ok) review.append(advancedPanel("Learned", json(learned.body)));
    if (isAdvanced()) {
      const retest = h("div");
      review.append(
        h("h3", { text: "Capability re-test" }),
        button("Run capability re-test", async () => {
          clear(retest).append(loading());
          const r = await api.admin.capabilityRetest({});
          clear(retest);
          retest.append(r.ok ? json(r.body) : errorPanel(r.body, { status: r.status }));
        }),
        retest,
      );
      const holds = await api.admin.custodyHolds();
      review.append(h("h3", { text: "Custody" }), holds.ok ? json(holds.body) : unavailable("Custody governance is not composed in this process.", holds.body && holds.body.error && holds.body.error.message));
    }
  }
  router.route("/intel/learning", learningPage);

  /* ----------------------------------------------------------- P17 Sample detail */
  async function samplePage(id) {
    const m = clear(main());
    m.append(pageHeader(`Sample ${shortId(id)}`, { crumb: "Intelligence · Learning" }), tabs("learning"));
    const box = h("div", {}, loading("sample"));
    m.append(box);
    const r = await api.admin.learningSample(id);
    clear(box);
    if (!gate(box, r, () => samplePage(id))) return;
    const rec = r.body || {};
    box.append(section("Lifecycle", lifecycleStrip(VERIFICATION_LEVELS, rec.verification_level)), section("Record", kv([["id", rec.id], ["source run", h("a", { href: `#/runs/${rec.source_execution_id}`, class: "mono", text: rec.source_execution_id })], ["eligibility", badge(rec.eligibility)], ["sanitization", badge(rec.sanitization_state)], ["verification level", badge(rec.verification_level, "level")], ["tenant", rec.tenant_id]]), advancedPanel("Raw record", json(rec))));
    const out = h("div");
    const actions = h("div", { class: "actions" });
    const harvested = { evaluation_id: null, regression_execution_id: null };
    SAMPLE_STEPS.filter((s) => s !== "promote").forEach((step) =>
      actions.append(
        button(step, async () => {
          clear(out).append(loading(step));
          const res = await api.admin.sampleStep(id, step, {});
          clear(out);
          if (!res.ok) out.append(errorPanel(res.body, { status: res.status }));
          else {
            if (res.body && res.body.evaluation_id) harvested.evaluation_id = res.body.evaluation_id;
            if (res.body && res.body.id && step === "evaluate") harvested.evaluation_id = harvested.evaluation_id || res.body.id;
            out.append(h("p", {}, h("strong", { text: `${step}: ` }), badge(res.status)), json(res.body));
            announce(`${step} recorded`);
            evalId.value = harvested.evaluation_id || evalId.value;
          }
        }),
      ),
    );
    const evalId = input({ type: "text", placeholder: "evaluation_id (harvested from Evaluate)" });
    const secEvalId = input({ type: "text", placeholder: "security_evaluation_id (same record if combined)" });
    const regId = input({ type: "text", placeholder: "regression_execution_id (a PASSED scenario replay)" });
    const attest = input({ type: "text", placeholder: "human attestation note" });
    const promoteErr = h("div");
    const promoteForm = h("form", { class: "stack", novalidate: true }, h("h3", { text: "Promote (strict evidence)" }), h("p", { class: "muted small", text: "Promotion requires evidence references the server resolves itself; self-asserted passes are refused." }), field("evaluation_id", evalId), field("security_evaluation_id", secEvalId), field("regression_execution_id", regId), field("Attestation", attest), promoteErr, h("div", { class: "actions" }, button("Promote", null, { primary: true, type: "submit" })));
    promoteForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(promoteErr);
      const body = { evidence_refs: { evaluation_id: evalId.value.trim() || undefined, security_evaluation_id: secEvalId.value.trim() || evalId.value.trim() || undefined, regression_execution_id: regId.value.trim() || undefined }, attestations: attest.value.trim() ? [attest.value.trim()] : [] };
      const res = await api.admin.sampleStep(id, "promote", body);
      if (!res.ok) promoteErr.append(errorPanel(res.body, { status: res.status }));
      else {
        promoteErr.append(h("p", {}, h("strong", { text: `promoted: ${res.body && res.body.promoted}` })), json(res.body));
        announce(res.body && res.body.promoted ? "Promoted to GOLD." : "Promotion refused by the server.");
        if (res.body && res.body.promoted) samplePage(id);
      }
    });
    box.append(section("Actions", actions, out, h("p", { class: "muted small", text: "Replay: create/replay a scenario for this sample's source run in Scenarios, then paste the PASSED execution id below." }), promoteForm));
  }
  router.route("/intel/learning/:id", ({ params }) => samplePage(params.id));

  /* -------------------------------------------------------------- P18 Scenarios */
  async function scenariosPage() {
    const m = clear(main());
    m.append(pageHeader("Scenarios", { crumb: "Intelligence" }), tabs("scenarios"));
    const box = h("div", {}, loading("scenarios"));
    m.append(box);
    const r = await api.admin.scenarios();
    clear(box);
    if (!gate(box, r, scenariosPage)) return;
    const rows = (r.body && r.body.scenarios) || (Array.isArray(r.body) ? r.body : []);
    const out = h("div");
    box.append(
      dataList(
        [
          { label: "scenario", render: (s) => h("span", { class: "mono", text: shortId(s.id || s.scenario_id) }) },
          { label: "name", render: (s) => renderValue(s.name || s.title) },
          { label: "source run", render: (s) => (s.source_execution_id ? h("a", { href: `#/runs/${s.source_execution_id}`, class: "mono", text: shortId(s.source_execution_id) }) : renderValue(null)) },
          { label: "checks", render: (s) => renderValue(s.checks || s.check_names) },
          {
            label: "actions",
            render: (s) =>
              button("Replay", async () => {
                clear(out).append(loading("replay"));
                const res = await api.admin.replayScenario(s.id || s.scenario_id);
                clear(out);
                out.append(res.ok ? h("div", {}, h("p", {}, h("strong", { text: "Replay: " }), badge(res.body && (res.body.status || res.body.verdict || res.status))), res.body && res.body.execution_id ? h("p", {}, "execution ", h("a", { href: `#/runs/${res.body.execution_id}`, class: "mono", text: res.body.execution_id })) : null, json(res.body)) : errorPanel(res.body, { status: res.status }));
              }),
          },
        ],
        rows,
        { emptyText: "No scenarios." },
      ),
      out,
    );
    const src = input({ type: "text", placeholder: "source execution id", required: true });
    const name = input({ type: "text", placeholder: "name" });
    const err = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: "Create scenario" }), field("Source execution", src), field("Name", name), err, h("div", { class: "actions" }, button("Create", null, { primary: true, type: "submit" }), button("Run regression pack", async () => {
      clear(out).append(loading("regression pack"));
      const res = await api.admin.regressionPack();
      clear(out);
      out.append(res.ok ? json(res.body) : errorPanel(res.body, { status: res.status }));
    })));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      const body = { source_execution_id: src.value.trim() };
      if (name.value.trim()) body.name = name.value.trim();
      const res = await api.admin.createScenario(body);
      if (!res.ok) err.append(errorPanel(res.body, { status: res.status }));
      else scenariosPage();
    });
    box.append(form);
  }
  router.route("/intel/scenarios", scenariosPage);

  /* ------------------------------------------------------------- P19 Evaluation */
  router.route("/intel/evaluations/:id", async ({ params }) => {
    const m = clear(main());
    m.append(pageHeader(`Evaluation ${shortId(params.id)}`, { crumb: "Intelligence" }));
    const box = h("div", {}, loading("evaluation"));
    m.append(box);
    const r = await api.admin.evaluation(params.id);
    clear(box);
    if (!gate(box, r, () => router.resolve())) return;
    const rec = r.body || {};
    box.append(section("Record", kv(Object.entries(rec).filter(([, v]) => typeof v !== "object" || v === null)), advancedPanel("Full record", json(rec))));
  });

  /* ------------------------------------------------------------ P20 Context Lab */
  async function contextLabPage() {
    const m = clear(main());
    m.append(pageHeader("Context Lab", { crumb: "Intelligence" }), tabs("context-lab"));
    const box = h("div", {}, loading("checks"));
    m.append(box);
    const r = await api.admin.contextLabChecks();
    clear(box);
    if (!gate(box, r, contextLabPage)) return;
    const checks = (r.body && r.body.checks) || (Array.isArray(r.body) ? r.body : []);
    box.append(section("Served checks", checks.length ? h("ul", {}, ...checks.map((c) => h("li", {}, h("strong", { text: typeof c === "string" ? c : c.name || c.id }), typeof c === "object" && c.description ? h("span", { class: "muted", text: ` — ${c.description}` }) : null))) : empty("No checks served.")));
    const ask = h("textarea", { class: "input", rows: "4", placeholder: "ask to compose context for" });
    const out = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: "Validate composition" }), field("Ask", ask), h("div", { class: "actions" }, button("Validate", null, { primary: true, type: "submit" })), out);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out).append(loading("validate"));
      const res = await api.admin.contextLabValidate({ ask: ask.value });
      clear(out);
      if (!res.ok) out.append(errorPanel(res.body, { status: res.status }));
      else {
        const results = (res.body && res.body.checks) || (res.body && res.body.results) || [];
        if (Array.isArray(results) && results.length) out.append(dataList([{ label: "check", render: (c) => renderValue(c.name || c.check) }, { label: "result", render: (c) => badge(c.passed === true ? "passed" : c.passed === false ? "failed" : c.status || c.result) }, { label: "detail", render: (c) => renderValue(c.detail || c.message) }], results));
        out.append(advancedPanel("Raw result", json(res.body)));
      }
    });
    box.append(form);
  }
  router.route("/intel/context-lab", contextLabPage);
  router.route("/intel", () => router.replace("/intel/skills"));
}
