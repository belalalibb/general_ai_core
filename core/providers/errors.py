"""Provider-boundary errors raised by Core-side provider plumbing.

These are CORE-side failures (registry/eligibility decisions), distinct from
the normalized ``ProviderError`` contract (30 §14) that ADAPTERS return for
provider-side failures.
"""

from __future__ import annotations


class ProviderBoundaryError(Exception):
    """Base class for Core-side provider-boundary failures."""


class ProviderNotRegistered(ProviderBoundaryError):
    """No provider with this key/id exists in the registry."""


class ProviderNotEligible(ProviderBoundaryError):
    """Provider exists but is not eligible for the requested task.

    Raised for: undeclared operation/capability (30 §5 — "Provider is
    ineligible for that task"), template/non-functional providers
    (31 §10), and disabled providers.
    """


class ModelNotRegistered(ProviderBoundaryError):
    """No model with this key/id exists in the model registry."""


class BindingNotFound(ProviderBoundaryError):
    """No (provider, model) binding exists, or it is unavailable."""


class DuplicateRegistration(ProviderBoundaryError):
    """A provider/model/binding with the same identity is already registered."""


class NoEligibleAccount(ProviderBoundaryError):
    """No account passes the 30 §10.3 eligibility filters (or none can be
    leased, 30 §10.4) for the requested provider/policy/context."""


class PoolOwnershipViolation(ProviderBoundaryError):
    """A 30 §10.5 pool-ownership rule was violated: mixing platform and
    user-side credentials in one pool, or moving an account across sides."""
