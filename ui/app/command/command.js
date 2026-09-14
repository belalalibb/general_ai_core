/* QEVION Command Center — R182-IMPL M1 "Honest topology".
   ADR-0013 Alternative C: one vanilla ES module. No framework, no build step,
   no runtime dependency, no drawing layer beyond SVG/CSS (the optional canvas
   layer is NOT in M1).

   Contract feeding this file (R182_HANDOFF §7):
     GET  /healthz                      -> reachability
     POST /v1/auth/login {email,password} -> {token}
     GET  /v1/auth/session               -> {email, tenant_id, is_admin}
     POST /v1/auth/logout
     GET  /v1/admin/system              -> {profile, scope, ...}
     GET  /v1/admin/capabilities        -> {scope, capabilities[]{id,state,evidence}}
     GET  /v1/executions                -> {executions[]{status, created_at, ...}}

   Honesty rules enforced by tests/ui/test_command_center_*_r182.py:
     * every node is one served capability record; ids come from `capability.id`;
     * NODE_STATES is the closed CapabilityState set + a LOUD UNKNOWN;
     * CORE_STATES is the closed R182_HANDOFF §8 set, derived from ExecutionStatus
       values + reachability — never invented;
     * exactly one fetch( inside api(); no EventSource/WebSocket/XHR/axios;
     * no setInterval; no roster; no provider branching. */

const state = { token: null, catalog: null, selected: null };

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

function nodeState(value) {
  return Object.prototype.hasOwnProperty.call(NODE_STATES, value) ? value : "UNKNOWN";
}

/* --- the single transport ----------------------------------------------------- */

async function api(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch (_networkError) {
    return { ok: false, status: 0, body: null };
  }
  const body = await response.json().catch(() => null);
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
const ORBIT = 300;

function svgEl(name, attrs) {
  const el = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, String(v));
  return el;
}

function renderCore(coreState) {
  const core = document.getElementById("core");
  const meta = CORE_STATES[coreState];
  core.setAttribute("data-state", coreState);
  core.setAttribute("class", `core ${meta.cls}`);
  document.getElementById("core-state-text").textContent = meta.label;
  document.getElementById("status-core").innerHTML = `core: <b>${meta.label}</b>`;
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

    traces.appendChild(
      svgEl("line", { x1: CENTER, y1: CENTER, x2: x, y2: y, class: `trace ${meta.cls}` })
    );

    const g = svgEl("g", {
      class: `node ${meta.cls}`,
      "data-id": capability.id,
      "data-state": stateKey,
      tabindex: "-1",
    });
    g.appendChild(svgEl("circle", { cx: x, cy: y, r: 16, class: "node-body" }));
    const label = svgEl("text", {
      x,
      y: y + (Math.sin(angle) >= 0 ? 34 : -26),
      "text-anchor": "middle",
      class: "node-label",
    });
    label.textContent = capability.id;
    g.appendChild(label);
    const title = svgEl("title");
    title.textContent = `${capability.id} — ${meta.label} — ${capability.evidence || ""}`;
    g.appendChild(title);
    g.addEventListener("click", () => selectNode(capability));
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
    button.addEventListener("click", () => selectNode(capability));
    li.appendChild(button);
    list.appendChild(li);
  });

  document.getElementById("status-nodes").innerHTML = `nodes: <b>${n}</b>`;
  document.getElementById("status-states").innerHTML =
    `available/inert/unavailable: <b>${counts.available}/${counts.inert}/${counts.unavailable}</b>` +
    (counts.UNKNOWN ? ` <b class="st-unknown">UNKNOWN ${counts.UNKNOWN}</b>` : "");
}

function selectNode(capability) {
  state.selected = capability.id;
  const stateKey = nodeState(capability.state);
  const meta = NODE_STATES[stateKey];
  document.querySelectorAll("[data-id]").forEach((el) => {
    el.classList.toggle("selected", el.getAttribute("data-id") === capability.id);
  });
  const detail = document.getElementById("node-detail");
  detail.hidden = false;
  document.getElementById("detail-id").textContent = capability.id;
  const badge = document.getElementById("detail-state");
  badge.textContent = meta.label;
  badge.className = `badge ${meta.cls}`;
  document.getElementById("detail-evidence").textContent = capability.evidence || "";
}

function renderScope(scope, profile) {
  const badge = document.getElementById("scope-badge");
  if (scope) {
    badge.hidden = false;
    badge.textContent = `scope: ${scope}`;
  }
  document.getElementById("status-profile").innerHTML = `profile: <b>${profile || "—"}</b>`;
}

/* --- load sequence (one read per surface; no polling) -------------------------- */

async function loadCenter() {
  const errorBox = document.getElementById("center-error");
  errorBox.hidden = true;

  const health = await api("/healthz");
  const reachable = health.ok;
  document.getElementById("status-health").innerHTML =
    `health: <b>${reachable ? (health.body && health.body.status) || "ok" : "unreachable"}</b>`;

  const system = await api("/v1/admin/system");
  if (system.ok) renderScope(system.body.scope, system.body.profile);

  const catalog = await api("/v1/admin/capabilities");
  if (!catalog.ok) {
    showError(errorBox, catalog.body);
    renderCore(reachable ? "idle" : "unreachable");
    return;
  }
  state.catalog = catalog.body;
  if (!system.ok) renderScope(catalog.body.scope, null);
  renderTopology(catalog.body);

  const executions = await api("/v1/executions");
  renderCore(deriveCoreState(reachable, executions.ok ? executions.body.executions : []));
}

/* --- session ------------------------------------------------------------------- */

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
  state.token = result.body.token;
  const session = await api("/v1/auth/session");
  if (!session.ok || session.body.is_admin !== true) {
    showError(errorBox, { error: { code: "unauthorized", message: "Admin access required." } });
    state.token = null;
    return;
  }
  document.getElementById("session-who").textContent =
    `${session.body.email || "?"} \u00b7 tenant ${String(session.body.tenant_id || "?").slice(0, 8)}\u2026`;
  document.getElementById("login-view").hidden = true;
  document.getElementById("center-view").hidden = false;
  document.getElementById("logout").hidden = false;
  await loadCenter();
});

document.getElementById("logout").addEventListener("click", async () => {
  const result = await api("/v1/auth/logout", { method: "POST" });
  if (!result.ok) return;
  state.token = null;
  state.catalog = null;
  state.selected = null;
  document.getElementById("session-who").textContent = "";
  document.getElementById("logout").hidden = true;
  document.getElementById("center-view").hidden = true;
  document.getElementById("login-view").hidden = false;
  document.getElementById("login-password").value = "";
});
