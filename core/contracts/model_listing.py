"""GET /v1/models response shapes (10 §6) — the public model listing.

Contract authority:

- docs/ai_orchestration_pack/final_docs_v3/10_API_CONTRACTS.md §6
  (``models`` array: id / name / tier / modalities / capabilities /
  availability — the row shape carried exactly).
- 41 §21 (FINAL Phase 18: GET /v1/models is a supporting public endpoint).
- 03 §4 (``Model`` entity + ``ProviderModelBinding.availability`` — the
  source records this module PROJECTS; nothing here re-defines them).

Recorded derivation decisions (no doc states these explicitly):

- ``name`` = ``Model.model_key``. The 10 §6 example (``example-max``) and
  the 10 §13.3/13.4 explicit-model references (``model_coding_strong``)
  are key-style stable identifiers, not display strings — the listing
  exposes the identifier users reference in model policies;
  ``display_name`` stays a UI concern.
- ``id`` = the registry UUID rendered as a string (10 §6 ``model_uuid``).
- ``availability`` is a PER-BINDING fact (03 §4 — "availability is a
  per-binding fact, never inferred from provider or model records"), but
  the 10 §6 row carries ONE availability value per model. The projection
  is the BEST availability across the model's bindings, in the closed
  03 §4 value order: any AVAILABLE binding ⇒ ``available``; else any
  DEGRADED binding ⇒ ``degraded``; else ⇒ ``unavailable``. A model with
  NO bindings is ``unavailable`` — deny-by-default (20 §4): a model no
  provider serves is not offered as available.
- ``tier``/``modalities`` render enum VALUES (the API surface speaks
  strings; the closed sets stay owned by the domain contracts).
"""

from __future__ import annotations

from pydantic import Field

from core.contracts.base import BoundedStr, ContractModel
from core.contracts.domain import BindingAvailability, Model, ProviderModelBinding


def derive_model_availability(
    bindings: list[ProviderModelBinding],
) -> BindingAvailability:
    """Project per-binding availability onto one 10 §6 row value.

    Best-across-bindings, closed 03 §4 set; empty ⇒ UNAVAILABLE
    (deny-by-default — see module docstring).
    """
    states = {binding.availability for binding in bindings}
    if BindingAvailability.AVAILABLE in states:
        return BindingAvailability.AVAILABLE
    if BindingAvailability.DEGRADED in states:
        return BindingAvailability.DEGRADED
    return BindingAvailability.UNAVAILABLE


class ModelListEntry(ContractModel):
    """One ``models`` row of GET /v1/models (10 §6)."""

    id: BoundedStr
    name: BoundedStr
    tier: BoundedStr
    modalities: list[BoundedStr] = Field(default_factory=list)
    capabilities: list[BoundedStr] = Field(default_factory=list)
    availability: BindingAvailability

    @classmethod
    def from_model(cls, model: Model, bindings: list[ProviderModelBinding]) -> ModelListEntry:
        """Project a registry Model + its bindings onto the 10 §6 row."""
        return cls(
            id=str(model.id),
            name=model.model_key,
            tier=model.tier.value,
            modalities=[modality.value for modality in model.modalities],
            capabilities=list(model.capabilities),
            availability=derive_model_availability(bindings),
        )


class ModelsListResponse(ContractModel):
    """GET /v1/models response (10 §6): the ``models`` array envelope."""

    models: list[ModelListEntry] = Field(default_factory=list)
