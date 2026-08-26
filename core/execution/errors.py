"""Execution-service boundary errors — composition faults that must be LOUD.

Distinction (deliberate):

- Provider failures during an attempt are DATA, not exceptions: they arrive
  as the normalized :class:`core.contracts.provider.ProviderError` (30 §14)
  and are recorded on the execution/node records — the service returns an
  Execution with ``status=failed``; it does not raise for provider weather.
- Platform wiring faults (no adapter bound for a provider the Router
  selected, no credential reference configured, malformed pipeline input)
  are BUGS in composition, not runtime provider failures — they raise
  immediately, BEFORE any provider work starts, so misconfiguration can
  never masquerade as a provider outage or interrupt an execution
  mid-flight (fail-fast, no partial execution on misconfiguration).
"""

from __future__ import annotations

from uuid import UUID


class ExecutionServiceError(Exception):
    """Base class for execution-service boundary failures."""


class AdapterNotBound(ExecutionServiceError):
    """No ProviderAdapter is bound for a provider the RoutingDecision selected.

    The Router only emits candidates from registered, eligible providers
    (11 §5); reaching execution without an adapter for one of them is a
    composition bug, never a fallback-worthy provider failure.
    """

    def __init__(self, provider_id: UUID) -> None:
        super().__init__(f"no provider adapter bound for provider {provider_id}")
        self.provider_id = provider_id


class CredentialNotConfigured(ExecutionServiceError):
    """No opaque credential reference is configured for the provider.

    Credentials cross the execution boundary as opaque references ONLY
    (20 §5); an absent reference is a configuration fault raised loudly —
    the service never invents, defaults, or logs credential material.
    """

    def __init__(self, provider_id: UUID) -> None:
        super().__init__(f"no credential reference configured for provider {provider_id}")
        self.provider_id = provider_id


class InvalidPipeline(ExecutionServiceError):
    """The pipeline stage list is structurally invalid (empty / duplicate keys).

    Node keys identify nodes in execution records (03 §5 ``node_key``);
    duplicates would make the records ambiguous, so they are rejected
    before any provider work starts.
    """
