"""Chunking: one chunk per body paragraph, carrying its matter id.

Every chunk carries ``matter_id`` denormalized from its document. The
store filters on the chunk's own matter column rather than joining back
to the document at query time — the access decision reads one field of
the row it is deciding about, with no join to silently get wrong.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from .ingest import Document


@dataclass(frozen=True)
class Chunk:
    chunk_id: str     # "<doc_id>:<seq>"
    doc_id: str
    matter_id: str
    date: dt.date | None
    seq: int
    text: str


def chunk_document(doc: Document) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", doc.body) if p.strip()]
    return [
        Chunk(
            chunk_id=f"{doc.doc_id}:{seq}",
            doc_id=doc.doc_id,
            matter_id=doc.matter_id,
            date=doc.date,
            seq=seq,
            text=text,
        )
        for seq, text in enumerate(paragraphs)
    ]


def chunk_all(docs: list[Document]) -> list[Chunk]:
    return [c for d in docs for c in chunk_document(d)]
