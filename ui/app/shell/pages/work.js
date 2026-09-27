/* WORK — P5 New Work · P12 Models · P8 Workspaces/Projects · P9 Memory ·
   P10 Webhooks · P11 Usage. Model-first: one row per served logical model
   (`id`); providers/runtime live in Advanced only. */

import { h, clear, section, pageHeader, badge, loading, empty, errorPanel, kv, button, field, input, select, confirmDialog, dataList, advancedPanel, json, renderValue, announce, unavailable } from "../components.js";
import { remember, set } from "../context.js";

export function registerWork({ api, router, main, ctx, isAdvanced }) {
  function runtimeTable(runtime) {
    const rows = Array.isArray(runtime) ? runtime : [];
    if (!rows.length) return h("p", { class: "muted", text: "No runtime rows served (no resource signals composed)." });
    return dataList(
      [
        { label: "provider", key: "provider" },
        { label: "binding availability", render: (r) => badge(r.binding_availability) },
        { label: "eligible", render: (r) => badge(r.eligible ? "eligible" : "not eligible", "elig") },
        { label: "reason", render: (r) => (r.reason ? h("span", { text: r.reason }) : h("span", { class: "muted", text: "—" })) },
        { label: "retry after", render: (r) => (typeof r.retry_after_ms === "number" ? h("span", { text: `~${Math.ceil(r.retry_after_ms / 1000)} s (${r.retry_after_ms} ms)` }) : h("span", { class: "muted", text: "—" })) },
      ],
      rows,
    );
  }

  function firstReason(m) {
    return ((m.runtime || []).map((r) => r.reason).filter(Boolean)[0]) || "no eligible runtime";
  }

  /** ModelPicker (radiogroup). Auto first; one row per served model id. */
  function modelPicker(models, selectedId) {
    const group = h("div", { class: "model-picker", role: "radiogroup", "aria-label": "model" });
    const mk = (value, label, meta, disabled, reason) => {
      const id = `mp-${value || "auto"}`;
      const radio = h("input", { type: "radio", name: "model", id, value, checked: (selectedId || "") === value ? true : null, disabled: disabled || null });
      const row = h("label", { class: `model-row${disabled ? " disabled" : ""}`, for: id }, radio, h("span", { class: "model-main", text: label }), meta || null);
      if (reason) {
        const rid = `${id}-why`;
        row.append(h("span", { class: "muted small", id: rid, text: reason }));
        radio.setAttribute("aria-describedby", rid);
      }
      group.append(row);
    };
    mk("", "Auto — the Router decides", h("span", { class: "muted small", text: "recommended" }));
    models.forEach((m) => {
      const blocked = (m.runtime || []).filter((r) => r.eligible === false);
      const isUnavailable = m.availability === "unavailable";
      const n = (m.providers || []).length;
      const meta = h("span", { class: "model-meta" }, badge(m.availability), h("span", { class: "muted small", text: `${n} provider${n === 1 ? "" : "s"}${blocked.length ? ` · ${blocked.length} not eligible` : ""}` }));
      mk(m.id, `${m.name}  ·  ${(m.capabilities || []).join(", ") || "—"}`, meta, isUnavailable, isUnavailable ? firstReason(m) : null);
    });
    return group;
  }

  /* --------------------------------------------------------------- P5 New Work */
  router.route("/work/new", async ({ query }) => {
    const m = clear(main());
    m.append(pageHeader("New Work", { crumb: "Work" }));
    const form = h("form", { class: "stack", novalidate: true });
    m.append(form);

    const ask = h("textarea", { class: "input", rows: "6", maxlength: "100000", required: true, placeholder: "What should QEVION do?" });
    ask.value = query.ask || "";
    const counter = h("p", { class: "muted small", "aria-live": "polite", text: `${ask.value.length} / 100000` });
    ask.addEventListener("input", () => {
      counter.textContent = `${ask.value.length} / 100000`;
    });

    const conv = input({ type: "text", placeholder: "continue a conversation id (optional)", value: query.conversation_id || "" });
    const contextBlock = section("Context", h("p", { class: "muted small", text: `workspace ${ctx().workspace_id || "none"} · project ${ctx().project_id || "none"} (change in the header)` }), field("Conversation", conv));

    const modelsBox = section("Model", loading("models"));
    const templateBox = section("Template (optional)", loading("templates"));
    const modeBox = section("Mode", loading("agent runtime"));

    const adv = advancedPanel("Advanced");
    const providerSel = select([{ value: "", label: "provider: router decides" }], { "aria-label": "provider pin" });
    const allowFallback = select([{ value: "", label: "allow_fallback: default" }, { value: "true", label: "allow_fallback: true" }, { value: "false", label: "allow_fallback: false" }], { "aria-label": "allow fallback" });
    const skillsBox = h("div", { class: "chips" }, h("span", { class: "muted", text: "loading skills…" }));
    const toolsBox = h("div", { class: "chips" });
    const webhook = input({ type: "url", placeholder: "https://… (optional webhook_url)" });
    adv.append(field("Provider pin (explicit model only)", providerSel), field("Fallback", allowFallback), h("div", { class: "field" }, h("span", { class: "label", text: "Skills" }), skillsBox), h("div", { class: "field" }, h("span", { class: "label", text: "Tools offered by the runtime" }), toolsBox), field("Webhook URL", webhook));

    const errBox = h("div");
    const submit = button("Execute", null, { primary: true, type: "submit" });
    form.append(section("Ask", field("Ask", ask), counter), contextBlock, modelsBox, templateBox, modeBox, adv, errBox, h("div", { class: "actions sticky" }, h("a", { class: "btn", href: "#/", text: "Cancel" }), submit));

    const [models, templates, agent, skills] = await Promise.all([api.work.models(), api.work.templates(), api.work.agentTools(), api.work.skills()]);

    let modelList = [];
    clear(modelsBox).append(h("h2", { text: "Model" }));
    if (models.ok) {
      modelList = (models.body && models.body.models) || [];
      remember("models", modelList);
      if (!modelList.length) modelsBox.append(empty("No active models are served."));
      const picker = modelPicker(modelList, query.model_id || ctx().model_id || "");
      modelsBox.append(picker);
      picker.addEventListener("change", () => {
        const chosen = picker.querySelector("input:checked");
        const mid = chosen ? chosen.value : "";
        set({ model_id: mid || null });
        clear(providerSel);
        providerSel.append(h("option", { value: "", text: "provider: router decides" }));
        const mm = modelList.find((x) => x.id === mid);
        (mm && mm.providers ? mm.providers : []).forEach((p) => providerSel.append(h("option", { value: p, text: p })));
      });
      picker.dispatchEvent(new Event("change"));
      modelsBox.append(h("a", { class: "small", href: "#/work/models", text: "Browse models" }));
    } else {
      modelsBox.append(errorPanel(models.body, { status: models.status }));
    }

    clear(templateBox).append(h("h2", { text: "Template (optional)" }));
    const tplSel = select([{ value: "", label: "none" }], { "aria-label": "template" });
    if (templates.ok) {
      ((templates.body && templates.body.templates) || []).forEach((t) => {
        const ref = t.ref || (t.version ? `${t.id}@${t.version}` : t.id);
        tplSel.append(h("option", { value: ref, text: ref, selected: query.template && (ref === query.template || t.id === query.template) ? true : null }));
      });
      templateBox.append(tplSel, h("p", { class: "muted small", text: "Template runs execute synchronously in this slice." }));
    } else if (templates.status === 404) templateBox.append(unavailable("Templates are not served by this process."));
    else templateBox.append(errorPanel(templates.body, { status: templates.status }));

    clear(modeBox).append(h("h2", { text: "Mode" }));
    const modeStd = h("input", { type: "radio", name: "mode", id: "mode-std", value: "", checked: true });
    const modeAgent = h("input", { type: "radio", name: "mode", id: "mode-agent", value: "agent" });
    const agentTools = agent.ok && agent.body && Array.isArray(agent.body.tools) ? agent.body.tools : [];
    const agentLabel = agent.ok ? `Agent — multi-step (${agent.body.strategy || "agent"}, max_steps ${agent.body.max_steps ?? "—"}, ${agentTools.length} tool${agentTools.length === 1 ? "" : "s"} offered)` : "Agent — runtime not served";
    if (!agent.ok || !agentTools.length) {
      modeAgent.disabled = true;
      modeAgent.setAttribute("aria-describedby", "agent-why");
    }
    modeBox.append(
      h("div", { role: "radiogroup", "aria-label": "execution mode" }, h("label", { class: "model-row", for: "mode-std" }, modeStd, h("span", { class: "model-main", text: "Standard — one answer" })), h("label", { class: `model-row${modeAgent.disabled ? " disabled" : ""}`, for: "mode-agent" }, modeAgent, h("span", { class: "model-main", text: agentLabel }))),
      modeAgent.disabled ? h("p", { class: "muted small", id: "agent-why", text: agent.ok ? "Disabled: this runtime offers no tools, so an agent run would have nothing to act with." : `Disabled: the agent runtime read failed (${agent.status}).` }) : null,
    );
    clear(toolsBox);
    if (agentTools.length) agentTools.forEach((t) => toolsBox.append(badge(typeof t === "string" ? t : t.name || JSON.stringify(t), "chip")));
    else toolsBox.append(h("span", { class: "muted", text: "No tools exposed by this runtime." }));

    clear(skillsBox);
    const skillChecks = [];
    if (skills.ok) {
      const list = (skills.body && skills.body.skills) || [];
      if (!list.length) skillsBox.append(h("span", { class: "muted", text: "No skills served." }));
      list.forEach((s) => {
        const key = s.key || s.id || s.name;
        const id = `sk-${key}`;
        const cb = h("input", { type: "checkbox", id, value: key });
        skillChecks.push(cb);
        skillsBox.append(h("label", { class: "chip-check", for: id }, cb, s.name || key));
      });
    } else skillsBox.append(h("span", { class: "muted", text: `Skills read failed (${skills.status}).` }));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errBox);
      if (!ask.value.trim()) {
        errBox.append(errorPanel({ error: { code: "validation_error", message: "Ask is required.", details: { field: "ask" } } }));
        ask.focus();
        return;
      }
      const body = { ask: ask.value };
      if (conv.value.trim()) body.conversation_id = conv.value.trim();
      if (ctx().project_id) body.project_id = ctx().project_id;
      const chosen = modelsBox.querySelector("input[name=model]:checked");
      if (chosen && chosen.value) {
        body.model_policy = { type: "explicit_model", model_id: chosen.value };
        if (providerSel.value) body.model_policy.provider_id = providerSel.value;
        if (allowFallback.value) body.model_policy.allow_fallback = allowFallback.value === "true";
      }
      if (tplSel.value) body.execution_strategy = { template_ref: tplSel.value };
      if (modeAgent.checked) body.execution_policy = { strategy: "agent" };
      const picked = skillChecks.filter((c) => c.checked).map((c) => c.value);
      if (picked.length) body.skills = picked;
      if (webhook.value.trim()) body.webhook_url = webhook.value.trim();
      submit.disabled = true;
      announce("Executing…");
      const r = await api.work.execute(body);
      submit.disabled = false;
      if (!r.ok) {
        errBox.append(errorPanel(r.body, { status: r.status, onRetry: () => form.requestSubmit() }));
        if (r.body && r.body.error && r.body.error.code === "entitlement_exceeded") errBox.append(h("a", { href: "#/work/usage", text: "See usage" }));
        announce("Execution refused.");
        return;
      }
      const id = r.body && r.body.execution_id;
      announce(r.status === 202 ? "Queued." : "Completed.");
      router.navigate(`/runs/${id}`);
    });
  });

  /* ----------------------------------------------------------------- P12 Models */
  async function modelsPage(expandId) {
    const m = clear(main());
    m.append(pageHeader("Models", { crumb: "Work", subtitle: "One row per logical model. Providers are detail, not the directory." }));
    const search = input({ type: "search", placeholder: "search name or capability", "aria-label": "search models" });
    const avail = select([{ value: "", label: "availability: all" }], { "aria-label": "availability filter" });
    const refresh = button("Refresh", () => modelsPage(expandId));
    m.append(h("div", { class: "filters" }, search, avail, refresh));
    const listBox = h("div", {}, loading("models"));
    m.append(listBox);
    const r = await api.work.models();
    if (!r.ok) {
      clear(listBox).append(errorPanel(r.body, { status: r.status, onRetry: () => modelsPage(expandId) }));
      return;
    }
    const models = (r.body && r.body.models) || [];
    remember("models", models);
    Array.from(new Set(models.map((x) => x.availability))).sort().forEach((v) => avail.append(h("option", { value: v, text: `availability: ${v}` })));
    const render = () => {
      clear(listBox);
      const q = search.value.trim().toLowerCase();
      const rows = models.filter((x) => (!q || x.name.toLowerCase().includes(q) || (x.capabilities || []).some((c) => c.toLowerCase().includes(q))) && (!avail.value || x.availability === avail.value));
      if (!rows.length) {
        listBox.append(empty(models.length ? "No models match the filter." : "No active models are served."));
        return;
      }
      rows.forEach((x) => {
        const blocked = (x.runtime || []).filter((rt) => rt.eligible === false).length;
        const isUnavailable = x.availability === "unavailable";
        const card = h("article", { class: `model-card is-${x.availability}`, id: `model-${x.id}` });
        card.append(
          h("div", { class: "model-head" }, h("h2", { text: x.name }), badge(x.availability)),
          kv([
            ["tier", x.tier],
            ["modalities", (x.modalities || []).join(", ")],
            ["capabilities", (x.capabilities || []).length ? (x.capabilities || []).join(", ") : "none declared"],
            ["providers", `${(x.providers || []).length}${blocked ? ` · ${blocked} not eligible` : ""}`],
          ]),
        );
        const use = isUnavailable ? h("span", { class: "btn btn-primary disabled", "aria-disabled": "true", text: "Use" }) : h("a", { class: "btn btn-primary", href: router.buildHash("/work/new", { model_id: x.id }), text: "Use" });
        if (isUnavailable) card.append(h("p", { class: "muted small", text: `Cannot use: ${firstReason(x)}` }));
        const advanced = advancedPanel("Advanced — providers & runtime", runtimeTable(x.runtime), h("p", { class: "muted small", text: `bound providers: ${(x.providers || []).join(", ") || "—"} · model id ${x.id}` }));
        if (expandId && expandId === x.id) advanced.open = true;
        card.append(h("div", { class: "actions" }, use), advanced);
        listBox.append(card);
      });
    };
    search.addEventListener("input", render);
    avail.addEventListener("change", render);
    render();
    if (expandId) {
      const el = document.getElementById(`model-${expandId}`);
      if (el) el.scrollIntoView({ block: "start" });
    }
  }
  router.route("/work/models", () => modelsPage(null));
  router.route("/work/models/:id", ({ params }) => modelsPage(params.id));

  registerWorkContext({ api, router, main, ctx, isAdvanced });
}

/* --------------------------------------------------- P8 · P9 · P10 · P11 */
function registerWorkContext({ api, router, main, ctx, isAdvanced }) {
  async function contextPage(tab) {
    const m = clear(main());
    m.append(pageHeader("Workspaces & Projects", { crumb: "Work" }));
    const isProjects = tab === "projects";
    m.append(h("div", { class: "tabs-inline", role: "tablist" }, h("a", { role: "tab", href: "#/work/context", "aria-selected": !isProjects ? "true" : "false", text: "Workspaces" }), h("a", { role: "tab", href: "#/work/context?tab=projects", "aria-selected": isProjects ? "true" : "false", text: "Projects" })));
    const box = h("div", {}, loading());
    m.append(box);
    const r = isProjects ? await api.work.projects() : await api.work.workspaces();
    clear(box);
    if (!r.ok) {
      box.append(errorPanel(r.body, { status: r.status, onRetry: () => contextPage(tab) }));
      return;
    }
    const rows = (r.body && (isProjects ? r.body.projects : r.body.workspaces)) || [];
    const current = isProjects ? ctx().project_id : ctx().workspace_id;
    box.append(
      dataList(
        [
          { label: "name", render: (row) => h("span", {}, row.name || "—", " ", row.id === current ? badge("current", "chip") : null) },
          { label: "id", render: (row) => h("span", { class: "mono", text: row.id }) },
          { label: "created", render: (row) => renderValue(row.created_at) },
          {
            label: "actions",
            render: (row) =>
              h(
                "div",
                { class: "row" },
                button("Set current", () => {
                  set(isProjects ? { project_id: row.id } : { workspace_id: row.id });
                  contextPage(tab);
                }),
                isProjects ? h("a", { class: "btn", href: `#/work/context/projects/${row.id}`, text: "Open" }) : null,
                button(
                  "Delete",
                  async () => {
                    const ok = await confirmDialog({ title: `Delete ${isProjects ? "project" : "workspace"}?`, verb: "Delete", body: kv([["name", row.name], ["id", row.id]]), destructive: true });
                    if (!ok) return;
                    const d = isProjects ? await api.work.deleteProject(row.id) : await api.work.deleteWorkspace(row.id);
                    if (!d.ok) box.prepend(errorPanel(d.body, { status: d.status }));
                    else {
                      if (row.id === current) set(isProjects ? { project_id: null } : { workspace_id: null });
                      contextPage(tab);
                    }
                  },
                  { danger: true },
                ),
              ),
          },
        ],
        rows,
        { emptyText: isProjects ? "No projects yet." : "No workspaces yet." },
      ),
    );
    const name = input({ type: "text", required: true, placeholder: "name" });
    const wsForProject = isProjects ? select([{ value: "", label: "workspace: none" }], { "aria-label": "workspace for project" }) : null;
    if (wsForProject) {
      const ws = await api.work.workspaces();
      (ws.ok && ws.body && ws.body.workspaces ? ws.body.workspaces : []).forEach((w) => wsForProject.append(h("option", { value: w.id, text: w.name || w.id, selected: w.id === ctx().workspace_id ? true : null })));
    }
    const err = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: isProjects ? "Create project" : "Create workspace" }), field("Name", name), wsForProject ? field("Workspace", wsForProject) : null, err, h("div", { class: "actions" }, button("Create", null, { primary: true, type: "submit" })));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      const body = { name: name.value.trim() };
      if (isProjects && wsForProject && wsForProject.value) body.workspace_id = wsForProject.value;
      const c = isProjects ? await api.work.createProject(body) : await api.work.createWorkspace(body);
      if (!c.ok) err.append(errorPanel(c.body, { status: c.status }));
      else contextPage(tab);
    });
    box.append(form);
  }
  router.route("/work/context", ({ query }) => contextPage(query.tab));
  router.route("/work/context/projects/:id", async ({ params }) => {
    const m = clear(main());
    m.append(pageHeader("Project", { crumb: "Work · Workspaces & Projects" }));
    const box = h("div", {}, loading());
    m.append(box);
    const r = await api.work.project(params.id);
    clear(box);
    if (!r.ok) box.append(errorPanel(r.body, { status: r.status }));
    else box.append(section("Record", json(r.body)), h("div", { class: "actions" }, button("Set as current project", () => set({ project_id: params.id }), { primary: true }), h("a", { class: "btn", href: "#/work/context?tab=projects", text: "Back" })));
  });

  async function memoryPage() {
    const m = clear(main());
    m.append(pageHeader("Preferences (memory)", { crumb: "Work", subtitle: "Stored preference memories. Read and delete only — no create/edit route is served." }));
    const box = h("div", {}, loading());
    m.append(box);
    const r = await api.work.preferences();
    clear(box);
    if (r.status === 404) return box.append(unavailable("Preference memory is not composed in this process."));
    if (!r.ok) return box.append(errorPanel(r.body, { status: r.status, onRetry: memoryPage }));
    const rows = (r.body && (r.body.preferences || r.body.items || r.body.memories)) || (Array.isArray(r.body) ? r.body : []);
    return box.append(
      dataList(
        [
          { label: "id", render: (row) => h("span", { class: "mono", text: row.id || row.memory_id }) },
          { label: "content", render: (row) => renderValue(row.content || row.value || row.text) },
          { label: "source", render: (row) => renderValue(row.source) },
          {
            label: "actions",
            render: (row) =>
              button(
                "Delete",
                async () => {
                  const ok = await confirmDialog({ title: "Delete preference?", verb: "Delete", body: json(row), destructive: true });
                  if (!ok) return;
                  const d = await api.work.deletePreference(row.id || row.memory_id);
                  if (!d.ok) box.prepend(errorPanel(d.body, { status: d.status }));
                  else memoryPage();
                },
                { danger: true },
              ),
          },
        ],
        rows,
        { emptyText: "No stored preferences." },
      ),
    );
  }
  router.route("/work/memory", memoryPage);

  async function webhooksPage() {
    const m = clear(main());
    m.append(pageHeader("Webhooks", { crumb: "Work" }));
    const box = h("div", {}, loading());
    m.append(box);
    const r = await api.work.webhooks();
    clear(box);
    if (r.status === 404) return box.append(unavailable("Webhooks are not composed in this process."));
    if (!r.ok) return box.append(errorPanel(r.body, { status: r.status, onRetry: webhooksPage }));
    const rows = (r.body && (r.body.webhooks || r.body.subscriptions)) || [];
    box.append(
      dataList(
        [
          { label: "id", render: (row) => h("span", { class: "mono", text: row.id || row.subscription_id }) },
          { label: "url", key: "url" },
          { label: "events", render: (row) => renderValue(row.events || row.event_types) },
          {
            label: "actions",
            render: (row) =>
              button(
                "Delete",
                async () => {
                  const ok = await confirmDialog({ title: "Delete webhook subscription?", verb: "Delete", body: json(row), destructive: true });
                  if (!ok) return;
                  const d = await api.work.deleteWebhook(row.id || row.subscription_id);
                  if (!d.ok) box.prepend(errorPanel(d.body, { status: d.status }));
                  else webhooksPage();
                },
                { danger: true },
              ),
          },
        ],
        rows,
        { emptyText: "No webhook subscriptions." },
      ),
    );
    const url = input({ type: "url", required: true, placeholder: "https://…" });
    const events = input({ type: "text", placeholder: "event types, comma-separated (the server validates)" });
    const err = h("div");
    const form = h("form", { class: "stack card", novalidate: true }, h("h2", { text: "Create subscription" }), field("URL", url), field("Events", events), err, h("div", { class: "actions" }, button("Create", null, { primary: true, type: "submit" })));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      const body = { url: url.value.trim() };
      const ev = events.value.split(",").map((s) => s.trim()).filter(Boolean);
      if (ev.length) body.events = ev;
      const c = await api.work.createWebhook(body);
      if (!c.ok) err.append(errorPanel(c.body, { status: c.status }));
      else webhooksPage();
    });
    box.append(form);
    if (isAdvanced()) box.append(h("p", { class: "muted small", text: "Deliveries are staged on execution.queued; no delivery log is served." }));
    return undefined;
  }
  router.route("/work/webhooks", webhooksPage);

  router.route("/work/usage", async () => {
    const m = clear(main());
    m.append(pageHeader("Usage", { crumb: "Work" }));
    const box = h("div", {}, loading());
    m.append(box);
    const r = await api.work.usage();
    clear(box);
    if (!r.ok) return box.append(errorPanel(r.body, { status: r.status }));
    const u = r.body || {};
    const tu = u.task_units || {};
    const pct = tu.limit ? Math.min(100, Math.round(((tu.used || 0) / tu.limit) * 100)) : 0;
    return box.append(
      section("Plan", kv([["plan", u.plan]]), h("div", { class: "meter", role: "meter", "aria-valuemin": "0", "aria-valuemax": String(tu.limit ?? 0), "aria-valuenow": String(tu.used ?? 0), "aria-label": "task units used" }, h("span", { style: `width:${pct}%` })), kv([["task units used", tu.used], ["limit", tu.limit], ["remaining", tu.remaining]])),
      section("Modality limits", Object.keys(u.modality_limits || {}).length ? kv(Object.entries(u.modality_limits)) : h("p", { class: "muted", text: "No modality limits configured." })),
    );
  });
}
