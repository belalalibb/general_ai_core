/* Admin Console — AA-2/AA-3 UI shell (doc D honesty rules as component contracts).
 *
 * HONESTY CONTRACTS enforced in this file:
 * - STATUS_CLASSES contains ONLY backend contract enum values; anything
 *   else renders the loud violet UNKNOWN badge (never gray-washed).
 * - openExecution refuses to render a trace unless as_recorded === true.
 *   There is no progress-bar code path in this file by design (doc A §6):
 *   traces are post-hoc evidence, not liveness theater.
 * - Claims without evidence citations render as refusals, never as facts.
 * - Ledger null renders "no ledger (accounting unbound)" — never invented.
 * - The amnesia banner is set in the store layer (api()) on first success.
 * - Exactly 4 POSTs exist (login, converse, lifecycle act, notification ack);
 *   publish/rollback are explicit human acts here — never agent tools.
 * - Lifecycle denials render VERBATIM via renderError (doc C §5 criterion 3).
 * - Notifications are a derived read-model polled by explicit Refresh —
 *   no setInterval, no push theater; toasts are feedback, never the record.
 */
"use strict";

const state = { token: null, surface: "agent" };

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

/* --- login ------------------------------------------------------------------ */

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
  loadSurface("agent");
});

/* --- navigation -------------------------------------------------------------- */

document.querySelectorAll(".rail-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".rail-item").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    loadSurface(btn.dataset.surface);
  });
});

function loadSurface(name) {
  state.surface = name;
  document.querySelectorAll(".surface").forEach((s) => (s.hidden = true));
  document.getElementById(`surface-${name}`).hidden = false;
  const loaders = {
    agent: loadAgent,
    overview: loadOverview,
    executions: loadExecutions,
    catalog: loadCatalog,
    changes: loadChanges,
    notifications: loadNotifications,
    usage: loadUsage,
    system: loadSystem,
  };
  loaders[name]();
}

/* --- toasts (transient feedback only — never the only record) ---------------- */

function toast(text, kind) {
  const region = document.getElementById("toast-region");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  region.appendChild(el);
  setTimeout(() => el.remove(), 6000);
}

/* --- Surface: Agent ----------------------------------------------------------- */

async function loadAgent() {
  const result = await api("/v1/agent/tools");
  const tbody = document.querySelector("#tools-table tbody");
  tbody.textContent = "";
  if (!result.ok) { renderError(document.getElementById("global-error"), result.body); return; }
  for (const tool of result.body.tools) {
    const tr = document.createElement("tr");
    const name = document.createElement("td"); name.textContent = tool.name;
    const cls = document.createElement("td"); cls.appendChild(statusBadge(tool.class));
    const args = document.createElement("td"); args.textContent = tool.arguments.join(", ") || "—";
    const desc = document.createElement("td"); desc.textContent = tool.description;
    tr.append(name, cls, args, desc);
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
      ? `✓ ${call.tool} (${call.tool_class})`
      : `✗ ${call.tool} — refused: ${call.refusal}`;
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

/* --- Surface: Overview --------------------------------------------------------- */

async function loadOverview() {
  const el = document.getElementById("overview-body");
  el.textContent = "";
  const [models, executions] = await Promise.all([
    api("/v1/models"),
    api("/v1/executions"),
  ]);
  const card = (title, value) => {
    const div = document.createElement("div"); div.className = "card";
    const h = document.createElement("h3"); h.textContent = title;
    const v = document.createElement("div"); v.textContent = value;
    div.append(h, v);
    return div;
  };
  if (models.ok) el.appendChild(card("Models", String((models.body.models || []).length)));
  if (executions.ok) el.appendChild(card("Executions (since process start)", String((executions.body.executions || []).length)));
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
    label.textContent = "Post-hoc trace, as recorded — not live progress.";
    traceEl.appendChild(label);
    for (const stage of trace.body.stages || []) {
      const div = document.createElement("div"); div.className = "card";
      const head = document.createElement("div");
      head.append(`stage ${stage.node_key} — `, statusBadge(stage.status));
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

/* --- Surface: Catalog ------------------------------------------------------------ */

async function loadCatalog() {
  const [models, providers] = await Promise.all([
    api("/v1/admin/models"),
    api("/v1/admin/providers"),
  ]);
  const modelsBody = document.querySelector("#models-table tbody");
  modelsBody.textContent = "";
  if (models.ok) {
    for (const m of models.body.models || []) {
      const tr = document.createElement("tr");
      const key = document.createElement("td"); key.className = "mono"; key.textContent = m.model_key;
      const name = document.createElement("td"); name.textContent = m.display_name;
      const tier = document.createElement("td"); tier.textContent = m.tier;
      const status = document.createElement("td"); status.appendChild(statusBadge(m.status));
      tr.append(key, name, tier, status);
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
      const template = document.createElement("td"); template.textContent = p.is_template ? "yes" : "no";
      const routable = document.createElement("td"); routable.textContent = p.is_routable ? "yes" : "no";
      tr.append(key, name, status, template, routable);
      providersBody.appendChild(tr);
    }
  }
}

/* --- Surface: Changes & Audit ------------------------------------------------------ */

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

/* --- Surface: Notifications (NTF-1 read-model, manual poll) --------------------------- */

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

document.getElementById("notif-refresh").addEventListener("click", loadNotifications);

/* --- Surface: Tenants & Usage -------------------------------------------------------- */

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
      const host = document.createElement("td"); host.textContent = w.url_host || "—";
      const events = document.createElement("td"); events.textContent = (w.events || []).join(", ");
      tr.append(id, host, events);
      webhooksBody.appendChild(tr);
    }
  }
}

/* --- Surface: System ------------------------------------------------------------------ */

async function loadSystem() {
  const health = await api("/healthz");
  const healthEl = document.getElementById("system-health");
  healthEl.textContent = "";
  if (health.ok) {
    healthEl.append(statusBadge(health.body.status), ` at ${health.body.time}`);
  } else {
    healthEl.textContent = "healthz unavailable";
  }
  const info = await api("/v1/admin/system");
  const infoEl = document.getElementById("system-info");
  infoEl.textContent = info.ok ? JSON.stringify(info.body, null, 2) : "system info unavailable";
}
