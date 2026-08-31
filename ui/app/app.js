/* End-user shell — P-D.2 (operator: "نفّذ P-D خيار A1.").
 *
 * HONESTY CONTRACTS enforced in this file (ui/admin posture carried):
 * - Profile is PROBED, never assumed: GET /v1/auth/session without a
 *   token distinguishes the demo profile (fixed-principal mode has NO
 *   auth routes ⇒ 404) from the durable profile (401 ⇒ auth view).
 *   Exactly one honesty banner shows.
 * - Provider labels render VERBATIM: a local-echo result is shown WITH
 *   its "no real model was called" label — never stripped (41 §49).
 * - STATUS_CLASSES contains ONLY backend contract enum values; anything
 *   else renders the loud UNKNOWN badge.
 * - Verification tokens NEVER appear in HTTP responses; the register
 *   panel says to read the SERVER CONSOLE — the UI never pretends an
 *   email was sent.
 * - Async progress is the REAL /events SSE stream (10 §11 event shapes)
 *   — no fabricated progress bars; frames render as received.
 * - Denials render the unified error VERBATIM via renderError.
 * - No setInterval polling theater: lists refresh on explicit Refresh.
 */
"use strict";

const state = { token: null, profile: null, email: null };

/* Status → badge class. KEYS MUST BE CONTRACT VALUES ONLY. */
const STATUS_CLASSES = {
  /* ExecutionStatus */
  queued: "info",
  running: "info",
  waiting_approval: "warn",
  succeeded: "ok",
  failed: "err",
  cancelled: "neutral",
  /* BindingAvailability */
  available: "ok",
  unavailable: "err",
  degraded: "warn",
  /* healthz literal */
  alive: "ok",
};

const $ = (id) => document.getElementById(id);

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

function clearError(el) {
  el.hidden = true;
  el.textContent = "";
}

/* --- profile probe ----------------------------------------------------------- */

async function probeProfile() {
  /* Durable profile: /v1/auth/session exists and answers 401 without a
     token. Demo profile: fixed-principal mode has NO auth routes (the
     pinned AA-1 fact) ⇒ 404. */
  const session = await api("/v1/auth/session");
  if (session.status === 404) {
    state.profile = "demo";
  } else {
    state.profile = "durable";
    if (session.ok) state.email = session.body.email;
  }
  $("demo-banner").hidden = state.profile !== "demo";
  $("durable-banner").hidden = state.profile !== "durable";
  if (state.profile === "demo") {
    enterMain("demo principal");
  } else {
    $("auth-view").hidden = false;
  }
  refreshHealth();
}

async function refreshHealth() {
  const health = await api("/healthz");
  const value = health.ok && health.body ? health.body.status : "unreachable";
  const dot = $("health-dot");
  const cls = STATUS_CLASSES[value];
  dot.className = cls === undefined ? "badge unknown" : `badge ${cls}`;
  dot.textContent = `health: ${value}`;
}

function enterMain(who) {
  $("auth-view").hidden = true;
  $("main-view").hidden = false;
  $("who").textContent = who;
  $("logout-button").hidden = state.profile !== "durable" || !state.token;
}

/* --- auth ---------------------------------------------------------------------- */

function wireAuth() {
  $("tab-login").addEventListener("click", () => {
    $("tab-login").classList.add("active");
    $("tab-register").classList.remove("active");
    $("login-form").hidden = false;
    $("register-form").hidden = true;
  });
  $("tab-register").addEventListener("click", () => {
    $("tab-register").classList.add("active");
    $("tab-login").classList.remove("active");
    $("register-form").hidden = false;
    $("login-form").hidden = true;
  });

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError($("login-error"));
    const result = await api("/v1/auth/login", {
      method: "POST",
      body: { email: $("login-email").value, password: $("login-password").value },
    });
    if (!result.ok) return renderError($("login-error"), result.body);
    state.token = result.body.token;
    const session = await api("/v1/auth/session");
    state.email = session.ok ? session.body.email : $("login-email").value;
    enterMain(state.email);
  });

  $("register-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError($("register-error"));
    const info = $("register-info");
    info.hidden = true;
    const result = await api("/v1/auth/register", {
      method: "POST",
      body: {
        email: $("register-email").value,
        password: $("register-password").value,
      },
    });
    if (!result.ok) return renderError($("register-error"), result.body);
    /* HONEST message: the token is on the SERVER CONSOLE, not in email. */
    info.hidden = false;
    info.textContent =
      `Account created (status: ${result.body.status}). Copy the ` +
      "verification token from the server console and paste it below.";
  });

  $("verify-button").addEventListener("click", async () => {
    clearError($("register-error"));
    const info = $("register-info");
    const result = await api("/v1/auth/verify", {
      method: "POST",
      body: { token: $("verify-token").value.trim() },
    });
    if (!result.ok) return renderError($("register-error"), result.body);
    info.hidden = false;
    info.textContent = `Email verified (${result.body.email}). Sign in now.`;
    $("tab-login").click();
  });

  $("logout-button").addEventListener("click", async () => {
    await api("/v1/auth/logout", { method: "POST" });
    state.token = null;
    state.email = null;
    $("main-view").hidden = true;
    $("auth-view").hidden = false;
  });
}

/* --- ask ------------------------------------------------------------------------ */

function renderResult(status, id, content) {
  $("ask-result-status").replaceChildren(statusBadge(status));
  $("ask-result-id").textContent = id || "";
  $("ask-result-content").textContent = content;
  $("ask-result").hidden = false;
}

function appendProgress(text) {
  const log = $("ask-progress");
  log.hidden = false;
  const line = document.createElement("div");
  line.textContent = text;
  log.appendChild(line);
}

async function followEvents(executionId) {
  /* REAL SSE frames (10 §11 shapes) rendered as received — no theater. */
  const headers = state.token
    ? { Authorization: `Bearer ${state.token}` }
    : {};
  const response = await fetch(`/v1/executions/${executionId}/events`, { headers });
  if (!response.ok || response.body === null) {
    appendProgress("event stream unavailable — falling back to final poll");
    return finishFromStatus(executionId);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index;
    while ((index = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      if (!frame.startsWith("data: ")) continue;
      const event = JSON.parse(frame.slice(6));
      appendProgress(`${event.type}${event.node ? `: ${event.node}` : ""}`);
      if (event.type === "final") {
        renderResult("succeeded", executionId,
          JSON.stringify(event.result, null, 2));
      } else if (event.type === "error") {
        renderResult("failed", executionId,
          JSON.stringify(event.error, null, 2));
      }
    }
  }
}

async function finishFromStatus(executionId) {
  const result = await api(`/v1/executions/${executionId}`);
  if (!result.ok) return renderError($("ask-error"), result.body);
  const body = result.body;
  renderResult(body.status, executionId,
    JSON.stringify(body.result ?? body.error ?? body.progress, null, 2));
}

function wireAsk() {
  $("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError($("ask-error"));
    $("ask-result").hidden = true;
    $("ask-progress").hidden = true;
    $("ask-progress").replaceChildren();
    $("ask-submit").disabled = true;
    try {
      const isAsync = $("ask-async").checked;
      const body = { ask: $("ask-input").value };
      if (isAsync) body.execution_policy = { async: true };
      const result = await api("/v1/execute", { method: "POST", body });
      if (!result.ok) return renderError($("ask-error"), result.body);
      if (result.status === 202) {
        appendProgress(`accepted: ${result.body.execution_id} (queued)`);
        await followEvents(result.body.execution_id);
      } else {
        /* Sync 200: render the labeled content VERBATIM (a local-echo
           label must stay visible — 41 §49). */
        renderResult(result.body.status, result.body.execution_id,
          result.body.result
            ? result.body.result.content
            : JSON.stringify(result.body, null, 2));
      }
    } finally {
      $("ask-submit").disabled = false;
    }
  });
}

/* --- executions ------------------------------------------------------------------ */

async function refreshExecutions() {
  clearError($("executions-error"));
  const result = await api("/v1/executions");
  if (!result.ok) return renderError($("executions-error"), result.body);
  const rows = $("executions-rows");
  rows.replaceChildren();
  for (const row of result.body.executions) {
    const tr = document.createElement("tr");
    const id = document.createElement("td");
    id.className = "mono";
    id.textContent = `${row.execution_id.slice(0, 8)}…`;
    const status = document.createElement("td");
    status.appendChild(statusBadge(row.status));
    const created = document.createElement("td");
    created.textContent = row.created_at;
    const open = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open";
    button.addEventListener("click", () => openExecution(row.execution_id));
    open.appendChild(button);
    tr.append(id, status, created, open);
    rows.appendChild(tr);
  }
}

async function openExecution(executionId) {
  const result = await api(`/v1/executions/${executionId}`);
  if (!result.ok) return renderError($("executions-error"), result.body);
  $("execution-detail-status").replaceChildren(statusBadge(result.body.status));
  $("execution-detail-id").textContent = executionId;
  $("execution-detail-body").textContent = JSON.stringify(result.body, null, 2);
  $("execution-detail").hidden = false;
}

/* --- models / usage ---------------------------------------------------------------- */

async function refreshModels() {
  clearError($("models-error"));
  const result = await api("/v1/models");
  if (!result.ok) return renderError($("models-error"), result.body);
  const rows = $("models-rows");
  rows.replaceChildren();
  for (const model of result.body.models) {
    const tr = document.createElement("tr");
    const name = document.createElement("td");
    name.textContent = model.name;
    const tier = document.createElement("td");
    tier.textContent = model.tier;
    const caps = document.createElement("td");
    caps.textContent = model.capabilities.join(", ");
    const availability = document.createElement("td");
    availability.appendChild(statusBadge(model.availability));
    tr.append(name, tier, caps, availability);
    rows.appendChild(tr);
  }
}

async function refreshUsage() {
  clearError($("usage-error"));
  const result = await api("/v1/usage");
  if (!result.ok) return renderError($("usage-error"), result.body);
  $("usage-body").textContent = JSON.stringify(result.body, null, 2);
  $("usage-card").hidden = false;
}

/* --- navigation ---------------------------------------------------------------------- */

function wireNav() {
  for (const item of document.querySelectorAll(".rail-item")) {
    item.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".rail-item")) {
        other.classList.toggle("active", other === item);
      }
      const surface = item.dataset.surface;
      for (const section of document.querySelectorAll(".surface")) {
        section.hidden = section.id !== `surface-${surface}`;
      }
      if (surface === "executions") refreshExecutions();
      if (surface === "models") refreshModels();
      if (surface === "usage") refreshUsage();
    });
  }
  $("executions-refresh").addEventListener("click", refreshExecutions);
  $("models-refresh").addEventListener("click", refreshModels);
  $("usage-refresh").addEventListener("click", refreshUsage);
}

/* --- boot ------------------------------------------------------------------------------ */

wireAuth();
wireAsk();
wireNav();
probeProfile();
