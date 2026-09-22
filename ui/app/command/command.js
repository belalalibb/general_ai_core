/* QEVION Command Center — R182-IMPL M1 "Honest topology" + M2 (execution graph / progress /
   conversation) + R185 experience (execution orbit, evaluation_status, layered Core, dialogs,
   keyboard access, transport indicator).
   ADR-0013 Alternative C: one vanilla ES module. No framework, no build step,
   no runtime dependency, no drawing layer beyond SVG/CSS.

   Contract feeding this file (R182_HANDOFF §7, R185_HANDOFF §1) — every route is an api()
   literal below, validated against the served OpenAPI by tests/ui/test_command_center_*.py
   (raw route-prefix occurrences are capped at 12, down only; this comment spends none):
     healthz                          -> reachability
     auth login / session / logout    -> {token} / {email, tenant_id, is_admin} / 204
     admin system                     -> {profile, scope, identity_mode, provider_keys[], ...}
     admin capabilities               -> {scope, capabilities[]{id,state,evidence}}
     executions (list)                -> {executions[]{execution_id, status, created_at, ...}}
     execute {ask}                    -> {execution_id, status, result, usage}
     agent converse {message}         -> {claims[], tool_calls[], reasoning_execution_ids[],
                                          rounds, stop_reason, verification{...}, reasoning_trace[]}
     executions/{id}                  -> {status, progress{current_stage, percent}}
     executions/{id}/events           -> text/event-stream of the FIVE emitted types
     agent executions/{id}/trace      -> {strategy, stages[]{node_key,status,attempts[]}, ledger, as_recorded}
     admin usage (R184)               -> {usage[]{execution_id, status, created_at, ledger, evaluation_status}}

   Honesty rules enforced by tests/ui/test_command_center_*.py:
     * every node is one served capability record; ids come from `capability.id`;
     * every orbit dot is one served execution row; ids come from `row.execution_id`;
     * NODE_STATES / CORE_STATES / EXECUTION_STATES / STAGE_STATES / STREAM_EVENTS /
       EVALUATION_STATUSES are the closed served sets + a LOUD UNKNOWN — never invented;
     * exactly one fetch( inside api(); no EventSource/WebSocket/XHR/axios;
     * no timers, no randomness, no JS animation loop: motion is CSS bound to data-state;
     * the transport indicator describes THIS browser's request, never the runtime. */

const state = {
  token: null,
  catalog: null,
  selected: null,
  health: null,
  system: null,
  session: null,
  executions: [],
  usageByExecution: new Map(),
  selectedExecution: null,
  pendingRequests: 0,
  dialogOpener: null,
};

/* --- closed vocabularies ------------------------------------------------------ */

/* CapabilityState (apps/api/capabilities.py) — verbatim values — plus UNKNOWN:
   anything else the server ever sends is rendered LOUD, never gray-washed. */
const NODE_STATES = Object.freeze({
  available: { cls: "st-available", label: "available" },
  inert: { cls: "st-inert", label: "inert" },
  unavailable: { cls: "st-unavailable", label: "unavailable" },
  UNKNOWN: { cls: "st-unknown", label: "UNKNOWN" },
});

/* R182_HANDOFF §8 Core vocabulary. */
const CORE_STATES = Object.freeze({
  idle: { cls: "core-idle", label: "idle" },
  running: { cls: "core-running", label: "running" },
  waiting_approval: { cls: "core-waiting", label: "waiting_approval" },
  failed: { cls: "core-failed", label: "failed" },
  unreachable: { cls: "core-unreachable", label: "unreachable" },
});

/* apps/api/streaming.py `SseEvent` — the FIVE types that ride the wire. `delta`
   exists in the contract but is never emitted (execute.token_streaming is
   unavailable): it is not here, and no code path renders partial text. */
const STREAM_EVENTS = Object.freeze({
  execution_started: { cls: "ev-started", label: "execution_started" },
  node_started: { cls: "ev-node", label: "node_started" },
  node_completed: { cls: "ev-node", label: "node_completed" },
  final: { cls: "ev-final", label: "final" },
  error: { cls: "ev-error", label: "error" },
});

/* core/contracts/execution.py ExecutionNodeStatus — verbatim — plus UNKNOWN. */
const STAGE_STATES = Object.freeze({
  pending: { cls: "st-pending", label: "pending" },
  running: { cls: "st-running", label: "running" },
  succeeded: { cls: "st-available", label: "succeeded" },
  failed: { cls: "st-unavailable", label: "failed" },
  skipped: { cls: "st-inert", label: "skipped" },
  cancelled: { cls: "st-unavailable", label: "cancelled" },
  UNKNOWN: { cls: "st-unknown", label: "UNKNOWN" },
});

/* core/contracts/execute.py ExecutionStatus — verbatim — plus UNKNOWN. */
const EXECUTION_STATES = Object.freeze({
  queued: { cls: "st-pending", label: "queued" },
  running: { cls: "st-running", label: "running" },
  waiting_approval: { cls: "st-inert", label: "waiting_approval" },
  succeeded: { cls: "st-available", label: "succeeded" },
  failed: { cls: "st-unavailable", label: "failed" },
  cancelled: { cls: "st-unavailable", label: "cancelled" },
  UNKNOWN: { cls: "st-unknown", label: "UNKNOWN" },
});

/* core/contracts/evaluation.py EvaluationStatus (R184, Q7 a) — verbatim — plus UNKNOWN.
   Served per execution on the admin usage row; derived server-side (EVALUATED iff at
   least one stored record above RAW). The UI never derives or defaults it. */
const EVALUATION_STATUSES = Object.freeze({
  NEVER_EVALUATED: { cls: "st-pending", label: "NEVER_EVALUATED" },
  EVALUATED: { cls: "st-available", label: "EVALUATED" },
  UNKNOWN: { cls: "st-unknown", label: "UNKNOWN" },
});

function nodeState(value) {
  return Object.prototype.hasOwnProperty.call(NODE_STATES, value) ? value : "UNKNOWN";
}

function closedKey(map, value) {
  return Object.prototype.hasOwnProperty.call(map, value) ? value : "UNKNOWN";
}

/* --- the single transport ----------------------------------------------------- */

function setTransportPending(step) {
  /* A fact about this browser's outstanding requests — shown as such (`request in
     flight`), never written into the Core's data-state. */
  state.pendingRequests = Math.max(0, state.pendingRequests + step);
  const indicator = document.getElementById("transport-indicator");
  const busy = state.pendingRequests > 0;
  indicator.hidden = !busy;
  indicator.setAttribute("aria-busy", busy ? "true" : "false");
  indicator.classList.toggle("is-pending", busy);
  document.body.classList.toggle("is-pending", busy);
}

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  setTransportPending(+1);
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (_networkError) {
    setTransportPending(-1);
    return { ok: false, status: 0, body: null };
  }
  if (options.stream) {
    /* SSE is READ through this same transport (fetch body reader) — no EventSource.
       The caller receives the raw body stream and parses `data:` frames. */
    setTransportPending(-1);
    return { ok: response.ok, status: response.status, body: null, stream: response.body };
  }
  const body = await response.json().catch(() => null);
  setTransportPending(-1);
  return { ok: response.ok, status: response.status, body };
}

function errorText(payload) {
  return payload && payload.error
    ? `${payload.error.code}: ${payload.error.message}`
    : "request failed";
}

function showError(el, payload) {
  el.hidden = false;
  el.textContent = errorText(payload);
}

/* --- Core derivation (ExecutionStatus + reachability) -------------------------- */

function deriveCoreState(reachable, executions) {
  if (!reachable) return "unreachable";
  const rows = Array.isArray(executions) ? executions : [];
  if (rows.some((e) => e.status === "waiting_approval")) return "waiting_approval";
  if (rows.some((e) => e.status === "running" || e.status === "queued")) return "running";
  const latest = rows
    .slice()
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")))[0];
  if (latest && latest.status === "failed") return "failed";
  return "idle";
}

/* --- rendering ------------------------------------------------------------------ */

const SVG_NS = "http://www.w3.org/2000/svg";
const CENTER = 400;
const ORBIT = 272;
const EXECUTION_ORBIT = 190;

function svgEl(name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  return el;
}

function activate(el, handler) {
  /* Pointer + keyboard activation for SVG elements exposed as role=button. */
  el.addEventListener("click", handler);
  el.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      handler(event);
    }
  });
}

function renderCore(coreState) {
  const core = document.getElementById("core");
  const meta = CORE_STATES[coreState];
  core.setAttribute("data-state", coreState);
  core.setAttribute("class", `core ${meta.cls}`);
  core.setAttribute("aria-label", `QEVION Core — ${meta.label} — open the system overview`);
  document.getElementById("core-state-text").textContent = meta.label;
  document.getElementById("status-core").innerHTML = `core: <b>${meta.label}</b>`;
  document.getElementById("overview-core").textContent = meta.label;
}

/* --- R200 (operator D2 = i): capability -> surface routing DERIVED from the served
   evidence string. The first route segment after the version prefix is parsed out
   of `evidence` (a served fact); the table below maps that SEGMENT to the QEVION
   surface that already consumes it (measured at f6991e16). No capability id is
   spelled here (R182 guard), no route literal is added (12 holds), and a row whose
   evidence names no route says so — nothing is hidden or invented. Hrefs are the
   served static mounts plus a boot-once hash the receiving tree reads (D3 = i). */
const SURFACE_BY_SEGMENT = Object.freeze({
  models: { tree: "Workbench", view: "models", href: "/app/#view=models", admin: false },
  templates: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false },
  usage: { tree: "Workbench", view: "usage", href: "/app/#view=usage", admin: false },
  workspaces: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false },
  projects: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false },
  execute: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false },
  executions: { tree: "Workbench", view: "runs", href: "/app/#view=runs", admin: false },
  auth: { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false },
  skills: { tree: "Admin", view: "skills", href: "/admin/#surface=skills", admin: true },
  webhooks: { tree: "Admin", view: "system", href: "/admin/#surface=system", admin: true },
  "agent-tools": { tree: "Admin", view: "overview", href: "/admin/#surface=overview", admin: true },
  agent: { tree: "Admin", view: "overview", href: "/admin/#surface=overview", admin: true },
  dev: { tree: "Admin", view: "engineering", href: "/admin/#surface=engineering", admin: true },
});
/* admin/<area> segment pair -> the Admin Console rail surface that owns that area. */
const ADMIN_SURFACE_BY_AREA = Object.freeze({
  capabilities: "intelligence",
  scenarios: "intelligence",
  "self-review": "intelligence",
  evaluations: "intelligence",
  executions: "executions",
  learning: "learning",
  skills: "skills",
  changes: "changes",
  "source-changes": "source",
  models: "catalog",
  providers: "catalog",
  routing: "catalog",
  usage: "usage",
  plans: "usage",
  notifications: "notifications",
  system: "system",
  audit: "changes",
  "context-lab": "intelligence",
  engineering: "engineering",
  onboarding: "onboarding",
});

/* R201 (operator D1 = a, D3 = i): the Admin Console surface that owns execution records,
   named ONCE so the execution-carrying link is built from a table entry, never minted. */
const ADMIN_EXECUTIONS_OWNER = Object.freeze({
  tree: "Admin", view: "executions", href: "/admin/#surface=executions", admin: true,
});

/* R201-A: '<owner.href>&execution=<id>' — the ONLY carried parameter. The receiver on the
   other side (applyDeepLink) hands the id to its EXISTING open-by-id function; the server's
   own 404/422 decides whether this session may read it. */
function executionHref(owner, executionId) {
  return `${owner.href}&execution=${encodeURIComponent(String(executionId))}`;
}

/* R201-A (admin tier): the selected execution offers its record in the Workbench (runs) and in
   the Admin Console (executions). Same permission rule as renderAffordance — the admin target
   stays visible for a non-admin session, disabled and labelled from the served session fact. */
function renderExecutionSurfaces(executionId, session) {
  const box = document.getElementById("execution-surfaces");
  if (!box) return;
  box.replaceChildren();
  if (!executionId) return;
  const targets = [SURFACE_BY_SEGMENT.executions, ADMIN_EXECUTIONS_OWNER];
  for (const owner of targets) {
    const link = document.createElement("a");
    link.className = "surface-link";
    link.textContent = `Open ${owner.tree} · ${owner.view} for this execution`;
    const permitted = !owner.admin || (session && session.is_admin === true);
    if (permitted) {
      link.href = executionHref(owner, executionId);
    } else {
      link.setAttribute("aria-disabled", "true");
      link.classList.add("is-disabled");
      link.title = `admin session required (session.is_admin = ${String(session ? session.is_admin : "unknown")})`;
      link.textContent += " — admin";
      link.addEventListener("click", (event) => event.preventDefault());
    }
    box.appendChild(link);
  }
}

function surfaceForEvidence(evidence) {
  const text = String(evidence || "");
  if (/\/healthz\b/.test(text)) {
    return { tree: "Workbench", view: "home", href: "/app/#view=home", admin: false, route: "/healthz" };
  }
  const match = /\/v1\/([a-z-]+)(?:\/([a-z-]+))?/.exec(text);
  if (!match) return { none: true, reason: "no surface owns this route (evidence names a seam, not a route)" };
  const segment = match[1];
  if (segment === "admin") {
    const area = match[2] || "";
    const surface = ADMIN_SURFACE_BY_AREA[area] || "overview";
    return { tree: "Admin", view: surface, href: `/admin/#surface=${surface}`, admin: true, route: match[0] };
  }
  const owner = SURFACE_BY_SEGMENT[segment];
  if (!owner) return { none: true, reason: `no surface owns this route (${match[0]})` };
  return Object.assign({ route: match[0] }, owner);
}

/* R200 (operator D5): the affordance is a FUNCTION of served state + session fact.
   available + owned + permitted -> link; available + owned + admin-only for a
   non-admin -> the SAME link, disabled and labelled "admin" (visible, never hidden);
   inert / unavailable -> no link, the served evidence stands; routeless -> its reason. */
function renderAffordance(container, capability, session) {
  container.replaceChildren();
  const stateKey = nodeState(capability.state);
  const target = surfaceForEvidence(capability.evidence);
  const line = document.createElement("span");
  line.className = "affordance";
  if (target.none) {
    line.textContent = target.reason;
    line.classList.add("muted");
    container.appendChild(line);
    return;
  }
  if (stateKey !== "available") {
    line.textContent = `${target.tree} · ${target.view} — not linked: node is ${NODE_STATES[stateKey].label}`;
    line.classList.add("muted");
    container.appendChild(line);
    return;
  }
  const link = document.createElement("a");
  link.className = "surface-link";
  link.textContent = `Open ${target.tree} · ${target.view}`;
  const permitted = !target.admin || (session && session.is_admin === true);
  if (permitted) {
    link.href = target.href;
  } else {
    link.setAttribute("aria-disabled", "true");
    link.classList.add("is-disabled");
    link.title = `admin session required (session.is_admin = ${String(session ? session.is_admin : "unknown")})`;
    link.textContent += " — admin";
    link.addEventListener("click", (event) => event.preventDefault());
  }
  container.appendChild(link);
  const route = document.createElement("code");
  route.className = "affordance-route";
  route.textContent = target.route;
  container.appendChild(route);
}

function renderTopology(catalog) {
  const nodesGroup = document.getElementById("topology-nodes");
  const traces = document.getElementById("topology-traces");
  const list = document.getElementById("topology-list");
  nodesGroup.replaceChildren();
  traces.replaceChildren();
  list.replaceChildren();

  const capabilities = Array.isArray(catalog.capabilities) ? catalog.capabilities : [];
  const counts = { available: 0, inert: 0, unavailable: 0, UNKNOWN: 0 };
  const n = capabilities.length;

  capabilities.forEach((capability, i) => {
    const stateKey = nodeState(capability.state);
    counts[stateKey] += 1;
    const meta = NODE_STATES[stateKey];
    const angle = (i / Math.max(n, 1)) * Math.PI * 2 - Math.PI / 2;
    const x = CENTER + Math.cos(angle) * ORBIT;
    const y = CENTER + Math.sin(angle) * ORBIT;
    /* Circuit trace: a radial segment with one elbow, PCB-like, from the Core edge. */
    const ex = CENTER + Math.cos(angle) * 150;
    const ey = CENTER + Math.sin(angle) * 150;
    const mx = CENTER + Math.cos(angle) * 230;
    const my = CENTER + Math.sin(angle) * 230;
    traces.appendChild(
      svgEl("path", {
        d: `M ${ex} ${ey} L ${mx} ${my} L ${x} ${y}`,
        class: `trace ${meta.cls}`,
        "data-for": capability.id,
        pathLength: "100",
      })
    );

    const g = svgEl("g", {
      class: `node ${meta.cls}`,
      "data-id": capability.id,
      "data-state": stateKey,
      tabindex: "0",
      role: "button",
      "aria-label": `${capability.id} — ${meta.label} — open record`,
      "aria-haspopup": "dialog",
    });
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 22, class: "node-hit" }));
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 16, class: "node-body" }));
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 5, class: "node-dot" }));
    /* Labels sit radially OUTSIDE the node (anchor follows the side of the circle) so
       neighbouring labels at the top/bottom never collide. */
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const radial = Math.abs(cos) > 0.3;
    const label = svgEl("text", {
      x: radial ? x + (cos > 0 ? 24 : -24) : x,
      y: radial ? y + 4 + sin * 10 : y + (sin >= 0 ? 36 + (i % 2) * 14 : -26 - (i % 2) * 14),
      "text-anchor": radial ? (cos > 0 ? "start" : "end") : "middle",
      class: "node-label",
    });
    label.textContent = capability.id;
    g.appendChild(label);
    const title = svgEl("title");
    title.textContent = `${capability.id} — ${meta.label} — ${capability.evidence || ""}`;
    g.appendChild(title);
    activate(g, () => selectNode(capability, g));
    nodesGroup.appendChild(g);

    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `list-node ${meta.cls}`;
    button.setAttribute("data-id", capability.id);
    button.setAttribute("aria-describedby", "detail-evidence");
    button.innerHTML = `<span class="list-id"></span> <span class="badge ${meta.cls}"></span>`;
    button.querySelector(".list-id").textContent = capability.id;
    button.querySelector(".badge").textContent = meta.label;
    button.title = capability.evidence || "";
    button.addEventListener("click", () => selectNode(capability, button));
    li.appendChild(button);
    list.appendChild(li);
  });

  document.getElementById("status-nodes").innerHTML = `nodes: <b>${n}</b>`;
  document.getElementById("status-states").innerHTML =
    `available/inert/unavailable: <b>${counts.available}/${counts.inert}/${counts.unavailable}</b>` +
    (counts.UNKNOWN ? ` <b class="st-unknown">UNKNOWN ${counts.UNKNOWN}</b>` : "");
}

/* --- dialogs (focus in, Escape/close out, focus back to the opener) ------------- */

function openDialog(dialog, opener) {
  state.dialogOpener = opener || document.activeElement;
  dialog.hidden = false;
  const closeButton = dialog.querySelector(".btn-close");
  if (closeButton) closeButton.focus();
}

function closeDialog(dialog) {
  if (dialog.hidden) return;
  dialog.hidden = true;
  const opener = state.dialogOpener;
  state.dialogOpener = null;
  if (opener && document.contains(opener) && typeof opener.focus === "function") opener.focus();
}

function closeAnyDialog() {
  const overview = document.getElementById("overview-dialog");
  const detail = document.getElementById("node-detail");
  if (!overview.hidden) closeDialog(overview);
  else if (!detail.hidden) closeDialog(detail);
}

function selectNode(capability, opener) {
  state.selected = capability.id;
  const stateKey = nodeState(capability.state);
  const meta = NODE_STATES[stateKey];
  document.querySelectorAll("[data-id]").forEach((el) => {
    el.classList.toggle("selected", el.getAttribute("data-id") === capability.id);
  });
  document.querySelectorAll("#topology-traces .trace").forEach((el) => {
    el.classList.toggle("selected", el.getAttribute("data-for") === capability.id);
  });
  const detail = document.getElementById("node-detail");
  document.getElementById("detail-id").textContent = capability.id;
  const badge = document.getElementById("detail-state");
  badge.textContent = meta.label;
  badge.className = `badge ${meta.cls}`;
  document.getElementById("detail-evidence").textContent = capability.evidence || "";
  renderAffordance(document.getElementById("detail-surface"), capability, state.session);
  if (detail.hidden) openDialog(detail, opener);
}

function openOverview(opener) {
  /* Served fields already in hand — opening the overview performs NO request and
     changes nothing in the runtime (APEX "energize" is not a QEVION state). */
  const system = state.system || {};
  const health = state.health;
  const session = state.session || {};
  document.getElementById("overview-health").textContent = health
    ? String(health.status || "ok")
    : "unreachable";
  document.getElementById("overview-profile").textContent = system.profile ?? "—";
  document.getElementById("overview-scope").textContent = system.scope ?? "—";
  document.getElementById("overview-identity").textContent = system.identity_mode ?? "—";
  document.getElementById("overview-providers").textContent = Array.isArray(system.provider_keys)
    ? system.provider_keys.length
      ? system.provider_keys.join(", ")
      : "none configured"
    : "—";
  document.getElementById("overview-admins").textContent =
    system.admin_emails_configured === undefined ? "—" : String(system.admin_emails_configured);
  document.getElementById("overview-session").textContent =
    `${session.email || "?"} · tenant ${String(session.tenant_id || "?").slice(0, 8)}…`;
  document.getElementById("overview-executions").textContent = String(state.executions.length);
  openDialog(document.getElementById("overview-dialog"), opener);
}

function renderScope(scope, profile) {
  const badge = document.getElementById("scope-badge");
  if (scope) {
    badge.hidden = false;
    badge.textContent = `scope: ${scope}`;
  }
  document.getElementById("status-profile").innerHTML = `profile: <b>${profile || "—"}</b>`;
}

/* --- R185: execution orbit + evaluation_status (R184 contract) ------------------ */

function renderExecutionOrbit(executions) {
  /* One dot per served execution row (newest first, clockwise from the top); class =
     ExecutionStatus (closed + UNKNOWN). Selecting a dot loads that record. */
  const orbit = document.getElementById("execution-orbit");
  orbit.replaceChildren();
  const rows = (Array.isArray(executions) ? executions : [])
    .slice()
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
  const n = rows.length;
  rows.forEach((row, i) => {
    const key = closedKey(EXECUTION_STATES, row.status);
    const meta = EXECUTION_STATES[key];
    const angle = (i / Math.max(n, 1)) * Math.PI * 2 - Math.PI / 2;
    const x = CENTER + Math.cos(angle) * EXECUTION_ORBIT;
    const y = CENTER + Math.sin(angle) * EXECUTION_ORBIT;
    const g = svgEl("g", {
      class: `exec-dot ${meta.cls}` + (row.execution_id === state.selectedExecution ? " selected" : ""),
      "data-id": row.execution_id,
      "data-state": key,
      tabindex: "0",
      role: "button",
      "aria-label": `execution ${String(row.execution_id).slice(0, 8)}… — ${meta.label} — open record`,
    });
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 12, class: "exec-dot-hit" }));
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 6, class: "exec-dot-body" }));
    const title = svgEl("title");
    title.textContent = `${row.execution_id} — ${meta.label} — ${row.created_at || ""}`;
    g.appendChild(title);
    activate(g, () => showExecution(row.execution_id));
    orbit.appendChild(g);
  });
  document.getElementById("status-executions").innerHTML = `executions: <b>${n}</b>`;
}

function renderEvaluationStatus(executionId) {
  /* The R184 field, from the admin usage row joined by execution_id. Three honest
     outcomes: a closed value, a LOUD UNKNOWN, or "no usage row" (the join has no row —
     execution_id is a key, not an FK). Never a default. */
  const el = document.getElementById("execution-evaluation");
  const row = state.usageByExecution.get(executionId);
  if (!row) {
    el.textContent = "no usage row";
    el.className = "badge st-inert";
    el.setAttribute("data-evaluation-status", "");
    return;
  }
  const key = closedKey(EVALUATION_STATUSES, row.evaluation_status);
  el.textContent = EVALUATION_STATUSES[key].label;
  el.className = `badge ${EVALUATION_STATUSES[key].cls}`;
  el.setAttribute("data-evaluation-status", key);
}

async function loadUsage() {
  const usage = await api("/v1/admin/usage");
  state.usageByExecution = new Map();
  const counts = { EVALUATED: 0, NEVER_EVALUATED: 0, UNKNOWN: 0 };
  if (usage.ok) {
    for (const row of Array.isArray(usage.body.usage) ? usage.body.usage : []) {
      state.usageByExecution.set(row.execution_id, row);
      counts[closedKey(EVALUATION_STATUSES, row.evaluation_status)] += 1;
    }
    document.getElementById("status-evaluation").innerHTML =
      `evaluation: <b>EVALUATED ${counts.EVALUATED} · NEVER_EVALUATED ${counts.NEVER_EVALUATED}</b>` +
      (counts.UNKNOWN ? ` <b class="st-unknown">UNKNOWN ${counts.UNKNOWN}</b>` : "");
  } else {
    document.getElementById("status-evaluation").innerHTML = "evaluation: <b>—</b>";
  }
}

async function refreshExecutions() {
  const executions = await api("/v1/executions");
  state.executions = executions.ok && Array.isArray(executions.body.executions)
    ? executions.body.executions
    : [];
  renderExecutionOrbit(state.executions);
  renderCore(deriveCoreState(state.health !== null, state.executions));
}

/* --- load sequence (one read per surface; no polling) -------------------------- */

/* R200 (operator D1 = B): ONE Command, two tiers decided by the served session fact.
   The server's 403 stays the only permission authority; the UI never emulates a gate —
   the tenant tier simply issues no request the tenant is not entitled to. */
async function loadCenter() {
  const errorBox = document.getElementById("center-error");
  errorBox.hidden = true;
  const isAdmin = Boolean(state.session && state.session.is_admin === true);
  document.getElementById("topology-view").hidden = !isAdmin;
  document.getElementById("tenant-view").hidden = isAdmin;
  document.getElementById("execution-panel").hidden = !isAdmin;
  if (isAdmin) {
    await loadAdminCenter(errorBox);
  } else {
    await loadTenantCenter(errorBox);
  }
}

/* Admin tier — the R185 request set, unchanged: healthz, admin/system, admin/capabilities,
   executions, admin/usage. */
async function loadAdminCenter(errorBox) {
  const health = await api("/healthz");
  const reachable = health.ok;
  state.health = reachable ? health.body || { status: "ok" } : null;
  document.getElementById("status-health").innerHTML =
    `health: <b>${reachable ? (health.body && health.body.status) || "ok" : "unreachable"}</b>`;

  const system = await api("/v1/admin/system");
  if (system.ok) {
    state.system = system.body;
    renderScope(system.body.scope, system.body.profile);
  }

  const catalog = await api("/v1/admin/capabilities");
  if (!catalog.ok) {
    showError(errorBox, catalog.body);
    renderCore(reachable ? "idle" : "unreachable");
    return;
  }
  state.catalog = catalog.body;
  if (!system.ok) renderScope(catalog.body.scope, null);
  renderTopology(catalog.body);

  await refreshExecutions();
  await loadUsage();
}

/* Tenant tier — reads ONLY what the tenant already may read (healthz, the session already
   in hand, the ONE executions read the admin tier also uses). The surfaces list is the SAME
   routing table the admin nodes use; the admin control plane is ONE locked node whose label
   quotes the session fact. Zero requests to admin or agent routes. */
async function loadTenantCenter(errorBox) {
  const health = await api("/healthz");
  const reachable = health.ok;
  state.health = reachable ? health.body || { status: "ok" } : null;
  document.getElementById("status-health").innerHTML =
    `health: <b>${reachable ? (health.body && health.body.status) || "ok" : "unreachable"}</b>`;
  renderScope(null, null);
  document.getElementById("status-nodes").innerHTML = "nodes: <b>—</b>";
  document.getElementById("status-states").innerHTML = "available/inert/unavailable: <b>— (admin read)</b>";
  document.getElementById("status-evaluation").innerHTML = "evaluation: <b>— (admin read)</b>";
  await refreshExecutions();
  if (errorBox) errorBox.hidden = true;
  renderTenantSurfaces(state.session, state.executions);
}

function renderTenantSurfaces(session, executions) {
  const list = document.getElementById("tenant-surfaces");
  list.replaceChildren();
  /* Distinct tenant targets from the routing table (served-mount hrefs, no requests). */
  const seen = new Set();
  for (const owner of Object.values(SURFACE_BY_SEGMENT)) {
    if (owner.admin || seen.has(owner.href)) continue;
    seen.add(owner.href);
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.className = "surface-link";
    link.href = owner.href;
    link.textContent = `${owner.tree} · ${owner.view}`;
    li.appendChild(link);
    list.appendChild(li);
  }
  const runs = document.getElementById("tenant-executions");
  runs.textContent = `executions in this tenant: ${executions.length}`;
  /* R201-A (operator D1 = a): every served row is one click from its record in the Workbench —
     built from the rows ALREADY in state.executions (no second read); id, status and created_at
     are repeated as served. The Workbench asks the server for the record; the server decides. */
  const rows = document.getElementById("tenant-execution-list");
  rows.replaceChildren();
  for (const row of executions) {
    const li = document.createElement("li");
    const link = document.createElement("a");
    link.className = "surface-link";
    link.href = executionHref(SURFACE_BY_SEGMENT.executions, row.execution_id);
    link.textContent = `Open ${SURFACE_BY_SEGMENT.executions.tree} · ${SURFACE_BY_SEGMENT.executions.view}`;
    const id = document.createElement("code");
    id.className = "affordance-route";
    id.textContent = String(row.execution_id);
    const fact = document.createElement("span");
    fact.className = "muted small";
    fact.textContent = ` ${String(row.status)} · ${String(row.created_at)}`;
    li.append(link, " ", id, fact);
    rows.appendChild(li);
  }
  const locked = document.getElementById("tenant-admin-node");
  locked.replaceChildren();
  const link = document.createElement("a");
  link.className = "surface-link is-disabled";
  link.setAttribute("aria-disabled", "true");
  link.textContent = "Admin · control plane — admin";
  link.title = `admin session required (session.is_admin = ${String(session ? session.is_admin : "unknown")})`;
  link.addEventListener("click", (event) => event.preventDefault());
  const fact = document.createElement("span");
  fact.className = "muted small";
  fact.textContent = ` session.is_admin = ${String(session ? session.is_admin : "unknown")} — the capability topology, system overview and agent are admin reads and are not requested here.`;
  locked.append(link, fact);
}

/* --- M2: execution graph / progress / stream / conversation --------------------- */

function setBadge(el, map, value) {
  const key = closedKey(map, value);
  el.textContent = map[key].label;
  el.className = `badge ${map[key].cls}`;
  return key;
}

function renderProgress(execution) {
  /* Row 10: status + progress{current_stage, percent} from the served record ONLY. */
  document.getElementById("execution-progress").hidden = false;
  document.getElementById("progress-execution-id").textContent = execution.execution_id || "";
  setBadge(document.getElementById("progress-status"), EXECUTION_STATES, execution.status);
  const progress = execution.progress || {};
  document.getElementById("progress-stage").textContent = progress.current_stage || "—";
  const percent = Number.isFinite(progress.percent) ? progress.percent : null;
  document.getElementById("progress-percent").textContent = percent === null ? "" : `${percent}%`;
  document.getElementById("progress-bar-track").setAttribute(
    "aria-valuenow", percent === null ? "0" : String(percent));
  document.getElementById("progress-bar").style.width = `${percent === null ? 0 : percent}%`;
}

function renderTrace(trace) {
  /* Row 8: nodes = trace.stages in recorded order; attempts from the record. */
  const graph = document.getElementById("execution-graph");
  graph.replaceChildren();
  const stages = Array.isArray(trace.stages) ? trace.stages : [];
  stages.forEach((stage, i) => {
    if (i > 0) {
      const edge = document.createElement("span");
      edge.className = "exec-edge";
      edge.setAttribute("aria-hidden", "true");
      graph.appendChild(edge);
    }
    const key = closedKey(STAGE_STATES, stage.status);
    const node = document.createElement("div");
    node.className = `exec-stage ${STAGE_STATES[key].cls}`;
    node.setAttribute("data-node-key", stage.node_key);
    node.setAttribute("data-state", key);
    const name = document.createElement("code");
    name.textContent = stage.node_key;
    const badge = document.createElement("span");
    setBadge(badge, STAGE_STATES, stage.status);
    node.append(name, badge);
    const attempts = Array.isArray(stage.attempts) ? stage.attempts : [];
    const list = document.createElement("ul");
    list.className = "attempts";
    attempts.forEach((attempt) => {
      const li = document.createElement("li");
      li.textContent =
        `#${attempt.attempt} ${attempt.provider_key || "?"}/${attempt.model_key || "?"} ` +
        `${attempt.succeeded ? "ok" : "failed"} ${attempt.latency_ms ?? "?"}ms`;
      list.appendChild(li);
    });
    node.appendChild(list);
    graph.appendChild(node);
  });
  const record = document.getElementById("execution-record");
  record.hidden = false;
  const ledger = trace.ledger || {};
  record.textContent =
    `strategy ${trace.strategy || "?"} · ledger ${ledger.status || "?"} ` +
    `(${ledger.units_reserved ?? "?"} reserved / ${ledger.units_settled ?? "?"} settled) · ` +
    `as_recorded: ${String(trace.as_recorded)}`;
}

function highlightStage(frame, type) {
  /* Edge animation is exactly node_started -> node_completed; nothing else moves. */
  if (type !== "node_started" && type !== "node_completed") return;
  const stages = document.querySelectorAll("#execution-graph .exec-stage");
  stages.forEach((el) => {
    if (el.getAttribute("data-node-key") === frame.node) {
      el.classList.toggle("live", type === "node_started");
    }
  });
  /* The Core mirrors the same frame: a stage is live between these two frames. */
  document.getElementById("core").classList.toggle("stage-live", type === "node_started");
}

function appendStreamFrame(frame) {
  /* Row 9: one <li> per frame, typed by the closed map; unknown types are LOUD. */
  const log = document.getElementById("stream-log");
  const li = document.createElement("li");
  const type = frame && typeof frame.type === "string" ? frame.type : undefined;
  if (type !== undefined && Object.prototype.hasOwnProperty.call(STREAM_EVENTS, type)) {
    li.className = `frame ${STREAM_EVENTS[type].cls}`;
    li.setAttribute("data-type", type);
    let detail = "";
    if (type === "execution_started") detail = frame.execution_id || "";
    else if (type === "node_started" || type === "node_completed") detail = frame.node || "";
    else if (type === "error") detail = JSON.stringify(frame.error || {});
    else detail = "result recorded";
    li.textContent = `${STREAM_EVENTS[type].label} ${detail}`;
    highlightStage(frame, type);
  } else {
    li.className = "frame st-unknown";
    li.setAttribute("data-type", "UNKNOWN_EVENT");
    li.textContent = `UNKNOWN event type: ${JSON.stringify(type)} (not in the served vocabulary)`;
  }
  log.appendChild(li);
}

async function readEvents(executionId) {
  /* The events route is read through api() as a body stream. Frames are
     `data: <json>\n\n`; the server closes the stream after final/error. */
  document.getElementById("stream-log").replaceChildren();
  const result = await api(`/v1/executions/${encodeURIComponent(executionId)}/events`, {
    stream: true,
    headers: { Accept: "text/event-stream" },
  });
  if (!result.ok || !result.stream) {
    appendStreamFrame({ type: "error", error: { code: "stream_unavailable", status: result.status } });
    return;
  }
  const reader = result.stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep = buffer.indexOf("\n\n");
    while (sep !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        let frame;
        try {
          frame = JSON.parse(line.slice(6));
        } catch (_e) {
          frame = { type: undefined };
        }
        appendStreamFrame(frame);
      }
      sep = buffer.indexOf("\n\n");
    }
  }
  document.getElementById("core").classList.remove("stage-live");
}

async function loadExecutionRecord(executionId) {
  /* Rows 8 + 10: the stored record and its trace — one read each, rendered verbatim. */
  const [execution, trace] = await Promise.all([
    api(`/v1/executions/${encodeURIComponent(executionId)}`),
    api(`/v1/agent/executions/${encodeURIComponent(executionId)}/trace`),
  ]);
  if (execution.ok) renderProgress(execution.body);
  if (trace.ok) renderTrace(trace.body);
  else {
    const record = document.getElementById("execution-record");
    record.hidden = false;
    record.textContent = `trace: ${errorText(trace.body)}`;
  }
}

async function showExecution(executionId) {
  state.selectedExecution = executionId;
  document.querySelectorAll("#execution-orbit .exec-dot").forEach((el) => {
    el.classList.toggle("selected", el.getAttribute("data-id") === executionId);
  });
  renderExecutionSurfaces(executionId, state.session);
  await loadExecutionRecord(executionId);
  await readEvents(executionId);
  /* Re-read after the stream closed: the events are a projection of stored truth. */
  await loadExecutionRecord(executionId);
  /* The orbit, the Core and the evaluation status follow the stored rows. */
  await refreshExecutions();
  await loadUsage();
  renderEvaluationStatus(executionId);
}

function appendTurn(role, textValue, fields) {
  /* Request/response turns; server text is TEXT content, never HTML. */
  const turns = document.getElementById("converse-turns");
  const li = document.createElement("li");
  li.className = `turn turn-${role}`;
  const who = document.createElement("span");
  who.className = "k";
  who.textContent = role;
  const text = document.createElement("pre");
  text.className = "turn-text";
  text.textContent = textValue;
  li.append(who, text);
  if (fields) {
    const dl = document.createElement("dl");
    dl.className = "turn-fields";
    for (const [k, v] of Object.entries(fields)) {
      const dt = document.createElement("dt");
      dt.textContent = k;
      const dd = document.createElement("dd");
      dd.textContent = v;
      dl.append(dt, dd);
    }
    li.appendChild(dl);
  }
  turns.appendChild(li);
}

document.getElementById("converse-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const errorBox = document.getElementById("converse-error");
  errorBox.hidden = true;
  const message = document.getElementById("converse-message").value;
  const mode = document.querySelector("input[name=converse-mode]:checked").value;
  appendTurn("request", message, { mode });
  if (mode === "execute") {
    const result = await api("/v1/execute", { method: "POST", body: { ask: message } });
    if (!result.ok) {
      showError(errorBox, result.body);
      return;
    }
    const r = result.body;
    const resultText =
      r.result && typeof r.result.content === "string"
        ? r.result.content
        : JSON.stringify(r.result || {});
    appendTurn("response", resultText, {
      execution_id: r.execution_id,
      status: closedKey(EXECUTION_STATES, r.status),
      "result.type": r.result ? String(r.result.type) : "—",
      "usage.units_settled": r.usage ? String(r.usage.units_settled) : "—",
    });
    await showExecution(r.execution_id);
    return;
  }
  const result = await api("/v1/agent/converse", { method: "POST", body: { message } });
  if (!result.ok) {
    showError(errorBox, result.body);
    return;
  }
  const r = result.body;
  /* R186 (F-R185-L02): AgentAnswer.verification is `JsonObject | None` — null ONLY when no
     final was ever proposed (reasoning_failed / invalid_proposal). Render that case by
     name, citing the served stop_reason, instead of stringifying missing fields. */
  const verificationFields = {};
  if (r.verification === null || r.verification === undefined) {
    verificationFields["verification"] =
      `no verification verdict — no final was proposed (stop_reason: ${String(r.stop_reason)})`;
  } else {
    const v = r.verification;
    /* The five served counters, verbatim (R182 pin), never a derived score. */
    const served = (value) => (value === undefined || value === null ? "—" : String(value));
    verificationFields["verification.verified"] = served(v.verified);
    verificationFields["verification.claims_admitted"] = served(v.claims_admitted);
    verificationFields["verification.claims_refused"] = served(v.claims_refused);
    verificationFields["verification.tool_calls_ok"] = served(v.tool_calls_ok);
    verificationFields["verification.tool_calls_total"] = served(v.tool_calls_total);
  }
  appendTurn("response", JSON.stringify({ claims: r.claims, tool_calls: r.tool_calls }, null, 2), {
    rounds: String(r.rounds),
    stop_reason: String(r.stop_reason),
    ...verificationFields,
    reasoning_execution_ids: (r.reasoning_execution_ids || []).join(", ") || "—",
  });
  const ids = Array.isArray(r.reasoning_execution_ids) ? r.reasoning_execution_ids : [];
  if (ids.length) await showExecution(ids[ids.length - 1]);
  else await refreshExecutions();
});

/* --- Core + dialogs wiring ------------------------------------------------------ */

activate(document.getElementById("core"), (event) => openOverview(event.currentTarget));
document.getElementById("overview-close").addEventListener("click", () => {
  closeDialog(document.getElementById("overview-dialog"));
});
document.getElementById("detail-close").addEventListener("click", () => {
  closeDialog(document.getElementById("node-detail"));
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeAnyDialog();
});

/* --- session ------------------------------------------------------------------- */

/* R187 (F-CS1-01): the bearer token is kept in sessionStorage — tab-scoped, gone when
   the tab closes, never localStorage — so a reload keeps the admin session. Boot and
   login share ONE probe of the served session route; a failed probe clears custody. */
const TOKEN_KEY = "qevion.command.session";

function rememberToken(token) {
  state.token = token;
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

async function probeSession() {
  /* R200 (D1 = B): any authenticated session enters; the tier is decided in loadCenter
     from the served `is_admin` fact. A stale/invalid token still clears. */
  const session = await api("/v1/auth/session");
  if (!session.ok || !session.body) {
    rememberToken(null);
    return null;
  }
  return session.body;
}

async function enterCenter(session) {
  state.session = session;
  document.getElementById("session-who").textContent =
    `${session.email || "?"} \u00b7 tenant ${String(session.tenant_id || "?").slice(0, 8)}\u2026`;
  document.getElementById("login-view").hidden = true;
  document.getElementById("center-view").hidden = false;
  document.getElementById("logout").hidden = false;
  await loadCenter();
}

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
  if (!result.ok) {
    showError(errorBox, result.body);
    return;
  }
  rememberToken(result.body.token);
  const session = await probeSession();
  if (!session) {
    showError(errorBox, { error: { code: "unauthenticated", message: "Session could not be read." } });
    return;
  }
  await enterCenter(session);
});

document.getElementById("logout").addEventListener("click", async () => {
  const result = await api("/v1/auth/logout", { method: "POST" });
  if (!result.ok) return;
  rememberToken(null);
  state.catalog = null;
  state.selected = null;
  state.session = null;
  state.system = null;
  state.executions = [];
  state.usageByExecution = new Map();
  state.selectedExecution = null;
  closeAnyDialog();
  document.getElementById("session-who").textContent = "";
  document.getElementById("logout").hidden = true;
  document.getElementById("center-view").hidden = true;
  document.getElementById("tenant-view").hidden = true;
  document.getElementById("login-view").hidden = false;
  document.getElementById("login-password").value = "";
});

/* boot: resume a session this tab already holds (F-CS1-01). One probe, no timers;
   when the stored token is stale the probe clears it and the login view stays. */
(async function boot() {
  const stored = sessionStorage.getItem(TOKEN_KEY);
  if (!stored) return;
  state.token = stored;
  const session = await probeSession();
  if (session) await enterCenter(session);
})();
