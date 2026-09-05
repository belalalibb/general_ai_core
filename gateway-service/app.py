"""Entrypoint ONLY: build_app() + uvicorn run. No logic lives here.

Dependency direction (fixed): providers import gateway.contracts; the
gateway core imports contracts; app.py imports the core. NOTHING imports
app.py back — providers are testable against gateway.contracts alone.
"""

from __future__ import annotations

from fastapi import FastAPI

from gateway.config import GatewayConfig, load_config_from_env
from gateway.provider_registry import ProviderRegistry
from gateway.route_registry import RouteRegistry
from gateway.routes import build_router


def build_app(
    config: GatewayConfig,
    providers: ProviderRegistry,
    routes: RouteRegistry | None = None,
) -> FastAPI:
    """Composition: wire config + registries into the HTTP surface."""

    app = FastAPI(title="Provider Gateway", docs_url=None, redoc_url=None, openapi_url=None)
    route_registry = routes or RouteRegistry(config.route_map, config.disabled_slugs)
    app.include_router(build_router(config, route_registry, providers))
    return app


def main() -> None:  # pragma: no cover — process entrypoint, not hermetic
    import uvicorn

    config = load_config_from_env()
    registry = ProviderRegistry()
    register_live_providers(registry)
    registry.eager_verify_all()
    uvicorn.run(build_app(config, registry), host="127.0.0.1", port=8800)


def register_live_providers(registry: ProviderRegistry) -> None:
    """Register the gateway's LIVE providers (G3: groq is the first).

    The slug is deployment-internal (5-layer identity: it never crosses to
    the platform); routing to it happens via opaque route tokens in the
    config's route_map. The Groq API key is resolved by the provider's own
    Layer 1 from the ``GW_GROQ_API_KEY`` environment variable (platform
    credential mode) — the platform never learns it.
    """

    from providers.assemblyai.definition import DEFINITION as ASSEMBLYAI_DEFINITION
    from providers.groq.definition import DEFINITION as GROQ_DEFINITION

    registry.register("groq", GROQ_DEFINITION, "providers.groq.adapter")
    # R174: second live provider, same door. Key: GW_ASSEMBLYAI_API_KEY (platform mode).
    registry.register("assemblyai", ASSEMBLYAI_DEFINITION, "providers.assemblyai.adapter")


if __name__ == "__main__":  # pragma: no cover
    main()
