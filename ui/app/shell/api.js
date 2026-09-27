/* QEVION shell — the ONE transport (UI-RECON-DEC-01 §C).

   Every served route the shell consumes is spelled HERE and nowhere else.
   Auth = HttpOnly cookie `qevion_session` (set by the server on login); the
   shell never sees or stores a token. State-changing calls carry the CSRF
   header `X-Requested-With: QEVION` (COMPLETION-V2 C-05). Responses are
   returned as {ok, status, body} — pages render the server body verbatim.
*/

const CSRF_HEADER = "X-Requested-With";
const CSRF_VALUE = "QEVION";

let onUnauthenticated = null;

/** Register the single 401 handler (the router redirects to auth). */
export function setUnauthenticatedHandler(fn) {
  onUnauthenticated = fn;
}

async function request(method, path, body) {
  const headers = { Accept: "application/json", [CSRF_HEADER]: CSRF_VALUE };
  const init = { method, headers, credentials: "same-origin" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (err) {
    return {
      ok: false,
      status: 0,
      body: { error: { code: "network_error", message: String(err && err.message ? err.message : err), retryable: true, details: {} } },
    };
  }
  let parsed = null;
  const text = await response.text();
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { raw: text };
    }
  }
  if (response.status === 401 && onUnauthenticated) onUnauthenticated();
  return { ok: response.ok, status: response.status, body: parsed };
}

const get = (path) => request("GET", path);
const post = (path, body) => request("POST", path, body === undefined ? {} : body);
const del = (path) => request("DELETE", path);

function query(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

/* ----- public (no principal) ---------------------------------------------- */
export const health = () => get("/healthz");

/* ----- auth ---------------------------------------------------------------- */
export const auth = {
  session: () => get("/v1/auth/session"),
  login: (email, password) => post("/v1/auth/login", { email, password }),
  register: (email, password) => post("/v1/auth/register", { email, password }),
  verify: (token) => post("/v1/auth/verify", { token }),
  logout: () => post("/v1/auth/logout"),
};

/* ----- work ---------------------------------------------------------------- */
export const work = {
  execute: (body) => post("/v1/execute", body),
  executions: (filters) => get(`/v1/executions${query(filters)}`),
  execution: (id) => get(`/v1/executions/${encodeURIComponent(id)}`),
  /** SSE stream for a run — the ONLY EventSource in the shell. */
  events: (id) => new EventSource(`/v1/executions/${encodeURIComponent(id)}/events`, { withCredentials: true }),
  models: () => get("/v1/models"),
  templates: () => get("/v1/templates"),
  template: (ref) => get(`/v1/templates/${encodeURIComponent(ref)}`),
  skills: () => get("/v1/skills"),
  agentTools: () => get("/v1/agent-tools"),
  usage: () => get("/v1/usage"),
  workspaces: () => get("/v1/workspaces"),
  createWorkspace: (body) => post("/v1/workspaces", body),
  deleteWorkspace: (id) => del(`/v1/workspaces/${encodeURIComponent(id)}`),
  projects: () => get("/v1/projects"),
  project: (id) => get(`/v1/projects/${encodeURIComponent(id)}`),
  createProject: (body) => post("/v1/projects", body),
  deleteProject: (id) => del(`/v1/projects/${encodeURIComponent(id)}`),
  preferences: () => get("/v1/memory/preferences"),
  deletePreference: (id) => del(`/v1/memory/preferences/${encodeURIComponent(id)}`),
  webhooks: () => get("/v1/webhooks"),
  createWebhook: (body) => post("/v1/webhooks", body),
  deleteWebhook: (id) => del(`/v1/webhooks/${encodeURIComponent(id)}`),
  agentTrace: (id) => get(`/v1/agent/executions/${encodeURIComponent(id)}/trace`),
  agentDiagnosis: (id) => get(`/v1/agent/executions/${encodeURIComponent(id)}/diagnosis`),
};

/* ----- admin control plane (server-gated: 403 for non-admin) --------------- */
const A = "/v1/admin";
export const admin = {
  capabilities: () => get(`${A}/capabilities`),
  capabilityActions: () => get(`${A}/capabilities/actions`),
  capabilitiesExercisable: () => get(`${A}/capabilities/exercisable`),
  exercise: (id) => post(`${A}/capabilities/${encodeURIComponent(id)}/exercise`),
  system: () => get(`${A}/system`),
  selfReview: () => get(`${A}/self-review`),
  audit: () => get(`${A}/audit`),
  usage: () => get(`${A}/usage`),
  models: () => get(`${A}/models`),
  providers: () => get(`${A}/providers`),
  onboardProvider: (body) => post(`${A}/providers/onboard`, body),
  plan: (tenantId) => get(`${A}/plans/${encodeURIComponent(tenantId)}`),
  routingWeights: () => get(`${A}/routing/weights`),
  notifications: () => get(`${A}/notifications`),
  ackNotification: (id) => post(`${A}/notifications/${encodeURIComponent(id)}/ack`),
  changes: () => get(`${A}/changes`),
  change: (id) => get(`${A}/changes/${encodeURIComponent(id)}`),
  createChange: (body) => post(`${A}/changes`, body),
  proposeChange: (body) => post(`${A}/changes/propose`, body),
  changeStep: (id, step) => post(`${A}/changes/${encodeURIComponent(id)}/${step}`),
  executionEvaluations: (id) => get(`${A}/executions/${encodeURIComponent(id)}/evaluations`),
  evaluation: (id) => get(`${A}/evaluations/${encodeURIComponent(id)}`),
  learningDashboard: () => get(`${A}/learning/dashboard`),
  learningSamples: () => get(`${A}/learning/samples`),
  learningSample: (id) => get(`${A}/learning/samples/${encodeURIComponent(id)}`),
  captureSample: (sourceExecutionId) => post(`${A}/learning/samples`, { source_execution_id: sourceExecutionId }),
  sampleStep: (id, step, body) => post(`${A}/learning/samples/${encodeURIComponent(id)}/${step}`, body),
  learned: () => get(`${A}/learning/learned`),
  learningAsk: (question) => post(`${A}/learning/ask`, { question }),
  capabilityRetest: (body) => post(`${A}/learning/capability-retest`, body),
  changesSinceReview: () => get(`${A}/learning/changes-since-review`),
  markReviewed: () => post(`${A}/learning/mark-reviewed`),
  custodyHolds: () => get(`${A}/learning/custody/holds`),
  scenarios: () => get(`${A}/scenarios`),
  createScenario: (body) => post(`${A}/scenarios`, body),
  replayScenario: (id) => post(`${A}/scenarios/${encodeURIComponent(id)}/replay`),
  regressionPack: () => post(`${A}/scenarios/regression-pack`),
  contextLabChecks: () => get(`${A}/context-lab/checks`),
  contextLabValidate: (body) => post(`${A}/context-lab/validate`, body),
  skillImports: () => get(`${A}/skills/imports`),
  importSkill: (body) => post(`${A}/skills/import`, body),
  skillImportStep: (id, step, body) => post(`${A}/skills/imports/${encodeURIComponent(id)}/${step}`, body),
  sourceChanges: () => get(`${A}/source-changes`),
  sourceChange: (id) => get(`${A}/source-changes/${encodeURIComponent(id)}`),
  createSourceChange: (body) => post(`${A}/source-changes`, body),
  sourceSnapshot: (body) => post(`${A}/source-changes/snapshots`, body),
  sourceChangeStep: (id, step, body) => post(`${A}/source-changes/${encodeURIComponent(id)}/${step}`, body),
  engineeringStatus: () => get(`${A}/engineering/status`),
  engineeringAuthorizations: () => get(`${A}/engineering/authorizations`),
  agentTools: () => get("/v1/agent/tools"),
  converse: (message) => post("/v1/agent/converse", { message }),
};
