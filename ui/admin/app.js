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
  /* LearningEligibility / SanitizationState (R160 Learning surface) */
  pending: "info",
  eligible: "ok",
  ineligible: "err",
  passed: "ok",
  /* VerificationLevel (core/contracts/evaluation.py — UPPERCASE literals) */
  RAW: "neutral",
  EVALUATED: "info",
  VALIDATED: "info",
  VERIFIED: "ok",
  GOLD: "ok",
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
  collapseAgentPanelIfNarrow();
  refreshHealth();
  loadAgent();
  loadPlatformAgentTools();
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
    learning: loadLearning,
    skills: loadSkills,
    onboarding: loadOnboarding,
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
document.getElementById("learning-refresh").addEventListener("click", loadLearning);
document.getElementById("skills-refresh").addEventListener("click", loadSkills);
document.getElementById("onboarding-refresh").addEventListener("click", loadOnboarding);

/* Agent companion panel toggle (layout state only — no data effect). */
document.getElementById("agent-toggle").addEventListener("click", () => {
  const panel = document.getElementById("agent-panel");
  const btn = document.getElementById("agent-toggle");
  const collapsed = panel.classList.toggle("collapsed");
  btn.setAttribute("aria-pressed", String(!collapsed));
});

/* Responsive layout DECISION: below 1180px the panel overlays the content,
   so it starts (and returns to) collapsed — opened explicitly via the
   toggle. Event-driven media query, no polling. */
const narrowViewport = window.matchMedia("(max-width: 1180px)");
function collapseAgentPanelIfNarrow() {
  if (!narrowViewport.matches) return;
  document.getElementById("agent-panel").classList.add("collapsed");
  document.getElementById("agent-toggle").setAttribute("aria-pressed", "false");
}
narrowViewport.addEventListener("change", collapseAgentPanelIfNarrow);

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

/* Admin parity (R160): the SAME platform-wide catalog every tenant reads —
   GET /v1/agent-tools (the strategy=agent allow-list seam). Admin consumes
   the generic surface; nothing is re-derived here. Absent route (no agent
   seam composed) renders as an honest note, never an invented list. */
async function loadPlatformAgentTools() {
  const result = await api("/v1/agent-tools");
  const note = document.getElementById("platform-tools-note");
  const tbody = document.querySelector("#platform-tools-table tbody");
  tbody.textContent = "";
  if (!result.ok) {
    note.textContent = result.status === 404
      ? "Shared agent runtime not composed in this profile (route absent)."
      : `Catalog unavailable (${result.status}).`;
    return;
  }
  const tools = result.body.tools || [];
  note.textContent = `strategy=${result.body.strategy} · max_steps=${result.body.max_steps} · ${tools.length} tool(s) offered`;
  for (const tool of tools) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.className = "mono";
    name.textContent = tool.name;
    name.title = tool.description || "";
    const perm = document.createElement("td"); perm.className = "mono"; perm.textContent = tool.permission;
    const risk = document.createElement("td"); risk.className = "mono"; risk.textContent = tool.risk_level;
    const args = document.createElement("td");
    args.textContent = Object.keys(tool.arguments || {}).join(", ") || "\u2014";
    tr.append(name, perm, risk, args);
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


/* --- Learning surface (R160) ---------------------------------------------------
   The 22 §8 lifecycle over the REAL admin routes. Absent routes (no lifecycle
   seam composed) render as an honest note. Every verdict is an explicit click
   with the SAME closed request shapes the API validates — no defaults here. */

/* The unified error envelope ({error:{code,message}}) rendered verbatim. */
function errorText(payload) {
  return payload && payload.error ? `${payload.error.code}: ${payload.error.message}` : "";
}

function td(text, cls) {
  const cell = document.createElement("td");
  if (cls) cell.className = cls;
  cell.textContent = text === undefined || text === null || text === "" ? "\u2014" : String(text);
  return cell;
}

function actionButton(label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "btn-ghost small";
  btn.textContent = label;
  btn.addEventListener("click", onClick);
  return btn;
}

function parseJsonObject(text, what) {
  try {
    const value = JSON.parse(text);
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new Error("not an object");
    return value;
  } catch (err) {
    toast(`${what}: invalid JSON object (${err.message})`, "err");
    return null;
  }
}

async function learningStep(sampleId, step, body) {
  const result = await api(`/v1/admin/learning/samples/${encodeURIComponent(sampleId)}/${step}`, { method: "POST", body });
  if (result.ok) toast(`${step}: ${sampleId.slice(0, 8)}… → ${JSON.stringify(result.body).slice(0, 80)}`, "ok");
  else toast(`${step} refused (${result.status}): ${errorText(result.body)}`, "err");
  loadLearning();
}

function sampleActions(sample) {
  const cell = document.createElement("td");
  cell.className = "actions";
  const id = sample.id;
  cell.append(
    actionButton("Evaluate", () => {
      const text = window.prompt("Evaluate: the observed OUTPUT (JSON object) to grade against the source execution", "{}");
      if (text === null) return;
      const output = parseJsonObject(text, "output");
      if (output) learningStep(id, "evaluate", { output });
    }),
    actionButton("Sanitize ✓", () => learningStep(id, "sanitize", { passed: true })),
    actionButton("Sanitize ✗", () => learningStep(id, "sanitize", { passed: false })),
    actionButton("Admit", () => {
      // Three explicit attestations — the API's closed shape; unchecked = false.
      const privacy = window.confirm("Attest: privacy policy allows training on this sample?");
      const tenant = window.confirm("Attest: tenant/user policy allows it?");
      const sensitive = window.confirm("Attest: sensitive data has been handled?");
      learningStep(id, "admit", {
        privacy_policy_allows: privacy,
        tenant_user_policy_allows: tenant,
        sensitive_data_handled: sensitive,
      });
    }),
    actionButton("Promote", () => {
      const offline = window.confirm("Attest: offline evaluation PASSED?");
      const regression = window.confirm("Attest: regression PASSED?");
      const security = window.confirm("Attest: security evaluation PASSED?");
      learningStep(id, "promote", {
        offline_eval_pass: offline,
        regression_pass: regression,
        security_eval_pass: security,
      });
    }),
  );
  return cell;
}

async function loadLearning() {
  const unavailable = document.getElementById("learning-unavailable");
  const [samples, learned, since] = await Promise.all([
    api("/v1/admin/learning/samples"),
    api("/v1/admin/learning/learned"),
    api("/v1/admin/learning/changes-since-review"),
  ]);
  const tbody = document.querySelector("#samples-table tbody");
  tbody.textContent = "";
  if (samples.status === 404) {
    unavailable.hidden = false;
    unavailable.textContent = "Learning lifecycle not composed in this profile (routes absent).";
    return;
  }
  unavailable.hidden = true;
  if (!samples.ok) { renderError(document.getElementById("global-error"), samples.body); return; }
  for (const s of samples.body.samples || []) {
    const tr = document.createElement("tr");
    tr.append(td(s.id, "mono"), td(s.source_execution_id, "mono"));
    for (const value of [s.eligibility, s.sanitization_state, s.verification_level]) {
      const cell = document.createElement("td"); cell.appendChild(statusBadge(value)); tr.appendChild(cell);
    }
    tr.appendChild(sampleActions(s));
    tbody.appendChild(tr);
  }
  const keys = document.getElementById("learned-keys");
  keys.textContent = learned.ok ? ((learned.body.keys || []).join(", ") || "(nothing learned yet)") : `unavailable (${learned.status})`;
  const sinceEl = document.getElementById("learning-since-review");
  sinceEl.textContent = since.ok ? JSON.stringify(since.body, null, 2) : `unavailable (${since.status})`;
}

document.getElementById("learning-capture-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const value = parseJsonObject(document.getElementById("capture-value").value, "knowledge_value");
  if (!value) return;
  const body = {
    knowledge_key: document.getElementById("capture-key").value.trim(),
    knowledge_value: value,
  };
  const execution = document.getElementById("capture-execution").value.trim();
  if (execution) body.source_execution_id = execution;
  const result = await api("/v1/admin/learning/samples", { method: "POST", body });
  if (result.ok) { toast("sample captured (PENDING)", "ok"); event.target.reset(); }
  else toast(`capture refused (${result.status}): ${errorText(result.body)}`, "err");
  loadLearning();
});

document.getElementById("learning-ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const key = document.getElementById("learning-ask-key").value.trim();
  const result = await api("/v1/admin/learning/ask", { method: "POST", body: { key } });
  document.getElementById("learning-ask-result").textContent =
    `${result.status} ${JSON.stringify(result.body, null, 2)}`;
});

let lastRetestSnapshot = null;
document.getElementById("learning-retest-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const probes = document.getElementById("retest-probes").value.split("\n").map((l) => l.trim()).filter(Boolean);
  const body = { probes };
  if (document.getElementById("retest-use-baseline").checked && lastRetestSnapshot) body.baseline = lastRetestSnapshot;
  const result = await api("/v1/admin/learning/capability-retest", { method: "POST", body });
  const out = document.getElementById("retest-result");
  if (!result.ok) { out.textContent = `${result.status} ${JSON.stringify(result.body, null, 2)}`; return; }
  lastRetestSnapshot = result.body.snapshot;
  const snap = result.body.snapshot;
  let text = `score ${snap.score} — found ${snap.found.length}/${snap.probes.length} · missing: ${snap.missing.join(", ") || "none"}`;
  if (result.body.delta) {
    const d = result.body.delta;
    text += `\ndelta vs baseline: gained ${JSON.stringify(d.gained)} · lost ${JSON.stringify(d.lost)} · still missing ${JSON.stringify(d.still_missing)}`;
  }
  out.textContent = text;
});

document.getElementById("learning-mark-reviewed").addEventListener("click", async () => {
  const result = await api("/v1/admin/learning/mark-reviewed", { method: "POST", body: {} });
  toast(result.ok ? "learning review marker recorded" : `refused (${result.status})`, result.ok ? "ok" : "err");
  loadLearning();
});

/* --- Skills acquisition surface (R160) -----------------------------------------
   14 §3 over /v1/admin/skills/*: the holding area (pending imports) and the
   registry view (/v1/skills) are BOTH read from the server — activation is
   visible as the row leaving one table and appearing in the other. */

const SKILL_NEXT_STEP = {
  imported: "scan",
  scanned: "validate",
  validated: "review",
  reviewed: "approve",
  approved: "activate",
};

async function skillStep(skillId, step) {
  const body = step === "scan" ? { findings: [] } : undefined;
  const result = await api(`/v1/admin/skills/imports/${encodeURIComponent(skillId)}/${step}`, { method: "POST", body });
  if (result.ok) toast(`${step} → ${result.body.status} (source ${result.body.source})`, "ok");
  else toast(`${step} refused (${result.status}): ${errorText(result.body)}`, "err");
  loadSkills();
}

async function loadSkills() {
  const unavailable = document.getElementById("skills-unavailable");
  const [imports, selectable] = await Promise.all([
    api("/v1/admin/skills/imports"),
    api("/v1/skills"),
  ]);
  const tbody = document.querySelector("#imports-table tbody");
  tbody.textContent = "";
  if (imports.status === 404) {
    unavailable.hidden = false;
    unavailable.textContent = "Skill acquisition pipeline not composed in this profile (routes absent).";
  } else if (!imports.ok) {
    unavailable.hidden = true;
    renderError(document.getElementById("global-error"), imports.body);
  } else {
    unavailable.hidden = true;
    document.getElementById("skills-allowed-sources").textContent = (imports.body.allowed_sources || []).join("  |  ");
    for (const s of imports.body.imports || []) {
      const tr = document.createElement("tr");
      const name = td(s.name); name.title = s.skill_id;
      tr.append(name, td(s.version, "mono"), td(s.type, "mono"));
      const status = document.createElement("td"); status.appendChild(statusBadge(s.status)); tr.appendChild(status);
      tr.append(
        td(s.provenance ? s.provenance.source_url : s.source, "mono small"),
        td(s.provenance ? s.provenance.reviewed_by : null, "mono small"),
      );
      const act = document.createElement("td"); act.className = "actions";
      const next = SKILL_NEXT_STEP[s.status];
      if (next) act.appendChild(actionButton(next, () => skillStep(s.skill_id, next)));
      else act.textContent = "\u2014";
      tr.appendChild(act);
      tbody.appendChild(tr);
    }
  }
  const selBody = document.querySelector("#selectable-skills-table tbody");
  selBody.textContent = "";
  if (selectable.ok) {
    for (const s of selectable.body.skills || []) {
      const tr = document.createElement("tr");
      tr.append(td(s.id, "mono"), td(s.name), td(s.version, "mono"), td((s.requires_tools || []).join(", "), "mono small"));
      selBody.appendChild(tr);
    }
  }
}

document.getElementById("skill-import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const manifest = parseJsonObject(document.getElementById("skill-manifest").value, "manifest");
  if (!manifest) return;
  const body = {
    manifest,
    content: document.getElementById("skill-content").value,
    source_url: document.getElementById("skill-source-url").value.trim(),
    source_version: document.getElementById("skill-source-version").value.trim(),
  };
  const checksum = document.getElementById("skill-checksum").value.trim();
  if (checksum) body.expected_checksum = checksum;
  const result = await api("/v1/admin/skills/import", { method: "POST", body });
  if (result.ok) { toast(`imported ${result.body.name} (status ${result.body.status} — not selectable yet)`, "ok"); event.target.reset(); }
  else toast(`import refused (${result.status}): ${errorText(result.body)}`, "err");
  loadSkills();
});

/* --- Provider onboarding surface (R160) -----------------------------------------
   Refs only (credential_ref / route_token_ref) — a raw key never enters this
   form. The response is a DRAFT enable payload; enabling stays the R2
   lifecycle's explicit publish (Changes & Audit). */

async function loadOnboarding() {
  const providers = await api("/v1/admin/providers");
  const tbody = document.querySelector("#onboarding-providers-table tbody");
  tbody.textContent = "";
  if (!providers.ok) { renderError(document.getElementById("global-error"), providers.body); return; }
  for (const p of providers.body.providers || []) {
    const tr = document.createElement("tr");
    tr.append(td(p.provider_key, "mono"), td(p.display_name));
    const status = document.createElement("td"); status.appendChild(statusBadge(p.status)); tr.appendChild(status);
    tbody.appendChild(tr);
  }
}

function csv(id) {
  return document.getElementById(id).value.split(",").map((s) => s.trim()).filter(Boolean);
}

document.getElementById("onboard-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const body = {
    provider_key: document.getElementById("onboard-key").value.trim(),
    display_name: document.getElementById("onboard-name").value.trim(),
    credential_ref: document.getElementById("onboard-credential-ref").value.trim(),
    route_token_ref: document.getElementById("onboard-route-token-ref").value.trim(),
    operations: csv("onboard-operations"),
    static_models: csv("onboard-models"),
    discover: document.getElementById("onboard-discover").checked,
  };
  const result = await api("/v1/admin/providers/onboard", { method: "POST", body });
  const out = document.getElementById("onboard-result");
  const unavailable = document.getElementById("onboarding-unavailable");
  if (result.status === 404) {
    unavailable.hidden = false;
    unavailable.textContent = "Provider onboarding not composed in this profile (route absent).";
  }
  out.textContent = `${result.status} ${JSON.stringify(result.body, null, 2)}`;
  if (result.ok) {
    toast(`onboarded ${result.body.provider_key} — steps: ${(result.body.steps_passed || []).join(", ")}; unverified: ${(result.body.unverified || []).join(", ") || "none"}`, "ok");
    loadOnboarding();
  } else {
    toast(`onboarding refused (${result.status})`, "err");
  }
});
