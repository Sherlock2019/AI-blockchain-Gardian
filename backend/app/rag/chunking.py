"""Document ingestion and chunking.

Policies are split on their numbered `##` sections so a citation points at a
clause a person can open and read ("Payment Policy §3"), not at an arbitrary
window of characters.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_SECTION = re.compile(r"^##\s+(?:(\d+)\.\s*)?(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    source_id: str
    kind: str
    title: str
    text: str


def _policy_title(stem: str) -> str:
    words = stem.replace("_", " ").title()
    return words.replace("Ai ", "AI ")


def chunk_policy(path: Path) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    matches = list(_SECTION.finditer(text))
    chunks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        number = match.group(1) or str(index + 1)
        body = " ".join(text[match.end() : end].split())
        chunks.append(
            Chunk(
                source_id=f"policy:{path.stem}#{number}",
                kind="policy",
                title=f"{_policy_title(path.stem)} §{number} — {match.group(2).strip()}",
                text=body,
            )
        )
    return chunks


def chunk_contracts(path: Path) -> list[Chunk]:
    contracts = json.loads(path.read_text(encoding="utf-8"))
    return [
        Chunk(
            source_id=f"contract:{c['id']}",
            kind="contract",
            title=c["title"],
            text=f"{c['terms']} Covers purchase orders: {', '.join(c['purchase_order_ids'])}.",
        )
        for c in contracts
    ]


def load_corpus(data_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted((data_dir / "policies").glob("*.md")):
        chunks.extend(chunk_policy(path))
    contracts = data_dir / "contracts.json"
    if contracts.exists():
        chunks.extend(chunk_contracts(contracts))
    return chunks
