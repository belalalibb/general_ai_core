"""Provider boundary — behavioral port (30 §8) + Core-side errors.

MVP Phase 4 (41 §43). Registries live in ``core/providers/registry.py``
(T-IMPL-019). Real adapters live under ``providers/`` (top-level package),
NEVER here: core must not import provider internals (40 §6.2 contract).
"""

from core.providers.errors import (
    BindingNotFound,
    DuplicateRegistration,
    ModelNotRegistered,
    ProviderBoundaryError,
    ProviderNotEligible,
    ProviderNotRegistered,
)
from core.providers.ports import (
    ProviderAccountLifecyclePort,
    ProviderAdapterPort,
    ProviderAssetsPort,
)

__all__ = [
    "BindingNotFound",
    "DuplicateRegistration",
    "ModelNotRegistered",
    "ProviderAccountLifecyclePort",
    "ProviderAdapterPort",
    "ProviderAssetsPort",
    "ProviderBoundaryError",
    "ProviderNotEligible",
    "ProviderNotRegistered",
]
