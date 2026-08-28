"""Hermetic persistence gates (ADR-0002) — no live database required.

Three protections:

1. Contract/schema parity — every identity contract field has a same-named
   column (tables map contracts; they never redefine truth, 40 §2.1).
2. Offline DDL compile — CREATE TABLE SQL renders for the postgresql
   dialect (catches metadata errors without a server).
3. Migration/metadata parity — the hand-written migration chain creates
   exactly the tables/columns/constraint names the metadata declares (as a
   UNION across all revisions), each downgrade fully reverses its upgrade
   (40 §8.2 rollback), and the revision chain is linear and unbroken.

Real upgrade/downgrade smoke tests against an ephemeral Postgres run
outside this hermetic path (ADR-0002 Testing note).
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from core.contracts.identity import Project, Tenant, User, Workspace
from core.contracts.plan import Plan
from infrastructure.db.tables import metadata, plans, projects, tenants, users, workspaces

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "infrastructure/db/migrations/versions"
MIGRATION_SOURCES = {
    path.name: path.read_text(encoding="utf-8")
    for path in sorted(VERSIONS_DIR.glob("*.py"))
    if path.name != "__init__.py"
}
ALL_SOURCE = "\n".join(MIGRATION_SOURCES.values())

CONTRACT_TABLE_PAIRS = [
    (Tenant, tenants),
    (User, users),
    (Workspace, workspaces),
    (Project, projects),
    (Plan, plans),
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

    def test_plans_is_platform_catalog_not_tenant_scoped(self) -> None:
        # Recorded derivation: the tenant side of the relation is
        # tenants.plan_id — plans itself carries NO tenant_id.
        assert "tenant_id" not in plans.columns
        assert plans.columns["name"].unique  # the 21 §5 `plan:` lookup key

    def test_tenants_plan_id_is_now_a_real_fk(self) -> None:
        # The 0001-era "plain UUID, FK lands with the plans migration"
        # deferral is closed by 0002.
        fk_targets = {fk.column.table.name for fk in tenants.columns["plan_id"].foreign_keys}
        assert fk_targets == {"plans"}

    def test_plans_json_defaults_are_empty_objects(self) -> None:
        # Deny-by-default: the DB default must parse to contract defaults
        # that grant NOTHING — never more than the contract grants.
        for column_name in ("limits", "entitlements", "model_control"):
            column = plans.columns[column_name]
            assert not column.nullable
            default = column.server_default
            assert default is not None and str(default.arg) == "{}"  # type: ignore[union-attr]
        # And the contract parse of that DB default grants nothing.
        empty = Plan(id=uuid4(), name="x", limits={}, entitlements={}, model_control={})
        assert empty.limits.task_units == 0
        assert empty.entitlements == {} and empty.model_control == {}


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
    """The reviewed migration chain must match the metadata it claims to map."""

    def test_migration_chain_creates_every_metadata_table(self) -> None:
        created = set(re.findall(r'op\.create_table\(\s*"(\w+)"', ALL_SOURCE))
        assert created == {t.name for t in metadata.sorted_tables}

    def test_no_table_is_created_twice_across_the_chain(self) -> None:
        created = re.findall(r'op\.create_table\(\s*"(\w+)"', ALL_SOURCE)
        assert len(created) == len(set(created)), f"duplicate create_table: {created}"

    def test_migrations_declare_every_column_of_each_table(self) -> None:
        for table in metadata.sorted_tables:
            block = self._table_block(table)
            declared = set(re.findall(r'sa\.Column\(\s*"(\w+)"', block))
            assert declared == {c.name for c in table.columns}, table.name

    def test_each_downgrade_drops_everything_its_upgrade_creates(self) -> None:
        for name, source in MIGRATION_SOURCES.items():
            created_tables = set(re.findall(r'op\.create_table\(\s*"(\w+)"', source))
            dropped_tables = set(re.findall(r'op\.drop_table\("(\w+)"\)', source))
            assert created_tables == dropped_tables, name
            created_ix = set(re.findall(r'op\.create_index\("(\w+)"', source))
            dropped_ix = set(re.findall(r'op\.drop_index\("(\w+)"', source))
            assert created_ix == dropped_ix, name
            created_fk = set(re.findall(r'op\.create_foreign_key\(\s*"(\w+)"', source))
            dropped_fk = set(re.findall(r'op\.drop_constraint\("(fk_\w+)"', source))
            assert created_fk == dropped_fk, name

    def test_revision_chain_is_linear_and_unbroken(self) -> None:
        revisions: dict[str, str | None] = {}
        for name, source in MIGRATION_SOURCES.items():
            rev = re.search(r'revision: str = "(\w+)"', source)
            parent = re.search(r'down_revision: str \| None = (?:"(\w+)"|None)', source)
            assert rev and parent, name
            revisions[rev.group(1)] = parent.group(1)
        roots = [r for r, p in revisions.items() if p is None]
        assert roots == ["0001"]
        # Every non-root parent must exist; each revision has at most one child.
        parents = [p for p in revisions.values() if p is not None]
        assert set(parents) <= set(revisions), "broken chain: missing parent revision"
        assert len(parents) == len(set(parents)), "branched chain: parent reused"

    def test_0002_lands_the_tenants_plan_fk(self) -> None:
        source = MIGRATION_SOURCES["0002_plans.py"]
        assert 'down_revision: str | None = "0001"' in source
        assert '"fk_tenants_plan_id_plans"' in source
        assert 'ondelete="RESTRICT"' in source

    def _table_block(self, table: Table) -> str:
        start = ALL_SOURCE.index(f'op.create_table(\n        "{table.name}"')
        end = ALL_SOURCE.index("op.create_", start + 1)
        return ALL_SOURCE[start:end]
