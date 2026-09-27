/* QEVION shell — shared UX primitives (design freeze Part 2).

   Every primitive renders SERVED facts verbatim. Status vocabularies are the
   server's own strings (badge text == served value); colours are derived from
   a closed CSS class set keyed by the served value and always accompanied by
   the text itself (non-colour-only status).
*/

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  Object.entries(attrs || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === false) return;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  });
  children.flat(Infinity).forEach((c) => {
    if (c === null || c === undefined || c === false) return;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  });
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
}

export function shortId(id) {
  return id ? String(id).slice(0, 8) : "—";
}

/** Badge: text is the served value; class derived from it, never a roster. */
export function badge(value, kind = "status") {
  const text = value === null || value === undefined || value === "" ? "—" : String(value);
  const token = text.toLowerCase().replace(/[^a-z0-9_]+/g, "-");
  return h("span", { class: `badge badge-${kind} is-${token}`, text, "data-value": text });
}

export function kv(pairs) {
  const dl = h("dl", { class: "kv" });
  pairs.forEach(([k, v]) => {
    if (v === undefined) return;
    dl.append(h("dt", { text: k }), h("dd", {}, v instanceof Node ? v : renderValue(v)));
  });
  return dl;
}

export function renderValue(v) {
  if (v === null || v === undefined) return h("span", { class: "muted", text: "—" });
  if (Array.isArray(v)) {
    if (!v.length) return h("span", { class: "muted", text: "(empty)" });
    if (v.every((x) => typeof x !== "object" || x === null)) return h("span", { text: v.join(", ") });
  }
  if (typeof v === "object") return h("pre", { class: "json", text: JSON.stringify(v, null, 2) });
  if (typeof v === "boolean") return h("span", { text: v ? "yes" : "no" });
  return h("span", { text: String(v) });
}

export function json(v) {
  return h("pre", { class: "json", text: JSON.stringify(v, null, 2) });
}

/** Skeleton placeholder while a served read is in flight. */
export function loading(label = "Loading") {
  return h("div", { class: "state state-loading", role: "status", "aria-busy": "true" }, h("span", { class: "skeleton" }), h("span", { class: "muted", text: `${label}…` }));
}

export function empty(text, action) {
  return h("div", { class: "state state-empty" }, h("p", { text }), action || null);
}

/** Honest absence: the seam is not composed / route not served in THIS process. */
export function unavailable(title, evidence) {
  return h(
    "div",
    { class: "state state-unavailable", role: "note" },
    h("strong", { text: title || "NOT AVAILABLE IN THIS PROCESS" }),
    evidence ? h("p", { class: "muted", text: String(evidence) }) : null,
  );
}

/** Server error rendered verbatim: code, message, details; Retry iff retryable. */
export function errorPanel(body, { onRetry, status } = {}) {
  const err = (body && body.error) || { code: status ? `http_${status}` : "error", message: (body && (body.detail || body.raw)) || "Request failed.", details: {} };
  const details = err.details && typeof err.details === "object" ? err.details : {};
  const panel = h(
    "div",
    { class: "state state-error", role: "alert" },
    h("div", { class: "error-head" }, badge(err.code, "error"), status ? h("span", { class: "muted", text: `HTTP ${status}` }) : null),
    h("p", { class: "error-message", text: err.message || "" }),
  );
  const entries = Object.entries(details);
  if (entries.length) {
    panel.append(kv(entries.map(([k, v]) => [k, v])));
  }
  if (err.trace_id) panel.append(h("p", { class: "muted", text: `trace ${err.trace_id}` }));
  if (err.retryable === true && onRetry) {
    panel.append(h("button", { class: "btn", type: "button", onClick: onRetry, text: "Retry" }));
  }
  return panel;
}

export function forbidden(body, status) {
  const panel = errorPanel(body, { status });
  panel.classList.add("state-forbidden");
  panel.prepend(h("p", { class: "muted", text: "The server refused this read; the shell hides nothing it was allowed to show." }));
  return panel;
}

/** Focus-trapped confirmation quoting the served preview/diff. */
export function confirmDialog({ title, verb, body, destructive }) {
  return new Promise((resolveP) => {
    const dialog = h("dialog", { class: "confirm" });
    const heading = h("h2", { id: "confirm-title", text: title });
    const content = h("div", { class: "confirm-body" }, body instanceof Node ? body : json(body));
    const cancel = h("button", { class: "btn", type: "button", text: "Cancel", onClick: () => finish(false) });
    const ok = h("button", { class: `btn btn-primary${destructive ? " btn-danger" : ""}`, type: "button", text: verb, onClick: () => finish(true) });
    dialog.setAttribute("aria-labelledby", "confirm-title");
    dialog.append(heading, content, h("div", { class: "actions" }, cancel, ok));
    dialog.addEventListener("cancel", (e) => {
      e.preventDefault();
      finish(false);
    });
    document.body.append(dialog);
    function finish(v) {
      dialog.close();
      dialog.remove();
      resolveP(v);
    }
    dialog.showModal();
    ok.focus();
  });
}

/** Horizontal stepper over the served ordered states; current == served. */
export function lifecycleStrip(states, current, terminal = []) {
  const ol = h("ol", { class: "lifecycle", "aria-label": "lifecycle" });
  const idx = states.indexOf(current);
  states.forEach((s, i) => {
    const cls = i < idx ? "done" : i === idx ? "current" : "todo";
    ol.append(h("li", { class: `step ${cls}`, "aria-current": i === idx ? "step" : null, text: s }));
  });
  if (terminal.includes(current)) {
    ol.append(h("li", { class: "step terminal current", "aria-current": "step", text: current }));
  }
  return ol;
}

/** Advanced panel — the ONE place per page for disclosed complexity. */
export function advancedPanel(title, ...children) {
  const details = h("details", { class: "advanced" }, h("summary", { text: title || "Advanced" }), ...children);
  return details;
}

/** Section card with heading. */
export function section(title, ...children) {
  return h("section", { class: "card" }, title ? h("h2", { text: title }) : null, ...children);
}

/** Page header with h1, optional breadcrumb, actions on the right. */
export function pageHeader(title, { crumb, actions, subtitle } = {}) {
  const head = h("header", { class: "page-head" });
  const left = h("div", {});
  if (crumb) left.append(h("nav", { class: "crumb", "aria-label": "breadcrumb", text: crumb }));
  left.append(h("h1", { id: "page-title", tabindex: "-1", text: title }));
  if (subtitle) left.append(h("p", { class: "muted", text: subtitle }));
  head.append(left);
  if (actions && actions.length) head.append(h("div", { class: "page-actions" }, ...actions));
  return head;
}

/** Table on desktop → stacked cards on mobile (CSS); rows are served records. */
export function dataList(columns, rows, { onRow, emptyText, limitNote } = {}) {
  if (!rows || !rows.length) return empty(emptyText || "Nothing to show.");
  const table = h("table", { class: "data" });
  table.append(h("thead", {}, h("tr", {}, ...columns.map((c) => h("th", { scope: "col", text: c.label })))));
  const tbody = h("tbody");
  rows.forEach((row) => {
    const tr = h("tr", { class: onRow ? "clickable" : null, tabindex: onRow ? "0" : null });
    columns.forEach((c) => {
      const cell = c.render ? c.render(row) : renderValue(row[c.key]);
      tr.append(h("td", { "data-label": c.label }, cell instanceof Node ? cell : String(cell)));
    });
    if (onRow) {
      tr.addEventListener("click", () => onRow(row));
      tr.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onRow(row);
        }
      });
    }
    tbody.append(tr);
  });
  table.append(tbody);
  const wrap = h("div", { class: "data-wrap" }, table);
  if (limitNote) wrap.append(h("p", { class: "muted limit-note", text: limitNote }));
  return wrap;
}

/** Simple labelled field. */
export function field(label, input, hint) {
  const id = input.id || `f-${Math.random().toString(36).slice(2, 8)}`;
  input.id = id;
  const wrap = h("div", { class: "field" }, h("label", { for: id, text: label }), input);
  if (hint) {
    const hid = `${id}-hint`;
    wrap.append(h("p", { class: "hint muted", id: hid, text: hint }));
    input.setAttribute("aria-describedby", hid);
  }
  return wrap;
}

export function input(attrs = {}) {
  return h("input", { class: "input", ...attrs });
}

export function select(options, attrs = {}) {
  const sel = h("select", { class: "input", ...attrs });
  options.forEach((o) => sel.append(h("option", { value: o.value, text: o.label, selected: o.selected || null, disabled: o.disabled || null })));
  return sel;
}

export function button(text, onClick, { primary, danger, disabled, type } = {}) {
  return h("button", { class: `btn${primary ? " btn-primary" : ""}${danger ? " btn-danger" : ""}`, type: type || "button", disabled: disabled || null, onClick, text });
}

/** Announce to the shell's aria-live region. */
export function announce(text) {
  const live = document.getElementById("live");
  if (live) {
    live.textContent = "";
    requestAnimationFrame(() => {
      live.textContent = text;
    });
  }
}

/** A run status chip: served status text + optional stage/percent facts. */
export function runStatus(record) {
  const wrap = h("span", { class: "run-status" }, badge(record && record.status));
  const p = record && record.progress;
  if (p && p.current_stage) wrap.append(h("span", { class: "muted", text: ` stage ${p.current_stage}` }));
  if (p && typeof p.percent === "number") wrap.append(h("span", { class: "muted", text: ` ${p.percent}%` }));
  return wrap;
}

/** Capability node: id / state / evidence from ONE served record — nothing else. */
export function capabilityNode(record, onSelect) {
  const node = h(
    "button",
    { class: `cap-node is-${String(record.state).toLowerCase()}`, type: "button", "data-id": record.id, "aria-label": `${record.id} — ${record.state}`, onClick: onSelect ? () => onSelect(record) : null },
    h("span", { class: "cap-id", text: record.id }),
    badge(record.state, "cap"),
  );
  node.title = record.evidence || "";
  return node;
}
