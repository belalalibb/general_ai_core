#!/bin/bash
# R165 — recreate the TARGET repo (a small `ledger` Python project) + a bare
# origin under /tmp/r165, OUTSIDE the platform checkout (ADR-0012 §14 guard).
# Usage: bash docs/benchmarks/r165-live-groq/mk_target.sh
set -e
rm -rf /tmp/r165 && mkdir -p /tmp/r165 && cd /tmp/r165
git init -q --bare remote.git && git init -q -b main ws && cd ws
git config user.name agent && git config user.email agent@platform.local
mkdir -p ledger tests
cat > ledger/__init__.py <<'EOF'
"""ledger — a tiny multi-currency ledger used by the reporting CLI."""

from ledger.money import Money
from ledger.accounts import Account, Ledger

__all__ = ["Money", "Account", "Ledger"]
EOF
cat > ledger/money.py <<'EOF'
"""Money value object: integer cents + ISO currency code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    cents: int
    currency: str

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.cents + other.cents, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise ValueError(f"currency mismatch: {self.currency} vs {other.currency}")
        return Money(self.cents - other.cents, self.currency)

    def __str__(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, frac = divmod(abs(self.cents), 100)
        return f"{sign}{whole}.{frac:02d} {self.currency}"


def parse_money(text: str) -> Money:
    """Parse '12.34 USD' or '-0.05 EUR' into Money."""
    amount, currency = text.strip().split()
    negative = amount.startswith("-")
    amount = amount.lstrip("-")
    whole, _, frac = amount.partition(".")
    frac = (frac + "00")[:2]
    cents = int(whole) * 100 + int(frac)
    return Money(-cents if negative else cents, currency.upper())
EOF
cat > ledger/accounts.py <<'EOF'
"""Accounts and the ledger that holds them."""

from __future__ import annotations

from dataclasses import dataclass, field

from ledger.money import Money


@dataclass
class Account:
    name: str
    currency: str
    entries: list[Money] = field(default_factory=list)

    def post(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise ValueError(f"account {self.name} is {self.currency}, got {amount.currency}")
        self.entries.append(amount)

    def balance(self) -> Money:
        total = Money(0, self.currency)
        for entry in self.entries:
            total = total + entry
        return total


class Ledger:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}

    def open(self, name: str, currency: str) -> Account:
        if name in self._accounts:
            raise KeyError(f"account exists: {name}")
        account = Account(name, currency)
        self._accounts[name] = account
        return account

    def get(self, name: str) -> Account:
        return self._accounts[name]

    def transfer(self, source: str, target: str, amount: Money) -> None:
        src = self.get(source)
        dst = self.get(target)
        src.post(Money(-amount.cents, amount.currency))
        dst.post(amount)

    def accounts(self) -> list[Account]:
        return sorted(self._accounts.values(), key=lambda a: a.name)
EOF
cat > ledger/report.py <<'EOF'
"""Text report over a ledger."""

from __future__ import annotations

from ledger.accounts import Ledger


def balances_report(ledger: Ledger) -> str:
    lines = ["ACCOUNT      BALANCE"]
    for account in ledger.accounts():
        lines.append(f"{account.name:<12} {account.balance()}")
    return "\n".join(lines)


def totals_by_currency(ledger: Ledger) -> dict[str, int]:
    totals: dict[str, int] = {}
    for account in ledger.accounts():
        totals[account.currency] = totals.get(account.currency, 0) + account.balance().cents
    return totals
EOF
cat > tests/test_money.py <<'EOF'
from ledger.money import Money, parse_money


def test_add_same_currency():
    assert Money(150, "USD") + Money(50, "USD") == Money(200, "USD")


def test_str_formats_cents():
    assert str(Money(1234, "USD")) == "12.34 USD"
    assert str(Money(-5, "EUR")) == "-0.05 EUR"


def test_parse_roundtrip():
    assert parse_money("12.34 usd") == Money(1234, "USD")
    assert parse_money("-0.05 EUR") == Money(-5, "EUR")
EOF
cat > tests/test_accounts.py <<'EOF'
from ledger import Ledger, Money


def test_transfer_moves_money():
    ledger = Ledger()
    ledger.open("cash", "USD")
    ledger.open("bank", "USD")
    ledger.get("cash").post(Money(10_000, "USD"))
    ledger.transfer("cash", "bank", Money(2_500, "USD"))
    assert ledger.get("cash").balance() == Money(7_500, "USD")
    assert ledger.get("bank").balance() == Money(2_500, "USD")
EOF
printf '# ledger\n\nTiny multi-currency ledger. Run tests with `python3 -m pytest -q`.\n' > README.md
python3 -m pytest -q 2>&1 | tail -1
git add -A && git commit -q -m "ledger: initial multi-module project"
git remote add origin /tmp/r165/remote.git && git push -q origin main && git log --oneline -1
