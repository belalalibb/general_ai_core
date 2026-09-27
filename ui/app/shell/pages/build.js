/* BUILD — P13 Plan an App. PLANNING ONLY (app_factory.plan@1). No generate /
   build / deploy / publish controls exist here — not even disabled ones. The
   result opens as a run (P14 = runs.js `/build/plan/:id`). */

import { h, clear, section, pageHeader, loading, errorPanel, kv, button, field, input, select, announce, unavailable } from "../components.js";
import { set } from "../context.js";

export function registerBuild({ api, router, main, ctx }) {
  router.route("/build", async ({ query }) => {
    const m = clear(main());
    m.append(pageHeader("Build · Plan an application", { crumb: "Build", subtitle: "QEVION plans applications in this process. Generation, build, deploy and publish are not served." }));
    m.append(h("p", { class: "notice", role: "note" }, h("strong", { text: "Current capability: PLANNING ONLY. " }), "Generation is deferred by the served template; the plan is inspectable as a run."));

    const form = h("form", { class: "stack", novalidate: true });
    m.append(form);

    const intent = h("textarea", { class: "input", rows: "5", required: true, placeholder: "Describe the application to plan…" });
    intent.value = query.ask || "";

    const srcInv = h("input", { type: "radio", name: "src", id: "src-inv", value: "inventory", checked: true });
    const srcBind = h("input", { type: "radio", name: "src", id: "src-bind", value: "binding" });
    const srcRemote = h("input", { type: "radio", name: "src", id: "src-remote", value: "remote" });
    const inventory = h("textarea", { class: "input mono", rows: "6", placeholder: '{"remote_url": "...", "branch": "main", "head_sha": "...", "file_count": 0, "languages": [], "manifests": []}' });
    const bindingId = input({ type: "text", placeholder: "repository binding id (uuid)" });
    const remoteUrl = input({ type: "url", placeholder: "https://…/repo.git" });
    const branch = input({ type: "text", value: "main" });
    const sources = section(
      "Inventory source",
      h("div", { role: "radiogroup", "aria-label": "inventory source" }, h("label", { class: "model-row", for: "src-inv" }, srcInv, h("span", { class: "model-main", text: "Paste a project inventory (JSON)" })), h("label", { class: "model-row", for: "src-bind" }, srcBind, h("span", { class: "model-main", text: "Repository binding id (governed; may be INERT in this process)" })), h("label", { class: "model-row", for: "src-remote" }, srcRemote, h("span", { class: "model-main", text: "Remote URL + branch (needs a bound project inspector)" }))),
      field("Project inventory", inventory),
      field("Binding id", bindingId),
      h("div", { class: "row" }, field("Remote URL", remoteUrl), field("Branch", branch)),
      h("p", { class: "muted small", text: "The server states exactly which context it needs; its refusal text is shown verbatim." }),
    );

    const templateBox = section("Template", loading("template"));
    const modelBox = section("Model", loading("models"));
    const err = h("div");
    const submit = button("Plan", null, { primary: true, type: "submit" });
    form.append(section("Intent", field("Intent", intent)), sources, modelBox, templateBox, err, h("div", { class: "actions sticky" }, h("a", { class: "btn", href: "#/", text: "Cancel" }), submit));
    m.append(section("Future architecture (not available)", h("p", { class: "muted", text: "Plan → Generate → Verify → Deploy — marked future; none of these stages beyond Plan is served by this process, so no controls are offered." })));

    const [templates, models] = await Promise.all([api.work.templates(), api.work.models()]);
    let planRef = null;
    clear(templateBox).append(h("h2", { text: "Template" }));
    if (templates.ok) {
      const list = (templates.body && templates.body.templates) || [];
      const plan = list.find((t) => (t.id || "").startsWith("app_factory")) || list[0];
      if (!plan) {
        templateBox.append(unavailable("No planning template is served."));
        submit.disabled = true;
      } else {
        planRef = plan.ref || (plan.version ? `${plan.id}@${plan.version}` : plan.id);
        const detail = await api.work.template(planRef);
        templateBox.append(kv([["ref", planRef], ["name", plan.name], ["origin", plan.origin], ["status", plan.status]]));
        if (detail.ok) {
          const stages = (detail.body && detail.body.strategy && detail.body.strategy.stages) || [];
          templateBox.append(h("p", { class: "muted small", text: `stages: ${stages.map((s) => s.key).join(" → ") || "—"}` }));
          if (detail.body && detail.body.description) templateBox.append(h("p", { class: "muted", text: detail.body.description }));
        }
      }
    } else {
      templateBox.append(errorPanel(templates.body, { status: templates.status }));
      submit.disabled = true;
    }

    clear(modelBox).append(h("h2", { text: "Model" }));
    const modelSel = select([{ value: "", label: "Auto — the Router decides" }], { "aria-label": "model" });
    if (models.ok) {
      ((models.body && models.body.models) || []).forEach((x) => modelSel.append(h("option", { value: x.id, text: `${x.name} · ${x.availability}`, disabled: x.availability === "unavailable" ? true : null, selected: x.id === ctx().model_id ? true : null })));
      modelBox.append(modelSel);
    } else modelBox.append(errorPanel(models.body, { status: models.status }));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(err);
      if (!intent.value.trim()) {
        err.append(errorPanel({ error: { code: "validation_error", message: "Intent is required.", details: { field: "ask" } } }));
        return;
      }
      const context = {};
      if (srcInv.checked) {
        if (inventory.value.trim()) {
          try {
            context.project_inventory = JSON.parse(inventory.value);
          } catch (ex) {
            err.append(errorPanel({ error: { code: "validation_error", message: `project_inventory is not valid JSON: ${ex.message}`, details: { field: "project_inventory" } } }));
            return;
          }
        }
      } else if (srcBind.checked) {
        if (bindingId.value.trim()) context.binding_id = bindingId.value.trim();
      } else {
        if (remoteUrl.value.trim()) context.remote_url = remoteUrl.value.trim();
        if (branch.value.trim()) context.branch = branch.value.trim();
      }
      const body = { ask: intent.value, execution_strategy: { template_ref: planRef }, context };
      if (ctx().project_id) body.project_id = ctx().project_id;
      if (modelSel.value) {
        body.model_policy = { type: "explicit_model", model_id: modelSel.value };
        set({ model_id: modelSel.value });
      }
      submit.disabled = true;
      announce("Planning…");
      const r = await api.work.execute(body);
      submit.disabled = false;
      if (!r.ok) {
        err.append(errorPanel(r.body, { status: r.status }));
        announce("Plan refused.");
        return;
      }
      router.navigate(`/build/plan/${r.body.execution_id}`);
    });
  });
}
