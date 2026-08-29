# gateway-service — Remote Provider Gateway (data plane)

Authority: ADR-0008 (ACCEPTED 2026-08-29). Phase: **G1 skeleton** —
contracts, auth, registries, dispatch, discovery, hermetic tests.
**No live providers. No real upstream. No real credentials.**

## Layout

```
gateway-service/            self-contained project root (own pyproject)
├── app.py                  entrypoint only (build_app + uvicorn); zero logic
├── gateway/                core package
│   ├── contracts.py        ★ Layer 3 — canonical contract (code source of truth)
│   ├── config.py           env config; misconfig fails loud
│   ├── auth.py             X-Gateway-Secret[+Version]; dual-accept rotation
│   ├── routes.py           thin HTTP surface (POST /v1/execute + discovery)
│   ├── route_registry.py   route_token → slug; hot-reload, revoke, disable
│   ├── provider_registry.py eager DEFINITION validation; lazy facade import
│   ├── context.py          ProviderContext builder (hides slug/token)
│   ├── credentials.py      credential-mode enforcement (user_key/platform)
│   ├── errors.py           12-category helpers + provider_code sanitizer
│   ├── discovery.py        /describe /models /health projections (no slug)
│   └── observability.py    closed allowed-field log contract
├── providers/
│   ├── _example/           D2: WORKING 3-layer reference vs mock (not live)
│   └── _template/          D2-bis: documented facade template (all 8 ops)
├── tests/                  hermetic only — zero network
└── docs/
    ├── CONTRACT.md         D1: human-readable contract (mirrors contracts.py)
    └── ONBOARDING.md       D3: provider onboarding runbook + dev form
```

## Three-layer provider model (mandatory)

Layer 1 (free internals) → Layer 2 (mandatory facade = the translator) →
Layer 3 (fixed canonical contract). See `docs/CONTRACT.md` and
`providers/_template/adapter.py`.

## Run tests

```bash
cd gateway-service
pip install -e ".[dev]"   # or: pip install fastapi pydantic uvicorn pytest pytest-asyncio httpx
python3 -m pytest
```

All tests are hermetic (in-process ASGI client, mock upstream).
