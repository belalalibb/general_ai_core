"""Groq provider — the FIRST live provider of the gateway (G3, ADR-0008).

Three-layer model, applied:

    Layer 1 (free)      -> _upstream.py            real httpx calls to Groq's
                                                    OpenAI-compatible API
    Layer 2 (mandatory) -> adapter.py               the facade: canonical in/out
    Layer 3 (fixed)     -> gateway.contracts        imported, never modified

Credential mode: ``platform`` — the API key is resolved INTERNALLY by this
package (environment variable ``GW_GROQ_API_KEY``; the NAME is documented,
the VALUE never appears anywhere). The platform never learns the key; the
request envelope carries no credential value.

Auto-discovery does NOT register this package (registration of live
providers is an explicit act in app composition / test composition).
"""
