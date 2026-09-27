/* CONTROL — the admin control plane (P21–P31). Inspect → Configure → Enable/
   Disable → Test → Observe → Audit. Every control maps to a served route; forms
   for Changes are GENERATED from GET /v1/admin/capabilities/actions
   (`actions[].fields[]{name,kind,required}`) — one generator, no duplicated
   schemas. Non-served areas render the honest NOT AVAILABLE state. */

import { h, clear, section, pageHeader, badge, loading, empty, errorPanel, forbidden, kv, button, field, input, select, confirmDialog, dataList, advancedPanel, json, renderValue, announce, unavailable, lifecycleStrip, shortId, fmtTime, capabilityNode } from "../components.js";
import { ctx, remember } from "../context.js";

/* Contract enum (core/contracts/admin.py ChangeState) rendered as a stepper. */
const CHANGE_FLOW = ["draft", "validated", "published"];
const CHANGE_TERMINAL = ["rejected", "rolled_back"];
const SEARCH_THRESHOLD = 50;

const AREAS = [
  ["capabilities", "Capabilities"],
  ["catalog", "Catalog"],
  ["changes", "Changes"],
  ["plans", "Plans"],
  ["routing", "Routing"],
  ["usage", "Usage"],
  ["audit", "Audit"],
  ["notifications", "Notifications"],
  ["system", "System"],
  ["self-review", "Self-review"],
  ["source", "Source changes"],
  ["engineering", "Engineering"],
];

export function registerControl(deps) {
  const { api, router, main, isAdvanced } = deps;

  function tabs(active) {
    return h("nav", { class: "tabs-inline wrap", "aria-label": "control areas" }, ...AREAS.map(([k, label]) => h("a", { href: `#/control/${k}`, "aria-current": active === k ? "page" : null, text: label })));
  }

  function frame(area, title, opts) {
    const m = clear(main());
    m.append(pageHeader(title, { crumb: "Control", ...(opts || {}) }), tabs(area));
    const box = h("div", {}, loading(title));
    m.append(box);
    return box;
  }

  function gate(box, r, retry) {
    if (r.status === 403) {
      box.append(forbidden(r.body, r.status));
      return false;
    }
    if (r.status === 404) {
      box.append(unavailable("NOT AVAILABLE IN THIS PROCESS", r.body && (r.body.detail || (r.body.error && r.body.error.message))));
      return false;
    }
    if (!r.ok) {
      box.append(errorPanel(r.body, { status: r.status, onRetry: retry }));
      return false;
    }
    return true;
  }

  /** Search-first list: > SEARCH_THRESHOLD rows render nothing until filtered. */
  function searchFirst(rows, render, placeholder) {
    const search = input({ type: "search", placeholder, "aria-label": placeholder });
    const out = h("div");
    const go = () => {
      clear(out);
      const q = search.value.trim().toLowerCase();
      if (rows.length > SEARCH_THRESHOLD && !q) {
        out.append(empty(`Type to search ${rows.length} records.`));
        return;
      }
      out.append(render(rows.filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q)).slice(0, SEARCH_THRESHOLD), rows.length));
    };
    search.addEventListener("input", go);
    go();
    return h("div", {}, h("div", { class: "filters" }, search), out);
  }

  const shared = { frame, gate, searchFirst, tabs };

  /* ----------------------------------------------------------- P31 Capabilities */
  async function capabilitiesPage() {
    const box = frame("capabilities", "Capabilities", { subtitle: "What THIS process can actually do — served records, rendered 1:1." });
    const [cat, ex] = await Promise.all([api.admin.capabilities(), api.admin.capabilitiesExercisable()]);
    clear(box);
    if (!gate(box, cat, capabilitiesPage)) return;
    const records = (cat.body && cat.body.capabilities) || [];
    const exercisable = new Set((ex.ok && ex.body && ex.body.exercisable) || []);
    const detail = h("div", { class: "cap-detail", "aria-live": "polite" }, h("p", { class: "muted", text: "Select a record." }));
    const ring = h("div", { class: "cap-ring", role: "list" });
    records.forEach((rec) => {
      ring.append(
        h(
          "div",
          { role: "listitem" },
          capabilityNode(rec, (r) => {
            clear(detail).append(kv([["id", r.id], ["state", badge(r.state, "cap")], ["evidence", r.evidence]]));
            if (exercisable.has(r.id)) {
              const out = h("div");
              detail.append(
                button("Exercise", async () => {
                  clear(out).append(loading("exercise"));
                  const res = await api.admin.exercise(r.id);
                  clear(out);
                  out.append(res.ok ? json(res.body) : errorPanel(res.body, { status: res.status }));
                }),
                out,
              );
            } else detail.append(h("p", { class: "muted small", text: "Not exercisable from the shell (server list)." }));
          }),
        ),
      );
    });
    box.append(section(`Catalog · scope ${cat.body.scope}`, ring, detail));
    if (isAdvanced()) {
      const msg = h("textarea", { class: "input", rows: "3", placeholder: "Ask the admin agent (read tools)…" });
      const out = h("div");
      const form = h("form", { class: "stack", novalidate: true }, field("Message", msg), h("div", { class: "actions" }, button("Ask", null, { primary: true, type: "submit" })), out);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        clear(out).append(loading("converse"));
        const res = await api.admin.converse(msg.value);
        clear(out);
        out.append(res.ok ? json(res.body) : errorPanel(res.body, { status: res.status }));
      });
      box.append(section("Admin agent (Advanced)", form));
    }
  }
  router.route("/control/capabilities", capabilitiesPage);
  router.route("/control", () => router.replace("/control/capabilities"));

  /* ---------------------------------------------------------------- P21 Catalog */
  async function catalogPage(tab) {
    const box = frame("catalog", "Catalog");
    const isProviders = tab === "providers";
    const [models, providers] = await Promise.all([api.admin.models(), api.admin.providers()]);
    clear(box);
    box.append(h("div", { class: "tabs-inline", role: "tablist" }, h("a", { role: "tab", href: "#/control/catalog", "aria-selected": !isProviders ? "true" : "false", text: "Models" }), h("a", { role: "tab", href: "#/control/catalog?tab=providers", "aria-selected": isProviders ? "true" : "false", text: "Providers" })));
    if (!isProviders) {
      if (!gate(box, models, () => catalogPage(tab))) return;
      const rows = (models.body && models.body.models) || [];
      box.append(
        searchFirst(
          rows,
          (visible, total) =>
            dataList(
              [
                { label: "model_key", render: (r) => h("span", { class: "mono", text: r.model_key }) },
                { label: "display", key: "display_name" },
                { label: "tier", key: "tier" },
                { label: "capabilities", render: (r) => renderValue(r.capabilities) },
                { label: "status", render: (r) => badge(r.status) },
                { label: "actions", render: (r) => h("a", { class: "btn", href: router.buildHash("/control/changes", { action: r.status === "active" ? "disable_model" : "enable_model", model_key: r.model_key, model_id: r.id }), text: r.status === "active" ? "Draft disable" : "Draft enable" }) },
              ],
              visible,
              { emptyText: "No models.", limitNote: total > visible.length ? `showing ${visible.length} of ${total}` : null },
            ),
          "search model key / capability",
        ),
      );
      if (isAdvanced()) box.append(advancedPanel("Scores (raw)", json(rows.map((r) => ({ model_key: r.model_key, quality_score: r.quality_score, speed_score: r.speed_score, cost_score: r.cost_score, reliability_score: r.reliability_score })))));
    } else {
      if (!gate(box, providers, () => catalogPage(tab))) return;
      const rows = (providers.body && providers.body.providers) || [];
      remember("providers", rows);
      box.append(
        searchFirst(
          rows,
          (visible, total) =>
            dataList(
              [
                { label: "provider_key", render: (r) => h("a", { href: `#/control/providers/${encodeURIComponent(r.provider_key)}`, class: "mono", text: r.provider_key }) },
                { label: "display", key: "display_name" },
                { label: "status", render: (r) => badge(r.status) },
                { label: "routable", render: (r) => badge(r.is_routable ? "routable" : "not routable", "flag") },
                { label: "template", render: (r) => (r.is_template ? badge("template", "flag") : h("span", { class: "muted", text: "—" })) },
                { label: "account pool", render: (r) => renderValue(r.supports_account_pool) },
              ],
              visible,
              { emptyText: "No providers.", limitNote: total > visible.length ? `showing ${visible.length} of ${total}` : null },
            ),
          "search provider key",
        ),
        h("div", { class: "actions" }, h("a", { class: "btn btn-primary", href: "#/control/providers/onboard", text: "Onboard gateway provider" })),
      );
    }
  }
  router.route("/control/catalog", ({ query }) => catalogPage(query.tab));

  /* -------------------------------------------------------- P21b Provider detail */
  router.route("/control/providers/onboard", async () => {
    const box = frame("catalog", "Onboard gateway provider", { crumb: "Control · Catalog" });
    clear(box);
    const f = {
      provider_key: input({ type: "text", required: true }),
      display_name: input({ type: "text", required: true }),
      operations: input({ type: "text", placeholder: "comma-separated" }),
      capabilities: input({ type: "text", placeholder: "comma-separated" }),
      static_models: input({ type: "text", placeholder: "comma-separated model keys" }),
      credential_ref: input({ type: "text" }),
      route_token_ref: input({ type: "text" }),
      credential_mode: input({ type: "text" }),
      definition_version: input({ type: "text" }),
    };
    const discover = h("input", { type: "checkbox", id: "discover" });
    const out = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, ...Object.entries(f).map(([k, el]) => field(k, el)), h("label", { class: "chip-check", for: "discover" }, discover, " discover (read the gateway's describe endpoint)"), h("p", { class: "muted small", text: "The provider is registered DISABLED; enabling is a Change." }), h("div", { class: "actions" }, h("a", { class: "btn", href: "#/control/catalog?tab=providers", text: "Cancel" }), button("Onboard", null, { primary: true, type: "submit" })), out);
    const csv = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out).append(loading("onboarding"));
      const body = { provider_key: f.provider_key.value.trim(), display_name: f.display_name.value.trim(), discover: discover.checked };
      const ops = csv(f.operations.value);
      if (ops.length) body.operations = ops;
      const caps = csv(f.capabilities.value);
      if (caps.length) body.capabilities = caps;
      const sm = csv(f.static_models.value);
      if (sm.length) body.static_models = sm;
      ["credential_ref", "route_token_ref", "credential_mode", "definition_version"].forEach((k) => {
        if (f[k].value.trim()) body[k] = f[k].value.trim();
      });
      const r = await api.admin.onboardProvider(body);
      clear(out);
      if (!r.ok) out.append(errorPanel(r.body, { status: r.status }));
      else {
        announce("Provider registered (disabled).");
        out.append(h("p", {}, h("strong", { text: "Registered DISABLED — enable via Changes." })), r.body && r.body.unverified ? h("p", { class: "muted", text: `unverified: ${JSON.stringify(r.body.unverified)}` }) : null, json(r.body), h("a", { class: "btn", href: "#/control/catalog?tab=providers", text: "Back to providers" }));
      }
    });
    box.append(form);
  });

  router.route("/control/providers/:key", async ({ params }) => {
    const box = frame("catalog", `Provider ${params.key}`, { crumb: "Control · Catalog" });
    const [providers, models] = await Promise.all([api.admin.providers(), api.work.models()]);
    clear(box);
    if (!gate(box, providers, () => router.resolve())) return;
    const row = ((providers.body && providers.body.providers) || []).find((p) => p.provider_key === params.key);
    if (!row) {
      box.append(unavailable("Unknown provider key in this process."));
      return;
    }
    box.append(section("Facts", kv(Object.entries(row))));
    const served = models.ok ? ((models.body && models.body.models) || []).filter((m) => (m.providers || []).includes(params.key)) : [];
    const rt = (m) => (m.runtime || []).find((r) => r.provider === params.key) || {};
    box.append(
      section(
        "Models served through this provider (active catalog)",
        served.length
          ? dataList(
              [
                { label: "model", render: (m) => h("a", { href: `#/work/models/${m.id}`, text: m.name }) },
                { label: "availability", render: (m) => badge(m.availability) },
                { label: "runtime (this provider)", render: (m) => badge(rt(m).eligible === false ? "not eligible" : "eligible", "elig") },
                { label: "reason", render: (m) => renderValue(rt(m).reason) },
              ],
              served,
            )
          : empty("No active model is bound to this provider."),
      ),
      section("Enable / disable", h("div", { class: "actions" }, h("a", { class: "btn", href: router.buildHash("/control/changes", { action: row.status === "active" ? "disable_provider" : "enable_provider", provider_key: row.provider_key, provider_id: row.id }), text: row.status === "active" ? "Draft disable" : "Draft enable" }))),
      section("Accounts", unavailable("NOT AVAILABLE — no account read/write route is served.")),
      section("Rate limits (RPM) / quotas", unavailable("NOT AVAILABLE — limits_metadata has no admin writer; the Router enforces declared RPM only.")),
    );
  });

  registerControlPlane(deps, shared);
}

/* ================= second half: changes · plans · routing · usage · audit ·
   notifications · system · self-review · source · engineering ================= */
function registerControlPlane({ api, router, isAdvanced }, { frame, gate, searchFirst }) {
  /* ---------------------------------------------------------------- P22 Changes */
  async function changesPage(query) {
    const box = frame("changes", "Changes", { subtitle: "draft → validate → preview → publish · rollback. Forms come from the server's action metadata." });
    const [list, meta] = await Promise.all([api.admin.changes(), api.admin.capabilityActions()]);
    clear(box);
    if (!gate(box, list, () => changesPage(query))) return;
    const rows = (list.body && list.body.changes) || [];
    const actions = (meta.ok && meta.body && meta.body.actions) || [];

    const actionSel = select([{ value: "", label: "action…" }, ...actions.map((a) => ({ value: a.action, label: `${a.action} (${a.area})`, selected: a.action === query.action }))], { "aria-label": "action" });
    const fieldsBox = h("div", { class: "stack" });
    const err = h("div");
    const renderFields = () => {
      clear(fieldsBox);
      const spec = actions.find((a) => a.action === actionSel.value);
      if (!spec) return;
      (spec.fields || []).forEach((fd) => {
        let el;
        if (fd.kind === "bool") el = select([{ value: "", label: "—" }, { value: "true", label: "true" }, { value: "false", label: "false" }], { "data-kind": fd.kind, "data-name": fd.name });
        else if (["object", "dict", "list", "json"].includes(fd.kind)) el = h("textarea", { class: "input mono", rows: "3", "data-kind": fd.kind, "data-name": fd.name, placeholder: "JSON" });
        else el = input({ type: ["int", "float", "number"].includes(fd.kind) ? "number" : "text", step: fd.kind === "float" ? "any" : null, "data-kind": fd.kind, "data-name": fd.name, value: query[fd.name] || "" });
        fieldsBox.append(field(`${fd.name}${fd.required ? " *" : ""}`, el, `${fd.kind}${fd.contract ? ` · ${fd.contract}` : ""}`));
      });
    };
    actionSel.addEventListener("change", renderFields);
    renderFields();
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: "New change" }), field("Action", actionSel), fieldsBox, err, h("div", { class: "actions" }, button("Create draft", null, { primary: true, type: "submit" })));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      if (!actionSel.value) {
        err.append(errorPanel({ error: { code: "validation_error", message: "Choose an action.", details: { field: "action" } } }));
        return;
      }
      const payload = {};
      let bad = null;
      fieldsBox.querySelectorAll("[data-name]").forEach((el) => {
        const v = el.value;
        const kind = el.dataset.kind;
        if (v === "" || v === undefined) return;
        if (kind === "bool") payload[el.dataset.name] = v === "true";
        else if (kind === "int") payload[el.dataset.name] = parseInt(v, 10);
        else if (kind === "float" || kind === "number") payload[el.dataset.name] = Number(v);
        else if (["object", "dict", "list", "json"].includes(kind)) {
          try {
            payload[el.dataset.name] = JSON.parse(v);
          } catch (ex) {
            bad = `${el.dataset.name}: ${ex.message}`;
          }
        } else payload[el.dataset.name] = v;
      });
      if (bad) {
        err.append(errorPanel({ error: { code: "validation_error", message: bad, details: {} } }));
        return;
      }
      const r = await api.admin.createChange({ action: actionSel.value, payload });
      if (!r.ok) {
        err.append(errorPanel(r.body, { status: r.status }));
        return;
      }
      announce("Draft created.");
      router.navigate(`/control/changes/${r.body.id}`);
    });

    const stateFilter = select([{ value: "", label: "state: all" }, ...Array.from(new Set(rows.map((r) => r.state))).map((s) => ({ value: s, label: `state: ${s}` }))], { "aria-label": "state filter" });
    const listBox = h("div");
    const render = () => {
      clear(listBox).append(
        dataList(
          [
            { label: "change", render: (r) => h("span", { class: "mono", text: shortId(r.id) }) },
            { label: "action", key: "action" },
            { label: "area", key: "area" },
            { label: "state", render: (r) => badge(r.state) },
            { label: "created", render: (r) => h("span", { text: fmtTime(r.created_at) }) },
          ],
          rows.filter((r) => !stateFilter.value || r.state === stateFilter.value).slice(0, SEARCH_THRESHOLD),
          { onRow: (r) => router.navigate(`/control/changes/${r.id}`), emptyText: "No changes.", limitNote: rows.length > SEARCH_THRESHOLD ? `showing ${SEARCH_THRESHOLD} of ${rows.length}` : null },
        ),
      );
    };
    stateFilter.addEventListener("change", render);
    render();
    box.append(h("div", { class: "filters" }, stateFilter), listBox, form);
    if (isAdvanced() && meta.ok) box.append(advancedPanel("Action metadata (served)", json(meta.body)));
  }
  router.route("/control/changes", ({ query }) => changesPage(query));

  router.route("/control/changes/:id", async ({ params }) => {
    const box = frame("changes", `Change ${shortId(params.id)}`, { crumb: "Control · Changes" });
    const load = async () => {
      const r = await api.admin.change(params.id);
      clear(box);
      if (!gate(box, r, load)) return;
      const rec = r.body;
      box.append(section("Lifecycle", lifecycleStrip(CHANGE_FLOW, rec.state, CHANGE_TERMINAL)), section("Record", kv([["id", rec.id], ["action", rec.action], ["area", rec.area], ["state", badge(rec.state)], ["actor", rec.actor_id], ["created", fmtTime(rec.created_at)], ["payload", json(rec.payload)]])));
      const preview = rec.impact_preview || rec.preview;
      if (rec.validation || rec.validation_result) box.append(section("Validation", json(rec.validation || rec.validation_result)));
      if (preview) box.append(section("Preview", json(preview)));
      const out = h("div");
      const actions = h("div", { class: "actions" });
      const step = (name, opts = {}) =>
        button(
          name,
          async () => {
            if (opts.confirm) {
              const ok = await confirmDialog({ title: `${opts.confirm} this change?`, verb: opts.confirm, body: json(preview || rec.payload), destructive: opts.destructive });
              if (!ok) return;
            }
            clear(out).append(loading(name));
            const res = await api.admin.changeStep(params.id, name);
            clear(out);
            if (!res.ok) out.append(errorPanel(res.body, { status: res.status }));
            else {
              announce(`${name} done`);
              load();
            }
          },
          { primary: opts.primary, danger: opts.destructive },
        );
      if (rec.state === "draft") actions.append(step("validate", { primary: true }));
      if (rec.state === "validated") actions.append(step("preview"), step("publish", { primary: true, confirm: "Publish" }));
      if (rec.state === "published") actions.append(step("rollback", { confirm: "Rollback", destructive: true }));
      if (!actions.children.length) actions.append(h("p", { class: "muted small", text: `No transition from state "${rec.state}".` }));
      box.append(section("Actions", actions, out), advancedPanel("Raw record", json(rec)), h("a", { href: "#/control/changes", text: "Back to changes" }));
    };
    await load();
  });

  /* ------------------------------------------------------------------ P23 Plans */
  router.route("/control/plans", async ({ query }) => {
    const box = frame("plans", "Plans", { subtitle: "Plan lookup is per explicit tenant id — no tenant directory is served." });
    clear(box);
    const tenant = input({ type: "text", value: query.tenant || (ctx().session && ctx().session.tenant_id) || "", "aria-label": "tenant id" });
    const out = h("div");
    const form = h("form", { class: "row", novalidate: true }, tenant, button("Look up", null, { primary: true, type: "submit" }));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out).append(loading("plan"));
      const r = await api.admin.plan(tenant.value.trim());
      clear(out);
      const draft = h("a", { class: "btn", href: router.buildHash("/control/changes", { action: "set_plan", tenant_id: tenant.value.trim() }), text: "Draft set_plan" });
      if (r.status === 404) out.append(errorPanel(r.body, { status: 404 }), draft);
      else if (gate(out, r, () => form.requestSubmit())) out.append(section("Plan summary", json(r.body)), draft);
    });
    box.append(form, out);
    if (tenant.value) form.requestSubmit();
  });

  /* ---------------------------------------------------------------- P24 Routing */
  router.route("/control/routing", async () => {
    const box = frame("routing", "Routing");
    const r = await api.admin.routingWeights();
    clear(box);
    if (!gate(box, r, () => router.resolve())) return;
    const w = r.body || {};
    const entries = Object.entries(w).filter(([k]) => k !== "version");
    box.append(section(`Default weights · version ${w.version || "—"}`, dataList([{ label: "dimension", render: ([k]) => h("span", { text: k }) }, { label: "weight", render: ([, v]) => h("span", { class: "mono", text: String(v) }) }, { label: "", render: ([, v]) => h("div", { class: "meter small", "aria-hidden": "true" }, h("span", { style: `width:${Math.round(Number(v) * 100)}%` })) }], entries)), h("div", { class: "actions" }, h("a", { class: "btn btn-primary", href: router.buildHash("/control/changes", { action: "set_routing_weights" }), text: "Draft set_routing_weights" })));
  });

  /* ------------------------------------------------------------------ P25 Usage */
  router.route("/control/usage", async () => {
    const box = frame("usage", "Usage (admin)", { subtitle: "Own tenant only — the admin usage read is tenant-scoped." });
    const r = await api.admin.usage();
    clear(box);
    if (!gate(box, r, () => router.resolve())) return;
    const rows = (r.body && r.body.usage) || [];
    box.append(
      searchFirst(
        rows,
        (visible, total) =>
          dataList(
            [
              { label: "run", render: (x) => h("a", { href: `#/runs/${x.execution_id}`, class: "mono", text: shortId(x.execution_id) }) },
              { label: "status", render: (x) => badge(x.status) },
              { label: "created", render: (x) => h("span", { text: fmtTime(x.created_at) }) },
              { label: "evaluation", render: (x) => badge(x.evaluation_status, "eval") },
              { label: "ledger", render: (x) => renderValue(x.ledger) },
            ],
            visible,
            { emptyText: "No usage rows.", limitNote: total > visible.length ? `showing ${visible.length} of ${total} — search to narrow` : null },
          ),
        "search status / run id",
      ),
    );
  });

  /* ------------------------------------------------------------------ P26 Audit */
  router.route("/control/audit", async ({ query }) => {
    const box = frame("audit", "Audit");
    const r = await api.admin.audit();
    clear(box);
    if (!gate(box, r, () => router.resolve())) return;
    const rows = (r.body && r.body.events) || [];
    box.append(h("p", { class: "muted small", text: `total_recorded ${r.body.total_recorded ?? rows.length}` }));
    const types = Array.from(new Set(rows.map((x) => x.event_type))).sort();
    const typeSel = select([{ value: "", label: "event type: all" }, ...types.map((t) => ({ value: t, label: t }))], { "aria-label": "event type" });
    const out = h("div");
    const render = () => {
      clear(out).append(
        dataList(
          [
            { label: "when", render: (x) => h("span", { text: fmtTime(x.occurred_at) }) },
            { label: "event", render: (x) => badge(x.event_type, "audit") },
            { label: "actor", render: (x) => h("span", { class: "mono", text: x.actor_id ? shortId(x.actor_id) : "system" }) },
            { label: "details", render: (x) => (Object.keys(x.details || {}).length ? advancedPanel("details", json(x.details)) : h("span", { class: "muted", text: "—" })) },
          ],
          rows.filter((x) => (!typeSel.value || x.event_type === typeSel.value) && (!query.id || x.id === query.id)).slice(0, SEARCH_THRESHOLD),
          { emptyText: "No audit events.", limitNote: rows.length > SEARCH_THRESHOLD ? `showing ${SEARCH_THRESHOLD} of ${rows.length} — filter by event type` : null },
        ),
      );
    };
    typeSel.addEventListener("change", render);
    render();
    box.append(h("div", { class: "filters" }, typeSel), out);
  });

  /* ---------------------------------------------------------- P3 Notifications */
  async function notificationsPage(query) {
    const box = frame("notifications", "Notifications", { subtitle: "A read-model over existing records (poll-based; acks are process-local)." });
    const r = await api.admin.notifications();
    clear(box);
    if (!gate(box, r, () => notificationsPage(query))) return;
    const rows = (r.body && r.body.notifications) || [];
    const polled = new Date().toLocaleTimeString();
    const cats = Array.from(new Set(rows.map((n) => n.category))).sort();
    const cat = select([{ value: "", label: "category: all" }, ...cats.map((c) => ({ value: c, label: c }))], { "aria-label": "category" });
    const out = h("div");
    const render = () => {
      clear(out);
      const visible = rows.filter((n) => !cat.value || n.category === cat.value);
      if (!visible.length) {
        out.append(empty(rows.length ? "No notifications in this category." : "No notifications derived from current records."));
        return;
      }
      const ul = h("ul", { class: "notif-list" });
      visible.forEach((n) => {
        const ev = n.evidence || {};
        let href = null;
        if (ev.kind && /execution/i.test(ev.kind)) href = `#/runs/${ev.ref}`;
        else if (ev.kind && /change/i.test(ev.kind)) href = `#/control/changes/${String(ev.ref).split(":")[0]}`;
        else if (ev.kind && /audit/i.test(ev.kind)) href = router.buildHash("/control/audit", { id: ev.ref });
        ul.append(
          h(
            "li",
            { class: `notif${n.read ? " read" : ""}` },
            badge(n.category, "notif"),
            h("span", { class: "notif-title", text: n.title }),
            h("span", { class: "muted small", text: fmtTime(n.occurred_at) }),
            href ? h("a", { href, class: "small", text: `${ev.kind} →` }) : h("span", { class: "muted small", text: ev.kind ? `${ev.kind} ${ev.ref}` : "" }),
            n.read
              ? badge("read", "flag")
              : button("Ack", async () => {
                  const a = await api.admin.ackNotification(n.id);
                  if (!a.ok) out.prepend(errorPanel(a.body, { status: a.status }));
                  else notificationsPage(query);
                }),
          ),
        );
      });
      out.append(ul);
    };
    cat.addEventListener("change", render);
    render();
    box.append(h("div", { class: "filters" }, cat, h("span", { class: "muted small", text: `unread ${r.body.unread ?? 0} · polled ${polled}` }), button("Refresh", () => notificationsPage(query))), out);
  }
  router.route("/control/notifications", ({ query }) => notificationsPage(query));

  /* ----------------------------------------------------------------- P27 System */
  router.route("/control/system", async () => {
    const box = frame("system", "System");
    const [s, hz] = await Promise.all([api.admin.system(), api.health()]);
    clear(box);
    if (!gate(box, s, () => router.resolve())) return;
    box.append(section("This process", kv(Object.entries(s.body || {}))), section("Health", hz.ok ? kv(Object.entries(hz.body || {})) : errorPanel(hz.body, { status: hz.status })));
  });

  /* ------------------------------------------------------------ P28 Self-review */
  router.route("/control/self-review", async () => {
    const box = frame("self-review", "Self-review");
    const r = await api.admin.selfReview();
    clear(box);
    if (!gate(box, r, () => router.resolve())) return;
    const caps = (r.body && r.body.capabilities) || {};
    box.append(section("Capabilities by state", kv(Object.entries(caps.by_state || {}))), section("Rows", h("div", { class: "cap-ring", role: "list" }, ...(caps.rows || []).map((rec) => h("div", { role: "listitem" }, capabilityNode(rec))))), advancedPanel("Raw self-review", json(r.body)));
  });

  /* --------------------------------------------------------- P29 Source changes */
  async function sourcePage() {
    const box = frame("source", "Source changes", { subtitle: "Governed source proposals: propose → verify → approve → apply · reject · rollback." });
    const r = await api.admin.sourceChanges();
    clear(box);
    if (!gate(box, r, sourcePage)) return;
    const rows = (r.body && r.body.proposals) || [];
    box.append(
      dataList(
        [
          { label: "proposal", render: (p) => h("span", { class: "mono", text: shortId(p.id || p.proposal_id) }) },
          { label: "state", render: (p) => badge(p.state || p.status) },
          { label: "operations", render: (p) => renderValue(Array.isArray(p.operations) ? p.operations.length : p.operations) },
          { label: "created", render: (p) => renderValue(p.created_at) },
        ],
        rows.slice(0, SEARCH_THRESHOLD),
        { onRow: (p) => router.navigate(`/control/source/${p.id || p.proposal_id}`), emptyText: "No source-change proposals." },
      ),
    );
    const snap = h("div");
    const proposal = h("textarea", { class: "input mono", rows: "8", placeholder: "proposal JSON — the server validates the shape" });
    const err = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: "Propose" }), field("Proposal (JSON)", proposal), err, h("div", { class: "actions" }, button("Snapshot", async () => {
      clear(snap).append(loading("snapshot"));
      const s = await api.admin.sourceSnapshot({});
      clear(snap);
      snap.append(s.ok ? json(s.body) : errorPanel(s.body, { status: s.status }));
    }), button("Propose", null, { primary: true, type: "submit" })), snap);
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      let body;
      try {
        body = JSON.parse(proposal.value);
      } catch (ex) {
        err.append(errorPanel({ error: { code: "validation_error", message: `not valid JSON: ${ex.message}`, details: {} } }));
        return;
      }
      const res = await api.admin.createSourceChange(body);
      if (!res.ok) {
        err.append(errorPanel(res.body, { status: res.status }));
        return;
      }
      router.navigate(`/control/source/${res.body.id || res.body.proposal_id}`);
    });
    box.append(form);
  }
  router.route("/control/source", sourcePage);

  router.route("/control/source/:id", async ({ params }) => {
    const box = frame("source", `Proposal ${shortId(params.id)}`, { crumb: "Control · Source changes" });
    const load = async () => {
      const r = await api.admin.sourceChange(params.id);
      clear(box);
      if (!gate(box, r, load)) return;
      const rec = r.body;
      const state = rec.state || rec.status;
      box.append(section("Record", kv([["id", rec.id || rec.proposal_id], ["state", badge(state)], ["operations", json(rec.operations || [])]])), advancedPanel("Raw record", json(rec)));
      const out = h("div");
      const cited = input({ type: "text", placeholder: "cited content hash (approve)" });
      const reason = input({ type: "text", placeholder: "reason (reject)" });
      const run = async (name, body, opts = {}) => {
        if (opts.confirm) {
          const ok = await confirmDialog({ title: `${opts.confirm} this proposal?`, verb: opts.confirm, body: json(rec.verification || rec.verify_result || rec.operations || rec), destructive: opts.destructive });
          if (!ok) return;
        }
        clear(out).append(loading(name));
        const res = await api.admin.sourceChangeStep(params.id, name, body);
        clear(out);
        if (!res.ok) out.append(errorPanel(res.body, { status: res.status }));
        else {
          announce(`${name} done`);
          load();
        }
      };
      const actions = h(
        "div",
        { class: "actions" },
        button("verify", () => run("verify", {}), { primary: true }),
        button("approve", () => run("approve", { cited_hash: cited.value.trim() })),
        button("reject", () => run("reject", { reason: reason.value.trim() }), { danger: true }),
        button("apply", () => run("apply", {}, { confirm: "Apply", destructive: true }), { danger: true }),
        button("rollback", () => run("rollback", {}, { confirm: "Rollback", destructive: true }), { danger: true }),
      );
      box.append(section("Actions (the server refuses invalid transitions)", h("div", { class: "row" }, field("cited_hash", cited), field("reason", reason)), actions, out), h("a", { href: "#/control/source", text: "Back" }));
    };
    await load();
  });

  /* ------------------------------------------------------------ P30 Engineering */
  router.route("/control/engineering", async () => {
    const box = frame("engineering", "Engineering");
    const r = await api.admin.engineeringStatus();
    clear(box);
    if (r.status === 404) {
      box.append(unavailable("NOT AVAILABLE IN THIS PROCESS", "The engineering seam is opt-in by environment (ADR-0012) and is not composed here; the route answers 404."));
      return;
    }
    if (!gate(box, r, () => router.resolve())) return;
    const auth = await api.admin.engineeringAuthorizations();
    box.append(section("Status", json(r.body)), section("Authorizations", auth.ok ? json(auth.body) : errorPanel(auth.body, { status: auth.status })));
  });
}
