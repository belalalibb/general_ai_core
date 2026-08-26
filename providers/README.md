# providers/ — Provider Scaffold (31 Part I)

Scaffold-state package. **No real providers exist yet** — see
`_pending_real_providers.md` (the 41 §49 truth ledger).

## Layout

```text
providers/
├── README.md                      ← this file
├── _pending_real_providers.md     ← 31 §9 pending ledger (41 §49 not-claimed list)
├── common/
│   ├── manifest_builder.py        ← shared 31 §7 template-manifest builder
│   └── template_adapter.py        ← non-functional adapter base (raises on invoke)
├── registry/                      ← reserved: registry composition lives in core/providers
└── templates/                     ← 12 disabled templates (31 §6 diversity categories)
```

Contract/registry code deliberately lives in `core/` (single source):

- Manifest schema + operation/capability/health/error contracts:
  `core/contracts/provider.py` (30 §5/§7/§11/§14)
- Adapter behavioral port: `core/providers/ports.py` (30 §8)
- Provider/model/binding registries + template exclusion:
  `core/providers/registry.py` (31 §10)

Import direction (import-linter enforced): `providers/` may import
`core.contracts` / `core.providers`; **core never imports providers**.

## Rules that bind this package

- Templates are `template_disabled`, `is_functional=false`,
  `real_provider_required=true` — never routable, never executable,
  never health-passing (31 §10).
- Templates hold **no credentials** (`auth.types: []`) and make **no network
  calls**; invoking one raises `TemplateProviderInvoked` (31 §11).
- The scaffold is capability-driven and must not force one provider shape
  (31 §12) — the template set spans api_key / oauth / session_cookie /
  no-auth-local and text-only / image-only / embeddings-only /
  moderation-only / multimodal / provider-agent shapes.
- Real providers land under `providers/real/<provider_key>/` per 31 Part II,
  never by mutating a template.
