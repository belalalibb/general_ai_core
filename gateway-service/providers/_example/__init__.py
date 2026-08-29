"""EXAMPLE PROVIDER — not a live provider. Never registered in a live registry.

Purpose: the WORKING reference showing the three-layer model in practice.
Copy this package (or providers/_template/) to build a real provider.

    Layer 1 (free)      -> _engine.py + _wire.py   internal subsystem, any shape
    Layer 2 (mandatory) -> adapter.py              the facade: translates to contract
    Layer 3 (fixed)     -> gateway.contracts       imported, never modified

The ``_`` prefix means the provider registry's auto-discovery SKIPS this
package by design.
"""
