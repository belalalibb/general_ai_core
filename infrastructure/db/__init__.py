"""Persistence infrastructure — PostgreSQL via SQLAlchemy 2.x async (ADR-0002).

Boundary rules (enforced by import-linter):

- ALL persistence code (engine, sessions, table metadata, migrations) lives
  here; ``core/`` never imports sqlalchemy/alembic/asyncpg/pgvector.
- Tables MAP the Pydantic contracts in ``core/contracts`` — they never
  redefine truth (40 §2.1 contract-first).
- PostgreSQL is the ONLY source of truth (40 §5.1).
"""
