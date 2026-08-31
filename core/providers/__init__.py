"""Provider boundary — behavioral port (30 §8) + Core-side errors.

MVP Phase 4 (41 §43). Registries live in ``core/providers/registry.py``
(T-IMPL-019). Real adapters live under ``providers/`` (top-level package),
NEVER here: core must not import provider internals (40 §6.2 contract).
"""

from core.providers.accounts import (
    LEASE_RESOURCE_PREFIX,
    AccountPool,
    AccountPoolManager,
    lease_resource_for,
)
from core.providers.errors import (
    BindingNotFound,
    DuplicateRegistration,
    ModelNotRegistered,
    NoEligibleAccount,
    PoolOwnershipViolation,
    ProviderBoundaryError,
    ProviderNotEligible,
    ProviderNotRegistered,
)
from core.providers.onboarding import (
    OnboardingRefused,
    OnboardingReport,
    ProviderOnboardingService,
)
from core.providers.ports import (
    ProviderAccountLifecyclePort,
    ProviderAdapterPort,
    ProviderAgentModulePort,
    ProviderAssetsPort,
)
from core.providers.registry import (
    TEMPLATE_DISABLED_STATUS,
    BindingRegistry,
    ModelRegistry,
    ProviderRegistry,
    RegisteredProvider,
    aggregate_provider_health,
)

__all__ = [
    "LEASE_RESOURCE_PREFIX",
    "OnboardingRefused",
    "OnboardingReport",
    "ProviderOnboardingService",
    "TEMPLATE_DISABLED_STATUS",
    "AccountPool",
    "AccountPoolManager",
    "BindingNotFound",
    "BindingRegistry",
    "DuplicateRegistration",
    "ModelNotRegistered",
    "ModelRegistry",
    "NoEligibleAccount",
    "PoolOwnershipViolation",
    "ProviderAccountLifecyclePort",
    "ProviderAdapterPort",
    "ProviderAgentModulePort",
    "ProviderAssetsPort",
    "ProviderBoundaryError",
    "ProviderNotEligible",
    "ProviderNotRegistered",
    "ProviderRegistry",
    "RegisteredProvider",
    "aggregate_provider_health",
    "lease_resource_for",
]
