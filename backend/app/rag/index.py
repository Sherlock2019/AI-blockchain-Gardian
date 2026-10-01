"""Vector index abstraction with an in-memory implementation.

`VectorIndex` is the seam where pgvector, Qdrant or similar would plug in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.rag.chunking import Chunk
from app.rag.embeddings import SparseVector


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    score: float


class VectorIndex(Protocol):
    def add(self, chunk: Chunk, vector: SparseVector) -> None: ...

    def search(self, vector: SparseVector, k: int, kind: str | None = None) -> list[SearchHit]: ...

    def get(self, source_id: str) -> Chunk | None: ...


class InMemoryIndex:
    """Cosine similarity over IDF-weighted sparse vectors."""

    def __init__(self) -> None:
        self._entries: list[tuple[Chunk, SparseVector]] = []
        self._by_id: dict[str, Chunk] = {}
        self._document_frequency: dict[int, int] = {}

    def add(self, chunk: Chunk, vector: SparseVector) -> None:
        self._entries.append((chunk, vector))
        self._by_id[chunk.source_id] = chunk
        for bucket in vector:
            self._document_frequency[bucket] = self._document_frequency.get(bucket, 0) + 1

    def get(self, source_id: str) -> Chunk | None:
        return self._by_id.get(source_id)

    def _weighted(self, vector: SparseVector) -> SparseVector:
        total = len(self._entries)
        return {
            bucket: value * math.log(1 + total / (1 + self._document_frequency.get(bucket, 0)))
            for bucket, value in vector.items()
        }

    def search(self, vector: SparseVector, k: int, kind: str | None = None) -> list[SearchHit]:
        query = self._weighted(vector)
        query_norm = math.sqrt(sum(v * v for v in query.values()))
        if not query_norm:
            return []
        hits = []
        for chunk, raw in self._entries:
            if kind and chunk.kind != kind:
                continue
            document = self._weighted(raw)
            dot = sum(weight * document.get(bucket, 0.0) for bucket, weight in query.items())
            if dot <= 0:
                continue
            norm = math.sqrt(sum(v * v for v in document.values()))
            hits.append(SearchHit(chunk, round(dot / (query_norm * norm), 4)))
        hits.sort(key=lambda hit: (-hit.score, hit.chunk.source_id))
        return hits[:k]
