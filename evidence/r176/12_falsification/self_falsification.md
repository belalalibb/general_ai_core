# A12 — Self-falsification (prompt §3.4) + probe coverage (§3.3) — EXECUTED

HEAD at start d00387b (reset #26; probe committed+pushed before run). `a12_falsify.py` → `falsification_probes.txt`.

## 1. Every major PASS, its strongest counter-argument, the cheapest test, the outcome

| PASS claimed | strongest argument against | falsifier executed | result | claim after |
|---|---|---|---|---|
| Tenant isolation (A5) | id lookup may be case/format-sensitive or list endpoints may not filter | F1a upper-cased id, F1b trailing slash, F1c list w/ query filter | 404 / 404 / B's list empty, A's id absent | **HOLDS** |
| Constant 401, no oracle (A5) | header-parsing variants may leak or bypass | F2a lowercase `bearer` → **200** (scheme case-insensitive, RFC 7235 — accepted, not a bypass); F2b Basic → 401; F2c empty Bearer → 401; F2d token+junk → 401 | one constant body for all failures | **HOLDS** |
| Admin 403 before validation (A5/A6) | malformed body might hit the parser first (400/422) | F3 non-admin POST malformed JSON | 403 | **HOLDS** |
| Usage accounting exact (A4/A5) | failed calls (422/503) might still reserve units | F4 usage before/after one 422 + one 503 | 1.0 → 1.0 | **HOLDS** |
| Closed shapes (A4) | nesting may not be `extra=forbid` | F6 unknown field inside `execution_policy` | 422 | **HOLDS** |
| Idempotency scoped per tenant (A7) | key namespace might be global → B replays A's job | F7 same key, two tenants | different execution ids; B gets B's ask; A's not leaked | **HOLDS** |
| **Webhook SSRF gate (A5 S-26c)** | `ipaddress.ip_address()` only parses canonical dotted-quad; non-canonical loopback spellings fall to the "named host" branch | F5: `127.1`, `0x7f000001`, `2130706433` → **201 admitted**; `localhost`, `[::1]`, `169.254.169.254`, `10.0.0.1` → 422 | **FALSIFIED for non-canonical IPv4 literals** | **DOWNGRADED → PARTIALLY VERIFIED** |

## 2. New finding from falsification

**F-R176-11 — SSRF admission bypass via non-canonical IPv4 literals (S2 latent / S3 today).**
- EXPECTED: `validate_webhook_url` refuses every loopback/private target regardless of spelling.
- ACTUAL (`core/events/webhooks.py:103-108`): `ipaddress.ip_address(hostname)` raises `ValueError` for `127.1`, `0x7f000001`,
  `2130706433`; the `except ValueError` branch treats them as **named hosts** and returns the url unchanged. Many HTTP clients
  (curl, browsers, some Python stacks via `inet_aton`) resolve these to 127.0.0.1.
- WHY NOT S1 NOW: the delivery relay is **not composed** (A5 O-02, `apps/api/app.py:536` "never claimed"); the URL is stored, never
  dereferenced. The module header itself records "connect-time resolution checking is the sender's recorded duty" — the second gate
  does not exist yet either. The moment a sender is composed without that connect-time check, this becomes an S1 SSRF.
- Classification: **MUST FIX BEFORE ANY WEBHOOK DELIVERY IS COMPOSED**; for the current closure: **SHOULD FIX BEFORE EXTERNAL
  CONSUMPTION**. Proposed **FIX-07** (not executed): (a) refuse hostnames that are all-digits / hex / dotted-shorthand (regex
  `^[0-9a-fA-Fx.]+$` and not a valid dotted-quad) — "ambiguous numeric host refused"; (b) failing-first tests for the three spellings
  in `tests/events/`; (c) keep the resolve-and-recheck duty documented for the future sender. Blast radius: one function + one test
  file; no contract change; `ui/app` unaffected.

## 3. Probe coverage — whole round (§3.3)

| priority | executed / total | items |
|---|---|---|
| **P0** | **8/8** | tenant isolation (2 tenants, concurrent) · async/worker context isolation (interleave + serialization) · authz under composition (direct/async/tool/skill/role/project) · credential containment (0 leaks in responses/logs/evidence) · admin boundaries (403-before-validation, admin≠data access) · crash/partial atomicity (Tier 1 fabric+chaos, wire idempotency) · learning poisoning (secret never reaches GOLD/retrieval/other tenant) · committed-secret gate (A0 — FAIL found) |
| **P1** | **44/46** | A4 24 runtime · A6 12 lifecycle · A7 9 wire · A9 6/7 (user-owned credential path BLOCKED) · A10 15 · falsification 7 — minus 1 BLOCKED (user credential) and 1 NOT EXECUTED (Groq live this round: key restricted) |
| **P2** | **0/6** | multi-instance run · config publish mid-flight · retry with foreign ambient tenant on the wire · skills import from allowed source E2E · `not_poisoned` heuristic characterisation · gateway streaming |

**NOT PROBED**: the six P2 items above; browser UI live suite (dependency absent — gate says NOT EVALUATED); webhook delivery (not composed).
**BLOCKED**: user-owned provider credential path (no user key); Groq live this round (org-restricted key — external).

## 4. Effect on the verdict
No PASS was reversed to FAIL; one PASS downgraded to PARTIALLY VERIFIED (SSRF gate) and produced F-R176-11. Isolation, authz,
usage and idempotency claims survived their falsifiers. The defect ledger for R176 now has 11 entries (1 S1 doc/secret, 0 S2 live,
1 S2-latent, 7 S3, 2 S4) — all with reproductions; none is a runtime security bypass within the composed envelope.
