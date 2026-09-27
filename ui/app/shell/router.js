/* QEVION shell — the ONE hash router (design freeze §21).

   Routes are `#/segment/...?query`. Hash routing is required because the
   shell is served by StaticFiles(html=True) with no SPA fallback: a refresh on
   any deep link must reload this document and re-resolve the route here.
   Browser back/forward arrive as `hashchange`; programmatic navigation pushes
   a history entry by assigning `location.hash`.
*/

const routes = [];
let notFound = null;
let beforeEach = null;
let current = null;

function compile(pattern) {
  const keys = [];
  const source = pattern
    .split("/")
    .map((part) => {
      if (part.startsWith(":")) {
        keys.push(part.slice(1));
        return "([^/]+)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return { regex: new RegExp(`^${source}$`), keys };
}

/** Register a route: pattern like "/runs/:id"; handler(ctx) renders it. */
export function route(pattern, handler, meta = {}) {
  routes.push({ pattern, ...compile(pattern), handler, meta });
}

export function setNotFound(handler) {
  notFound = handler;
}

/** One guard executed before every resolution (session refresh lives here). */
export function setBeforeEach(fn) {
  beforeEach = fn;
}

export function parseHash(hash) {
  const raw = (hash || "").replace(/^#/, "") || "/";
  const [pathPart, queryPart = ""] = raw.split("?");
  const path = pathPart.startsWith("/") ? pathPart : `/${pathPart}`;
  const query = {};
  new URLSearchParams(queryPart).forEach((v, k) => {
    query[k] = v;
  });
  return { path, query };
}

export function buildHash(path, query) {
  const q = new URLSearchParams();
  Object.entries(query || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return `#${path}${s ? `?${s}` : ""}`;
}

/** Navigate (pushes a history entry). */
export function navigate(path, query) {
  const target = buildHash(path, query);
  if (location.hash === target) {
    resolve();
    return;
  }
  location.hash = target;
}

/** Replace the current entry (used for auth redirects). */
export function replace(path, query) {
  const target = buildHash(path, query);
  history.replaceState(null, "", `${location.pathname}${location.search}${target}`);
  resolve();
}

export function currentRoute() {
  return current;
}

export async function resolve() {
  const { path, query } = parseHash(location.hash);
  let match = null;
  for (const r of routes) {
    const m = r.regex.exec(path);
    if (m) {
      const params = {};
      r.keys.forEach((k, i) => {
        params[k] = decodeURIComponent(m[i + 1]);
      });
      match = { route: r, params };
      break;
    }
  }
  const ctx = { path, query, params: match ? match.params : {}, meta: match ? match.route.meta : {} };
  current = ctx;
  if (beforeEach) {
    const proceed = await beforeEach(ctx);
    if (proceed === false) return;
  }
  if (match) {
    await match.route.handler(ctx);
  } else if (notFound) {
    await notFound(ctx);
  }
}

export function start() {
  window.addEventListener("hashchange", () => {
    resolve();
  });
  return resolve();
}
