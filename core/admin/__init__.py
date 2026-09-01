"""Admin control plane (MVP Phase 7 slice 3, 41 §46).

Public surface: the config-lifecycle service over the EXISTING registries
plus its errors. Contracts live in ``core/contracts/admin.py`` (consumers
import that submodule directly, matching the Phase 6/7 convention).
"""

from core.admin.errors import (
    AdminError,
    ChangeNotFound,
    InactiveAdminArea,
    InvalidLifecycleTransition,
    RollbackUnavailable,
)
from core.admin.service import (
    AdminConfigService,
    AdminPersistencePort,
    RoutingWeightsPort,
    UsageConfigurationPort,
)

__all__ = [
    "AdminConfigService",
    "AdminError",
    "AdminPersistencePort",
    "ChangeNotFound",
    "InactiveAdminArea",
    "InvalidLifecycleTransition",
    "RollbackUnavailable",
    "RoutingWeightsPort",
    "UsageConfigurationPort",
]
