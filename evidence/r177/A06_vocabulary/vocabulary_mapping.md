# R177-A06 — Vocabulary mapping (§8): operator terms → repository reality (HEAD 16cae488)

Explicit statement (required by §8): none of the terms below claims that the system has emotions, consciousness or a "self". "Soul" is
operator vocabulary for durable, tenant-scoped personalization/relationship context and nothing more.

## 0. Contract facts the whole table rests on (KNOWN, read from source)
- `core/contracts/memory.py`: **there is no `MemoryType` enum.** The six 13 §2 types are NOT a field. A `MemoryItem` = id, tenant_id,
  user_id?, `scope` (closed: global, tenant, workspace, project, conversation, role), key, value, `source` (free BoundedStr), confidence,
  evidence_count, last_seen, expires_at?, `sensitivity` (closed: low, medium, high). ⇒ the "type" of a memory is expressed by
  `scope` × `source` × `user_id` presence.
- `source` values written by runtime code: `learning.gold` (GOLD_KNOWLEDGE_SOURCE, lifecycle.py:90, the ONLY runtime writer of
  `MemoryStorePort.upsert` — lifecycle.py:490); composer-side provenance labels `request`, `memory:*`, `message:*`, `role:*`, `local`.
- `core/memory/preferences.py` `PreferenceLearningGate` (13 §6: ≥2 evidence, no contradiction, one clear scope, sensitivity) is exported
  from `core/memory/__init__.py` but **has no runtime caller** (grep over core/apps: 0 non-test call sites).
- Conversation memory = `Conversation`/`Message` via `ConversationStorePort` (create/get/set_status/list/append_message/get_history).
- Identity = `core/identity/devices.py` `DeviceRegistry` (pair/trust/… state machine) + `core/identity/service.py` sessions — DEVICE and
  session identity; no persona/profile object.
- `core/context/composer.py`: deterministic composition role → memory (scope-priority 13 §4: conversation > project > workspace > user
  ownership > tenant > global; role ranks last), gates relevance → sensitivity (HIGH refused unless `allow_high_sensitivity`, app-set,
  default False) → confidence → budget.
- Evaluation: `GraderType` closed 7 (deterministic, model_based, pairwise, counter_evaluation, skill_specific, role_specific, security);
  `ModelJudgePort` (optional seam) + `AdapterModelJudge`; `EvaluationPolicyService`; `VerificationLevel` closed 5.
- "Teacher" appears only in final_docs_v3 {21,22 §10 "Teacher / Max Model Review", 41} and as `AdminDraftRequest.teacher_agreement:
  float | None` (core/contracts/admin.py:298). No module, class, port or route named teacher.

## 1. Mapping table
| Operator term | Nearest existing concept(s) | Implementing module(s) | Contract(s) | Coverage | Minimum expression WITHOUT a new subsystem | Parallel-concept risk |
|---|---|---|---|---|---|---|
| **Identity** | device identity + session | core/identity/devices.py, service.py; apps/api/auth.py | Device, DeviceState, Session; Principal | **ALREADY COVERED** for device/session; **MISSING** for "who is this user across devices" beyond `user_id` (no profile object) | keep `user_id` as the identity key; any "profile" = MemoryItems with `scope=tenant`, `user_id` set | LOW — do not create a Persona entity; `user_id` already threads every store |
| **Preferences** | 13 §6 learned preference | core/memory/preferences.py (gate), core/memory/memory.py (store) | MemoryItem (scope, key, value, confidence, evidence_count) | **PARTIALLY COVERED** — gate exists, tested, **not wired**; no write path from executions; 13 §8 visibility (view/edit/delete/disable) has no route | wire `PreferenceLearningGate` behind the execution path as an OPTIONAL seam (composition), writes = MemoryItem `source="preference"`; user visibility = 2–3 routes over MemoryStorePort filtered by source | MEDIUM if a separate "preferences store" is built — must stay a MemoryItem view |
| **Memory (6 types)** | scope × source × user_id | core/memory/memory.py, ports.py | MemoryItem, MemoryScope, MemorySensitivity | **COVERED BUT NEEDS STRONGER EVIDENCE** — the 6 types are documentary; code never names them, and only GOLD knowledge is written at runtime | a documented (docs/architecture) mapping table type → (scope, source) convention; no enum unless approved (closed-set consequence) | MEDIUM — a `MemoryType` enum would be a new closed set; prefer convention + test pin |
| ↳ Conversation Memory | Conversation/Message history | core/memory/memory.py (ConversationStorePort) | Conversation, Message | **ALREADY COVERED** (R176 A5/A10 probed persistence + isolation) | — | — |
| ↳ Working Context | composed context per request | core/context/composer.py | ContextComposeRequest, ComposedContext | **ALREADY COVERED** (deterministic, budgeted) | — | — |
| ↳ Project Memory | MemoryItem scope=project/workspace | core/memory/memory.py; projects/workspaces stores | MemoryScope.PROJECT/WORKSPACE | **PARTIALLY COVERED** — scopes exist and compose; **no runtime writer** produces project-scoped items | writer = same OPTIONAL learning/preference seam with scope=project | LOW |
| ↳ Episodic / relationship memory | none dedicated; nearest = conversation history + scope=tenant items with user_id | — | MemoryItem | **MISSING** as a distinct capability; expressible as MemoryItem `source="episode"`, `scope=tenant`, user_id, expires_at | convention + optional writer; NO new store | MEDIUM — the tempting "relationship graph" would be a parallel subsystem; refuse |
| ↳ Semantic/User Memory | scope=tenant + user_id items | core/memory/memory.py | MemoryItem | **PARTIALLY COVERED** (readable/composable; no writer) | as above | LOW |
| ↳ Verified Intelligence | GOLD memory | core/learning/lifecycle.py promote_to_gold | MemoryItem source=learning.gold; VerificationLevel.GOLD | **ALREADY COVERED** | — | — |
| **Soul / personalization** | preferences + user-scoped memory + composer | core/memory/*, core/context/composer.py | MemoryItem | **NEW VOCABULARY, not a new component** — fully expressible as: (Preferences wired) + (user/tenant-scoped MemoryItems) + (composer already ranks them) | no package, no contract term; a docs/architecture note names "Soul" = this composition; optional per app (memory seam absent ⇒ composer has nothing to compose — degrades honestly) | **HIGH if literalised** — a `core/soul/` package or `SoulProfile` contract would duplicate memory; must be refused without approval |
| **Knowledge** | GOLD MemoryItems + ask_learned/learned_keys | core/learning/lifecycle.py:90,490,525,544 | MemoryItem source=learning.gold | **ALREADY COVERED** for promoted knowledge; **PARTIALLY COVERED** for intake (only execution captures + `capture_external`; no CSV/Excel/JSON/file normaliser — see A07) | intake normalisers as OPTIONAL adapters feeding `capture_external` (providers/ or apps/composition/, never core/) | MEDIUM — a "knowledge base" store would duplicate memory+GOLD |
| **Teacher** | evaluation review layer | core/evaluation/{graders,policy,memory,ports}.py; core/learning/gates.py PromotionGate.admin_approved; `teacher_agreement` field | GraderType (closed 7), ModelJudgePort, PromotionSignals | **PARTIALLY COVERED** — the ROLE is discharged by ModelJudgePort (model_based grader, optional seam) + PromotionGate + admin approval; the NAME does not exist in code, and 22 §10's selective policy (high-value / uncertain / new-category / calibration / canary) is not implemented as a selector | "Teacher" = a `ModelJudgePort` binding + a selection policy over 22 §10 criteria; disabled ⇒ `model_based` grader absent, deterministic graders + gates still run, promotion still requires admin_approved | MEDIUM — a "TeacherService" owning the lifecycle would invert 22's design (evaluation reviews; lifecycle owns) |

## 2. Findings
- **F-R177-02 (S3, capability)**: `PreferenceLearningGate` is dead code at runtime — exported, tested, never called; no execution path
  writes user preferences; 13 §8 memory visibility (view/edit/delete/disable) has no route. Evidence: grep 0 callers; route list A04 (no
  /v1/memory* or /v1/preferences*).
- **F-R177-03 (S4, documentation/contract)**: the six 13 §2 memory types have no code expression (no field, no convention pinned by test);
  only `learning.gold` is written at runtime. Evidence: core/contracts/memory.py fields; single runtime `upsert` caller.
- **F-R177-04 (S4, vocabulary)**: "Soul" and "Teacher" are absent from code; both are fully expressible over existing primitives. Any
  literalisation (new package/contract) is a parallel-concept risk and requires approval.

## 3. Design rules applied (§8) — verdicts
- Soul belongs to Core conceptually → YES, as memory+preferences+composer (all core/, provider-free). Provider-native memory/session
  (e.g. a vendor "threads" API) → allowed only as an adapter in providers/ or apps/composition/ (import-linter forbids the reverse).
- Apps may disable it → already true: `memory`/`composer`/`conversations` seams absent ⇒ execute still works (execute.sync always
  AVAILABLE; catalog shows INERT).
- Tenant scoping → MemoryItem keyed by tenant_id (+user_id); R176 A5 isolation probes held; unchanged.
