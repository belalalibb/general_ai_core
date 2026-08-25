"""Capability Firewall skeleton (MVP Phase 2, 41 §41).

Deterministic deny-by-default evaluator over the 20 §4 decision contract.
"""

from core.security.firewall import CapabilityFirewall, TenantPolicy

__all__ = [
    "CapabilityFirewall",
    "TenantPolicy",
]
