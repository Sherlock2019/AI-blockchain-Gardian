"""Canonical JSON and SHA-256 helpers.

Everything that is hashed goes through `canonical_json`, so two parties holding
the same data always derive the same hash. Floats are rejected: money is
carried as a fixed two-decimal string.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

ZERO_HASH = "0x" + "00" * 32


def money_str(amount: Decimal | str | int) -> str:
    return f"{Decimal(amount):.2f}"


def _reject_floats(value: Any) -> None:
    if isinstance(value, float):
        raise TypeError("floats are not allowed in canonical JSON; use a decimal string")
    if isinstance(value, dict):
        for v in value.values():
            _reject_floats(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _reject_floats(v)


def canonical_json(value: Any) -> str:
    _reject_floats(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return "0x" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_object(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def id_hash(kind: str, identifier: str) -> str:
    """Hash of a namespaced identifier, used wherever an id is published on-chain."""
    return sha256_hex(f"{kind}:{identifier}")
