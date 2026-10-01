"""Embedding abstraction.

The default is a hashed bag-of-words vector: no model download, no network,
fully deterministic. It is lexical, not semantic. It is good enough for a
few dozen policy clauses and is the first thing to replace for a real corpus.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

SparseVector = dict[int, float]

_TOKEN = re.compile(r"[a-z0-9$][a-z0-9$,.\-]*[a-z0-9]|[a-z0-9]")
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in is it its may must not of on or "
    "that the their this to was when which who with".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class Embedder(Protocol):
    def embed(self, text: str) -> SparseVector: ...


class HashingEmbedder:
    def __init__(self, dimensions: int = 2048) -> None:
        self._dimensions = dimensions

    def _bucket(self, token: str) -> int:
        # hashlib, not hash(): Python salts hash() per process.
        return int.from_bytes(hashlib.md5(token.encode()).digest()[:4], "big") % self._dimensions

    def embed(self, text: str) -> SparseVector:
        vector: SparseVector = {}
        for token in tokenize(text):
            bucket = self._bucket(token)
            vector[bucket] = vector.get(bucket, 0.0) + 1.0
        return {bucket: 1.0 + math.log(count) for bucket, count in vector.items()}
