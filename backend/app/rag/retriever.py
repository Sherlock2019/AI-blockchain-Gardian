"""Retrieval over the local corpus."""

from __future__ import annotations

from pathlib import Path

from app.rag.chunking import Chunk, load_corpus
from app.rag.embeddings import Embedder, HashingEmbedder
from app.rag.index import InMemoryIndex, SearchHit, VectorIndex


class Retriever:
    def __init__(self, embedder: Embedder, index: VectorIndex) -> None:
        self._embedder = embedder
        self._index = index

    def ingest(self, chunks: list[Chunk]) -> int:
        for chunk in chunks:
            self._index.add(chunk, self._embedder.embed(f"{chunk.title}. {chunk.text}"))
        return len(chunks)

    def search(self, query: str, k: int = 4, kind: str | None = None) -> list[SearchHit]:
        return self._index.search(self._embedder.embed(query), k, kind)

    def get(self, source_id: str) -> Chunk | None:
        return self._index.get(source_id)


def build_retriever(data_dir: Path) -> Retriever:
    retriever = Retriever(HashingEmbedder(), InMemoryIndex())
    retriever.ingest(load_corpus(data_dir))
    return retriever
