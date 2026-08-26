"""Non-functional template adapter base for scaffold templates (31 §7, §10, §11).

T-IMPL-020 (MVP Phase 4 slice 3). Spec anchors:

- 31 §7: templates are "scaffold template only" — never activatable without a
  real provider adapter and contract tests.
- 31 §10: template health checks CANNOT pass (real_provider_required=true).
- 31 §11: "templates cannot execute generation" and tests must never pretend
  generation works — so every template invocation raises, deterministically.
- 41 §49 scaffold-state rules: templates prove the adapter CONTRACT SHAPE
  (they satisfy ``ProviderAdapterPort``) without any network or secrets.

This base implements the full 30 §8.1 required interface so the type checker
and tests can verify "provider contract can be implemented later" (31 §11) —
but every runtime path either reports non-functional state or raises
:class:`TemplateProviderInvoked`.
"""

from __future__ import annotations

from uuid import UUID

from core.contracts.provider import (
    CredentialHealth,
    CredentialStatus,
    DiscoveredModel,
    HealthScope,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCategory,
    ProviderGenerateRequest,
    ProviderGenerateResponse,
    ProviderHealth,
    ProviderHealthState,
    ProviderManifest,
)


class TemplateProviderInvoked(RuntimeError):
    """A scaffold template was asked to do real provider work (31 §11).

    This is a HARD failure by design: templates are non-functional and must
    never be routed to, executed, or used to fake generation output.
    """

    def __init__(self, provider_id: str, operation: str) -> None:
        super().__init__(
            f"template provider '{provider_id}' cannot perform '{operation}': "
            "it is a scaffold template (is_functional=false, "
            "real_provider_required=true; see 31 §7/§10)"
        )
        self.provider_id = provider_id
        self.operation = operation


class TemplateProviderAdapter:
    """Base adapter for the 12 scaffold templates (31 §6).

    Satisfies ``ProviderAdapterPort`` structurally. Declarative methods
    (manifest/capabilities) work — the registry may load templates for schema
    validation, docs, and scaffolding tests (31 §10). Operational methods
    (credential validation, discovery, generation) raise
    :class:`TemplateProviderInvoked`; health always reports UNAVAILABLE.
    """

    def __init__(self, manifest: ProviderManifest) -> None:
        if not manifest.is_template:
            msg = "TemplateProviderAdapter requires a manifest with is_template=true"
            raise ValueError(msg)
        self._manifest = manifest

    # -- declarative surface (allowed for templates, 31 §10) --------------------

    def get_manifest(self) -> ProviderManifest:
        """Return the template's self-declaration (loadable per 31 §10)."""
        return self._manifest

    async def get_capabilities(self) -> ProviderCapabilities:
        """Return declared capabilities — declaration only, never execution."""
        return self._manifest.capabilities

    # -- operational surface (must never work for templates, 31 §11) ------------

    async def validate_credential(self, credential_ref: str) -> CredentialHealth:
        """Templates hold no credentials; any ref presented to one is invalid.

        Returns INVALID rather than raising: credential *checking* is a safe,
        read-only question, and the answer for a template is always "no".
        The opaque ``credential_ref`` is echoed back unresolved (20 §5).
        """
        return CredentialHealth(
            credential_ref=credential_ref,
            status=CredentialStatus.INVALID,
            detail="template provider holds no credentials (31 §7)",
        )

    async def discover_models(
        self, account_id: UUID | None = None
    ) -> list[DiscoveredModel]:
        """Templates declare ``models.discovery: not_implemented`` (31 §7)."""
        raise TemplateProviderInvoked(self._manifest.id, "discover_models")

    async def generate(
        self, request: ProviderGenerateRequest
    ) -> ProviderGenerateResponse:
        """31 §11: templates cannot execute generation — always raises."""
        raise TemplateProviderInvoked(self._manifest.id, request.operation.value)

    async def health_check(self, scope: HealthScope) -> ProviderHealth:
        """31 §10: real_provider_required providers cannot pass health checks."""
        return ProviderHealth(
            provider_id=self._manifest.id,
            state=ProviderHealthState.UNAVAILABLE,
            detail="non-functional scaffold template (real_provider_required)",
        )

    def normalize_error(self, error: object) -> ProviderError:
        """Even template failures normalize to the 30 §14 shape."""
        if isinstance(error, TemplateProviderInvoked):
            return ProviderError(
                category=ProviderErrorCategory.UNSUPPORTED_CAPABILITY,
                retryable=False,
                safe_message="template provider is non-functional (31 §7)",
            )
        return ProviderError(
            category=ProviderErrorCategory.NON_RETRYABLE_ERROR,
            retryable=False,
            safe_message="template provider cannot produce provider errors",
        )
