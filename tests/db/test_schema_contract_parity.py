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

from core.contracts.conversation import Conversation, Message
from core.contracts.domain import Credential, Model, Provider
from core.contracts.evaluation import EvaluationRecord
from core.contracts.execution import Execution, ExecutionNode
from core.contracts.identity import Project, Tenant, User, Workspace
from core.contracts.learning import LearningSample
from core.contracts.memory import MemoryItem
from core.contracts.permission import Permission
from core.contracts.plan import Plan
from core.contracts.roles import Role
from core.contracts.skills import Skill
from core.contracts.usage import UsageLedger
from infrastructure.db.tables import (
    conversations,
    credentials,
    evaluations,
    execution_nodes,
    executions,
    learning_samples,
    memory_embeddings,
    memory_items,
    messages,
    metadata,
    models,
    permissions,
    plans,
    projects,
    providers,
    roles,
    skills,
    tenants,
    usage_ledger,
    users,
    workspaces,
)

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
    (Role, roles),
    (Permission, permissions),
    (Skill, skills),
    (Model, models),
    (Provider, providers),
    (Conversation, conversations),
    (Message, messages),
    (MemoryItem, memory_items),
    (Execution, executions),
    (ExecutionNode, execution_nodes),
    (UsageLedger, usage_ledger),
    (EvaluationRecord, evaluations),
    (LearningSample, learning_samples),
    (Credential, credentials),
]
# memory_embeddings is deliberately NOT in CONTRACT_TABLE_PAIRS: 03 §3
# defines NO embedding field on MemoryItem — the table is infrastructure
# retrieval data (41 §6 pgvector), not a contract entity mapping.


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
        for table in (
            users,
            workspaces,
            projects,
            conversations,
            memory_items,
            executions,
            usage_ledger,
            evaluations,
        ):
            assert "tenant_id" in table.columns
            indexed = {col.name for ix in table.indexes for col in ix.columns}
            assert "tenant_id" in indexed, f"{table.name}: tenant_id not indexed"

    def test_messages_isolation_flows_through_conversation_fk(self) -> None:
        # 03 §3 defines NO tenant_id on Message — isolation resolves through
        # the tenant-scoped parent. The FK must exist, RESTRICT, and be
        # indexed (20 §6 checks resolve through it).
        assert "tenant_id" not in messages.columns
        fks = {fk.column.table.name for fk in messages.columns["conversation_id"].foreign_keys}
        assert fks == {"conversations"}
        indexed = {col.name for ix in messages.indexes for col in ix.columns}
        assert "conversation_id" in indexed

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

    def test_roles_and_permissions_are_platform_catalogs(self) -> None:
        # Recorded derivations: role applicability is the 03 §6 `scope`
        # field; per-tenant permission grants are firewall policy DATA.
        assert "tenant_id" not in roles.columns
        assert "tenant_id" not in permissions.columns
        assert permissions.columns["key"].unique  # the 20 §4 dotted identifier

    def test_roles_name_version_composite_unique(self) -> None:
        composites = {
            tuple(sorted(c.name for c in constraint.columns))
            for constraint in roles.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        assert ("name", "version") in composites

    def test_skills_is_platform_metadata_catalog(self) -> None:
        # 41 §6 "skills metadata": catalog row only — no tenant_id (03 §6
        # defines none); (name, version) composite unique like roles;
        # status has NO server_default — lifecycle stage must be explicit
        # (14 §9 forbids implicit activation).
        assert "tenant_id" not in skills.columns
        composites = {
            tuple(sorted(c.name for c in constraint.columns))
            for constraint in skills.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        assert ("name", "version") in composites
        assert skills.columns["status"].server_default is None
        assert not skills.columns["status"].nullable

    def test_models_providers_are_platform_registries(self) -> None:
        # 03 §4 defines no tenant_id; tenant visibility is admin policy
        # DATA (21 §10). Registry lookup keys are unique.
        assert "tenant_id" not in models.columns
        assert "tenant_id" not in providers.columns
        assert models.columns["model_key"].unique
        assert providers.columns["provider_key"].unique

    def test_no_credential_value_columns_in_registries(self) -> None:
        # 41 §6 verbatim: credentials live in the Secret Manager — never a
        # column. (Same 20 §5 posture the users table already enforces.)
        forbidden = {"credential", "credential_value", "secret", "api_key", "token"}
        for table in (models, providers):
            assert not forbidden & {c.name for c in table.columns}, table.name

    def test_agent_capability_has_no_permissive_default(self) -> None:
        # 30 §4.3: unknown must NOT read as supported — nullable with no
        # server_default; NULL parses to contract None (undeclared).
        column = models.columns["agent_capability"]
        assert column.nullable and column.server_default is None

    def test_executions_idempotency_key_unique_with_default_null_treatment(self) -> None:
        # 10 §10: same tenant + same idempotency key must not create
        # duplicate executions. The key is nullable BY SPEC — executions
        # WITHOUT a key must never collide, so this constraint must use
        # the Postgres DEFAULT null treatment (NULLS DISTINCT), the
        # OPPOSITE posture from the memory upsert key.
        uniques = {
            tuple(sorted(c.name for c in constraint.columns)): constraint
            for constraint in executions.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        key = ("idempotency_key", "tenant_id")
        assert key in uniques
        opts = uniques[key].dialect_options["postgresql"]
        assert not opts.get("nulls_not_distinct")
        assert executions.columns["idempotency_key"].nullable

    def test_execution_nodes_isolation_flows_through_execution_fk(self) -> None:
        # 03 §5 defines NO tenant_id on ExecutionNode — isolation resolves
        # through the tenant-scoped parent (same posture as messages).
        assert "tenant_id" not in execution_nodes.columns
        fk_targets = {
            fk.column.table.name
            for fk in execution_nodes.columns["execution_id"].foreign_keys
        }
        assert fk_targets == {"executions"}
        indexed = {col.name for ix in execution_nodes.indexes for col in ix.columns}
        assert "execution_id" in indexed
        # Per-run node_key uniqueness — the DB enforces the service's
        # InvalidPipeline invariant.
        composites = {
            tuple(sorted(c.name for c in constraint.columns))
            for constraint in execution_nodes.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        assert ("execution_id", "node_key") in composites

    def test_credentials_store_ref_only_never_secret_value(self) -> None:
        # 20 §5 / 40 §5.1: the DB stores credential_ref ONLY — no
        # secret-value column exists or ever will.
        forbidden = {"secret", "secret_value", "api_key", "token", "password", "value"}
        assert not forbidden & {c.name for c in credentials.columns}
        # UNIQUE ref: store() mints a new immutable ref per custody record.
        assert credentials.columns["credential_ref"].unique
        # Ownership union (platform|tenant|user): owner_id nullable BY
        # SPEC, and deliberately NO polymorphic FK (recorded).
        owner = credentials.columns["owner_id"]
        assert owner.nullable and not list(owner.foreign_keys)
        # provider linkage real: FK + index.
        provider_col = credentials.columns["provider_id"]
        assert {fk.column.table.name for fk in provider_col.foreign_keys} == {"providers"}
        indexed = {col.name for ix in credentials.indexes for col in ix.columns}
        assert "provider_id" in indexed
        # Lifecycle state is an explicit claim.
        assert credentials.columns["status"].server_default is None
        assert not credentials.columns["status"].nullable

    def test_learning_samples_nullable_tenant_and_zero_grant_defaults(self) -> None:
        # tenant_id NULLABLE BY SPEC (03 §7 uuid|null) — deliberately NOT
        # in the NOT-NULL tenant-scoped matrix; attributed samples still
        # get FK + index (20 §6 for tenant-filtered queries).
        column = learning_samples.columns["tenant_id"]
        assert column.nullable
        assert {fk.column.table.name for fk in column.foreign_keys} == {"tenants"}
        indexed = {col.name for ix in learning_samples.indexes for col in ix.columns}
        assert "tenant_id" in indexed
        # 22 §9 "source trace exists": source_execution_id FK + indexed.
        source = learning_samples.columns["source_execution_id"]
        assert not source.nullable
        assert {fk.column.table.name for fk in source.foreign_keys} == {"executions"}
        assert "source_execution_id" in indexed
        # dataset_id: PLAIN nullable UUID — no Dataset table in 41 §6, so
        # NO FK target may be invented.
        dataset = learning_samples.columns["dataset_id"]
        assert dataset.nullable and not list(dataset.foreign_keys)
        # Deny-by-default: DB defaults == contract defaults — a new row
        # grants NOTHING toward the 22 §9 training gate.
        assert str(learning_samples.columns["eligibility"].server_default.arg) == "pending"  # type: ignore[union-attr]
        assert (
            str(learning_samples.columns["sanitization_state"].server_default.arg)  # type: ignore[union-attr]
            == "pending"
        )
        assert (
            str(learning_samples.columns["verification_level"].server_default.arg)  # type: ignore[union-attr]
            == "RAW"
        )

    def test_evaluations_execution_level_attachment_and_separate_judgment(self) -> None:
        # R049 boundary (d): evaluation attaches at EXECUTION level in
        # MVP — NO node_id column (03 §8 node-level stays representable
        # later, never silently pre-built).
        assert "node_id" not in evaluations.columns
        column = evaluations.columns["execution_id"]
        # NOT unique — multiple evaluations per execution are permitted.
        assert not column.unique
        assert {fk.column.table.name for fk in column.foreign_keys} == {"executions"}
        indexed = {col.name for ix in evaluations.indexes for col in ix.columns}
        assert "execution_id" in indexed
        # 22 §4: score and confidence are SEPARATE nullable columns —
        # never merged into one number.
        assert evaluations.columns["score"].nullable
        assert evaluations.columns["confidence"].nullable
        assert "quality" not in evaluations.columns
        # graders default '[]' == contract default (); level must be an
        # explicit claim (no server_default).
        assert str(evaluations.columns["graders"].server_default.arg) == "[]"  # type: ignore[union-attr]
        assert evaluations.columns["level"].server_default is None
        assert not evaluations.columns["level"].nullable

    def test_usage_ledger_one_entry_per_execution_and_honest_defaults(self) -> None:
        # core/usage/memory.py keys the ledger by execution_id and a
        # reservation resolves exactly once — execution_id UNIQUE + FK.
        column = usage_ledger.columns["execution_id"]
        assert column.unique
        assert {fk.column.table.name for fk in column.foreign_keys} == {"executions"}
        # Deny-by-default: DB defaults equal contract defaults — an
        # unresolved entry claims NO settled consumption.
        assert str(usage_ledger.columns["units_settled"].server_default.arg) == "0"  # type: ignore[union-attr]
        assert str(usage_ledger.columns["modality_costs"].server_default.arg) == "{}"  # type: ignore[union-attr]
        # Lifecycle stage must be explicit (same posture as skills.status).
        assert usage_ledger.columns["status"].server_default is None
        assert not usage_ledger.columns["status"].nullable

    def test_memory_items_upsert_key_is_nulls_not_distinct_unique(self) -> None:
        # core/memory/ports.py keys upserts by (tenant, user, scope, key);
        # user_id NULL (tenant-shared, 03 §3) must collide like a value —
        # NULLS NOT DISTINCT — or tenant-shared upserts would duplicate.
        uniques = {
            tuple(sorted(c.name for c in constraint.columns)): constraint
            for constraint in memory_items.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        }
        key = ("key", "scope", "tenant_id", "user_id")
        assert key in uniques
        assert uniques[key].dialect_options["postgresql"]["nulls_not_distinct"] is True
        # And the sensitivity DB default matches the contract default (LOW).
        column = memory_items.columns["sensitivity"]
        assert not column.nullable
        assert str(column.server_default.arg) == "low"  # type: ignore[union-attr]

    def test_memory_embeddings_is_infrastructure_retrieval_data(self) -> None:
        # Not a contract entity: exactly one row per memory item (PK = FK,
        # CASCADE — derived data never outlives its source); model_key
        # records the producing model (vectors from incompatible spaces
        # are never compared); embedding dimension-UNCONSTRAINED (the
        # embedding model is admin config; no ANN index until pinned).
        assert {c.name for c in memory_embeddings.columns} == {
            "memory_item_id",
            "model_key",
            "embedding",
        }
        pk_column = memory_embeddings.columns["memory_item_id"]
        assert pk_column.primary_key
        fks = list(pk_column.foreign_keys)
        assert len(fks) == 1
        assert fks[0].column.table.name == "memory_items"
        assert fks[0].ondelete == "CASCADE"
        assert memory_embeddings.columns["embedding"].type.dim is None  # type: ignore[union-attr]
        assert not memory_embeddings.indexes  # no ANN index until a model is pinned

    def test_permissions_db_default_is_most_restrictive(self) -> None:
        # Deny-by-default: the DB default must equal the contract default
        # (ALWAYS) — the DB can never grant more than the contract.
        column = permissions.columns["approval"]
        assert not column.nullable
        assert column.server_default is not None
        assert str(column.server_default.arg) == "always"  # type: ignore[union-attr]
        assert Permission(id=uuid4(), key="x").approval.value == "always"


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

    def test_0007_creates_pgvector_extension_idempotently(self) -> None:
        # The vector column type requires the extension; upgrade must
        # create it idempotently. Downgrade must NOT drop it (extension
        # lifecycle is database-level administration).
        source = MIGRATION_SOURCES["0007_memory.py"]
        assert 'op.execute("CREATE EXTENSION IF NOT EXISTS vector")' in source
        assert "DROP EXTENSION" not in source
        assert 'down_revision: str | None = "0006"' in source
        assert "postgresql_nulls_not_distinct=True" in source
        assert 'ondelete="CASCADE"' in source

    def test_0002_lands_the_tenants_plan_fk(self) -> None:
        source = MIGRATION_SOURCES["0002_plans.py"]
        assert 'down_revision: str | None = "0001"' in source
        assert '"fk_tenants_plan_id_plans"' in source
        assert 'ondelete="RESTRICT"' in source

    def _table_block(self, table: Table) -> str:
        start = ALL_SOURCE.index(f'op.create_table(\n        "{table.name}"')
        # The block ends at the next op.* call — or at end-of-source when
        # this create_table is the last operation in the chain.
        end = ALL_SOURCE.find("op.create_", start + 1)
        if end == -1:
            end = len(ALL_SOURCE)
        return ALL_SOURCE[start:end]
