"""Heuristic detector for instruction-like text in untrusted documents.

This is a tripwire, not a defence. Pattern matching is trivially evaded and
will also flag innocent text. Its only effect is to *add* human review. The
control that actually stops an injected action is the permission allow-list in
`app.governance.permissions`, which does not care what the text said.
"""

from __future__ import annotations

import re

_PATTERNS = (
    r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+instructions",
    r"disregard\s+(all\s+)?(the\s+)?(previous|prior|above)",
    r"\b(change|update|replace)\b.{0,40}\bbank\s+account",
    r"immediately\s+(send|release|make)\s+(the\s+)?payment",
    r"you\s+are\s+now\b",
    r"system\s+prompt",
    r"do\s+not\s+(ask|require|wait\s+for)\s+.{0,20}approval",
)
_COMPILED = tuple(re.compile(p, re.IGNORECASE | re.DOTALL) for p in _PATTERNS)


def find_injection_signals(text: str) -> list[str]:
    """Returns the matched fragments, empty when nothing looks like an instruction."""
    return [m.group(0) for pattern in _COMPILED if (m := pattern.search(text or ""))]


def looks_like_injection(text: str) -> bool:
    return bool(find_injection_signals(text))
