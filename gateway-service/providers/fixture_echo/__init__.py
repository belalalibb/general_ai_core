"""fixture_echo — a HERMETIC gateway provider for routing-identity proofs (R174 §7).

Purpose (one, narrow): prove that the platform→gateway link routes by
PROVIDER (route token → slug), never by model NAME. To do that a second
provider must declare a model name that ALREADY exists on a live provider
(AssemblyAI's ``qwen3.5-4b-32k-fast``) and answer in a way that is
unmistakably NOT the live provider — with zero upstream calls, zero
credentials, zero cost.

Three-layer model, applied:

    Layer 1 (free)      -> none. There is no upstream; the facade IS the
                           whole provider. That is the point.
    Layer 2 (mandatory) -> adapter.py               canonical in/out
    Layer 3 (fixed)     -> gateway.contracts        imported, never modified

Credential mode: ``platform`` — mirrors the live providers so the platform
side composes it through the exact same door (F-3 route-token custody).
No environment variable is read; there is nothing to leak.

Registration is EXPLICIT (``app.py`` opt-in via ``GW_ENABLE_FIXTURE_ECHO=1``),
never a default: a fixture answering on a production model name would be a
lie to a paying tenant. Auto-discovery does NOT register this package.
"""
