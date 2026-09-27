/* RUNS — P7 list · P6 run detail (shared by Work and Build).
   Timeline = the served SSE frames (execution_started / node_started / delta /
   node_completed / final / error); status/progress/result/error verbatim. */

import { h, clear, section, pageHeader, badge, loading, empty, errorPanel, forbidden, kv, button, input, select, dataList, advancedPanel, json, renderValue, announce, runStatus, fmtTime, shortId } from "../components.js";
import { remember } from "../context.js";

const LIVE = new Set(["queued", "running", "waiting_approval"]);

export function registerRuns({ api, router, main, isAdmin, isAdvanced }) {
  let stream = null;
  function closeStream() {
    if (stream) {
      stream.close();
      stream = null;
    }
  }
  window.addEventListener("hashchange", closeStream);

  /* ------------------------------------------------------------------ P7 list */
  router.route("/runs", async ({ query }) => {
    const m = clear(main());
    m.append(pageHeader("Runs", { subtitle: "Tenant-scoped. Narrow the filters to find more — lists are bounded by limit." }));
    const status = input({ type: "text", placeholder: "status (server enum)", value: query.status || "", "aria-label": "status filter", list: "status-hints" });
    const initiated = input({ type: "text", placeholder: "initiated_by", value: query.initiated_by || "", "aria-label": "initiated by" });
    const from = input({ type: "datetime-local", value: query.created_after || "", "aria-label": "created after" });
    const to = input({ type: "datetime-local", value: query.created_before || "", "aria-label": "created before" });
    const limit = select([10, 25, 50, 100].map((n) => ({ value: String(n), label: `limit ${n}`, selected: String(n) === (query.limit || "25") })), { "aria-label": "limit" });
    const apply = button("Apply", () => router.navigate("/runs", { status: status.value.trim(), initiated_by: initiated.value.trim(), created_after: from.value ? new Date(from.value).toISOString() : "", created_before: to.value ? new Date(to.value).toISOString() : "", limit: limit.value }), { primary: true });
    m.append(h("div", { class: "filters" }, status, initiated, from, to, limit, apply));
    const box = h("div", {}, loading("runs"));
    m.append(box);
    const r = await api.work.executions({ status: query.status, initiated_by: query.initiated_by, created_after: query.created_after, created_before: query.created_before, limit: query.limit || 25 });
    clear(box);
    if (!r.ok) return box.append(errorPanel(r.body, { status: r.status, onRetry: () => router.resolve() }));
    const rows = (r.body && r.body.executions) || [];
    remember("runs", rows);
    const hints = h("datalist", { id: "status-hints" });
    Array.from(new Set(rows.map((x) => x.status))).forEach((s) => hints.append(h("option", { value: s })));
    m.append(hints);
    let evalByExec = null;
    if (isAdmin() && isAdvanced()) {
      const u = await api.admin.usage();
      if (u.ok) {
        evalByExec = {};
        ((u.body && u.body.usage) || []).forEach((row) => {
          evalByExec[row.execution_id] = row.evaluation_status;
        });
      }
    }
    const columns = [
      { label: "status", render: (row) => runStatus(row) },
      { label: "run", render: (row) => h("span", { class: "mono", text: shortId(row.execution_id) }) },
      { label: "created", render: (row) => h("span", { text: fmtTime(row.created_at) }) },
      { label: "initiated by", render: (row) => renderValue(row.initiated_by) },
      { label: "context", render: (row) => (row.context ? h("span", { class: "muted small", text: [row.context.mode, row.context.strategy, row.context.template_ref].filter(Boolean).join(" · ") || "—" }) : h("span", { class: "muted", text: "—" })) },
    ];
    if (evalByExec) columns.push({ label: "evaluation", render: (row) => badge(evalByExec[row.execution_id] || "—", "eval") });
    return box.append(dataList(columns, rows, { onRow: (row) => router.navigate(`/runs/${row.execution_id}`), emptyText: "No runs match.", limitNote: `showing up to ${query.limit || 25} rows — narrow the filters to find more` }));
  });

  /* ---------------------------------------------------------------- P6 detail */
  async function runDetail(id, { crumb, title } = {}) {
    closeStream();
    const m = clear(main());
    const head = h("div");
    m.append(head);
    const body = h("div", {}, loading("run"));
    m.append(body);

    const render = async () => {
      const r = await api.work.execution(id);
      clear(head);
      clear(body);
      if (r.status === 404) {
        head.append(pageHeader(title || "Run", { crumb: crumb || "Runs" }));
        body.append(errorPanel(r.body, { status: 404 }), h("p", { class: "muted", text: "Unknown, foreign and absent runs answer the same 404 in this tenant." }), h("a", { href: "#/runs", text: "Back to runs" }));
        return null;
      }
      if (!r.ok) {
        head.append(pageHeader(title || "Run", { crumb: crumb || "Runs" }));
        body.append(errorPanel(r.body, { status: r.status, onRetry: render }));
        return null;
      }
      const rec = r.body;
      const rerun = h("a", { class: "btn", href: router.buildHash("/work/new", { ask: rec.context && rec.context.ask ? rec.context.ask : "", conversation_id: rec.conversation_id || "" }), text: "Re-run (new)" });
      const copy = button("Copy id", () => navigator.clipboard && navigator.clipboard.writeText(rec.execution_id));
      head.append(pageHeader(`${title || "Run"} ${shortId(rec.execution_id)}`, { crumb: crumb || "Runs", actions: [copy, rerun] }));
      head.append(h("div", { class: "run-head" }, runStatus(rec), rec.created_at ? h("span", { class: "muted", text: fmtTime(rec.created_at) }) : null, rec.initiated_by ? h("span", { class: "muted", text: rec.initiated_by }) : null));

      if (rec.context) body.append(section("Context", kv(Object.entries(rec.context))));

      const timeline = h("ol", { class: "timeline", "aria-live": "polite", "aria-label": "execution timeline" });
      const liveBox = section("Progress", timeline);
      body.append(liveBox);

      if (rec.result) {
        const res = rec.result;
        const content = typeof res.content === "string" ? res.content : JSON.stringify(res.content, null, 2);
        body.append(section("Result", h("pre", { class: "result", text: content }), res.format ? h("p", { class: "muted small", text: `format ${res.format} · type ${res.type || "—"}` }) : null, Array.isArray(res.artifacts) && res.artifacts.length ? advancedPanel(`Artifacts (${res.artifacts.length})`, json(res.artifacts)) : null));
      }
      if (rec.error) {
        const errSec = section("Error", errorPanel({ error: rec.error }));
        if (rec.error.details && rec.error.details.stage) errSec.append(h("p", {}, "Failed stage: ", badge(rec.error.details.stage, "stage")));
        body.append(errSec);
      }
      if (rec.status === "waiting_approval") body.append(section("Approval", h("p", { class: "muted", text: "This run is waiting for approval. No approval route is served to this shell." })));

      /* Advanced: raw record, agent trace/diagnosis (own runs), admin evaluations + capture */
      const adv = advancedPanel("Advanced", json(rec));
      const traceBox = h("div", {}, h("p", { class: "muted small", text: "Loading agent trace…" }));
      adv.append(h("h3", { text: "Agent trace / diagnosis" }), traceBox);
      if (isAdmin()) {
        const evalBox = h("div", {}, h("p", { class: "muted small", text: "Loading evaluations…" }));
        adv.append(h("h3", { text: "Evaluations (admin)" }), evalBox);
        adv.append(
          button("Capture as learning sample", async () => {
            const c = await api.admin.captureSample(rec.execution_id);
            if (!c.ok) adv.append(errorPanel(c.body, { status: c.status }));
            else router.navigate(`/intel/learning/${c.body.id || c.body.sample_id}`);
          }),
        );
        api.admin.executionEvaluations(rec.execution_id).then((ev) => {
          clear(evalBox);
          if (ev.ok) {
            const list = (ev.body && (ev.body.evaluations || ev.body.records)) || (Array.isArray(ev.body) ? ev.body : []);
            if (!list.length) evalBox.append(h("p", { class: "muted small", text: "No evaluation records for this run." }));
            else list.forEach((e) => evalBox.append(h("p", {}, h("a", { href: `#/intel/evaluations/${e.id || e.evaluation_id}`, class: "mono", text: shortId(e.id || e.evaluation_id) }), " ", badge(e.status || e.verdict || "record", "eval"))));
          } else if (ev.status === 403) evalBox.append(forbidden(ev.body, ev.status));
          else evalBox.append(errorPanel(ev.body, { status: ev.status }));
        });
      }
      body.append(adv);
      api.work.agentTrace(rec.execution_id).then(async (t) => {
        clear(traceBox);
        if (t.status === 404) return traceBox.append(h("p", { class: "muted small", text: "No agent trace: not an agent run, or not found in this tenant (same 404)." }));
        if (!t.ok) return traceBox.append(errorPanel(t.body, { status: t.status }));
        traceBox.append(json(t.body));
        const d = await api.work.agentDiagnosis(rec.execution_id);
        if (d.ok) traceBox.append(h("h4", { text: "Diagnosis" }), json(d.body));
        return undefined;
      });

      /* Timeline: live SSE while the run is live; otherwise a one-shot replay */
      attachTimeline(rec, timeline, liveBox, render);
      return rec;
    };
    await render();
  }

  function attachTimeline(rec, timeline, liveBox, rerender) {
    closeStream();
    const add = (frame) => {
      const li = h("li", { class: `frame is-${frame.type}` });
      const label = h("strong", { text: frame.type });
      li.append(label);
      if (frame.node || frame.stage || frame.key) li.append(" ", h("span", { class: "mono", text: frame.node || frame.stage || frame.key }));
      if (frame.kind || frame.role) li.append(" ", h("span", { class: "muted small", text: [frame.kind, frame.role].filter(Boolean).join(" · ") }));
      if (frame.type === "delta" && typeof frame.text === "string") li.append(h("span", { class: "muted small", text: ` +${frame.text.length} chars` }));
      if (frame.type === "error" && frame.error) li.append(errorPanel({ error: frame.error }));
      if (frame.type === "final" && frame.status) li.append(" ", badge(frame.status));
      timeline.append(li);
    };
    let count = 0;
    try {
      stream = api.work.events(rec.execution_id);
    } catch {
      liveBox.append(h("p", { class: "muted small", text: "Live events unavailable in this browser." }));
      return;
    }
    stream.onmessage = (e) => {
      let frame;
      try {
        frame = JSON.parse(e.data);
      } catch {
        frame = { type: "message", raw: e.data };
      }
      count += 1;
      add(frame);
      if (frame.type === "final" || frame.type === "error") {
        closeStream();
        if (LIVE.has(rec.status)) {
          announce(`Run ${frame.type === "error" ? "failed" : "finished"}.`);
          rerender();
        }
      }
    };
    stream.onerror = () => {
      closeStream();
      if (!count) timeline.append(h("li", { class: "muted small", text: "No stored events for this run." }));
      else if (LIVE.has(rec.status)) {
        const note = h("p", { class: "muted small" }, "Live updates disconnected. ", button("Reconnect", () => rerender()));
        liveBox.append(note);
      }
    };
  }

  router.route("/runs/:id", ({ params }) => runDetail(params.id));
  router.route("/build/plan/:id", ({ params }) => runDetail(params.id, { crumb: "Build", title: "App plan" }));
}
