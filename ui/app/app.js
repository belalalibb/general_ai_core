/* QEVION · Workbench — end-user workspace shell (UI/UX directive; P-D.2 posture kept).
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
 * - Verification tokens appear in the register response ONLY on the
 *   in-memory/dev profile, where the server labels them
 *   (verification: "dev_token" + dev_note); the UI repeats that label and
 *   never pretends an email was sent. Durable profile: server console.
 * - Session custody (C-05, operator D-2): the server sets an HttpOnly
 *   cookie on login; this file NEVER stores the bearer token (no
 *   sessionStorage/localStorage token). State changes send the
 *   X-Requested-With: QEVION header (CSRF rule for cookie sessions).
 * - Async activity is the REAL /events SSE stream (10 §11 shapes) —
 *   frames render as received; no invented progress, no percentages.
 * - Runs are EXECUTIONS: no fake chat-thread persistence (§13).
 * - Denials and refusals render the unified error VERBATIM.
 * - No setInterval polling theater: lists refresh on explicit action.
 */
"use strict";

const state = {
  token: null,             /* kept null on purpose: the HttpOnly cookie IS the session (C-05) */
  profile: null,
  email: null,
  view: "home",
  workspaces: [],           // as the API reported them — never synthesized
  projects: [],             // flat list (all projects for the tenant)
  selectedWorkspace: null,  // workspace_id or null
  templateDetail: null,     // R202: the served StrategyTemplate for the chosen ref, or null
  isAdmin: false,           // served fact from /v1/auth/session (C-07 orientation, C-11 links)
  agentTools: null,         // C-11: served /v1/agent-tools rows or null when the seam is absent
  runsFilterProject: "",    // C-04: client-side filter over the served context.project_id
  lastRun: null,            // C-03: the last served execution body (for the raw toggle)
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
  const headers = Object.assign({}, csrfHeaders(), options.headers || {});
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const response = await fetch(path, {
    method: options.method || "GET",
    headers,
    credentials: "same-origin",
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  const body = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, body };
}

/* C-05: the CSRF header every request carries (a cross-site form cannot set it). */
function csrfHeaders() {
  return { "X-Requested-With": "QEVION" };
}

/* C-09: one-line NEXT STEP per unified error code — the code is the server's; the hint
   is the product's. Unknown codes get no hint (never invented). */
const ERROR_HINTS = {
  unauthenticated: "Sign in again — your session is missing or expired.",
  unauthorized: "This action needs a permission your account does not have (admin surfaces need an admin session).",
  validation_error: "Check the highlighted input; the server refused the request shape or a reference it could not find in your tenant.",
  entitlement_exceeded: "Your task-unit budget or plan refused this run. Check Usage, or ask your operator for a larger plan.",
  capability_denied: "The Capability Firewall refused a tool call — the run cannot use that capability on this deployment.",
  provider_unavailable: "The model provider is unavailable right now. Retry later or pick another model in the composer.",
  model_unavailable: "No eligible model could serve this request. Check Models for runtime availability.",
  tool_approval_required: "A tool step is waiting for approval — an admin must approve it before the run continues.",
  rate_limited: "Too many requests — wait for the window to pass and retry.",
  execution_failed: "The run stopped. Open it in Runs to read the failing stage and provider category.",
  internal_error: "Something failed inside the platform. Retry; if it persists report the execution id shown.",
};

function renderError(el, payload) {
  /* Denials are content — render the unified error verbatim, then (C-09) ONE actionable
     next step derived from the served code. Nothing about the error itself is rewritten. */
  el.hidden = false;
  el.replaceChildren();
  const detail = payload && payload.error
    ? `${payload.error.code}: ${payload.error.message}`
    : "request failed";
  const line = document.createElement("div");
  line.textContent = detail;
  el.appendChild(line);
  const err = payload && payload.error ? payload.error : null;
  if (err && err.details && err.details.execution_id) {
    const ref = document.createElement("div");
    ref.className = "mono small";
    ref.textContent = `execution ${err.details.execution_id}`;
    el.appendChild(ref);
  }
  if (err && err.details && err.details.stage) {
    const st = document.createElement("div");
    st.className = "small";
    st.textContent = `failing stage: ${err.details.stage}`;
    el.appendChild(st);
  }
  const hint = err ? ERROR_HINTS[err.code] : undefined;
  if (hint) {
    const next = document.createElement("div");
    next.className = "error-hint";
    next.textContent = `Next: ${hint}`;
    el.appendChild(next);
  }
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
    if (session.ok) {
      state.email = session.body.email;
      state.isAdmin = session.body.is_admin === true;
    }
  }
  $("demo-banner").hidden = state.profile !== "demo";
  $("durable-banner").hidden = state.profile !== "durable";
  if (state.profile === "demo") {
    enterMain("demo principal");
  } else if (session.ok && state.email) {
    /* C-05: the HttpOnly session cookie is still valid — reload / navigation keeps the
       session; no re-login is forced. */
    enterMain(state.email);
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

async function enterMain(who) {
  $("auth-view").hidden = true;
  $("main-view").hidden = false;
  $("who").textContent = who;
  $("logout-button").hidden = state.profile !== "durable";
  renderOrientation();
  /* R201-C: the served lists must exist BEFORE a stored selection may be re-applied — a
     selection is restored only when the server still offers it. */
  await refreshWorkspaces();
  await populateTemplateSelect();
  await probeAgentTools();
  restoreContext();
  applyDeepLink();
  renderFirstRun();
}

/* R200-B (operator D3 = i): boot-once deep link. Command links here as /app/#view=<name>.
   Read ONCE when the main view opens; no hashchange listener, no timer, no request.
   Unknown names are ignored — no view is invented.
   R201-B (operator D1 = a, D3 = i): an optional "&execution=<uuid>" is carried ONLY into the
   EXISTING openRun() on the runs view. The regex stays anchored, so a malformed id makes the
   whole hash unmatched (ignored, like an unknown view). Ownership is the server's call: a
   foreign or unknown id yields its own 404/422, rendered verbatim in the runs error box. */
function applyDeepLink() {
  const match =
    /^#view=([a-z]+)(?:&execution=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}))?$/
      .exec(location.hash || "");
  if (!match) return;
  const view = match[1];
  if (!VIEWS.includes(view)) return;
  showView(view);
  if (match[2] && view === "runs") openRun(match[2]);
}

/* --- R201-C (operator D2 = i): tab-scoped, NON-SECRET selection memory ------------------
   Key holds {view, selectedWorkspace, project, template} — never the token; tab-scoped
   storage only, never a persistent store (R187 rule). Written when the selection changes; read once in enterMain after
   the served lists resolved; applied only when the server still offers the value; an explicit
   hash (#view=…) wins over the stored view; forgotten on logout. */
const CONTEXT_KEY = "qevion.app.context";

function saveContext() {
  const snapshot = {
    view: state.view,
    selectedWorkspace: state.selectedWorkspace,
    project: $("ask-project").value || null,
    template: $("ask-template").value || null,
  };
  try {
    sessionStorage.setItem(CONTEXT_KEY, JSON.stringify(snapshot));
  } catch (_error) {
    /* storage unavailable: nothing is remembered, nothing breaks */
  }
}

function clearContext() {
  try {
    sessionStorage.removeItem(CONTEXT_KEY);
  } catch (_error) {
    /* storage unavailable */
  }
}

function restoreContext() {
  let stored = null;
  try {
    stored = JSON.parse(sessionStorage.getItem(CONTEXT_KEY) || "null");
  } catch (_error) {
    stored = null;
  }
  if (!stored || typeof stored !== "object") return;
  if (
    typeof stored.selectedWorkspace === "string" &&
    state.workspaces.some((w) => w.workspace_id === stored.selectedWorkspace)
  ) {
    state.selectedWorkspace = stored.selectedWorkspace;
    renderWorkspaceTree();
    renderWorkspaceDetail();
  }
  for (const [field, value] of [["ask-project", stored.project], ["ask-template", stored.template]]) {
    const select = $(field);
    if (typeof value === "string" && [...select.options].some((o) => o.value === value)) {
      select.value = value;
      if (field === "ask-template") loadTemplateDetail(value);
    }
  }
  const hashHasView = /^#view=/.test(location.hash || "");
  if (!hashHasView && typeof stored.view === "string" && VIEWS.includes(stored.view)) {
    showView(stored.view);
  }
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
    /* C-05 (D-2): the server set the HttpOnly session cookie; the bearer token in the
       body is NOT kept anywhere in script-reachable state. */
    const session = await api("/v1/auth/session");
    state.email = session.ok ? session.body.email : $("login-email").value;
    state.isAdmin = session.ok && session.body.is_admin === true;
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
    info.hidden = false;
    if (result.body.verification === "dev_token" && result.body.dev_verification_token) {
      /* C-02 (operator D-1 = b): the in-memory/dev profile returns the token, LABELLED by
         the server. The UI pre-fills it and repeats the label — no email was sent. */
      $("verify-token").value = result.body.dev_verification_token;
      info.textContent =
        `Account created (status: ${result.body.status}). Development profile: ` +
        `${result.body.dev_note || "the verification token was returned by the server"} ` +
        "— it has been filled in below; press \u201cVerify email\u201d to continue.";
    } else {
      /* HONEST message: the token is on the SERVER CONSOLE, not in email. */
      info.textContent =
        `Account created (status: ${result.body.status}). Copy the ` +
        "verification token from the server console and paste it below.";
    }
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
    state.isAdmin = false;
    clearContext();
    $("main-view").hidden = true;
    $("auth-view").hidden = false;
  });
}

/* --- view router ------------------------------------------------------------------ */

const VIEWS = ["home", "runs", "models", "usage", "capabilities"];

function showView(view) {
  state.view = view;
  saveContext();
  for (const name of VIEWS) $(`view-${name}`).hidden = name !== view;
  for (const item of document.querySelectorAll(".nav-item")) {
    item.classList.toggle("active", item.dataset.view === view);
  }
  $("side-nav").classList.remove("open");
  if (view === "runs") refreshRuns();
  if (view === "models") refreshModels();
  if (view === "usage") refreshUsage();
  if (view === "capabilities") refreshCapabilities();
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
  $("caps-refresh").addEventListener("click", refreshCapabilities);
  $("runs-filter-project").addEventListener("change", () => {
    state.runsFilterProject = $("runs-filter-project").value;
    refreshRuns();
  });
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

/* --- strategy templates (R197, AD-3 read seam) -------------------------------------- */

async function populateTemplateSelect() {
  /* The ONLY template source is the served templates read model (R196 AD-3:
     ACTIVE SYSTEM templates, ref-ordered by the server) — the one api() call below. Runs once the
     session is established (enterMain), never at module load. Idempotent: a
     re-read replaces the offered set; a refused read leaves NO stale option
     behind and renders the platform's error verbatim — the UI never guesses. */
  const select = $("ask-template");
  clearError($("ask-error"));
  const result = await api("/v1/templates");
  while (select.options.length > 1) select.remove(1);
  if (!result.ok) {
    renderError($("ask-error"), result.body);
    return;
  }
  for (const row of result.body.templates || []) {
    const opt = document.createElement("option");
    opt.value = row.ref;
    opt.textContent = `${row.name} \u00b7 ${row.ref} \u00b7 ${row.stage_count} stage${row.stage_count === 1 ? "" : "s"}`;
    select.appendChild(opt);
  }
}

/* --- R202 (operator D1 = a, D2 = i, D3 = i, D6 = i): the served template detail ------------
   ONE read of the EXISTING detail route per choice — on the picker change and when a stored
   choice is restored; never at module load; the empty choice clears the panel with NO request.
   Everything rendered is a served field of the StrategyTemplate; the model posture is DERIVED
   from the served stage model_policy (null = the Router decides). No selector, no override,
   no second surface — the template IS the App Factory UX. A refused read shows the server's
   own error verbatim. */
async function loadTemplateDetail(ref) {
  const panel = $("template-detail");
  clearError($("template-detail-error"));
  if (!ref) {
    state.templateDetail = null;
    panel.hidden = true;
    return;
  }
  const result = await api(`/v1/templates/${encodeURIComponent(ref)}`);
  if (!result.ok) {
    state.templateDetail = null;
    panel.hidden = false;
    $("template-detail-name").textContent = ref;
    $("template-detail-meta").textContent = "";
    $("template-detail-description").textContent = "";
    $("template-detail-tags").replaceChildren();
    $("template-stages").replaceChildren();
    renderError($("template-detail-error"), result.body);
    return;
  }
  state.templateDetail = result.body;
  renderTemplateDetail(result.body);
}

function stagePolicyText(policy) {
  /* Served model_policy of ONE stage: null means the Router decides (AUTO); a present
     policy is repeated as served (type + its fields), never interpreted. */
  if (!policy) return "auto (Router decides)";
  const parts = [String(policy.type || "policy")];
  for (const key of ["tier", "model_id", "provider_id"]) {
    if (policy[key] !== undefined && policy[key] !== null) parts.push(`${key}=${policy[key]}`);
  }
  return parts.join(" \u00b7 ");
}

function renderTemplateDetail(template) {
  const panel = $("template-detail");
  panel.hidden = false;
  $("template-detail-name").textContent =
    `${template.name} \u00b7 ${template.id}@${template.version} \u00b7 ${template.origin}/${template.status}`;
  $("template-detail-description").textContent = template.description || "";
  const tags = $("template-detail-tags");
  tags.replaceChildren();
  const chips = [
    ...(template.tags || []).map((t) => ["tag", t]),
    ...(template.skills || []).map((t) => ["skill", t]),
    ...(template.required_capabilities || []).map((t) => ["requires", t]),
  ];
  if (chips.length === 0) {
    const none = document.createElement("span");
    none.className = "muted small";
    none.textContent = "no tags, skills or required capabilities declared";
    tags.appendChild(none);
  }
  for (const [kind, text] of chips) {
    const chip = document.createElement("span");
    chip.className = "template-chip";
    chip.textContent = `${kind}: ${text}`;
    tags.appendChild(chip);
  }
  const strategy = template.strategy || {};
  const stages = strategy.stages || [];
  const table = $("template-stages");
  table.replaceChildren();
  const head = document.createElement("tr");
  for (const label of ["#", "stage", "kind", "role", "depends on", "model policy", "instruction"]) {
    const th = document.createElement("th");
    th.textContent = label;
    head.appendChild(th);
  }
  table.appendChild(head);
  stages.forEach((stage, index) => {
    const tr = document.createElement("tr");
    const cells = [
      String(index + 1),
      stage.key,
      stage.kind,
      stage.role || "\u2014",
      (stage.depends_on || []).join(", ") || "\u2014",
      stagePolicyText(stage.model_policy),
      stage.instruction || "\u2014",
    ];
    cells.forEach((text, i) => {
      const td = document.createElement("td");
      td.textContent = text;
      if (i === 1) td.className = "mono";
      if (i === 6) td.className = "template-instruction";
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });
  $("template-detail-meta").textContent =
    `mode ${strategy.mode || "\u2014"} \u00b7 ${stages.length} stage${stages.length === 1 ? "" : "s"} \u00b7 max_parallel ${strategy.max_parallel ?? "\u2014"}`;
}

function stageLabel(nodeKey) {
  /* R202-B (operator D4 = i): label a timeline node with the kind · role of the matching stage
     from the ALREADY-LOADED template detail. No read; unknown keys stay bare. */
  const detail = state.templateDetail;
  const stages = detail && detail.strategy ? detail.strategy.stages || [] : [];
  const stage = stages.find((s) => s.key === nodeKey);
  if (!stage) return nodeKey;
  return `${nodeKey} \u00b7 ${stage.kind}${stage.role ? ` \u00b7 ${stage.role}` : ""}`;
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
  /* C-08: clicking a workspace SELECTS it (idempotent) — it never toggles the detail away.
     Deselection is the explicit "Close" affordance in the detail panel. */
  state.selectedWorkspace = workspaceId;
  renderWorkspaceTree();
  renderWorkspaceDetail();
  showView("home");
  saveContext();
}

function deselectWorkspace() {
  state.selectedWorkspace = null;
  renderWorkspaceTree();
  renderWorkspaceDetail();
  saveContext();
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
      saveContext();
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
    headers: csrfHeaders(),
    credentials: "same-origin",
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
    headers: csrfHeaders(),
    credentials: "same-origin",
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
  $("ws-close-btn").addEventListener("click", deselectWorkspace);
  $("prj-new-btn").addEventListener("click", createProject);
  $("first-run-ws-btn").addEventListener("click", createWorkspace);
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
  const response = await fetch(`/v1/executions/${executionId}/events`, {
    headers: csrfHeaders(),
    credentials: "same-origin",
  });
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
        timelineEntry(`${event.type}${event.node ? `: ${stageLabel(event.node)}` : ""}`);
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
    /* Template mode (R197): the chosen ref is what the executor resolves
       (ExecutionStrategySpec mode="template"); no choice ⇒ body unchanged. */
    const templateRef = $("ask-template").value;
    if (templateRef) body.execution_strategy = { mode: "template", template_id: templateRef };
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
  $("ask-project").addEventListener("change", saveContext);
  $("ask-template").addEventListener("change", () => {
    saveContext();
    loadTemplateDetail($("ask-template").value);
  });
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
  /* R199-D (operator D4): the truth strip repeats what THIS response said — the
     distinct provider keys bound to the served models, the model count and the
     availability counts. No second read, no provider-name branching, no prose
     that the API did not return. Absent providers[] is shown as absent. */
  const truth = $("models-truth");
  truth.replaceChildren();
  const providerKeys = new Set();
  const availabilityCounts = new Map();
  let providersServed = false;
  for (const model of result.body.models) {
    if (Array.isArray(model.providers)) {
      providersServed = true;
      for (const key of model.providers) providerKeys.add(key);
    }
    availabilityCounts.set(model.availability, (availabilityCounts.get(model.availability) || 0) + 1);
  }
  let providersText = "not served";
  if (providersServed) providersText = providerKeys.size ? [...providerKeys].sort().join(", ") : "none bound";
  const truthRows = [
    ["models", String(result.body.models.length)],
    ["providers", providersText],
    ["availability", [...availabilityCounts].map(([k, n]) => `${k} ${n}`).join(" · ") || "—"],
  ];
  for (const [label, value] of truthRows) {
    const cell = document.createElement("span");
    cell.className = "truth-cell";
    const k = document.createElement("span");
    k.className = "truth-k";
    k.textContent = label;
    const v = document.createElement("span");
    v.className = "truth-v mono";
    v.textContent = value;
    cell.append(k, v);
    truth.appendChild(cell);
  }
  truth.hidden = false;
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
    /* R199-D: providers[] as served (R188 C4) — one chip per key, verbatim. */
    const providers = document.createElement("div");
    providers.className = "model-providers";
    const providersLabel = document.createElement("span");
    providersLabel.className = "muted small";
    providersLabel.textContent = "providers:";
    providers.appendChild(providersLabel);
    if (!Array.isArray(model.providers)) {
      const none = document.createElement("span");
      none.className = "muted small";
      none.textContent = "not served";
      providers.appendChild(none);
    } else if (model.providers.length === 0) {
      const none = document.createElement("span");
      none.className = "muted small";
      none.textContent = "none bound";
      providers.appendChild(none);
    } else {
      for (const key of model.providers) {
        const chip = document.createElement("span");
        chip.className = "provider-chip mono";
        chip.textContent = key;
        providers.appendChild(chip);
      }
    }
    card.append(head, tier, providers, caps);
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
