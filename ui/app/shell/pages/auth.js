/* P32 — Auth: sign in · create account · verify · session recovery.
   Only the served flows: register → verify (dev token echoed by the in-memory
   profile, labelled) → login (cookie set server-side). No reset, no OAuth. */

import { h, clear, field, input, button, errorPanel, announce } from "../components.js";

export function registerAuth({ api, router, main, refreshSession, renderContextSelector }) {
  function frame(title, ...children) {
    const m = clear(main());
    m.append(
      h(
        "div",
        { class: "auth-wrap" },
        h("section", { class: "card auth-card" }, h("p", { class: "brand-lg", "aria-hidden": "true", text: "◆ QEVION" }), h("h1", { id: "page-title", tabindex: "-1", text: title }), ...children),
      ),
    );
  }

  router.route("/auth", ({ query }) => {
    const email = input({ type: "email", autocomplete: "username", required: true });
    const password = input({ type: "password", autocomplete: "current-password", required: true });
    const errBox = h("div");
    const form = h("form", { class: "stack", novalidate: true }, field("Email", email), field("Password", password), errBox);
    const submit = button("Sign in", null, { primary: true, type: "submit" });
    form.append(h("div", { class: "actions" }, h("a", { href: "#/auth/register", text: "Create account" }), submit));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(errBox);
      submit.disabled = true;
      const r = await api.auth.login(email.value.trim(), password.value);
      submit.disabled = false;
      if (!r.ok) {
        errBox.append(errorPanel(r.body, { status: r.status }));
        announce("Sign in failed.");
        return;
      }
      await refreshSession(true);
      await renderContextSelector();
      announce("Signed in.");
      const next = query.next || "/";
      const parsed = router.parseHash(`#${next}`);
      router.replace(parsed.path, parsed.query);
    });
    frame("Sign in", form);
  });

  router.route("/auth/register", () => {
    const email = input({ type: "email", autocomplete: "username", required: true });
    const password = input({ type: "password", autocomplete: "new-password", required: true });
    const out = h("div");
    const form = h("form", { class: "stack", novalidate: true }, field("Email", email), field("Password", password, "Password rules are enforced by the server."), out);
    const submit = button("Create account", null, { primary: true, type: "submit" });
    form.append(h("div", { class: "actions" }, h("a", { href: "#/auth", text: "Back to sign in" }), submit));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out);
      submit.disabled = true;
      const r = await api.auth.register(email.value.trim(), password.value);
      submit.disabled = false;
      if (!r.ok) {
        out.append(errorPanel(r.body, { status: r.status }));
        return;
      }
      const b = r.body || {};
      out.append(h("p", {}, h("strong", { text: "Account created." }), ` status ${b.status || "—"} · verification ${b.verification || "—"}`));
      if (b.dev_note) out.append(h("p", { class: "muted", text: b.dev_note }));
      const q = { email: email.value.trim() };
      if (b.dev_verification_token) q.token = b.dev_verification_token;
      out.append(h("a", { class: "btn btn-primary", href: router.buildHash("/auth/verify", q), text: "Verify" }));
      announce("Account created; verification required.");
    });
    frame("Create account", form);
  });

  router.route("/auth/verify", ({ query }) => {
    const token = input({ type: "text", autocomplete: "one-time-code", required: true, value: query.token || "" });
    const out = h("div");
    const form = h("form", { class: "stack", novalidate: true }, field("Verification token", token, query.token ? "Pre-filled from the server's dev-token response (in-memory profile only)." : "Paste the token you received."), out);
    const submit = button("Verify", null, { primary: true, type: "submit" });
    form.append(h("div", { class: "actions" }, h("a", { href: "#/auth", text: "Back to sign in" }), submit));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      clear(out);
      submit.disabled = true;
      const r = await api.auth.verify(token.value.trim());
      submit.disabled = false;
      if (!r.ok) {
        out.append(errorPanel(r.body, { status: r.status }));
        return;
      }
      out.append(h("p", {}, h("strong", { text: "Verified." }), " You can sign in now."));
      out.append(h("a", { class: "btn btn-primary", href: "#/auth", text: "Sign in" }));
      announce("Email verified.");
    });
    frame("Verify", form);
  });
}
