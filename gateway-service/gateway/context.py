"""ProviderContext construction — the Layer 2 input builder.

This is where the boundary is enforced physically: the context handed to a
provider facade contains NO slug, NO route_token, NO gateway secret, NO
caller network identity. Whatever the facade does internally (Layer 1), it
starts from exactly this and must return exactly a FacadeResult.
"""

from __future__ import annotations

from gateway.contracts import ProviderContext, RequestEnvelope


def build_context(envelope: RequestEnvelope) -> ProviderContext:
    """Project the wire envelope into the facade-facing context.

    ``credential_value`` passes through ONLY for user_key mode (memory-only
    handoff); platform-mode facades resolve credentials internally by their
    own means — the context never carries them.
    """

    return ProviderContext(
        operation=envelope.operation,
        model=envelope.model,
        request_id=envelope.request_id,
        tenant_id=envelope.tenant_id,
        credential_mode=envelope.credential.mode,
        credential_value=envelope.credential.value,
        payload=envelope.payload,
        timeout_ms=envelope.timeout_ms,
    )
