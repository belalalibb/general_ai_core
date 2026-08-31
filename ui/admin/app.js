/* SUBSTRATE / CONTROL — admin console shell (UI/UX directive Chunk 2).
 * AA-2/AA-3 honesty rules carried as component contracts:
 *
 * - STATUS_CLASSES contains ONLY backend contract enum values; anything
 *   else renders the loud pink UNKNOWN badge (never gray-washed). States
 *   outside that vocabulary (e.g. capability "inert", proposal
 *   verification states) deliberately render UNKNOWN — loud beats fake.
 * - openExecution refuses to render a trace unless as_recorded === true.
 *   There is no progress-bar code path in this file by design (doc A §6):
 *   traces are post-hoc evidence, not liveness theater.
 * - Claims without evidence citations render as refusals, never as facts.
 * - Ledger null renders "no ledger (accounting unbound)" — never invented.
 * - The amnesia banner is set in the store layer (api()) on first success.
 * - Exactly 4 POSTs exist (login, converse, lifecycle act, notification
 *   ack); every NEW surface (overview, intelligence, source) is read-only.
 *   Scenario replays / capability probes run via the agent's sanctioned
 *   tools, never ad-hoc UI writes.
 * - Lifecycle denials render VERBATIM via renderError (doc C §5).
 * - Every read is an explicit Refresh — no setInterval, no push theater;
 *   toasts are feedback, never the record.
 */
"use strict";

const state = { token: null, surface: "overview" };

/* Status → badge class. KEYS MUST BE CONTRACT VALUES ONLY (tested). */
const STATUS_CLASSES = {
  /* ExecutionStatus */
  queued: "info",
  running: "info",
  waiting_approval: "warn",
  succeeded: "ok",
  failed: "err",
  cancelled: "neutral",
  /* UsageLedgerStatus */
  reserved: "info",
  settled: "ok",
  refunded: "warn",
  /* ModelStatus / ProviderStatus (active/disabled shared) */
  active: "ok",
  disabled: "neutral",
  deprecated: "warn",
  maintenance: "warn",
  /* BindingAvailability */
  available: "ok",
  unavailable: "err",
  degraded: "warn",
  /* ConfigLifecycleState */
  draft: "info",
  validated: "info",
  rejected: "err",
  published: "ok",
  rolled_back: "warn",
  /* SkillStatus (pipeline states beyond shared ones) */
  imported: "info",
  scanned: "info",
  reviewed: "info",
  approved: "ok",
  /* healthz literal */
  alive: "ok",
  /* agent ToolClass values */
  r0_read: "info",
  r1_execute_test: "warn",
  r2_config_change: "warn",
  /* NotificationCategory (NTF-1, doc A §12) */
  success: "ok",
  info: "info",
  warning: "warn",
  error: "err",
  security: "err",
  change: "info",
};

function statusBadge(value) {
  const cls = STATUS_CLASSES[value];
  const span = document.createElement("span");
  if (cls === undefined) {
    span.className = "badge unknown";
    span.textContent = `UNKNOWN: ${String(value)}`;
  } else {
    span.className = `badge ${cls}`;
    span.textContent = value;
  }
  return span;
}

/* --- store layer ----------------------------------------------------------- */

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const body = await response.json().catch(() => null);
  if (response.ok) {
    /* Amnesia banner: any successful read means the process is serving
       in-memory data — say so (doc D §4.3). */
    document.getElementById("amnesia-banner").hidden = false;
  }
  return { ok: response.ok, status: response.status, body };
}

function renderError(el, payload) {
  /* Denials are content — render the unified error verbatim. */
  el.hidden = false;
  const detail = payload && payload.error
    ? `${payload.error.code}: ${payload.error.message}`
    : "request failed";
  el.textContent = detail;
}

/* --- small render helpers ---------------------------------------------------- */

function card(title, contentNode) {
  const div = document.createElement("div");
  div.className = "card";
  const h = document.createElement("h3");
  h.textContent = title;
  const v = document.createElement("div");
  v.className = "figure";
  if (contentNode instanceof Node) v.appendChild(contentNode);
  else v.textContent = String(contentNode);
  div.append(h, v);
  return div;
}

function chip(label, value) {
  const span = document.createElement("span");
  span.className = "chip";
  const b = document.createElement("b");
  b.textContent = String(value);
  span.append(`${label} `, b);
  return span;
}

/* --- health dot (topbar) — a real /healthz read, on demand ------------------- */

async function refreshHealth() {
  const el = document.getElementById("health-dot");
  const health = await api("/healthz");
  if (!health.ok) {
    el.className = "badge err";
    el.textContent = "health: unreachable";
    return null;
  }
  const cls = STATUS_CLASSES[health.body.status];
  if (cls === undefined) {
    el.className = "badge unknown";
    el.textContent = `UNKNOWN: ${String(health.body.status)}`;
  } else {
    el.className = `badge ${cls}`;
    el.textContent = health.body.status;
  }
  return health.body;
}

/* --- login (POST 1 of 4) ------------------------------------------------------ */

document.getElementById("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = document.getElementById("login-error");
  errorBox.hidden = true;
  const result = await api("/v1/auth/login", {
    method: "POST",
    body: {
      email: document.getElementById("login-email").value,
      password: document.getElementById("login-password").value,
    },
  });
  if (!result.ok) { renderError(errorBox, result.body); return; }
  state.token = result.body.token;
  /* is_admin lives on the session read, not the login body — verify it. */
  const session = await api("/v1/auth/session");
  if (!session.ok || session.body.is_admin !== true) {
    renderError(errorBox, { error: { code: "unauthorized", message: "Admin access required." } });
    state.token = null;
    return;
  }
  document.getElementById("login-view").hidden = true;
  document.getElementById("console-view").hidden = false;
  refreshHealth();
  loadAgent();
  loadSurface("overview");
});

/* --- navigation --------------------------------------------------------------- */

document.querySelectorAll(".rail-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".rail-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadSurface(btn.dataset.surface);
  });
});

function loadSurface(name) {
  state.surface = name;
  document.getElementById("global-error").hidden = true;
  document.querySelectorAll(".surface").forEach((s) => (s.hidden = true));
  document.getElementById(`surface-${name}`).hidden = false;
  const loaders = {
    overview: loadOverview,
    notifications: loadNotifications,
    executions: loadExecutions,
    usage: loadUsage,
    catalog: loadCatalog,
    intelligence: loadIntelligence,
    changes: loadChanges,
    source: loadSource,
    system: loadSystem,
  };
  loaders[name]();
}

/* Explicit refresh wiring — reads happen when the operator asks. */
document.getElementById("overview-refresh").addEventListener("click", loadOverview);
document.getElementById("executions-refresh").addEventListener("click", loadExecutions);
document.getElementById("catalog-refresh").addEventListener("click", loadCatalog);
document.getElementById("intelligence-refresh").addEventListener("click", loadIntelligence);
document.getElementById("changes-refresh").addEventListener("click", loadChanges);
document.getElementById("source-refresh").addEventListener("click", loadSource);
document.getElementById("notif-refresh").addEventListener("click", loadNotifications);
document.getElementById("usage-refresh").addEventListener("click", loadUsage);
document.getElementById("system-refresh").addEventListener("click", loadSystem);

/* Agent companion panel toggle (layout state only — no data effect). */
document.getElementById("agent-toggle").addEventListener("click", () => {
  const panel = document.getElementById("agent-panel");
  const btn = document.getElementById("agent-toggle");
  const collapsed = panel.classList.toggle("collapsed");
  btn.setAttribute("aria-pressed", String(!collapsed));
});

/* --- toasts (transient feedback only — never the only record) ------------------ */

function toast(text, kind) {
  const region = document.getElementById("toast-region");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  region.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

/* --- Agent companion (§9 hybrid: persistent panel, POST 2 of 4) ---------------- */

async function loadAgent() {
  const result = await api("/v1/agent/tools");
  const tbody = document.querySelector("#tools-table tbody");
  tbody.textContent = "";
  if (!result.ok) { renderError(document.getElementById("global-error"), result.body); return; }
  for (const tool of result.body.tools) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.className = "mono";
    name.textContent = tool.name;
    name.title = tool.description;
    const cls = document.createElement("td"); cls.appendChild(statusBadge(tool.class));
    const args = document.createElement("td"); args.textContent = tool.arguments.join(", ") || "\u2014";
    tr.append(name, cls, args);
    tbody.appendChild(tr);
  }
}

document.getElementById("agent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const textarea = document.getElementById("agent-message");
  const message = textarea.value.trim();
  if (!message) return;
  const log = document.getElementById("agent-log");

  const userTurn = document.createElement("div");
  userTurn.className = "turn";
  const who = document.createElement("div"); who.className = "who"; who.textContent = "You";
  const text = document.createElement("div"); text.textContent = message;
  userTurn.append(who, text);
  log.prepend(userTurn);
  textarea.value = "";

  const result = await api("/v1/agent/converse", { method: "POST", body: { message } });
  const agentTurn = document.createElement("div");
  agentTurn.className = "turn";
  const agentWho = document.createElement("div"); agentWho.className = "who"; agentWho.textContent = "Agent";
  agentTurn.appendChild(agentWho);

  if (!result.ok) {
    const err = document.createElement("div"); err.className = "error-box";
    renderError(err, result.body);
    agentTurn.appendChild(err);
    log.prepend(agentTurn);
    return;
  }

  /* Full tool transcript — every dispatch, including refusals. */
  for (const call of result.body.tool_calls || []) {
    const row = document.createElement("div");
    row.className = call.ok ? "tool-row" : "tool-row refused";
    row.textContent = call.ok
      ? `\u2713 ${call.tool} (${call.tool_class})`
      : `\u2717 ${call.tool} \u2014 refused: ${call.refusal}`;
    agentTurn.appendChild(row);
  }

  /* Claims: evidence citations are mandatory content. */
  const claims = result.body.claims || [];
  if (claims.length === 0 && (result.body.tool_calls || []).length === 0) {
    const none = document.createElement("div");
    none.className = "claim refused";
    none.textContent = result.body.note || "no substantiated claims this turn";
    agentTurn.appendChild(none);
  }
  for (const claim of claims) {
    const div = document.createElement("div");
    if (!claim.evidence || claim.evidence.length === 0) {
      div.className = "claim refused";
      div.textContent = "claim refused: no evidence citation";
    } else {
      div.className = "claim";
      const t = document.createElement("div"); t.textContent = claim.text;
      const ev = document.createElement("div"); ev.className = "evidence";
      ev.textContent = "evidence: " + claim.evidence.map((e) => `${e.kind}:${e.ref}`).join(", ");
      div.append(t, ev);
    }
    agentTurn.appendChild(div);
  }
  if (result.body.note && claims.length > 0) {
    const note = document.createElement("div"); note.className = "claim refused";
    note.textContent = result.body.note;
    agentTurn.appendChild(note);
  }
  log.prepend(agentTurn);
});

/* --- Surface: Overview — attention synthesis (every figure a real read) -------- */

async function loadOverview() {
  const el = document.getElementById("overview-body");
  const errorBox = document.getElementById("overview-error");
  errorBox.hidden = true;
  el.textContent = "";

  const [health, notifications, executions, capabilities, changes] = await Promise.all([
    refreshHealth(),
    api("/v1/admin/notifications"),
    api("/v1/executions"),
    api("/v1/admin/capabilities"),
    api("/v1/admin/changes"),
  ]);

  /* Health */
  el.appendChild(card("Health", health ? statusBadge(health.status) : statusBadge("unreachable")));

  /* Unread notifications — the primary attention figure. */
  if (notifications.ok) {
    const n = document.createElement("span");
    n.textContent = String(notifications.body.unread);
    if (notifications.body.unread > 0) {
      n.append(" ", statusBadge("warning"));
    }
    el.appendChild(card("Unread notifications", n));
  } else {
    renderError(errorBox, notifications.body);
  }

  /* Executions: totals + failure count (counted from real rows). */
  if (executions.ok) {
    const rows = executions.body.executions || [];
    const failed = rows.filter((r) => r.status === "failed").length;
    const running = rows.filter((r) => r.status === "queued" || r.status === "running").length;
    const v = document.createElement("span");
    v.textContent = String(rows.length);
    const detail = document.createElement("div");
    detail.className = "small muted";
    detail.textContent = `${failed} failed \u00b7 ${running} in flight`;
    const wrap = document.createElement("span");
    wrap.append(v, detail);
    el.appendChild(card("Executions", wrap));
  } else {
    renderError(errorBox, executions.body);
  }

  /* Capability posture: counts by state, from the closed set. */
  if (capabilities.ok) {
    const rows = capabilities.body.capabilities || [];
    const byState = {};
    for (const c of rows) byState[c.state] = (byState[c.state] || 0) + 1;
    const wrap = document.createElement("span");
    const total = document.createElement("span");
    total.textContent = String(rows.length);
    const detail = document.createElement("div");
    detail.className = "small muted";
    detail.textContent = Object.entries(byState)
      .map(([k, v]) => `${v} ${k}`)
      .join(" \u00b7 ") || "none";
    wrap.append(total, detail);
    el.appendChild(card("Capabilities", wrap));
  } else {
    renderError(errorBox, capabilities.body);
  }

  /* Governance: validated changes awaiting an explicit human publish. */
  if (changes.ok) {
    const rows = changes.body.changes || [];
    const awaiting = rows.filter((c) => c.state === "validated").length;
    const wrap = document.createElement("span");
    const total = document.createElement("span");
    total.textContent = String(rows.length);
    const detail = document.createElement("div");
    detail.className = "small muted";
    detail.textContent = `${awaiting} validated \u2014 awaiting publish decision`;
    wrap.append(total, detail);
    el.appendChild(card("Config changes", wrap));
  } else {
    renderError(errorBox, changes.body);
  }
}

/* --- Surface: Executions -------------------------------------------------------- */

function ledgerText(ledger) {
  if (ledger === null || ledger === undefined) {
    return "no ledger (accounting unbound)";
  }
  return `${ledger.status}: ${ledger.units_settled}/${ledger.units_reserved}`;
}

async function loadExecutions() {
  const result = await api("/v1/executions");
  const tbody = document.querySelector("#executions-table tbody");
  tbody.textContent = "";
  if (!result.ok) { renderError(document.getElementById("global-error"), result.body); return; }
  for (const row of result.body.executions || []) {
    const tr = document.createElement("tr");
    const id = document.createElement("td"); id.className = "mono"; id.textContent = row.execution_id;
    const status = document.createElement("td"); status.appendChild(statusBadge(row.status));
    const created = document.createElement("td"); created.textContent = row.created_at;
    const ledger = document.createElement("td"); ledger.textContent = ledgerText(row.ledger);
    const open = document.createElement("td");
    const btn = document.createElement("button"); btn.textContent = "Open";
    btn.addEventListener("click", () => openExecution(row.execution_id));
    open.appendChild(btn);
    tr.append(id, status, created, ledger, open);
    tbody.appendChild(tr);
  }
}

async function openExecution(executionId) {
  const detail = document.getElementById("execution-detail");
  detail.hidden = false;
  const traceEl = document.getElementById("tab-trace");
  const diagEl = document.getElementById("tab-diagnosis");
  traceEl.textContent = "";
  diagEl.textContent = "";

  const trace = await api(`/v1/agent/executions/${executionId}/trace`);
  if (!trace.ok) {
    renderError(traceEl.appendChild(document.createElement("div")), trace.body);
  } else if (trace.body.as_recorded !== true) {
    /* Component contract: refuse to render anything not marked as recorded. */
    const refusal = document.createElement("div");
    refusal.className = "error-box";
    refusal.hidden = false;
    refusal.textContent = "trace refused: response is not marked as_recorded";
    traceEl.appendChild(refusal);
  } else {
    const label = document.createElement("p");
    label.className = "muted";
    label.textContent = "Post-hoc trace, as recorded \u2014 not live progress.";
    traceEl.appendChild(label);
    for (const stage of trace.body.stages || []) {
      const div = document.createElement("div"); div.className = "card";
      const head = document.createElement("div");
      head.append(`stage ${stage.node_key} \u2014 `, statusBadge(stage.status));
      div.appendChild(head);
      for (const attempt of stage.attempts || []) {
        const row = document.createElement("div"); row.className = "tool-row";
        row.textContent =
          `attempt ${attempt.attempt}: ${attempt.model_key}@${attempt.provider_key} ` +
          (attempt.succeeded ? "succeeded" : `failed (${attempt.error_category || "no category"})`);
        div.appendChild(row);
      }
      traceEl.appendChild(div);
    }
  }

  const diag = await api(`/v1/agent/executions/${executionId}/diagnosis`);
  if (!diag.ok) {
    renderError(diagEl.appendChild(document.createElement("div")), diag.body);
  } else {
    const tier = document.createElement("p");
    tier.append("tier: ", statusBadge(diag.body.tier));
    diagEl.appendChild(tier);
    for (const claim of diag.body.claims || []) {
      const div = document.createElement("div");
      if (!claim.evidence || claim.evidence.length === 0) {
        div.className = "claim refused";
        div.textContent = "claim refused: no evidence citation";
      } else {
        div.className = "claim";
        const t = document.createElement("div"); t.textContent = claim.text;
        const ev = document.createElement("div"); ev.className = "evidence";
        ev.textContent = "evidence: " + claim.evidence.map((e) => `${e.kind}:${e.ref}`).join(", ");
        div.append(t, ev);
      }
      diagEl.appendChild(div);
    }
    for (const missing of diag.body.missing_evidence || []) {
      const div = document.createElement("div"); div.className = "claim refused";
      div.textContent = `missing evidence: ${missing}`;
      diagEl.appendChild(div);
    }
  }
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-trace").hidden = tab.dataset.tab !== "trace";
    document.getElementById("tab-diagnosis").hidden = tab.dataset.tab !== "diagnosis";
  });
});

/* --- Surface: Catalog (models + providers + routing weights, all reads) --------- */

async function loadCatalog() {
  const [models, providers, weights] = await Promise.all([
    api("/v1/admin/models"),
    api("/v1/admin/providers"),
    api("/v1/admin/routing/weights"),
  ]);
  const modelsBody = document.querySelector("#models-table tbody");
  modelsBody.textContent = "";
  if (!models.ok) {
    renderError(document.getElementById("global-error"), models.body);
  } else {
    for (const m of models.body.models || []) {
      const tr = document.createElement("tr");
      const key = document.createElement("td"); key.className = "mono"; key.textContent = m.model_key;
      const name = document.createElement("td"); name.textContent = m.display_name;
      const tier = document.createElement("td"); tier.textContent = m.tier;
      const scores = document.createElement("td"); scores.className = "mono";
      scores.textContent =
        `${m.quality_score}/${m.speed_score}/${m.cost_score}/${m.reliability_score}`;
      const status = document.createElement("td"); status.appendChild(statusBadge(m.status));
      tr.append(key, name, tier, scores, status);
      modelsBody.appendChild(tr);
    }
  }
  const providersBody = document.querySelector("#providers-table tbody");
  providersBody.textContent = "";
  if (providers.ok) {
    for (const p of providers.body.providers || []) {
      const tr = document.createElement("tr");
      const key = document.createElement("td"); key.className = "mono"; key.textContent = p.provider_key;
      const name = document.createElement("td"); name.textContent = p.display_name;
      const status = document.createElement("td"); status.appendChild(statusBadge(p.status));
      const auth = document.createElement("td");
      auth.textContent = (p.auth_types || []).join(", ") || "\u2014";
      const template = document.createElement("td"); template.textContent = p.is_template ? "yes" : "no";
      const routable = document.createElement("td"); routable.textContent = p.is_routable ? "yes" : "no";
      tr.append(key, name, status, auth, template, routable);
      providersBody.appendChild(tr);
    }
  }
  const weightsEl = document.getElementById("routing-weights");
  weightsEl.textContent = "";
  if (weights.ok) {
    const w = weights.body;
    weightsEl.append(
      chip("version", w.version),
      chip("quality", w.quality),
      chip("reliability", w.reliability),
      chip("cost", w.cost),
      chip("latency", w.latency),
      chip("context_fit", w.context_fit),
      chip("policy_preference", w.policy_preference),
    );
    const note = document.createElement("div");
    note.className = "muted small";
    note.textContent = "Weight changes travel through the config-change lifecycle (Governance), never direct edits.";
    weightsEl.appendChild(note);
  } else {
    const err = document.createElement("div");
    err.className = "error-box";
    renderError(err, weights.body);
    weightsEl.appendChild(err);
  }
}

/* --- Surface: Intelligence (capabilities / scenarios / self-review / learning) --- */

async function loadIntelligence() {
  const [capabilities, exercisable, scenarios, selfReview, learning, labChecks] =
    await Promise.all([
      api("/v1/admin/capabilities"),
      api("/v1/admin/capabilities/exercisable"),
      api("/v1/admin/scenarios"),
      api("/v1/admin/self-review"),
      api("/v1/admin/learning/changes-since-review"),
      api("/v1/admin/context-lab/checks"),
    ]);

  /* Capabilities: state is composition truth. "inert" is outside the badge
     vocabulary on purpose — it renders as the loud UNKNOWN badge rather
     than being quietly absorbed into a softer class. */
  const capBody = document.querySelector("#capabilities-table tbody");
  capBody.textContent = "";
  if (!capabilities.ok) {
    renderError(document.getElementById("global-error"), capabilities.body);
  } else {
    for (const c of capabilities.body.capabilities || []) {
      const tr = document.createElement("tr");
      const id = document.createElement("td"); id.className = "mono"; id.textContent = c.id;
      const st = document.createElement("td"); st.appendChild(statusBadge(c.state));
      const ev = document.createElement("td"); ev.className = "mono small";
      ev.textContent = typeof c.evidence === "string" ? c.evidence : JSON.stringify(c.evidence);
      tr.append(id, st, ev);
      capBody.appendChild(tr);
    }
  }
  const exNote = document.getElementById("exercisable-note");
  if (exercisable.ok) {
    const ids = exercisable.body.exercisable || [];
    exNote.textContent = ids.length
      ? `Exercisable now (${ids.length}): ${ids.join(", ")}`
      : "Nothing exercisable in this composition.";
  } else {
    exNote.textContent = "";
  }

  const scBody = document.querySelector("#scenarios-table tbody");
  scBody.textContent = "";
  if (scenarios.ok) {
    const rows = scenarios.body.scenarios || [];
    if (rows.length === 0) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.className = "muted";
      td.textContent = "No scenarios recorded since process start.";
      tr.appendChild(td);
      scBody.appendChild(tr);
    }
    for (const s of rows) {
      const tr = document.createElement("tr");
      const name = document.createElement("td"); name.textContent = s.name;
      const ask = document.createElement("td"); ask.textContent = s.ask;
      const checks = document.createElement("td"); checks.className = "mono small";
      checks.textContent = JSON.stringify(s.checks);
      const created = document.createElement("td"); created.textContent = s.created_at;
      tr.append(name, ask, checks, created);
      scBody.appendChild(tr);
    }
  }

  /* Self-review: real by_state counts, nothing synthesized. */
  const reviewEl = document.getElementById("self-review-body");
  reviewEl.textContent = "";
  if (selfReview.ok && selfReview.body.capabilities) {
    const byState = selfReview.body.capabilities.by_state || {};
    for (const [stateName, count] of Object.entries(byState)) {
      reviewEl.appendChild(card(stateName, String(count)));
    }
  }

  const learnEl = document.getElementById("learning-review");
  learnEl.textContent = "";
  if (learning.ok) {
    const pre = document.createElement("pre");
    pre.className = "mono small";
    pre.textContent = JSON.stringify(learning.body, null, 2);
    learnEl.appendChild(pre);
  } else {
    const err = document.createElement("div");
    err.className = "error-box";
    renderError(err, learning.body);
    learnEl.appendChild(err);
  }

  const labEl = document.getElementById("lab-checks");
  labEl.textContent = "";
  if (labChecks.ok) {
    const rows = labChecks.body.checks || [];
    labEl.textContent = rows.length
      ? JSON.stringify(rows, null, 2)
      : "No context-lab checks recorded.";
  } else {
    /* Seam not composed here — say so verbatim, never pretend. */
    const err = document.createElement("div");
    err.className = "error-box";
    renderError(err, labChecks.body);
    labEl.appendChild(err);
  }
}

/* --- Surface: Changes & Audit (POST 3 of 4 — explicit human act) ----------------- */

async function lifecycleAct(changeId, step) {
  /* Explicit human act (doc C §5): publish/rollback exist ONLY here —
     denials from the backend render verbatim (criterion 3). */
  const errorBox = document.getElementById("lifecycle-error");
  errorBox.hidden = true;
  const result = await api(`/v1/admin/changes/${changeId}/${step}`, { method: "POST" });
  if (!result.ok) {
    renderError(errorBox, result.body);
    toast(`${step} refused`, "err");
  } else {
    toast(`${step}: ${result.body.state}`, "ok");
  }
  loadChanges();
}

async function loadChanges() {
  const [changes, audit] = await Promise.all([
    api("/v1/admin/changes"),
    api("/v1/admin/audit"),
  ]);
  const changesBody = document.querySelector("#changes-table tbody");
  changesBody.textContent = "";
  if (changes.ok) {
    for (const c of changes.body.changes || []) {
      const tr = document.createElement("tr");
      const id = document.createElement("td"); id.className = "mono"; id.textContent = c.id;
      const area = document.createElement("td"); area.textContent = c.area;
      const action = document.createElement("td"); action.textContent = c.action;
      const stateCell = document.createElement("td"); stateCell.appendChild(statusBadge(c.state));
      const validation = document.createElement("td");
      validation.textContent = c.validation_result || "\u2014";
      const created = document.createElement("td"); created.textContent = c.created_at;
      const act = document.createElement("td");
      if (c.state === "validated" && c.impact_preview !== undefined) {
        const btn = document.createElement("button");
        btn.className = "danger";
        btn.textContent = "Publish";
        btn.addEventListener("click", () => lifecycleAct(c.id, "publish"));
        act.appendChild(btn);
      } else if (c.state === "published") {
        const btn = document.createElement("button");
        btn.className = "danger";
        btn.textContent = "Rollback";
        btn.addEventListener("click", () => lifecycleAct(c.id, "rollback"));
        act.appendChild(btn);
      } else {
        act.textContent = "\u2014";
      }
      tr.append(id, area, action, stateCell, validation, created, act);
      changesBody.appendChild(tr);
    }
  }
  const auditBody = document.querySelector("#audit-table tbody");
  auditBody.textContent = "";
  if (audit.ok) {
    for (const e of audit.body.events || []) {
      const tr = document.createElement("tr");
      const id = document.createElement("td"); id.className = "mono"; id.textContent = e.id;
      const type = document.createElement("td"); type.textContent = e.event_type;
      const occurred = document.createElement("td"); occurred.textContent = e.occurred_at;
      const details = document.createElement("td"); details.className = "mono";
      details.textContent = JSON.stringify(e.details);
      tr.append(id, type, occurred, details);
      auditBody.appendChild(tr);
    }
  }
}

/* --- Surface: Source changes (ADR-0009 pipeline — read-only surface) -------------- */

async function loadSource() {
  const result = await api("/v1/admin/source-changes");
  const tbody = document.querySelector("#source-table tbody");
  tbody.textContent = "";
  if (!result.ok) { renderError(document.getElementById("global-error"), result.body); return; }
  const rows = result.body.proposals || [];
  if (rows.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 6;
    td.className = "muted";
    td.textContent = "No source-change proposals since process start.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  for (const p of rows) {
    const tr = document.createElement("tr");
    const id = document.createElement("td"); id.className = "mono"; id.textContent = p.proposal_id;
    /* Proposal verification states are outside the badge vocabulary on
       purpose — they render as the loud UNKNOWN badge, never absorbed. */
    const st = document.createElement("td"); st.appendChild(statusBadge(p.state));
    const hash = document.createElement("td"); hash.className = "mono";
    hash.title = p.patch_hash || "";
    hash.textContent = p.patch_hash ? p.patch_hash.slice(0, 12) + "\u2026" : "\u2014";
    const rationale = document.createElement("td"); rationale.textContent = p.rationale;
    const approval = document.createElement("td"); approval.className = "mono small";
    if (p.approval) {
      approval.textContent =
        `${p.approval.approver_id} cited ${String(p.approval.approved_patch_hash).slice(0, 12)}\u2026`;
    } else {
      approval.textContent = "\u2014";
    }
    const created = document.createElement("td"); created.textContent = p.created_at;
    tr.append(id, st, hash, rationale, approval, created);
    tbody.appendChild(tr);
  }
}

/* --- Surface: Notifications (NTF-1 read-model, manual poll; POST 4 of 4 = ack) ---- */

async function loadNotifications() {
  const result = await api("/v1/admin/notifications");
  const badge = document.getElementById("notif-unread");
  const tbody = document.querySelector("#notif-table tbody");
  tbody.textContent = "";
  if (!result.ok) { renderError(document.getElementById("global-error"), result.body); return; }
  badge.textContent = String(result.body.unread);
  badge.hidden = result.body.unread === 0;
  for (const n of result.body.notifications || []) {
    const tr = document.createElement("tr");
    const category = document.createElement("td"); category.appendChild(statusBadge(n.category));
    const title = document.createElement("td"); title.textContent = n.title;
    const occurred = document.createElement("td"); occurred.textContent = n.occurred_at;
    /* Criterion 4: every notification links its evidence record. */
    const evidence = document.createElement("td"); evidence.className = "mono";
    evidence.textContent = `${n.evidence.kind}: ${n.evidence.ref}`;
    const read = document.createElement("td");
    if (n.read) {
      read.textContent = "read";
    } else {
      const btn = document.createElement("button");
      btn.textContent = "Mark read";
      btn.addEventListener("click", async () => {
        const ack = await api(`/v1/admin/notifications/${encodeURIComponent(n.id)}/ack`, { method: "POST" });
        if (!ack.ok) { renderError(document.getElementById("global-error"), ack.body); return; }
        loadNotifications();
      });
      read.appendChild(btn);
    }
    tr.append(category, title, occurred, evidence, read);
    tbody.appendChild(tr);
  }
}

/* --- Surface: Tenants & Usage ------------------------------------------------------ */

async function loadUsage() {
  const [drill, webhooks] = await Promise.all([
    api("/v1/admin/usage"),
    api("/v1/webhooks"),
  ]);
  const usageBody = document.querySelector("#usage-table tbody");
  usageBody.textContent = "";
  if (drill.ok) {
    for (const row of drill.body.usage || []) {
      const tr = document.createElement("tr");
      const id = document.createElement("td"); id.className = "mono"; id.textContent = row.execution_id;
      const status = document.createElement("td"); status.appendChild(statusBadge(row.status));
      const created = document.createElement("td"); created.textContent = row.created_at;
      const ledger = document.createElement("td"); ledger.textContent = ledgerText(row.ledger);
      tr.append(id, status, created, ledger);
      usageBody.appendChild(tr);
    }
  }
  const webhooksBody = document.querySelector("#webhooks-table tbody");
  webhooksBody.textContent = "";
  if (webhooks.ok) {
    for (const w of webhooks.body.webhooks || []) {
      const tr = document.createElement("tr");
      const id = document.createElement("td"); id.className = "mono"; id.textContent = w.subscription_id;
      const host = document.createElement("td"); host.textContent = w.url_host || "\u2014";
      const events = document.createElement("td"); events.textContent = (w.events || []).join(", ");
      tr.append(id, host, events);
      webhooksBody.appendChild(tr);
    }
  }
}

/* --- Surface: System ---------------------------------------------------------------- */

async function loadSystem() {
  const health = await refreshHealth();
  const healthEl = document.getElementById("system-health");
  healthEl.textContent = "";
  if (health) {
    healthEl.append(statusBadge(health.status), ` at ${health.time}`);
  } else {
    healthEl.textContent = "healthz unavailable";
  }
  const info = await api("/v1/admin/system");
  const infoEl = document.getElementById("system-info");
  infoEl.textContent = info.ok ? JSON.stringify(info.body, null, 2) : "system info unavailable";
}
