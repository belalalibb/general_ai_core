"""Hermetic persistence gates (ADR-0002) — no live database required.

Three protections:

1. Contract/schema parity — every identity contract field has a same-named
   column (tables map contracts; they never redefine truth, 40 §2.1).
2. Offline DDL compile — CREATE TABLE SQL renders for the postgresql
   dialect (catches metadata errors without a server).
3. Migration/metadata parity — the hand-written 0001 migration creates
   exactly the tables/columns/constraint names the metadata declares, and
   downgrade fully reverses upgrade (40 §8.2 rollback).

Real upgrade/downgrade smoke tests against an ephemeral Postgres run
outside this hermetic path (ADR-0002 Testing note).
"""

from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from core.contracts.identity import Project, Tenant, User, Workspace
from infrastructure.db.tables import metadata, projects, tenants, users, workspaces

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "infrastructure/db/migrations/versions/0001_identity_tenancy.py"
)

CONTRACT_TABLE_PAIRS = [
    (Tenant, tenants),
    (User, users),
    (Workspace, workspaces),
    (Project, projects),
]


class TestContractSchemaParity:
    def test_every_contract_field_has_a_column(self) -> None:
        for contract, table in CONTRACT_TABLE_PAIRS:
            fields = set(contract.model_fields)
            columns = {c.name for c in table.columns}
            missing = fields - columns
            assert not missing, f"{table.name}: contract fields without columns: {missing}"

    def test_no_extra_columns_beyond_contract(self) -> None:
        # Schema must not invent state the contract does not define.
        for contract, table in CONTRACT_TABLE_PAIRS:
            extra = {c.name for c in table.columns} - set(contract.model_fields)
            assert not extra, f"{table.name}: columns without contract fields: {extra}"

    def test_tenant_scoped_tables_carry_indexed_tenant_id(self) -> None:
        # 20 §6 — tenant isolation at the schema level.
        for table in (users, workspaces, projects):
            assert "tenant_id" in table.columns
            indexed = {col.name for ix in table.indexes for col in ix.columns}
            assert "tenant_id" in indexed, f"{table.name}: tenant_id not indexed"

    def test_users_email_unique_and_no_credential_columns(self) -> None:
        assert users.columns["email"].unique
        # 20 §5 — no credential material in identity tables (this slice).
        forbidden = {"password", "password_hash", "secret", "token"}
        assert not forbidden & {c.name for c in users.columns}


class TestOfflineDdlCompile:
    def test_all_tables_compile_for_postgresql(self) -> None:
        dialect = postgresql.dialect()
        for table in metadata.sorted_tables:
            sql = str(CreateTable(table).compile(dialect=dialect))
            assert f"CREATE TABLE {table.name}" in sql

    def test_closed_set_checks_render_contract_values(self) -> None:
        dialect = postgresql.dialect()
        tenants_sql = str(CreateTable(tenants).compile(dialect=dialect))
        assert "'personal'" in tenants_sql and "'organization'" in tenants_sql
        users_sql = str(CreateTable(users).compile(dialect=dialect))
        for value in ("'active'", "'disabled'", "'pending'"):
            assert value in users_sql


class TestMigrationMetadataParity:
    """The reviewed 0001 migration must match the metadata it claims to map."""

    source = MIGRATION.read_text(encoding="utf-8")

    def test_migration_creates_every_metadata_table(self) -> None:
        created = set(re.findall(r'op\.create_table\(\s*"(\w+)"', self.source))
        assert created == {t.name for t in metadata.sorted_tables}

    def test_migration_declares_every_column_of_each_table(self) -> None:
        for table in metadata.sorted_tables:
            block = self._table_block(table)
            declared = set(re.findall(r'sa\.Column\(\s*"(\w+)"', block))
            assert declared == {c.name for c in table.columns}, table.name

    def test_downgrade_drops_everything_upgrade_creates(self) -> None:
        created_tables = set(re.findall(r'op\.create_table\(\s*"(\w+)"', self.source))
        dropped_tables = set(re.findall(r'op\.drop_table\("(\w+)"\)', self.source))
        assert created_tables == dropped_tables
        created_ix = set(re.findall(r'op\.create_index\("(\w+)"', self.source))
        dropped_ix = set(re.findall(r'op\.drop_index\("(\w+)"', self.source))
        assert created_ix == dropped_ix

    def test_migration_has_revision_0001_and_no_parent(self) -> None:
        assert 'revision: str = "0001"' in self.source
        assert "down_revision: str | None = None" in self.source

    def _table_block(self, table: Table) -> str:
        start = self.source.index(f'op.create_table(\n        "{table.name}"')
        end = self.source.index("op.create_", start + 1)
        return self.source[start:end]
