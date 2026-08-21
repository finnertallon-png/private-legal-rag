"""Parse matter documents: labeled header lines, then body paragraphs.

Every document names its matter in its own header. The alternative —
inferring matter membership from folder layout alone — makes the access
boundary depend on file organization, which is exactly the kind of
implicit state an ethical wall must not rest on. Ingest refuses any
document whose header lacks a matter id.

Header lines are found by label anywhere in the first dozen lines, not
by fixed position: converters and DMS exports drop and reorder blank
lines (a failure observed in project 02, not hypothesized).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

_HEADER_SCAN = 12
_LABELS = ("MATTER", "DOC", "DATE", "TITLE")


class IngestError(ValueError):
    pass


@dataclass(frozen=True)
class Document:
    matter_id: str
    doc_id: str
    title: str
    date: dt.date | None
    text: str       # full original text, header included
    body: str       # text after the header block


def parse_document(text: str, source: str = "<memory>") -> Document:
    fields: dict[str, str] = {}
    header_end = 0
    for i, line in enumerate(text.splitlines()[:_HEADER_SCAN]):
        m = re.match(r"^([A-Z]+):\s*(.+)$", line.strip())
        if m and m.group(1) in _LABELS:
            fields[m.group(1)] = m.group(2).strip()
            header_end = i + 1
    if "MATTER" not in fields or "DOC" not in fields:
        raise IngestError(
            f"{source}: no MATTER/DOC header — a document that does not "
            "declare its matter cannot be placed inside an access boundary"
        )
    date = None
    if "DATE" in fields:
        try:
            date = dt.date.fromisoformat(fields["DATE"])
        except ValueError as exc:
            raise IngestError(f"{source}: bad DATE {fields['DATE']!r}") from exc
    body = "\n".join(text.splitlines()[header_end:]).strip()
    return Document(
        matter_id=fields["MATTER"],
        doc_id=fields["DOC"],
        title=fields.get("TITLE", ""),
        date=date,
        text=text,
        body=body,
    )


def load_dir(root: Path) -> list[Document]:
    """Load every .txt under root. Header, not folder, decides the matter."""
    docs = []
    for path in sorted(root.rglob("*.txt")):
        docs.append(parse_document(path.read_text(encoding="utf-8"),
                                   source=str(path)))
    return docs
