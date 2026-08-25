"""Contract layer — the single source of truth for schemas and types.

Authority: docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md
Rule (41 Phase 1): no Contract imports a specific Implementation.
"""

from core.contracts.base import ContractModel
from core.contracts.errors import ErrorCode, ErrorDetail, ErrorEnvelope

__all__ = [
    "ContractModel",
    "ErrorCode",
    "ErrorDetail",
    "ErrorEnvelope",
]
