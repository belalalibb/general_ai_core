/* QEVION shell — unified context (design freeze §1.4).

   ctx = { session, workspace_id, project_id, mode, last_route, model_id }
   `session` lives in memory only (served by GET /v1/auth/session through the
   transport). The NON-SECRET part (workspace/project/mode/last_route/model)
   persists per tab in sessionStorage under "qevion.app.context" (R201
   posture). The token never touches the shell: it is an HttpOnly cookie.
*/

const KEY = "qevion.app.context";
const PERSISTED = ["workspace_id", "project_id", "mode", "last_route", "model_id"];

const state = {
  session: null,
  health: null,
  workspace_id: null,
  project_id: null,
  model_id: null,
  mode: "normal",
  last_route: null,
  cache: {},
};

const listeners = new Set();

function load() {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return;
    const saved = JSON.parse(raw);
    PERSISTED.forEach((k) => {
      if (saved[k] !== undefined) state[k] = saved[k];
    });
    if (state.mode !== "advanced") state.mode = "normal";
  } catch {
    /* corrupt or unavailable storage: start clean */
  }
}

function persist() {
  const out = {};
  PERSISTED.forEach((k) => {
    out[k] = state[k];
  });
  try {
    sessionStorage.setItem(KEY, JSON.stringify(out));
  } catch {
    /* storage unavailable: memory only */
  }
}

export function ctx() {
  return state;
}

export function set(patch) {
  Object.assign(state, patch);
  persist();
  listeners.forEach((fn) => fn(state));
}

export function onChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function isAdmin() {
  return Boolean(state.session && state.session.is_admin === true);
}

export function isAdvanced() {
  return state.mode === "advanced";
}

export function toggleMode() {
  set({ mode: isAdvanced() ? "normal" : "advanced" });
}

/** Tiny per-tab memo for lists the Go-to overlay reuses (never a truth source). */
export function remember(key, value) {
  state.cache[key] = value;
}

export function recall(key) {
  return state.cache[key];
}

export function clearSession() {
  state.session = null;
  state.cache = {};
  listeners.forEach((fn) => fn(state));
}

load();
