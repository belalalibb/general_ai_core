"""Context composer tests (13 §5/§4/§9/§10) — T-IMPL-027 slice.

Covers the applicable 13 §10 test list: scope conflict resolution, tenant
isolation (via the store ports), irrelevant memory excluded, context
budget respected, project memory overrides broader memory — plus
sensitivity gating, low-confidence exclusion, role admission delegation,
history tail composition, and deterministic output. Hermetic: in-memory
stores + registries only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from core.context import ContextBudgetExceeded, ContextComposer
from core.contracts.context import (
    ContextBlockType,
    ContextComposeRequest,
    ContextExclusionReason,
)
from core.contracts.conversation import (
    Conversation,
    ConversationStatus,
    Message,
    MessageRole,
)
from core.contracts.memory import MemoryItem, MemoryScope, MemorySensitivity
from core.contracts.roles import Role, RoleScope, RoleStatus
from core.memory import InMemoryConversationStore, InMemoryMemoryStore
from core.roles import RoleNotSelectable, RoleRegistry

TENANT = uuid4()
OTHER_TENANT = uuid4()
USER = uuid4()
OTHER_USER = uuid4()

NOW = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)

Stores = tuple[InMemoryMemoryStore, InMemoryConversationStore, RoleRegistry]


def make_item(
    *,
    key: str = "preferred_language",
    value: object = "ar",
    scope: MemoryScope = MemoryScope.PROJECT,
    tenant_id: UUID = TENANT,
    user_id: UUID | None = USER,
    confidence: float = 0.9,
    sensitivity: MemorySensitivity = MemorySensitivity.LOW,
) -> MemoryItem:
    return MemoryItem(
        id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        scope=scope,
        key=key,
        value=value,
        source="conversation",
        confidence=confidence,
        evidence_count=1,
        last_seen=NOW,
        sensitivity=sensitivity,
    )


def make_role(status: RoleStatus = RoleStatus.ACTIVE, objective: str = "Be helpful.") -> Role:
    return Role(
        id=uuid4(),
        scope=RoleScope.SYSTEM,
        name="assistant",
        version="1.0.0",
        objective=objective,
        status=status,
    )


@pytest.fixture()
def stores() -> Stores:
    return InMemoryMemoryStore(), InMemoryConversationStore(), RoleRegistry()


def make_composer(stores: Stores, min_confidence: float = 0.5) -> ContextComposer:
    memory, conversations, roles = stores
    return ContextComposer(
        memory_store=memory,
        conversation_store=conversations,
        role_registry=roles,
        min_confidence=min_confidence,
    )


def request(**overrides: object) -> ContextComposeRequest:
    payload: dict[str, object] = {
        "tenant_id": TENANT,
        "user_id": USER,
        "ask": "translate this",
    }
    payload.update(overrides)
    return ContextComposeRequest.model_validate(payload)


def _seed_history(conversations: InMemoryConversationStore, contents: list[str]) -> Conversation:
    conversation = Conversation(
        id=uuid4(),
        tenant_id=TENANT,
        user_id=USER,
        title="chat",
        status=ConversationStatus.ACTIVE,
    )
    conversations.create_conversation(conversation)
    for index, content in enumerate(contents):
        conversations.append_message(
            TENANT,
            Message(
                id=uuid4(),
                conversation_id=conversation.id,
                role=MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT,
                content=content,
                created_at=NOW.replace(minute=index),
            ),
        )
    return conversation


# --- basic composition ---------------------------------------------------------


def test_minimal_compose_is_just_the_ask(stores: Stores) -> None:
    composed = make_composer(stores).compose(request())
    assert [b.type for b in composed.context_blocks] == [ContextBlockType.ASK]
    assert composed.context_blocks[0].content == "translate this"
    assert composed.context_blocks[0].source == "request"
    assert composed.excluded == []


def test_block_order_role_memory_history_ask(stores: Stores) -> None:
    memory, conversations, roles = stores
    role = make_role()
    roles.register(role)
    memory.upsert(make_item())
    conversation = _seed_history(conversations, ["hello"])
    composed = make_composer(stores).compose(
        request(role_id=role.id, conversation_id=conversation.id)
    )
    assert [b.type for b in composed.context_blocks] == [
        ContextBlockType.ROLE,
        ContextBlockType.PREFERENCE,
        ContextBlockType.HISTORY,
        ContextBlockType.ASK,
    ]


def test_memory_block_carries_provenance_and_confidence(stores: Stores) -> None:
    memory, _, _ = stores
    stored = memory.upsert(make_item(confidence=0.92))
    composed = make_composer(stores).compose(request())
    block = composed.context_blocks[0]
    assert block.type is ContextBlockType.PREFERENCE
    assert block.source == f"memory:{stored.id}"
    assert block.confidence == 0.92
    assert block.content == 'preferred_language = "ar"'


def test_deterministic_same_inputs_same_output(stores: Stores) -> None:
    memory, _, _ = stores
    memory.upsert(make_item(key="a", scope=MemoryScope.TENANT, user_id=None))
    memory.upsert(make_item(key="b"))
    composer = make_composer(stores)
    assert composer.compose(request()) == composer.compose(request())


# --- 13 §4 scope conflict --------------------------------------------------------


def test_scope_conflict_more_specific_wins(stores: Stores) -> None:
    """13 §10: project memory overrides broader memory for the same key."""
    memory, _, _ = stores
    tenant_item = memory.upsert(make_item(value="en", scope=MemoryScope.TENANT, user_id=None))
    project_item = memory.upsert(make_item(value="ar", scope=MemoryScope.PROJECT))
    composed = make_composer(stores).compose(request())
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert [b.content for b in prefs] == ['preferred_language = "ar"']
    assert prefs[0].source == f"memory:{project_item.id}"
    conflict = [e for e in composed.excluded if e.reason is ContextExclusionReason.SCOPE_CONFLICT]
    assert [e.memory_id for e in conflict] == [tenant_item.id]


def test_scope_conflict_user_owned_beats_tenant_shared_same_tier(
    stores: Stores,
) -> None:
    """13 §4 'User' rank = user ownership within the same scope tier."""
    memory, _, _ = stores
    shared = memory.upsert(make_item(value="en", scope=MemoryScope.TENANT, user_id=None))
    owned = memory.upsert(make_item(value="ar", scope=MemoryScope.TENANT, user_id=USER))
    composed = make_composer(stores).compose(request())
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert prefs[0].source == f"memory:{owned.id}"
    assert any(
        e.memory_id == shared.id and e.reason is ContextExclusionReason.SCOPE_CONFLICT
        for e in composed.excluded
    )


def test_low_confidence_specific_loses_to_confident_broad(stores: Stores) -> None:
    """13 §4 'more specific wins UNLESS low confidence'."""
    memory, _, _ = stores
    weak_specific = memory.upsert(
        make_item(value="fr", scope=MemoryScope.CONVERSATION, confidence=0.2)
    )
    strong_broad = memory.upsert(
        make_item(value="ar", scope=MemoryScope.TENANT, user_id=None, confidence=0.9)
    )
    composed = make_composer(stores).compose(request())
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert prefs[0].source == f"memory:{strong_broad.id}"
    assert any(
        e.memory_id == weak_specific.id and e.reason is ContextExclusionReason.LOW_CONFIDENCE
        for e in composed.excluded
    )


def test_different_keys_do_not_conflict(stores: Stores) -> None:
    memory, _, _ = stores
    memory.upsert(make_item(key="language", scope=MemoryScope.TENANT, user_id=None))
    memory.upsert(make_item(key="tone", value="formal"))
    composed = make_composer(stores).compose(request())
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert len(prefs) == 2
    assert not composed.excluded


def test_memory_ordered_by_scope_priority_then_key(stores: Stores) -> None:
    memory, _, _ = stores
    memory.upsert(make_item(key="z_conv", scope=MemoryScope.CONVERSATION))
    memory.upsert(make_item(key="a_tenant", scope=MemoryScope.TENANT, user_id=None))
    memory.upsert(make_item(key="m_project", scope=MemoryScope.PROJECT))
    composed = make_composer(stores).compose(request())
    keys = [
        b.content.split(" = ")[0]
        for b in composed.context_blocks
        if b.type is ContextBlockType.PREFERENCE
    ]
    assert keys == ["z_conv", "m_project", "a_tenant"]


# --- 13 §9 gates ------------------------------------------------------------------


def test_high_sensitivity_denied_by_default(stores: Stores) -> None:
    memory, _, _ = stores
    item = memory.upsert(make_item(sensitivity=MemorySensitivity.HIGH))
    composed = make_composer(stores).compose(request())
    assert [b.type for b in composed.context_blocks] == [ContextBlockType.ASK]
    assert composed.excluded[0].reason is ContextExclusionReason.HIGH_SENSITIVITY
    assert composed.excluded[0].memory_id == item.id


def test_high_sensitivity_included_when_policy_allows(stores: Stores) -> None:
    memory, _, _ = stores
    memory.upsert(make_item(sensitivity=MemorySensitivity.HIGH))
    composed = make_composer(stores).compose(request(allow_high_sensitivity=True))
    assert any(b.type is ContextBlockType.PREFERENCE for b in composed.context_blocks)
    assert not composed.excluded


def test_low_confidence_excluded_with_named_reason(stores: Stores) -> None:
    memory, _, _ = stores
    item = memory.upsert(make_item(confidence=0.3))
    composed = make_composer(stores).compose(request())
    assert composed.excluded[0].reason is ContextExclusionReason.LOW_CONFIDENCE
    assert composed.excluded[0].memory_id == item.id


def test_relevance_allowlist_excludes_other_keys(stores: Stores) -> None:
    """13 §10 'irrelevant memory excluded' — MVP allowlist relevance."""
    memory, _, _ = stores
    relevant = memory.upsert(make_item(key="preferred_language"))
    noise = memory.upsert(make_item(key="favorite_color", value="blue"))
    composed = make_composer(stores).compose(request(relevant_keys=["preferred_language"]))
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert [b.source for b in prefs] == [f"memory:{relevant.id}"]
    assert composed.excluded[0].reason is ContextExclusionReason.IRRELEVANT
    assert composed.excluded[0].memory_id == noise.id


def test_tenant_isolation_via_store(stores: Stores) -> None:
    """13 §10 tenant isolation: other tenants' memory never composes."""
    memory, _, _ = stores
    memory.upsert(make_item(tenant_id=OTHER_TENANT, user_id=None, scope=MemoryScope.TENANT))
    composed = make_composer(stores).compose(request())
    assert [b.type for b in composed.context_blocks] == [ContextBlockType.ASK]
    assert not composed.excluded  # invisible at the port, not merely excluded


def test_other_users_memory_never_composes(stores: Stores) -> None:
    memory, _, _ = stores
    memory.upsert(make_item(user_id=OTHER_USER))
    composed = make_composer(stores).compose(request())
    assert [b.type for b in composed.context_blocks] == [ContextBlockType.ASK]
    assert not composed.excluded  # 13 §7: invisible, no exclusion row


# --- role composition --------------------------------------------------------------


def test_role_objective_composed_with_provenance(stores: Stores) -> None:
    _, _, roles = stores
    role = make_role(objective="Translate everything to Arabic.")
    roles.register(role)
    composed = make_composer(stores).compose(request(role_id=role.id))
    block = composed.context_blocks[0]
    assert block.type is ContextBlockType.ROLE
    assert block.content == "Translate everything to Arabic."
    assert block.source == f"role:{role.id}"
    assert block.confidence is None


def test_non_active_role_fails_loudly(stores: Stores) -> None:
    _, _, roles = stores
    role = make_role(status=RoleStatus.DRAFT)
    roles.register(role)
    with pytest.raises(RoleNotSelectable):
        make_composer(stores).compose(request(role_id=role.id))


def test_role_scoped_memory_composes_only_with_role(stores: Stores) -> None:
    memory, _, roles = stores
    role = make_role()
    roles.register(role)
    item = memory.upsert(make_item(key="style_guide", scope=MemoryScope.ROLE))

    without_role = make_composer(stores).compose(request())
    assert without_role.excluded[0].reason is ContextExclusionReason.IRRELEVANT
    assert without_role.excluded[0].memory_id == item.id

    with_role = make_composer(stores).compose(request(role_id=role.id))
    prefs = [b for b in with_role.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert [b.source for b in prefs] == [f"memory:{item.id}"]


def test_role_scoped_memory_never_wins_scope_conflict(stores: Stores) -> None:
    """ROLE is outside the 13 §4 chain: both items compose, no conflict."""
    memory, _, roles = stores
    role = make_role()
    roles.register(role)
    memory.upsert(make_item(key="lang", value="en", scope=MemoryScope.ROLE))
    memory.upsert(make_item(key="lang", value="ar", scope=MemoryScope.PROJECT))
    composed = make_composer(stores).compose(request(role_id=role.id))
    prefs = [b.content for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert prefs == ['lang = "ar"', 'lang = "en"']  # chain winner first
    assert not composed.excluded


# --- history ------------------------------------------------------------------------


def test_history_tail_oldest_first_with_role_prefix(stores: Stores) -> None:
    _, conversations, _ = stores
    conversation = _seed_history(conversations, ["one", "two", "three"])
    composed = make_composer(stores).compose(
        request(conversation_id=conversation.id, history_limit=2)
    )
    history = [b.content for b in composed.context_blocks if b.type is ContextBlockType.HISTORY]
    assert history == ["assistant: two", "user: three"]


def test_history_blocks_carry_message_provenance(stores: Stores) -> None:
    _, conversations, _ = stores
    conversation = _seed_history(conversations, ["one"])
    composed = make_composer(stores).compose(request(conversation_id=conversation.id))
    history = [b for b in composed.context_blocks if b.type is ContextBlockType.HISTORY]
    assert history[0].source.startswith("message:")


def test_history_limit_zero_composes_none(stores: Stores) -> None:
    _, conversations, _ = stores
    conversation = _seed_history(conversations, ["one"])
    composed = make_composer(stores).compose(
        request(conversation_id=conversation.id, history_limit=0)
    )
    assert [b.type for b in composed.context_blocks] == [ContextBlockType.ASK]


# --- 13 §5/§10 context budget ---------------------------------------------------------


def test_budget_mandatory_blocks_must_fit(stores: Stores) -> None:
    with pytest.raises(ContextBudgetExceeded) as exc:
        make_composer(stores).compose(request(ask="x" * 100, context_budget=50))
    assert exc.value.required == 100
    assert exc.value.budget == 50


def test_budget_counts_role_as_mandatory(stores: Stores) -> None:
    _, _, roles = stores
    role = make_role(objective="o" * 40)
    roles.register(role)
    with pytest.raises(ContextBudgetExceeded) as exc:
        make_composer(stores).compose(request(role_id=role.id, ask="x" * 20, context_budget=59))
    assert exc.value.required == 60


def test_budget_excludes_memory_over_budget_with_named_reason(
    stores: Stores,
) -> None:
    memory, _, _ = stores
    small = memory.upsert(make_item(key="a", value="x", scope=MemoryScope.CONVERSATION))
    big = memory.upsert(make_item(key="big_note", value="y" * 500, scope=MemoryScope.PROJECT))
    ask = "hi"
    budget = len(ask) + len('a = "x"') + 10  # room for small, not big
    composed = make_composer(stores).compose(request(ask=ask, context_budget=budget))
    prefs = [b for b in composed.context_blocks if b.type is ContextBlockType.PREFERENCE]
    assert [b.source for b in prefs] == [f"memory:{small.id}"]
    assert composed.excluded[0].reason is ContextExclusionReason.OVER_BUDGET
    assert composed.excluded[0].memory_id == big.id


def test_budget_keeps_newest_contiguous_history_tail(stores: Stores) -> None:
    _, conversations, _ = stores
    conversation = _seed_history(conversations, ["aaaa", "bbbb", "cccc"])
    ask = "hi"
    # "user: cccc" costs 10; allow exactly one turn beyond the ask.
    composed = make_composer(stores).compose(
        request(conversation_id=conversation.id, ask=ask, context_budget=len(ask) + 10)
    )
    history = [b.content for b in composed.context_blocks if b.type is ContextBlockType.HISTORY]
    assert history == ["user: cccc"]


def test_budget_total_content_never_exceeds_budget(stores: Stores) -> None:
    memory, conversations, _ = stores
    for index in range(5):
        memory.upsert(make_item(key=f"k{index}", value="v" * 20))
    conversation = _seed_history(conversations, ["hello world"] * 5)
    budget = 120
    composed = make_composer(stores).compose(
        request(conversation_id=conversation.id, ask="ok", context_budget=budget)
    )
    assert sum(len(b.content) for b in composed.context_blocks) <= budget


# --- composer construction ------------------------------------------------------------


def test_invalid_min_confidence_rejected(stores: Stores) -> None:
    memory, conversations, roles = stores
    with pytest.raises(ValueError):
        ContextComposer(
            memory_store=memory,
            conversation_store=conversations,
            role_registry=roles,
            min_confidence=1.5,
        )
