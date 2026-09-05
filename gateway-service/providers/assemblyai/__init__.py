"""AssemblyAI LLM Gateway provider — the SECOND live provider (R174).

Built through the SAME door as Groq (three-layer model, ADR-0008):

    Layer 1 (free)      -> _upstream.py            real httpx calls to
                                                    llm-gateway.assemblyai.com/v1
    Layer 2 (mandatory) -> adapter.py               the facade: canonical in/out
    Layer 3 (fixed)     -> gateway.contracts        imported, never modified

Credential mode: ``platform`` — the API key is resolved INTERNALLY by this
package (environment variable ``GW_ASSEMBLYAI_API_KEY``; the NAME is
documented, the VALUE never appears anywhere). The platform never learns
the key; the request envelope carries no credential value.

Scope: ``generate_text`` ONLY. AssemblyAI's tools / structured output /
transcript injection / fallbacks are outside the canonical payload and are
declared as not supported (deny-by-default). AssemblyAI STT is a separate
API and is NOT this provider.

Auto-discovery does NOT register this package (registration of live
providers is an explicit act in app composition / test composition — F-1).
"""
