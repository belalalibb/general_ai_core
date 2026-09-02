/* Substrate — end-user workspace shell (UI/UX directive; P-D.2 posture kept).
 *
 * HONESTY CONTRACTS enforced in this file (non-negotiable):
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
 * - Async activity is the REAL /events SSE stream (10 §11 shapes) —
 *   frames render as received; no invented progress, no percentages.
 * - Runs are EXECUTIONS: no fake chat-thread persistence (§13).
 * - Denials and refusals render the unified error VERBATIM.
 * - No setInterval polling theater: lists refresh on explicit action.
 */
"use strict";

const state = {
  token: null,
  profile: null,
  email: null,
  view: "home",
  workspaces: [],           // as the API reported them — never synthesized
  projects: [],             // flat list (all projects for the tenant)
  selectedWorkspace: null,  // workspace_id or null
};

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

/* --- transport --------------------------------------------------------------- */

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

/* --- profile probe ------------------------------------------------------------ */

async function probeProfile() {
  /* Durable profile: /v1/auth/session answers 401 without a token.
     Demo profile: either NO auth routes (404, fixed-principal mode) or the
     R160 hybrid answer 200 {mode:"demo"} — the server SAYS it is demo. */
  const session = await api("/v1/auth/session");
  if (session.status === 404 || (session.ok && session.body && session.body.mode === "demo")) {
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
  refreshWorkspaces();
}

/* --- auth ----------------------------------------------------------------------- */

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

/* --- view router ------------------------------------------------------------------ */

const VIEWS = ["home", "runs", "models", "usage"];

function showView(view) {
  state.view = view;
  for (const name of VIEWS) $(`view-${name}`).hidden = name !== view;
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", item.dataset.view === view);
  }
  $("side-nav").classList.remove("open");
  if (view === "runs") refreshRuns();
  if (view === "models") refreshModels();
  if (view === "usage") refreshUsage();
}

function wireNav() {
  for (const item of document.querySelectorAll(".nav-item")) {
    item.addEventListener("click", () => showView(item.dataset.view));
  }
  $("nav-toggle").addEventListener("click", () => {
    $("side-nav").classList.toggle("open");
  });
  $("runs-refresh").addEventListener("click", refreshRuns);
  $("models-refresh").addEventListener("click", refreshModels);
  $("usage-refresh").addEventListener("click", refreshUsage);
}

/* --- modal (promise-based, single instance) ---------------------------------------- */

let modalResolve = null;

function openModal({ title, bodyBuilder, okLabel = "OK", danger = false }) {
  return new Promise((resolve) => {
    modalResolve = resolve;
    $("modal-title").textContent = title;
    const body = $("modal-body");
    body.replaceChildren();
    if (bodyBuilder) bodyBuilder(body);
    clearError($("modal-error"));
    const ok = $("modal-ok");
    ok.textContent = okLabel;
    ok.className = danger ? "btn-danger" : "btn-primary";
    $("modal").hidden = false;
    const input = body.querySelector("input");
    if (input) input.focus();
  });
}

function closeModal(value) {
  $("modal").hidden = true;
  if (modalResolve) {
    modalResolve(value);
    modalResolve = null;
  }
}

function wireModal() {
  $("modal-cancel").addEventListener("click", () => closeModal(null));
  $("modal-ok").addEventListener("click", () => {
    const input = $("modal-body").querySelector("input");
    closeModal(input ? input.value : true);
  });
  $("modal").addEventListener("click", (event) => {
    if (event.target === $("modal")) closeModal(null);
  });
  $("modal-body").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      $("modal-ok").click();
    }
  });
}

function promptModal(title, placeholder, okLabel) {
  return openModal({
    title,
    okLabel,
    bodyBuilder: (body) => {
      const label = document.createElement("label");
      const input = document.createElement("input");
      input.type = "text";
      input.placeholder = placeholder;
      input.autocomplete = "off";
      label.appendChild(input);
      body.appendChild(label);
    },
  });
}

function confirmModal(title, message, okLabel) {
  return openModal({
    title,
    okLabel,
    danger: true,
    bodyBuilder: (body) => {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = message;
      body.appendChild(p);
    },
  });
}

/* --- workspaces & projects (GAP-1 API — real state only) ---------------------------- */

async function refreshWorkspaces() {
  clearError($("ws-tree-error"));
  const [wsResult, prjResult] = await Promise.all([
    api("/v1/workspaces"),
    api("/v1/projects"),
  ]);
  if (!wsResult.ok) return renderError($("ws-tree-error"), wsResult.body);
  if (!prjResult.ok) return renderError($("ws-tree-error"), prjResult.body);
  state.workspaces = wsResult.body.workspaces;
  state.projects = prjResult.body.projects;
  renderWorkspaceTree();
  renderProjectSelect();
  if (state.selectedWorkspace !== null) {
    const still = state.workspaces.some(
      (w) => w.workspace_id === state.selectedWorkspace
    );
    if (!still) state.selectedWorkspace = null;
  }
  renderWorkspaceDetail();
}

function renderWorkspaceTree() {
  const tree = $("ws-tree");
  tree.replaceChildren();
  if (state.workspaces.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small ws-empty";
    empty.textContent = "no workspaces yet";
    tree.appendChild(empty);
    return;
  }
  for (const ws of state.workspaces) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "ws-node";
    node.classList.toggle("active", ws.workspace_id === state.selectedWorkspace);
    const glyph = document.createElement("span");
    glyph.className = "ws-glyph";
    glyph.textContent = "▣";
    const name = document.createElement("span");
    name.className = "ws-name";
    name.textContent = ws.name;
    const count = state.projects.filter(
      (p) => p.workspace_id === ws.workspace_id
    ).length;
    const meta = document.createElement("span");
    meta.className = "ws-count muted";
    meta.textContent = String(count);
    node.append(glyph, name, meta);
    node.addEventListener("click", () => selectWorkspace(ws.workspace_id));
    tree.appendChild(node);
  }
}

function selectWorkspace(workspaceId) {
  state.selectedWorkspace =
    state.selectedWorkspace === workspaceId ? null : workspaceId;
  renderWorkspaceTree();
  renderWorkspaceDetail();
  showView("home");
}

function renderWorkspaceDetail() {
  const ws = state.workspaces.find(
    (w) => w.workspace_id === state.selectedWorkspace
  );
  const chip = $("home-context");
  if (!ws) {
    $("ws-detail").hidden = true;
    chip.textContent = "no workspace selected";
    chip.classList.add("muted");
    return;
  }
  chip.textContent = `workspace: ${ws.name}`;
  chip.classList.remove("muted");
  $("ws-detail").hidden = false;
  $("ws-detail-name").textContent = ws.name;
  $("ws-detail-id").textContent = ws.workspace_id;
  clearError($("ws-detail-error"));
  const list = $("prj-list");
  list.replaceChildren();
  const linked = state.projects.filter(
    (p) => p.workspace_id === ws.workspace_id
  );
  if (linked.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small";
    empty.textContent = "no projects in this workspace";
    list.appendChild(empty);
  }
  for (const prj of linked) {
    const row = document.createElement("div");
    row.className = "prj-row";
    const name = document.createElement("span");
    name.className = "prj-name";
    name.textContent = prj.name;
    const id = document.createElement("span");
    id.className = "mono muted small";
    id.textContent = `${prj.project_id.slice(0, 8)}…`;
    const use = document.createElement("button");
    use.type = "button";
    use.className = "btn-ghost small";
    use.textContent = "Use in composer";
    use.addEventListener("click", () => {
      $("ask-project").value = prj.project_id;
      $("ask-input").focus();
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "btn-danger small";
    del.textContent = "Delete";
    del.addEventListener("click", () => deleteProject(prj));
    row.append(name, id, use, del);
    list.appendChild(row);
  }
}

function renderProjectSelect() {
  const select = $("ask-project");
  const current = select.value;
  select.replaceChildren();
  const none = document.createElement("option");
  none.value = "";
  none.textContent = "— none —";
  select.appendChild(none);
  for (const prj of state.projects) {
    const ws = state.workspaces.find(
      (w) => w.workspace_id === prj.workspace_id
    );
    const option = document.createElement("option");
    option.value = prj.project_id;
    option.textContent = ws ? `${ws.name} / ${prj.name}` : prj.name;
    select.appendChild(option);
  }
  if ([...select.options].some((o) => o.value === current)) {
    select.value = current;
  }
}

async function createWorkspace() {
  const name = await promptModal("New workspace", "Workspace name", "Create");
  if (!name || !name.trim()) return;
  const result = await api("/v1/workspaces", {
    method: "POST",
    body: { name: name.trim() },
  });
  if (!result.ok) return renderError($("ws-tree-error"), result.body);
  state.selectedWorkspace = result.body.workspace_id;
  await refreshWorkspaces();
  showView("home");
}

async function deleteWorkspace() {
  const ws = state.workspaces.find(
    (w) => w.workspace_id === state.selectedWorkspace
  );
  if (!ws) return;
  const confirmed = await confirmModal(
    "Delete workspace",
    `Delete "${ws.name}"? A workspace that still has projects will be ` +
      "refused by the platform (shown verbatim below).",
    "Delete"
  );
  if (!confirmed) return;
  const response = await fetch(`/v1/workspaces/${ws.workspace_id}`, {
    method: "DELETE",
    headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
  });
  if (response.status !== 204) {
    /* 409 workspace_not_empty renders verbatim — the RESTRICT contract
       is surfaced, never silently cascaded. */
    const body = await response.json().catch(() => null);
    return renderError($("ws-detail-error"), body);
  }
  state.selectedWorkspace = null;
  await refreshWorkspaces();
}

async function createProject() {
  const ws = state.workspaces.find(
    (w) => w.workspace_id === state.selectedWorkspace
  );
  if (!ws) return;
  const name = await promptModal(
    `New project in "${ws.name}"`,
    "Project name",
    "Create"
  );
  if (!name || !name.trim()) return;
  const result = await api("/v1/projects", {
    method: "POST",
    body: { name: name.trim(), workspace_id: ws.workspace_id },
  });
  if (!result.ok) return renderError($("ws-detail-error"), result.body);
  await refreshWorkspaces();
}

async function deleteProject(prj) {
  const confirmed = await confirmModal(
    "Delete project",
    `Delete "${prj.name}"? This removes the project record.`,
    "Delete"
  );
  if (!confirmed) return;
  const response = await fetch(`/v1/projects/${prj.project_id}`, {
    method: "DELETE",
    headers: state.token ? { Authorization: `Bearer ${state.token}` } : {},
  });
  if (response.status !== 204) {
    const body = await response.json().catch(() => null);
    return renderError($("ws-detail-error"), body);
  }
  await refreshWorkspaces();
}

function wireWorkspaces() {
  $("ws-new-btn").addEventListener("click", createWorkspace);
  $("ws-delete-btn").addEventListener("click", deleteWorkspace);
  $("prj-new-btn").addEventListener("click", createProject);
}

/* --- composer: idea → context → run ------------------------------------------------- */

function renderResult(status, id, content) {
  $("ask-result-status").replaceChildren(statusBadge(status));
  $("ask-result-id").textContent = id || "";
  $("ask-result-content").textContent = content;
  $("ask-result").hidden = false;
}

function timelineEntry(text, kind) {
  /* One <li> per REAL received frame — the timeline IS the event log. */
  const li = document.createElement("li");
  li.textContent = text;
  if (kind) li.className = kind;
  $("run-timeline").appendChild(li);
}

async function followEvents(executionId) {
  /* REAL SSE frames (10 §11 shapes) rendered as received — no theater. */
  const headers = state.token
    ? { Authorization: `Bearer ${state.token}` }
    : {};
  const response = await fetch(`/v1/executions/${executionId}/events`, { headers });
  if (!response.ok || response.body === null) {
    timelineEntry("event stream unavailable — falling back to final poll");
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
      if (event.type === "final") {
        timelineEntry("final", "evt-final");
        renderResult("succeeded", executionId,
          JSON.stringify(event.result, null, 2));
      } else if (event.type === "error") {
        timelineEntry("error", "evt-error");
        renderResult("failed", executionId,
          JSON.stringify(event.error, null, 2));
      } else {
        timelineEntry(`${event.type}${event.node ? `: ${event.node}` : ""}`);
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

async function submitAsk() {
  clearError($("ask-error"));
  $("ask-result").hidden = true;
  $("run-live").hidden = true;
  $("run-timeline").replaceChildren();
  $("ask-submit").disabled = true;
  try {
    const isAsync = $("ask-async").checked;
    const body = { ask: $("ask-input").value };
    const projectId = $("ask-project").value;
    if (projectId) body.project_id = projectId;
    if (isAsync) body.execution_policy = { async: true };
    const result = await api("/v1/execute", { method: "POST", body });
    if (!result.ok) return renderError($("ask-error"), result.body);
    if (result.status === 202) {
      $("run-live").hidden = false;
      $("run-live-id").textContent = result.body.execution_id;
      timelineEntry(`accepted: ${result.body.execution_id} (queued)`);
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
}

function wireAsk() {
  $("ask-submit").addEventListener("click", submitAsk);
  $("ask-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submitAsk();
    }
  });
  $("result-to-runs").addEventListener("click", () => {
    const id = $("ask-result-id").textContent;
    showView("runs");
    if (id) openRun(id);
  });
}

/* --- runs (executions — listed as the API reports them) ------------------------------ */

async function refreshRuns() {
  clearError($("runs-error"));
  const result = await api("/v1/executions");
  if (!result.ok) return renderError($("runs-error"), result.body);
  const list = $("runs-list");
  list.replaceChildren();
  if (result.body.executions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small";
    empty.textContent = "no executions recorded";
    list.appendChild(empty);
  }
  for (const row of result.body.executions) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "run-row";
    const id = document.createElement("span");
    id.className = "mono";
    id.textContent = `${row.execution_id.slice(0, 8)}…`;
    const created = document.createElement("span");
    created.className = "muted small";
    created.textContent = row.created_at;
    item.append(id, statusBadge(row.status), created);
    item.addEventListener("click", () => openRun(row.execution_id));
    list.appendChild(item);
  }
}

async function openRun(executionId) {
  const result = await api(`/v1/executions/${executionId}`);
  if (!result.ok) return renderError($("runs-error"), result.body);
  $("run-detail-status").replaceChildren(statusBadge(result.body.status));
  $("run-detail-id").textContent = executionId;
  $("run-detail-body").textContent = JSON.stringify(result.body, null, 2);
  $("run-detail").hidden = false;
}

/* --- models (real catalog rows only) -------------------------------------------------- */

async function refreshModels() {
  clearError($("models-error"));
  const result = await api("/v1/models");
  if (!result.ok) return renderError($("models-error"), result.body);
  const grid = $("models-grid");
  grid.replaceChildren();
  if (result.body.models.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small";
    empty.textContent = "no models in the catalog";
    grid.appendChild(empty);
  }
  for (const model of result.body.models) {
    const card = document.createElement("div");
    card.className = "model-card";
    const head = document.createElement("div");
    head.className = "model-head";
    const name = document.createElement("strong");
    name.textContent = model.name;
    head.append(name, statusBadge(model.availability));
    const tier = document.createElement("div");
    tier.className = "muted small";
    tier.textContent = `tier: ${model.tier}`;
    const caps = document.createElement("div");
    caps.className = "model-caps";
    for (const capability of model.capabilities) {
      const chip = document.createElement("span");
      chip.className = "cap-chip";
      chip.textContent = capability;
      caps.appendChild(chip);
    }
    card.append(head, tier, caps);
    grid.appendChild(card);
  }
}

/* --- usage (real numbers only — rendered as reported) ---------------------------------- */

async function refreshUsage() {
  clearError($("usage-error"));
  const result = await api("/v1/usage");
  if (!result.ok) return renderError($("usage-error"), result.body);
  const bodyEl = $("usage-body");
  bodyEl.replaceChildren();
  /* Generic honest rendering: every field the API reported, verbatim —
     nothing summarized into invented gauges. */
  const pre = document.createElement("pre");
  pre.className = "result-body";
  pre.textContent = JSON.stringify(result.body, null, 2);
  bodyEl.appendChild(pre);
}

/* --- command palette (search / command discovery — §14) --------------------------------- */

function cmdkCommands() {
  const commands = [
    { label: "Go to Home", hint: "view", run: () => showView("home") },
    { label: "Go to Runs", hint: "view", run: () => showView("runs") },
    { label: "Go to Models", hint: "view", run: () => showView("models") },
    { label: "Go to Usage", hint: "view", run: () => showView("usage") },
    { label: "New workspace", hint: "action", run: createWorkspace },
    { label: "Refresh workspaces", hint: "action", run: refreshWorkspaces },
    { label: "Refresh health", hint: "action", run: refreshHealth },
  ];
  for (const ws of state.workspaces) {
    commands.push({
      label: `Open workspace: ${ws.name}`,
      hint: "workspace",
      run: () => {
        state.selectedWorkspace = ws.workspace_id;
        renderWorkspaceTree();
        renderWorkspaceDetail();
        showView("home");
      },
    });
  }
  return commands;
}

function openCmdk() {
  $("cmdk").hidden = false;
  $("cmdk-input").value = "";
  renderCmdkResults("");
  $("cmdk-input").focus();
}

function closeCmdk() {
  $("cmdk").hidden = true;
}

function renderCmdkResults(query) {
  const results = $("cmdk-results");
  results.replaceChildren();
  const q = query.trim().toLowerCase();
  const matches = cmdkCommands().filter(
    (c) => q === "" || c.label.toLowerCase().includes(q)
  );
  if (matches.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted small cmdk-empty";
    empty.textContent = "no matching command";
    results.appendChild(empty);
  }
  matches.forEach((command, position) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "cmdk-item";
    if (position === 0) item.classList.add("focused");
    const label = document.createElement("span");
    label.textContent = command.label;
    const hint = document.createElement("span");
    hint.className = "muted small";
    hint.textContent = command.hint;
    item.append(label, hint);
    item.addEventListener("click", () => {
      closeCmdk();
      command.run();
    });
    results.appendChild(item);
  });
}

function wireCmdk() {
  $("cmdk-open").addEventListener("click", openCmdk);
  $("cmdk-input").addEventListener("input", (event) => {
    renderCmdkResults(event.target.value);
  });
  $("cmdk-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const focused = $("cmdk-results").querySelector(".cmdk-item.focused")
        || $("cmdk-results").querySelector(".cmdk-item");
      if (focused) focused.click();
    }
  });
  $("cmdk").addEventListener("click", (event) => {
    if (event.target === $("cmdk")) closeCmdk();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      if ($("cmdk").hidden) openCmdk();
      else closeCmdk();
    }
    if (event.key === "Escape") {
      if (!$("cmdk").hidden) closeCmdk();
      if (!$("modal").hidden) closeModal(null);
    }
  });
}

/* --- boot -------------------------------------------------------------------------------- */

wireAuth();
wireNav();
wireModal();
wireWorkspaces();
wireAsk();
wireCmdk();
probeProfile();
