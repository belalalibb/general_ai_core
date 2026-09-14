/* QEVION Command Center — R182-IMPL M1 "Honest topology" + M2 (execution graph / progress / conversation).
   ADR-0013 Alternative C: one vanilla ES module. No framework, no build step,
   no runtime dependency, no drawing layer beyond SVG/CSS (the optional canvas
   layer is NOT in M1).

   Contract feeding this file (R182_HANDOFF §7) — every route is an api() literal below,
   validated against the served OpenAPI by tests/ui/test_command_center_static_check_r182.py
   (raw `/v1/` occurrences are capped at 12, down only; this comment spends none):
     healthz                          -> reachability
     auth login / session / logout    -> {token} / {email, tenant_id, is_admin} / 204
     admin system                     -> {profile, scope, ...}
     admin capabilities               -> {scope, capabilities[]{id,state,evidence}}
     executions (list)                -> {executions[]{status, created_at, ...}}
   M2 (HANDOFF §7 rows 8-11):
     execute {ask}                    -> {execution_id, status, result, usage}
     agent converse {message}         -> {claims[], tool_calls[], reasoning_execution_ids[],
                                          rounds, stop_reason, verification{...}, reasoning_trace[]}
     executions/{id}                  -> {status, progress{current_stage, percent}}
     executions/{id}/events           -> text/event-stream of the FIVE emitted types
     agent executions/{id}/trace      -> {strategy, stages[]{node_key,status,attempts[]}, ledger, as_recorded}

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

function nodeState(value) {
  return Object.prototype.hasOwnProperty.call(NODE_STATES, value) ? value : "UNKNOWN";
}

function closedKey(map, value) {
  return Object.prototype.hasOwnProperty.call(map, value) ? value : "UNKNOWN";
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
  if (options.stream) {
    /* SSE is READ through this same transport (fetch body reader) — no EventSource.
       The caller receives the raw body stream and parses `data:` frames. */
    return { ok: response.ok, status: response.status, body: null, stream: response.body };
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
  await loadExecutionRecord(executionId);
  await readEvents(executionId);
  /* Re-read after the stream closed: the events are a projection of stored truth. */
  await loadExecutionRecord(executionId);
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
  const v = r.verification || {};
  appendTurn("response", JSON.stringify({ claims: r.claims, tool_calls: r.tool_calls }, null, 2), {
    rounds: String(r.rounds),
    stop_reason: String(r.stop_reason),
    "verification.verified": String(v.verified),
    "verification.claims_admitted": String(v.claims_admitted),
    "verification.claims_refused": String(v.claims_refused),
    "verification.tool_calls_ok": String(v.tool_calls_ok),
    "verification.tool_calls_total": String(v.tool_calls_total),
    reasoning_execution_ids: (r.reasoning_execution_ids || []).join(", ") || "—",
  });
  const ids = Array.isArray(r.reasoning_execution_ids) ? r.reasoning_execution_ids : [];
  if (ids.length) await showExecution(ids[ids.length - 1]);
});

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
