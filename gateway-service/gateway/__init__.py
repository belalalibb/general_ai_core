"""Provider Gateway — data-plane service (ADR-0008, G1 skeleton).

Dependency direction (fixed, enforced by convention + tests):

    providers/*  --imports-->  gateway.contracts  <--imports--  gateway core  <--  app.py

Providers NEVER import ``app`` or gateway core modules; ``app.py`` contains
zero logic. Every provider package is testable in isolation against
``gateway.contracts`` alone.
"""

API_VERSION = "v1"
