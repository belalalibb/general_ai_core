# AI Orchestration Platform — Documentation Pack V3 (Blueprint + Live Index)

```text
STATUS: V3_AUTHORITATIVE — MIGRATION_COMPLETE (all 20 V3 documents COMPLETE_AUTHORITATIVE)
AUTHORED_BY_TASK: T-DOC-002
LAST_MIGRATION_TASK: T-DOC-013 (QA gate passed; V2 pack marked ARCHIVED_BASELINE)
V2_PACK_STATUS: ARCHIVED_BASELINE — read-only historical source material; no V2 document is authoritative
```

## Purpose

This file is the authoritative V3 documentation architecture:
target structure, V2→V3 traceability map, per-document migration status, and the authority rule during migration.

## Audience

- Documentation re-architecture Agents performing migration tasks.
- Future implementation Agents locating the authoritative spec for any area.

## Authoritative Content

- The V3 target document structure (may not be changed silently; changes require an entry in the Decision Log).
- The per-document MIGRATION STATUS table below (the only place that says which version of a document is authoritative).
- The migration order and its task boundaries.

---

## 1. Authority Rule During Migration — BINDING

```text
1. A V2 document remains authoritative until its V3 successor is:
   created + content-complete + verified + committed,
   AND the V2 source is marked SUPERSEDED with a pointer to the successor.
2. Until then, the V3 successor file must not exist as a partial stub.
3. No two documents may be authoritative for the same contract at the same time.
4. The MIGRATION STATUS column in this index is the single switch of authority.
5. Migration must preserve decisions, requirements, contracts, invariants,
   and security constraints. Structure may change; decisions may not change silently.
6. Every migration commit updates this index in the same commit.
```

MIGRATION COMPLETE (T-DOC-013): all 20 V3 documents are COMPLETE_AUTHORITATIVE
and all 25 V2 documents carry SUPERSEDED banners. The V2 pack
(`../final_docs_v2/`) is ARCHIVED_BASELINE: read-only historical source
material for traceability audits only. Never cite a V2 document as authority.

Pack-level files stay outside `final_docs_v3/` and are unaffected by migration:

```text
README.md                      = permanent operating contract
PROJECT_EXECUTION_STATE.md     = single mutable project state
CURRENT_SESSION_DECISIONS.md   = session-level decision record (authority rank 2)
DESIGN_OPINIONS_AND_SUGGESTIONS.md = advisory only (authority rank 4)
conversation_archive/          = raw material only
```

---

## 2. V3 Target Structure and Traceability Map

Layer prefixes: `0x` Product/Architecture, `1x` Core Contracts, `2x` Security/Governance Specs, `3x` Provider Subsystem, `4x` Engineering Execution, `5x` Agent Operation Protocols, `6x` Decision Records.

| V3 Document | Sources (V2) | Structural Change | Migration Status |
|---|---|---|---|
| `00_INDEX.md` (this file) | v2 `00_INDEX.md` | REBUILT as blueprint + live authority switch | ACTIVE (v2 index is ARCHIVED_BASELINE since T-DOC-013) |
| `01_PRODUCT_REQUIREMENTS.md` | v2 `01` | CARRY (surgical cleanup only) | COMPLETE_AUTHORITATIVE (T-DOC-006; v2 `01` SUPERSEDED with pointer banner) |
| `02_ARCHITECTURE_BASELINE_AND_INVARIANTS.md` | v2 `02` | CARRY (invariants unchanged) | COMPLETE_AUTHORITATIVE (T-DOC-006; v2 `02` SUPERSEDED with pointer banner) |
| `03_DOMAIN_MODEL.md` | v2 `03` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-006; v2 `03` SUPERSEDED with pointer banner) |
| `10_API_CONTRACTS.md` | v2 `04` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-007; v2 `04` SUPERSEDED with pointer banner) |
| `11_MODEL_ROUTING_AND_MODEL_CONTROL.md` | v2 `06` | CARRY (keep all modes: AUTO / TIER / EXPLICIT_MODEL / EXPLICIT_MODELS / AGENT_NODE_MAPPING) | COMPLETE_AUTHORITATIVE (T-DOC-007; v2 `06` SUPERSEDED with pointer banner) |
| `12_EXECUTION_GRAPH_AND_AGENT_MODE.md` | v2 `07` + v2 `21` | MERGE (provider-agent orchestration is execution-graph behavior; one authority for Agent Mode) | COMPLETE_AUTHORITATIVE (T-DOC-005; v2 `07` + `21` SUPERSEDED with pointer banners) |
| `13_MEMORY_AND_CONTEXT.md` | v2 `08` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-008; v2 `08` SUPERSEDED with pointer banner) |
| `14_SKILLS_AND_TOOLS.md` | v2 `09` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-008; v2 `09` SUPERSEDED with pointer banner) |
| `20_SECURITY_THREAT_MODEL.md` | v2 `10` | CARRY (Capability Firewall + deny-by-default unchanged) | COMPLETE_AUTHORITATIVE (T-DOC-009; v2 `10` SUPERSEDED with pointer banner) |
| `21_ADMIN_CONTROL_PLANE.md` | v2 `11` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-009; v2 `11` SUPERSEDED with pointer banner) |
| `22_EVALUATION_AND_LEARNING.md` | v2 `12` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-009; v2 `12` SUPERSEDED with pointer banner) |
| `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md` | v2 `24` + v2 `05` | MERGE (v2 `24` is already declared the final provider reference; v2 `05` detail folds under it — removes dual authority) | COMPLETE_AUTHORITATIVE (T-DOC-003; v2 `24` + `05` SUPERSEDED with pointer banners) |
| `31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md` | v2 `23` + v2 `25` | MERGE (both cover the "no real providers yet" state and the path to real providers, by type) | COMPLETE_AUTHORITATIVE (T-DOC-004; v2 `23` + `25` SUPERSEDED with pointer banners) |
| `40_ENGINEERING_PROTOCOL.md` | v2 `13` | REWRITE-COMPRESS (defect-justified: 2385 lines; legacy STATE.md/PROGRESS.md scheme conflicts with single-state decision D10/D11) | COMPLETE_AUTHORITATIVE (T-DOC-010; v2 `13` SUPERSEDED with pointer banner; §39/§40/§41/§50 explicitly superseded by D10/D11) |
| `41_IMPLEMENTATION_PLAN_AND_MVP.md` | v2 `14` + v2 `15` | MERGE (one plan with explicit FINAL vs MVP vs FUTURE separation; removes duplicated phase lists and legacy state-file references) | COMPLETE_AUTHORITATIVE (T-DOC-011; v2 `14` + `15` SUPERSEDED with pointer banners; v2 14 §32/§33/§35/§37/§39/§42 explicitly superseded by D10/D11) |
| `50_AGENT_EXECUTION_PROMPT.md` | v2 `20` + v2 `16` | MERGE (v2 `20` is the base; v2 `16` becomes its short standard-mode profile — one build prompt authority) | COMPLETE_AUTHORITATIVE (T-DOC-012; v2 `20` + `16` SUPERSEDED with pointer banners; legacy state-file/FUTURE_IMPROVEMENTS references explicitly superseded by D10/D11) |
| `51_AGENT_COGNITIVE_PROTOCOL.md` | v2 `19` | CARRY | COMPLETE_AUTHORITATIVE (T-DOC-012; v2 `19` SUPERSEDED with pointer banner) |
| `52_RESUME_AND_PROGRESS_PROTOCOL.md` | v2 `22` (supersedes v2 `17`) | CARRY + ABSORB (v2 `17` is stale: dead `final_docs/` paths, forbidden STATE.md/PROGRESS.md/HANDOFF.md scheme) | COMPLETE_AUTHORITATIVE (T-DOC-012; v2 `22` + `17` SUPERSEDED with pointer banners; v2 `17` retired, still-valid rules absorbed as 52 §17) |
| `60_DECISION_LOG.md` | v2 `18` | CARRY (Q&A log continues; conflict resolutions during migration are appended here) | COMPLETE_AUTHORITATIVE (T-DOC-012; v2 `18` SUPERSEDED with pointer banner; live append-only log with migration records MR-001..MR-004) |

Result: 26 → 20 files (v2 count incl. index → v3 count incl. index). No capability area is dropped.

### Removed / Superseded (Decision Preservation Ledger — structural level)

| V2 Item | Classification | Reason |
|---|---|---|
| `17_RESUME_PROMPT.md` | SUPERSEDED_BY `52_RESUME_AND_PROGRESS_PROTOCOL.md` + `PROJECT_EXECUTION_STATE.md` | References non-existent `final_docs/` paths and the legacy STATE/PROGRESS/HANDOFF state files forbidden by D10/D11. Its still-valid rule ("Git commit = only trusted proof") already lives in v2 `22` and README. |
| `16_MASTER_BUILD_PROMPT.md` | MERGED_INTO `50_AGENT_EXECUTION_PROMPT.md` | Two parallel build prompts create authority ambiguity; v2 `20` is the stronger superset. |
| `21_PROVIDER_AGENT_ORCHESTRATION_SPEC.md` | MERGED_INTO `12_EXECUTION_GRAPH_AND_AGENT_MODE.md` | Provider-agent orchestration is Execution Graph behavior; splitting it invited drift. Critical rule preserved: Provider Agent Capability != Platform Agent Runtime; platform stays authoritative. |
| `05_PROVIDER_PLUGIN_SPEC.md` | MERGED_INTO `30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md` | v2 `24` already declared final provider authority; merge ends the dual-authority pointer chain. |
| `23` + `25` | MERGED_INTO `31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md` | Same lifecycle stage (scaffold-only state → real onboarding by type); merging keeps "no real providers yet" stated once, authoritatively. |
| `14` + `15` | MERGED_INTO `41_IMPLEMENTATION_PLAN_AND_MVP.md` | Overlapping phase plans; merged with explicit FINAL/MVP/FUTURE separation. |
| Legacy STATE.md/PROGRESS.md/HANDOFF.md schema inside v2 `13`/`14` | REMOVED_AS_NO_EXECUTION_VALUE (superseded by D10/D11) | Single mutable state = `PROJECT_EXECUTION_STATE.md`. |

Fine-grained (section-level) ledger entries are recorded per migration task in its commit and, when conflicts are resolved, in `60_DECISION_LOG.md`.

---

## 3. Capability Coverage Check (25 required areas → V3)

```text
Product Requirements → 01        Architecture Baseline → 02       Domain Model → 03
API Contracts → 10               Provider Plugin Spec → 30        Model Routing/Control → 11
Execution Graph + Agent Mode →12 Memory/Context → 13              Skill/Tool → 14
Security Threat Model → 20       Admin Control Plane → 21         Evaluation/Learning → 22
Engineering Protocol → 40        Implementation Plan → 41         MVP Roadmap → 41
Build Prompt → 50                Resume Prompt → 52 + PROJECT_EXECUTION_STATE.md
Q&A Decision Log → 60            Cognitive Protocol → 51          Ultra Execution Prompt → 50
Provider Agent Orchestration →12 Lightweight Resume Protocol → 52 Providers Scaffolding → 31
Final Provider Architecture → 30 Real Provider Onboarding → 31
```

All 25 areas covered. None dropped.

---

## 4. Migration Order (one micro-task per cluster, one cluster per session)

```text
T-DOC-003  30_PROVIDER_ARCHITECTURE_AND_PLUGIN_SPEC.md   (v2 24 + 05)
T-DOC-004  31_PROVIDER_SCAFFOLDING_AND_ONBOARDING.md     (v2 23 + 25)
T-DOC-005  12_EXECUTION_GRAPH_AND_AGENT_MODE.md          (v2 07 + 21)
T-DOC-006  01, 02, 03                                    (carry cluster: product/architecture/domain)
T-DOC-007  10, 11                                        (carry cluster: API + routing/model control)
T-DOC-008  13, 14                                        (carry cluster: memory + skills/tools)
T-DOC-009  20, 21, 22                                    (carry cluster: security/admin/evaluation)
T-DOC-010  40_ENGINEERING_PROTOCOL.md                    (compress v2 13)
T-DOC-011  41_IMPLEMENTATION_PLAN_AND_MVP.md             (v2 14 + 15)
T-DOC-012  50, 51, 52, 60                                (agent-operation cluster; retire v2 16/17)
T-DOC-013  V3 finalization: QA gate, exit checks, mark v2 pack ARCHIVED_BASELINE
```

Order rationale: highest-defect clusters first (provider dual authority, split execution spec), low-churn carries in batches, largest rewrite (40) after patterns stabilize, prompts and finalization last.

Only `PROJECT_EXECUTION_STATE.md` authorizes the next task. This list is a plan, not authorization.

---

## 5. Resume Rule Pointer

```text
Git committed state is the only trusted progress.
Read PROJECT_EXECUTION_STATE.md for the authorized task.
Full protocol: final_docs_v3/52_RESUME_AND_PROGRESS_PROTOCOL.md (authoritative since T-DOC-012)
```
