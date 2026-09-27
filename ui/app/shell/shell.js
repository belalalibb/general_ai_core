/* QEVION unified shell — entry module (design freeze Part 1 + P2/P4).

   ONE header, ONE rail (Command · Work · Build · Intelligence · Runs · Control),
   ONE router, ONE context. Control appears only for session.is_admin; the
   server stays the authority (a forced admin URL renders the served 403).
*/

import * as api from "./api.js";
import * as router from "./router.js";
import { ctx, set, onChange, isAdmin, isAdvanced, toggleMode, clearSession, remember, recall } from "./context.js";
import { h, clear, button, select, announce, badge } from "./components.js";
import { registerCommand } from "./pages/command.js";
import { registerAuth } from "./pages/auth.js";
import { registerWork } from "./pages/work.js";
import { registerRuns } from "./pages/runs.js";
import { registerBuild } from "./pages/build.js";
import { registerIntelligence } from "./pages/intelligence.js";
import { registerControl } from "./pages/control.js";

/* Navigation model: six sections, fixed order. Pure navigation (not capability
   topology) — permitted by the guard frame. */
const SECTIONS = [
  { key: "command", label: "Command", path: "/", match: (p) => p === "/" },
  { key: "work", label: "Work", path: "/work/new", match: (p) => p.startsWith("/work") },
  { key: "build", label: "Build", path: "/build", match: (p) => p.startsWith("/build") },
  { key: "intel", label: "Intelligence", path: "/intel/skills", match: (p) => p.startsWith("/intel") },
  { key: "runs", label: "Runs", path: "/runs", match: (p) => p.startsWith("/runs") },
  { key: "control", label: "Control", path: "/control/capabilities", match: (p) => p.startsWith("/control"), admin: true },
];

const main = () => document.getElementById("main");

/* ---------------- session ---------------- */
let sessionPromise = null;

async function refreshSession(force = false) {
  if (!force && ctx().session) return ctx().session;
  if (!sessionPromise) {
    sessionPromise = api.auth.session().then((r) => {
      sessionPromise = null;
      if (r.ok) {
        set({ session: r.body });
        return r.body;
      }
      clearSession();
      return null;
    });
  }
  return sessionPromise;
}

api.setUnauthenticatedHandler(() => {
  clearSession();
  const { path, query } = router.parseHash(location.hash);
  if (!path.startsWith("/auth")) {
    announce("Session expired. Sign in to continue.");
    router.replace("/auth", { next: router.buildHash(path, query).slice(1) });
  }
});

/* ---------------- header + rail ---------------- */
function renderRail(path) {
  const rail = document.getElementById("rail-list");
  const tabs = document.getElementById("tabs-list");
  [rail, tabs].forEach((list) => {
    if (!list) return;
    clear(list);
    SECTIONS.forEach((s) => {
      if (s.admin && !isAdmin()) return;
      const active = s.match(path);
      const a = h("a", { href: `#${s.path}`, class: `nav-item${active ? " active" : ""}`, "aria-current": active ? "page" : null, text: s.label });
      list.append(h("li", {}, a));
    });
  });
}

function renderHeader() {
  const s = ctx().session;
  const who = document.getElementById("session-menu");
  clear(who);
  if (!s) {
    who.append(h("a", { href: "#/auth", class: "btn btn-ghost", text: "Sign in" }));
  } else {
    const details = h("details", { class: "menu" });
    details.append(h("summary", { class: "btn btn-ghost", "aria-label": `session ${s.email || s.user_id}` }, h("span", { class: "avatar", "aria-hidden": "true", text: (s.email || "?").slice(0, 1).toUpperCase() }), h("span", { class: "who", text: s.email || s.user_id })));
    const body = h("div", { class: "menu-body" });
    body.append(h("p", {}, h("strong", { text: s.email || "(no email)" })));
    body.append(h("p", { class: "muted mono", text: `tenant ${s.tenant_id}` }));
    body.append(h("p", {}, badge(s.is_admin ? "admin" : "user", "role")));
    body.append(
      button("Log out", async () => {
        await api.auth.logout();
        clearSession();
        set({ workspace_id: null, project_id: null, model_id: null });
        router.navigate("/auth");
      }),
    );
    details.append(body);
    who.append(details);
  }
  const mode = document.getElementById("mode-toggle");
  mode.textContent = isAdvanced() ? "Advanced" : "Normal";
  mode.setAttribute("aria-pressed", isAdvanced() ? "true" : "false");
  document.documentElement.dataset.mode = isAdvanced() ? "advanced" : "normal";
  const notif = document.getElementById("notif-link");
  notif.hidden = !isAdmin();
}

async function renderContextSelector() {
  const box = document.getElementById("context-selector");
  clear(box);
  if (!ctx().session) return;
  const [ws, pr] = await Promise.all([api.work.workspaces(), api.work.projects()]);
  const workspaces = ws.ok && ws.body && Array.isArray(ws.body.workspaces) ? ws.body.workspaces : [];
  const projects = pr.ok && pr.body && Array.isArray(pr.body.projects) ? pr.body.projects : [];
  remember("workspaces", workspaces);
  remember("projects", projects);
  const wsSel = select(
    [{ value: "", label: workspaces.length ? "workspace: none" : "no workspaces" }, ...workspaces.map((w) => ({ value: w.id, label: w.name || w.id, selected: w.id === ctx().workspace_id }))],
    { "aria-label": "workspace", class: "input input-sm" },
  );
  wsSel.addEventListener("change", () => set({ workspace_id: wsSel.value || null }));
  const prSel = select(
    [{ value: "", label: projects.length ? "project: none" : "no projects" }, ...projects.map((p) => ({ value: p.id, label: p.name || p.id, selected: p.id === ctx().project_id }))],
    { "aria-label": "project", class: "input input-sm" },
  );
  prSel.addEventListener("change", () => set({ project_id: prSel.value || null }));
  box.append(wsSel, prSel, h("a", { href: "#/work/context", class: "muted small", text: "Manage" }));
}

/* ---------------- Go to… (navigation only; executes nothing) ---------------- */
function openGoTo() {
  const dlg = document.getElementById("goto");
  const inp = document.getElementById("goto-input");
  const list = document.getElementById("goto-list");
  const build = () => {
    const q = inp.value.trim().toLowerCase();
    clear(list);
    const groups = [];
    const pages = [
      ...SECTIONS.filter((s) => !s.admin || isAdmin()).map((s) => ({ label: s.label, href: `#${s.path}` })),
      { label: "New Work", href: "#/work/new" },
      { label: "Models", href: "#/work/models" },
      { label: "Workspaces & Projects", href: "#/work/context" },
      { label: "Preferences", href: "#/work/memory" },
      { label: "Webhooks", href: "#/work/webhooks" },
      { label: "Usage", href: "#/work/usage" },
      { label: "Plan an App", href: "#/build" },
      { label: "Skills", href: "#/intel/skills" },
    ];
    groups.push(["Pages", pages]);
    if (isAdmin()) {
      groups.push([
        "Control",
        ["capabilities", "catalog", "changes", "plans", "routing", "usage", "audit", "system", "self-review", "source", "engineering", "notifications"].map((k) => ({ label: `Control · ${k}`, href: `#/control/${k}` })),
      ]);
      groups.push(["Intelligence", ["learning", "scenarios", "context-lab"].map((k) => ({ label: `Intelligence · ${k}`, href: `#/intel/${k}` }))]);
    }
    const runs = recall("runs") || [];
    groups.push(["Runs", runs.map((r) => ({ label: `${r.status} · ${(r.execution_id || "").slice(0, 8)}`, href: `#/runs/${r.execution_id}` }))]);
    const models = recall("models") || [];
    groups.push(["Models", models.map((m) => ({ label: m.name, href: `#/work/models/${m.id}` }))]);
    if (/^[0-9a-f-]{36}$/.test(q)) groups.push(["Open run by id", [{ label: q, href: `#/runs/${q}` }]]);
    groups.forEach(([name, items]) => {
      const hits = items.filter((i) => !q || i.label.toLowerCase().includes(q));
      if (!hits.length) return;
      list.append(h("li", { class: "goto-group", role: "presentation", text: name }));
      hits.slice(0, 8).forEach((i) => {
        list.append(h("li", { role: "option" }, h("a", { href: i.href, text: i.label, onClick: () => dlg.close() })));
      });
    });
    if (!list.children.length) list.append(h("li", { class: "muted", role: "presentation", text: "No matches." }));
  };
  inp.value = "";
  build();
  inp.oninput = build;
  inp.onkeydown = (e) => {
    if (e.key === "Enter") {
      const first = list.querySelector("a");
      if (first) {
        first.click();
      }
    }
  };
  dlg.showModal();
  inp.focus();
}

/* ---------------- boot ---------------- */
function registerRoutes() {
  const deps = { api, router, ctx, set, main, isAdmin, isAdvanced, refreshSession, renderContextSelector };
  registerCommand(deps);
  registerAuth(deps);
  registerWork(deps);
  registerRuns(deps);
  registerBuild(deps);
  registerIntelligence(deps);
  registerControl(deps);
  router.setNotFound(({ path }) => {
    const m = clear(main());
    m.append(h("h1", { id: "page-title", tabindex: "-1", text: "Page not found" }), h("p", { class: "muted", text: `No page at ${path}.` }), h("a", { href: "#/", text: "Back to Command" }));
  });
}

router.setBeforeEach(async ({ path, query }) => {
  const isAuth = path.startsWith("/auth");
  const session = await refreshSession();
  if (!session && !isAuth) {
    router.replace("/auth", { next: router.buildHash(path, query).slice(1) });
    return false;
  }
  if (session && isAuth && path === "/auth") {
    router.replace(query.next ? query.next.split("?")[0] : "/", query.next && query.next.includes("?") ? router.parseHash(`#${query.next}`).query : {});
    return false;
  }
  renderRail(path);
  renderHeader();
  set({ last_route: router.buildHash(path, query) });
  document.getElementById("status-route").textContent = router.buildHash(path, query);
  return true;
});

onChange(() => {
  renderHeader();
});

async function boot() {
  document.getElementById("mode-toggle").addEventListener("click", () => {
    toggleMode();
    router.resolve();
  });
  document.getElementById("goto-open").addEventListener("click", openGoTo);
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      openGoTo();
    }
  });
  const hp = api.health();
  registerRoutes();
  if (!location.hash && ctx().last_route) {
    history.replaceState(null, "", `${location.pathname}${ctx().last_route}`);
  }
  await router.start();
  const health = await hp;
  const chip = document.getElementById("status-health");
  chip.textContent = health.ok ? `health: ${(health.body && health.body.status) || "ok"}` : "health: unreachable";
  set({ health: health.ok ? health.body : null });
  await renderContextSelector();
  // focus management: move focus to the page title after each route change
  window.addEventListener("hashchange", () => {
    setTimeout(() => {
      const t = document.getElementById("page-title");
      if (t) t.focus({ preventScroll: false });
    }, 0);
  });
}

boot();
