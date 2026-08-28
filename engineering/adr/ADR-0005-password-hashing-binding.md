# ADR-0005 — Password Hashing Production Binding (Argon2id)

```text
STATUS: ACCEPTED (explicit operator decision, 2026-08-28: "ADR-0005 = ACCEPTED")
DATE: 2026-08-28
TASK: T-IMPL-040 (Lane B — FINAL Phase 2 gap: "Argon2id" in the 41 §5 security list)
SUPERSEDES: NONE
```

Format authority: `docs/ai_orchestration_pack/final_docs_v3/40_ENGINEERING_PROTOCOL.md` §8.1.
Gate: the Argon2id infrastructure binding must not land — and no password-hashing
dependency may be added to `pyproject.toml` — until this ADR is ACCEPTED with
explicit operator sign-off (same governance as ADR-0002/0003/0004).

---

## Context

Fixed constraints (40 §5.2; 41 §5 FINAL Phase 2 security list; 20 §5):

```text
- 40 §5.2 Authentication Baseline is NOT negotiable: "Password = Argon2id,
  unique salt, strong policy, compromised-password checks". The choice here
  is WHICH implementation binds PasswordHasherPort, not whether Argon2id.
- core/identity/ports.py already defines PasswordHasherPort (hash/verify)
  with the docstring "Production binding must be Argon2id ... that binding
  lives in infrastructure/". Core purity (import-linter): the binding goes
  under infrastructure/, core never imports it.
- 20 §5: plaintext never stored/logged; the hash is opaque to the service.
- Hermetic gates: tests must not need network; Argon2id is CPU-local, so a
  real binding IS hermetically testable (unlike provider credentials).
- Upgrade path (40 §5.2): Passkeys/MFA/TOTP addable without changing core
  auth boundaries — the port already isolates this.
```

## Alternatives

### A. argon2-cffi (the argon2-cffi package, official CFFI bindings)

Pros:
```text
- The de-facto Python Argon2 implementation (maintained by the PyCA
  ecosystem author); wraps the phc-winner-argon2 reference C code.
- PasswordHasher defaults follow RFC 9106 recommendations and are kept
  current by the library (time_cost/memory_cost/parallelism, unique salt
  per hash — satisfying "unique salt" verbatim).
- verify() raises typed exceptions; check_needs_rehash() supports policy
  upgrades — matches the "strong policy" requirement and future rotation.
- Already present in the sandbox environment (v25.1.0) — zero new install
  friction; pure local CPU, hermetic-testable.
```
Cons:
```text
- CFFI native extension — needs wheels (universally available) or a C
  toolchain at build time.
```

### B. passlib[argon2]

Pros:
```text
- Multi-scheme facade (bcrypt/argon2/scrypt) with a built-in upgrade story.
```
Cons:
```text
- Maintenance has stalled (no release since 2020; known Python 3.13
  bcrypt-detection issues); delegates Argon2 to argon2-cffi anyway —
  an extra, weaker-maintained layer over alternative A for no gain here
  (the port already provides our upgrade seam).
```

### C. hashlib.scrypt (stdlib, no new dependency)

Pros:
```text
- Zero dependencies.
```
Cons:
```text
- NOT Argon2id — directly violates the non-negotiable 40 §5.2 baseline.
  Rejected on spec grounds.
```

## Decision

ACCEPTED: Alternative A — add `argon2-cffi>=23` to `[project] dependencies`
and implement `infrastructure/security/password.py` binding
`PasswordHasherPort` via `argon2.PasswordHasher` (library defaults, which
track RFC 9106; parameters overridable at composition root only).
`check_needs_rehash` exposed for future rotation policy. Compromised-password
checks (40 §5.2) are a SEPARATE later concern (needs a corpus/service
decision — recorded, not bundled here).

## Reason

Only A satisfies the Argon2id mandate directly with a maintained,
reference-backed implementation; B adds an unmaintained layer over A;
C fails the spec.

## Consequences

```text
+ FINAL Phase 2 "Argon2id" item becomes implementable and hermetically
  verifiable (hash/verify round-trip, wrong-password rejection, unique-salt
  property, needs-rehash signal).
+ One new runtime dependency (argon2-cffi) confined to infrastructure/ by
  the existing import-linter contracts.
- Compromised-password checks remain OPEN (future ADR/task when a data
  source is chosen) — recorded in the state file, not silently dropped.
```

## Status

ACCEPTED — explicit operator sign-off 2026-08-28 ("ADR-0005 = ACCEPTED").
Implementation: T-IMPL-040 — argon2-cffi dependency + infrastructure/security/password.py.
