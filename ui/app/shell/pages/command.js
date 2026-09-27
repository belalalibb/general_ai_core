/* P1 — Command Home: where am I · what is running · what next.
   Non-admin renders NO capability topology (OD-1 = B) and infers nothing.
   Admin Advanced renders the served /v1/admin/capabilities records 1:1. */

import { h, clear, section, pageHeader, badge, loading, empty, errorPanel, forbidden, kv, button, runStatus, fmtTime, capabilityNode, advancedPanel, json } from "../components.js";
import { remember } from "../context.js";

export function registerCommand({ api, router, main, ctx, isAdmin, isAdvanced }) {
  router.route("/", async () => {
    const m = clear(main());
    const session = ctx().session;
    m.append(pageHeader("Command", { subtitle: `${session.email || session.user_id} · tenant-scoped` }));

    const ask = h("input", { class: "input", type: "text", "aria-label": "What do you want to do?", placeholder: "Describe the task… (Enter opens New Work)" });
    ask.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && ask.value.trim()) router.navigate("/work/new", { ask: ask.value.trim() });
    });
    const start = section("Start", h("div", { class: "row" }, ask, button("Start", () => router.navigate("/work/new", ask.value.trim() ? { ask: ask.value.trim() } : {}), { primary: true })));

    const usageBox = section("Usage", loading("usage"));
    m.append(h("div", { class: "grid-2" }, start, usageBox));

    const runsBox = section("Recent runs", loading("runs"));
    m.append(runsBox);

    let capsBox = null;
    let notifBox = null;
    if (isAdmin()) {
      notifBox = section("Notifications", loading("notifications"));
      m.append(notifBox);
      if (isAdvanced()) {
        capsBox = section("Capability topology", loading("capabilities"));
        m.append(capsBox);
      } else {
        m.append(section("Capability topology", h("p", { class: "muted", text: "Switch to Advanced to see this process's served capability records." })));
      }
    }

    const [usage, runs] = await Promise.all([api.work.usage(), api.work.executions({ limit: 5 })]);

    clear(usageBox).append(h("h2", { text: "Usage" }));
    if (usage.ok) {
      const u = usage.body || {};
      const tu = u.task_units || {};
      const pct = tu.limit ? Math.min(100, Math.round(((tu.used || 0) / tu.limit) * 100)) : 0;
      usageBox.append(
        kv([["plan", u.plan]]),
        h("div", { class: "meter", role: "meter", "aria-valuemin": "0", "aria-valuemax": String(tu.limit ?? 0), "aria-valuenow": String(tu.used ?? 0), "aria-label": "task units used" }, h("span", { style: `width:${pct}%` })),
        h("p", { class: "muted", text: `task units ${tu.used ?? "—"} used of ${tu.limit ?? "—"} · ${tu.remaining ?? "—"} remaining` }),
        h("a", { href: "#/work/usage", text: "Usage details" }),
      );
    } else if (usage.status === 404) {
      usageBox.append(h("p", { class: "muted", text: "Usage is not served by this process." }));
    } else {
      usageBox.append(errorPanel(usage.body, { status: usage.status }));
    }

    clear(runsBox).append(h("h2", { text: "Recent runs" }), h("a", { class: "head-link", href: "#/runs", text: "All runs" }));
    if (runs.ok) {
      const rows = (runs.body && runs.body.executions) || [];
      remember("runs", rows);
      if (!rows.length) runsBox.append(empty("No runs yet. Start one above."));
      else {
        const ul = h("ul", { class: "run-list" });
        rows.forEach((r) => {
          ul.append(h("li", {}, h("a", { href: `#/runs/${r.execution_id}`, class: "run-row" }, runStatus(r), h("span", { class: "mono", text: String(r.execution_id).slice(0, 8) }), h("span", { class: "muted", text: fmtTime(r.created_at) }), r.initiated_by ? h("span", { class: "muted", text: r.initiated_by }) : null)));
        });
        runsBox.append(ul);
      }
    } else {
      runsBox.append(errorPanel(runs.body, { status: runs.status }));
    }

    if (notifBox) {
      const n = await api.admin.notifications();
      clear(notifBox).append(h("h2", { text: "Notifications" }));
      if (n.ok) {
        const unread = n.body && typeof n.body.unread === "number" ? n.body.unread : 0;
        notifBox.append(h("p", {}, `unread ${unread} · as of ${new Date().toLocaleTimeString()} `, h("a", { href: "#/control/notifications", text: "Open" })));
      } else if (n.status === 403) notifBox.append(forbidden(n.body, n.status));
      else notifBox.append(errorPanel(n.body, { status: n.status }));
    }

    if (capsBox) {
      const cat = await api.admin.capabilities();
      clear(capsBox).append(h("h2", { text: "Capability topology" }));
      if (cat.ok) renderTopology(capsBox, cat.body);
      else if (cat.status === 403) capsBox.append(forbidden(cat.body, cat.status));
      else capsBox.append(errorPanel(cat.body, { status: cat.status }));
    }
  });

  /* Renders the served catalog 1:1: each node prints record.id / record.state /
     record.evidence. No id, no state, no route is spelled on the client. */
  function renderTopology(box, catalog) {
    const capabilities = Array.isArray(catalog.capabilities) ? catalog.capabilities : [];
    box.append(h("p", { class: "muted", text: `scope ${catalog.scope || "—"} · ${capabilities.length} records` }));
    const detail = h("div", { class: "cap-detail", "aria-live": "polite" }, h("p", { class: "muted", text: "Select a node to read its record." }));
    const ring = h("div", { class: "cap-ring", role: "list" });
    capabilities.forEach((record) => {
      const node = capabilityNode(record, (rec) => {
        clear(detail).append(kv([["id", rec.id], ["state", badge(rec.state, "cap")], ["evidence", rec.evidence]]));
      });
      ring.append(h("div", { role: "listitem" }, node));
    });
    box.append(ring, detail, advancedPanel("Raw catalog", json(catalog)), h("a", { href: "#/control/capabilities", text: "Control · Capabilities" }));
  }
}
