"""ProviderAdapter behavioral port (30 §8) — the ONLY seam between Core and
any provider implementation.

Spec anchors:

- 30 §8.1 required interface: get_manifest / validate_credential /
  discover_models / get_capabilities / generate / health_check /
  normalize_error — mapped 1:1 (snake_case per stack conventions;
  "Exact language and file extensions depend on the project stack", 31 §5).
- 30 §8.1 note: ``generate`` is the normalized entry point; internally the
  adapter dispatches to the capability-specific operations of 30 §5. A
  provider without the requested capability rejects with
  ``unsupported_capability``.
- 30 §8.2 optional interfaces: account lifecycle and asset transfer are
  SEPARATE protocols — an adapter implements them only if the provider
  needs them (account pool is optional, 30 §10.1).
- 30 §15.2 optional provider-agent interface (FINAL Phase 4, T-IMPL-054):
  same SEPARATE-protocol pattern — only providers declaring the
  ``provider_agent`` capability implement ``ProviderAgentModulePort``;
  payload/event shapes live in ``core/contracts/provider_agent.py``.
- 30 §9: provider request mechanics (HTTP, cookies, retries, polling...)
  live behind this port; "The Core must not see these details."
- 30 §14: adapters return/raise only normalized ProviderError shapes.
- 20 §5: credentials cross this boundary as opaque references only.

Async posture: adapter operations are I/O by nature (network in real
implementations), so the port is async — matching the runtime ports
(core/runtime/ports.py). Hermetic fakes in tests implement it in-memory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from core.contracts.provider import (
    CredentialHealth,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderManifest,
)
from core.contracts.provider_agent import (
    ProviderAgentEvent,
    ProviderAgentRequest,
    ProviderAgentResponse,
    ProviderAgentRun,
    ProviderAgentRunStatus,
)


class ProviderAdapterPort(Protocol):
    """Required provider interface (30 §8.1) — every adapter implements this.

    Contract obligations on implementors:

    - ``get_manifest`` returns the provider's complete self-declaration
      (30 §7); the registry trusts ONLY this declaration (30 §4.2).
    - ``validate_credential`` receives an OPAQUE reference and must never
      log, echo, or resolve it into anything it returns (20 §5).
    - ``discover_models`` reports provider-declared models; an empty list
      is valid (30 §4.3 — never assume every provider has models).
    - ``generate`` must reject operations the manifest does not declare
      with a normalized ``unsupported_capability`` error (30 §8.1 note);
      it never raises raw provider exceptions across the boundary.
    - ``health_check`` keeps provider health and account health separate
      (30 §11) — one failed account never means the provider is down.
    - ``normalize_error`` maps ANY raw provider failure object into the
      12-category normalized :class:`ProviderError` (30 §14).
    """

    def get_manifest(self) -> ProviderManifest:
        """Return the provider's manifest (synchronous: static declaration)."""
        ...

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        """Check one opaque credential reference and report its health."""
        ...

    async def discover_models(self, account_id: UUID | None = None) -> list[DiscoveredModel]:
        """Report the provider's declared models (possibly empty)."""
        ...

    async def get_capabilities(self) -> ProviderCapabilities:
        """Return the declared capability set (deny-by-default keys)."""
        ...

    async def generate(self, request: ProviderGenerateRequest) -> ProviderGenerateResponse:
        """Execute one normalized operation; never leak raw errors."""
        ...

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        """Report health for the requested scope (30 §11 separation)."""
        ...

    def normalize_error(self, error: object) -> ProviderError:
        """Translate a raw provider failure into the normalized shape (30 §14)."""
        ...


class ProviderAccountLifecyclePort(Protocol):
    """Optional account-lifecycle interface (30 §8.2).

    Only providers with account pools implement this (30 §10.1). Account
    identifiers are UUIDs of ``ProviderAccount`` records (03 §4).
    """

    async def refresh_account(self, account_id: UUID) -> bool:
        """Attempt refresh; True iff the account is usable again."""
        ...

    async def disable_account(self, account_id: UUID) -> None:
        """Mark the account unusable (lifecycle DISABLED, 30 §10.2)."""
        ...


class ProviderAgentModulePort(Protocol):
    """Optional provider-native agent interface (30 §15.2).

    Only providers declaring the ``provider_agent`` capability implement
    this — 30 §15.2 marks every method optional in the TS interface; here
    the PORT itself is the optional unit (same pattern as the other §8.2
    optional protocols: an adapter without the capability simply does not
    implement this protocol).

    Contract obligations on implementors:

    - Provider Agent Capability != Platform Agent Runtime (30 §15): the
      platform still owns authorization, capability firewall, tool
      approval, tenant isolation, usage accounting, evaluation, audit,
      and the final response — none of that moves behind this port.
    - All emitted events are the normalized 30 §15.3 shapes; raw provider
      agent semantics never cross this boundary.
    - ``run_id`` values are opaque provider-managed handles; the platform
      never parses them.
    - Provider-side tool use is deny-by-default (30 §15.4): honored only
      when the request explicitly grants it AND policy allows.
    - Errors are normalized :class:`ProviderError` shapes only (30 §14).
    """

    async def run_agent(self, request: ProviderAgentRequest) -> ProviderAgentResponse:
        """Execute one provider-agent invocation to completion (one-shot)."""
        ...

    async def create_agent_run(self, request: ProviderAgentRequest) -> ProviderAgentRun:
        """Start a provider-managed run; return its opaque handle."""
        ...

    async def get_agent_run(self, run_id: str) -> ProviderAgentRunStatus:
        """Report the run's normalized point-in-time status."""
        ...

    async def cancel_agent_run(self, run_id: str) -> None:
        """Request cancellation of a provider-managed run (30 §15.4 cleanup)."""
        ...

    def stream_agent_run(self, run_id: str) -> AsyncIterator[ProviderAgentEvent]:
        """Stream normalized 30 §15.3 events for a run."""
        ...


class ProviderAssetsPort(Protocol):
    """Optional asset-transfer interface (30 §8.2).

    References are opaque handles (object-storage keys / provider asset
    ids); payload bytes move through the object-storage port, not here.
    """

    async def upload_asset(self, tenant_id: UUID, file_ref: str) -> str:
        """Push a platform file to the provider; return the provider asset ref."""
        ...

    async def download_asset(self, tenant_id: UUID, asset_ref: str) -> str:
        """Fetch a provider asset into platform storage; return the file ref."""
        ...
