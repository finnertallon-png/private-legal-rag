"""The store: file-backed hybrid retrieval with segregation built in.

This is the enforcement point named in docs/ACCESS_CONTROL.md, and its
design goal is that the unsafe call does not exist. ``search`` requires
an ``Identity`` (obtainable only through the access policy); the
identity's matter set becomes the candidate universe before either
ranking channel runs. The keyword channel filters in SQL; the vector
channel never loads an embedding from an ungranted matter. Documents
outside the grant are not candidates, not ranked, not logged, and not
countable — to a walled-off user, the store behaves identically to one
in which the matter was never ingested. The segregation suite asserts
that equivalence literally, store against store.

Retrieval mechanics are project 02's, deliberately: SQLite FTS5 keyword
ranks fused with brute-force cosine ranks by RRF (k=60). What changed is
where they run — a persistent SQLite file, one store per deployment,
because docs/DEPLOYMENT.md promises a file-backed local store and an
answer to "what happens on deletion". Chunks from different matters are
never grouped or deduplicated: project 02 collapsed repeated text across
the record, but here a cross-matter group would be a structure whose very
existence relates walled documents. Brute-force cosine over the granted
matters is the honest choice at demo scale; the per-matter candidate
pull is the seam where an ANN index would slot in.

Deletion removes the document's rows, its FTS entries, and its
embeddings in one transaction, then VACUUMs — SQLite's DELETE leaves row
images in the file until vacuum, and "deleted" must mean gone from the
bytes on disk, not merely unreachable by query. The deletion test greps
the raw database file to hold this to account.
"""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .access import Identity
from .audit import AuditLog
from .chunk import Chunk, chunk_document
from .embed import Embedder
from .ingest import Document

_RRF_K = 60
_POOL = 50
_KW_SCAN = 400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id    TEXT PRIMARY KEY,
    matter_id TEXT NOT NULL,
    title     TEXT NOT NULL,
    doc_date  TEXT,
    text      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id  TEXT PRIMARY KEY,
    doc_id    TEXT NOT NULL REFERENCES documents(doc_id),
    matter_id TEXT NOT NULL,
    doc_date  TEXT,
    seq       INTEGER NOT NULL,
    text      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_matter ON chunks(matter_id);
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(
    text, chunk_id UNINDEXED, matter_id UNINDEXED
);
CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id TEXT PRIMARY KEY REFERENCES chunks(chunk_id),
    vector   BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class Hit:
    chunk: Chunk
    score: float
    keyword_rank: int | None
    vector_rank: int | None


class Store:
    def __init__(self, path: Path | str, embedder: Embedder,
                 audit: AuditLog | None = None):
        self._db = sqlite3.connect(str(path))
        self._db.executescript(_SCHEMA)
        self._embedder = embedder
        self._audit = audit

    def close(self) -> None:
        self._db.close()

    # A store queried with a different embedder than it was built with
    # returns garbage similarities (or a shape error) with no hint why —
    # so the store records which embedder produced its vectors.
    def set_meta(self, key: str, value: str) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    def get_meta(self, key: str) -> str | None:
        row = self._db.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    # -- ingest ------------------------------------------------------------

    def add_documents(self, docs: list[Document]) -> int:
        """Insert documents and their chunks; embeds chunk text locally."""
        added = 0
        for doc in docs:
            chunks = chunk_document(doc)
            vectors = self._embedder.encode([c.text for c in chunks]) \
                if chunks else np.empty((0, 1), dtype=np.float32)
            with self._db:
                self._db.execute(
                    "INSERT INTO documents VALUES (?, ?, ?, ?, ?)",
                    (doc.doc_id, doc.matter_id, doc.title,
                     doc.date.isoformat() if doc.date else None, doc.text))
                for chunk, vec in zip(chunks, vectors):
                    self._db.execute(
                        "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                        (chunk.chunk_id, chunk.doc_id, chunk.matter_id,
                         chunk.date.isoformat() if chunk.date else None,
                         chunk.seq, chunk.text))
                    self._db.execute(
                        "INSERT INTO chunk_fts VALUES (?, ?, ?)",
                        (chunk.text, chunk.chunk_id, chunk.matter_id))
                    self._db.execute(
                        "INSERT INTO embeddings VALUES (?, ?)",
                        (chunk.chunk_id,
                         np.asarray(vec, dtype=np.float32).tobytes()))
            added += 1
        return added

    # -- retrieval ---------------------------------------------------------

    def search(self, identity: Identity, query: str, k: int = 8) -> list[Hit]:
        """Hybrid search inside the identity's matter grant. Audited."""
        matters = sorted(identity.matters)
        hits: list[Hit] = []
        if matters:  # no grant, no candidates — same shape as empty store
            kw = self._keyword_ranks(query, matters)
            vec = self._vector_ranks(query, matters)
            fused: dict[str, float] = {}
            for chunk_id, rank in kw.items():
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            for chunk_id, rank in vec.items():
                fused[chunk_id] = fused.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
            ranked = sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
            hits = [Hit(chunk=self._chunk(cid), score=score,
                        keyword_rank=kw.get(cid), vector_rank=vec.get(cid))
                    for cid, score in ranked]
        if self._audit is not None:
            self._audit.record(
                user=identity.user, matters=identity.matters, query=query,
                chunk_ids=[h.chunk.chunk_id for h in hits],
                doc_ids=sorted({h.chunk.doc_id for h in hits}))
        return hits

    def _keyword_ranks(self, query: str, matters: list[str]) -> dict[str, int]:
        tokens = re.findall(r"[A-Za-z0-9]+", query)
        if not tokens:
            return {}
        match = " OR ".join(f'"{t}"' for t in tokens)
        placeholders = ",".join("?" * len(matters))
        rows = self._db.execute(
            f"SELECT chunk_id FROM chunk_fts "
            f"WHERE chunk_fts MATCH ? AND matter_id IN ({placeholders}) "
            f"ORDER BY bm25(chunk_fts) LIMIT ?",
            (match, *matters, _KW_SCAN)).fetchall()
        return {cid: rank for rank, (cid,) in
                enumerate(rows[:_POOL], start=1)}

    def _vector_ranks(self, query: str, matters: list[str]) -> dict[str, int]:
        q = self._embedder.encode([query])[0]
        norm = np.linalg.norm(q)
        if norm < 1e-9:
            return {}
        placeholders = ",".join("?" * len(matters))
        rows = self._db.execute(
            f"SELECT e.chunk_id, e.vector FROM embeddings e "
            f"JOIN chunks c ON c.chunk_id = e.chunk_id "
            f"WHERE c.matter_id IN ({placeholders}) "
            f"ORDER BY e.chunk_id",
            matters).fetchall()
        if not rows:
            return {}
        matrix = np.frombuffer(b"".join(v for _, v in rows),
                               dtype=np.float32).reshape(len(rows), -1)
        norms = np.linalg.norm(matrix, axis=1)
        scores = (matrix @ (q / norm)) / np.maximum(norms, 1e-9)
        # Zero-similarity chunks are not results. Padding the list with
        # them would make every query "find" something, and here it would
        # also hand a walled-off user a nonzero result count for a query
        # that matches nothing they can see.
        order = [int(i) for i in np.argsort(-scores) if scores[i] > 1e-9]
        return {rows[i][0]: rank
                for rank, i in enumerate(order[:_POOL], start=1)}

    def _chunk(self, chunk_id: str) -> Chunk:
        row = self._db.execute(
            "SELECT chunk_id, doc_id, matter_id, doc_date, seq, text "
            "FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return Chunk(chunk_id=row[0], doc_id=row[1], matter_id=row[2],
                     date=dt.date.fromisoformat(row[3]) if row[3] else None,
                     seq=row[4], text=row[5])

    # -- lifecycle ---------------------------------------------------------

    def delete_document(self, doc_id: str) -> bool:
        """Remove a document, its chunks, and its embeddings — from the
        file's bytes, not just from query reach."""
        with self._db:
            found = self._db.execute(
                "SELECT 1 FROM documents WHERE doc_id = ?", (doc_id,)
            ).fetchone()
            if not found:
                return False
            self._db.execute(
                "DELETE FROM embeddings WHERE chunk_id IN "
                "(SELECT chunk_id FROM chunks WHERE doc_id = ?)", (doc_id,))
            self._db.execute(
                "DELETE FROM chunk_fts WHERE chunk_id IN "
                "(SELECT chunk_id FROM chunks WHERE doc_id = ?)", (doc_id,))
            self._db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            self._db.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            # FTS5 keeps deleted terms in its index segments until they
            # merge; 'optimize' forces the merge. VACUUM (which must run
            # outside the transaction) then drops the freed pages. Without
            # both, "deleted" text is still recoverable from the file.
            self._db.execute(
                "INSERT INTO chunk_fts(chunk_fts) VALUES('optimize')")
        self._db.execute("VACUUM")
        return True

    def close_matter(self, matter_id: str) -> int:
        """Delete every document in a matter (docs/DEPLOYMENT.md item 5)."""
        doc_ids = [r[0] for r in self._db.execute(
            "SELECT doc_id FROM documents WHERE matter_id = ?",
            (matter_id,)).fetchall()]
        for doc_id in doc_ids:
            self.delete_document(doc_id)
        return len(doc_ids)

    def stats(self) -> dict:
        docs, = self._db.execute("SELECT COUNT(*) FROM documents").fetchone()
        chunks, = self._db.execute("SELECT COUNT(*) FROM chunks").fetchone()
        matters = [r[0] for r in self._db.execute(
            "SELECT DISTINCT matter_id FROM documents ORDER BY matter_id")]
        return {"documents": docs, "chunks": chunks, "matters": matters}
