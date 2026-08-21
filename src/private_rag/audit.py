"""Audit log: append-only JSONL, one record per retrieval.

Written by the store at its enforcement point, so a query cannot retrieve
without leaving a record — logging is not a courtesy the caller may skip.
Each record carries who asked, what they asked, which matters their
identity resolved to, and which chunks came back. The log therefore
answers an internal review's first questions (who searched what, when,
and what did they see) without a reconstruction exercise.

What the log must never contain: anything from a matter outside the
identity's grant. Since it records only the filtered results, that holds
structurally — and the segregation suite asserts it anyway, because the
log is itself a leakage channel if the structure is ever wrong.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, *, user: str, matters: frozenset[str], query: str,
               chunk_ids: list[str], doc_ids: list[str]) -> None:
        entry = {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            "user": user,
            "granted_matters": sorted(matters),
            "query": query,
            "result_chunks": chunk_ids,
            "result_docs": doc_ids,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line]
