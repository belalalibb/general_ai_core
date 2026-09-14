# ADR-0013 — UI Front-End Stack and Serving Posture (QEVION Command Center)

```text
STATUS: PROPOSED — AWAITING OPERATOR DECISION
DATE: 2026-09-13
TASK: R182 (UI readiness / round opening) → governs R182-IMPL
SUPERSEDES: NONE (fulfils the deferral written into ADR-0001: "admin UI / client runtime …
            their stack is a future ADR when those apps start")
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
No significant architecture change is allowed without an ADR. **This ADR is not accepted.
Preparing it authorizes nothing**: no dependency installation, no `package.json`/lockfile,
no build-system change, no UI implementation. The agent may not mark it ACCEPTED.

---

## Context

- ADR-0001 (ACCEPTED) chose Python/FastAPI and explicitly deferred the client stack
  (lines 118-120, 150-152): "Admin UI / client-runtime apps will likely need a second
  language (JS/TS) later … Their stack is deferred to a future ADR." No such ADR exists;
  R182 opens the UI round, so the deferred decision is now due.
- Current serving posture (measured): two hand-written vanilla trees served by Starlette
  `StaticFiles(html=True)` — `ui/admin` at `/admin` (`apps/composition/admin_console.py:84`)
  and `ui/app` at `/app` (`apps/composition/runtime.py:1187-1192`, mount guarded by
  `UI_APP_DIR.is_dir()`, additive after every API route). No `package.json`, no lockfile,
  no `node_modules`, no build step anywhere in the repository (verified,
  `evidence/r182/governance_frame_743e203f.txt`).
- Governance any client stack must survive (measured): manifest `ui_static_check` (exact
  file list for `ui/admin`; `/v1/` literal ceiling N0=73 on `ui/admin/app.js`, currently
  AT ceiling; exception ceiling 0; exactly one `fetch(` inside `async function api(`;
  `EventSource(` / `WebSocket(` / `XMLHttpRequest` / `axios` banned); secret scan over
  `*.js *.json *.html *.css` (only `node_modules dist build` excluded); NOT-EVALUATED
  ceiling 2 with the browser live-suite already occupying slot #1; pytest min_passed 3504.
- Visual/interaction reference: APEX-UI (`evidence/r182/apex_reference_inspection.txt`).
  MIT code, but "the name Apex and the Reznikov Engineering branding are not part of this
  license"; two 21st.dev components with unresolved attribution. **Actual imports**:
  `react`, `next`, `lucide-react`, and — in exactly one file, `ApexCore3D.jsx` (504 lines)
  — `three`, `@react-three/fiber`, `@react-three/postprocessing`. The orb ring
  (`ApexOrb.jsx`), reasoning web (`ReasoningWeb.jsx`), status bar and overview panel are
  hand-written SVG/CSS with no library dependency. APEX's state machine is a tap cycle +
  8 s timer — not runtime data; QEVION's Core must be state-driven by served contracts.
- Contract facts that hold under every alternative: topology from
  `GET /v1/admin/capabilities` (closed `CapabilityState`, 23 ids with `evidence`);
  execution visuals from `GET /v1/executions/{id}` + `/events` (closed 6-type vocabulary;
  `delta` never emitted while `execute.token_streaming` is `unavailable`).

## Alternatives

### A. Vanilla ES-module JavaScript + hand-written SVG/CSS (no framework, no build)
- Same posture as the two PROVEN trees; a new tree (`ui/command/`) served by the same
  `StaticFiles` pattern. **The mount is one line at the composition root
  (`apps/composition/`, frozen in R182)** → the mount lands in the round that unfreezes
  it, under its own budget; until then the tree can only be served under an existing mount.
- Guardable by the existing static-check pattern verbatim (own literal ceiling, single
  transport, banned transports, no hardcoded `CAPABILITY_IDS`); source == served artifact,
  so secret scan and pins read the real thing; zero third-party licence surface; no
  lockfile; no Node toolchain (there is no CI to host one).
- Costs: the particle core has to be rebuilt as CSS/SVG/2D-canvas; component reuse is
  by hand; no JSX ergonomics.

### B. Next.js 15 + React 19 + three / @react-three/fiber / @react-three/postprocessing (APEX-identical)
- Fastest fidelity to APEX; JSX component model; particle core conceptually reusable.
- Costs: `package.json` + lockfile + Node toolchain; a **build step** whose minified,
  hash-named output is what would be served — literal-count, single-`fetch(` and pin
  guards are meaningless on a bundle, so a NEW source-level guard frame plus a
  reproducible-build proof would be needed; `next start` is a **second server process**
  unless statically exported (`output: 'export'`) — a runtime/deployment posture change
  (`docs/OPERATIONS.md`); hundreds of transitive packages with no SBOM/licence gate;
  secret scan must learn the build dir; `three` is ~1 MB+ client payload for a decorative
  core; TS strict + ESLint gates would have to be declared in the manifest.

### C. Vanilla ES modules (as A) + an ISOLATED, optional hand-written WebGL2 layer (no three)
- A's governance profile; the particle/shader effect as a small hand-written WebGL2 module
  behind feature checks (`WebGL2RenderingContext`, `prefers-reduced-motion`), falling
  back to the SVG ring. No dependency, no build.
- Costs: shader authoring by hand (APEX's `ShaderBackground` has unresolved attribution →
  REBUILT, never copied — the same constraint under every alternative).

### D. React/Preact via Vite static export (no Next.js, no three)
- Component model + static export served by `StaticFiles`; still needs `package.json`,
  lockfile, Node, reproducible-build proof and a source-level guard frame — the same
  class of governance change as B, smaller.

## Decision

**NOT TAKEN — operator decision required.** The operating default used by the R182
readiness analysis and by `R182_HANDOFF.md` is **Alternative C**, because it alone
(1) keeps source == served artifact so every existing UI guard applies verbatim,
(2) adds zero licence/provenance surface while the reference's own attribution is
unresolved, (3) needs no second server process and no deployment change, and (4) is
fully compatible with a later, separately-ADR'd move to B/D (contract consumption code is
stack-neutral).

If the operator selects **B** or **D**, the following MUST be declared before any code:
Node/npm version pin; `package.json` + lockfile location; build command and the
reproducible-build proof (hash of the served dir committed alongside); served directory
and its `StaticFiles` mount (frozen-tree change → budget); source-level guard frame
replacing the literal counters; secret-scan `exclude_dirs` additions; a TypeScript/ESLint
entry in manifest `non_test_items`; licence inventory of transitive dependencies.

## Reason

Invariants served: replaceable implementations (02); contract-first thin consumers
(ADR-0001 mitigation); single verifier `check_repo.sh` reading the manifest (R168 §6);
no silent guard-scope extension; provenance honesty.

## Consequences

- Under A/C: one new static tree + one mount line at the composition root (production
  change, budgeted in the round that lands it) + a declared guard frame (manifest
  `ui_static_check`-style block for the new tree BEFORE code) + `tests/ui` pins.
  Command Center contracts: `R182_READINESS.md` §4 (BACKED / INERT / MISSING).
- Under B/D: all of the above PLUS toolchain, build, SBOM and deployment changes; the round
  that lands them records acceptance here by operator text, never by editing this file's
  alternatives.
- In every alternative: NO APEX source vendored or imported; no Apex branding, ROSTER or
  INFO; no weather/social external calls; no fabricated `speaking`/`listening`/token-stream
  states; `ui/admin` keeps its EventSource/WebSocket prohibition unchanged.

## Status

PROPOSED — AWAITING OPERATOR DECISION (R182, 2026-09-13). Not accepted; nothing installed.
Acceptance, when given, is recorded here by the operator's explicit text and in
`60_DECISION_LOG.md`; the implementation round then declares its budget and guard frame.
