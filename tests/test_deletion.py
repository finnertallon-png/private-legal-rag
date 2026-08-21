"""Deletion: an embedding derived from a deleted document must not
survive it — in query results or in the bytes of the store file.

The bytes-level assertion is the one comparable systems fail: SQLite's
DELETE leaves row images in free pages, and FTS5 keeps deleted terms in
index segments until merged. The store optimizes and vacuums on delete;
these tests grep the raw file to hold it to that.
"""

import pytest

from private_rag.access import AccessPolicy
from private_rag.corpus import MATTERS, generate
from private_rag.embed import HashingEmbedder
from private_rag.ingest import load_dir
from private_rag.store import Store

ATLAS = "atlas-escrow"
POLICY = AccessPolicy({"bob": [m.matter_id for m in MATTERS]})


@pytest.fixture
def loaded(tmp_path):
    generate(tmp_path / "corpus")
    docs = load_dir(tmp_path / "corpus")
    db = tmp_path / "store.db"
    store = Store(db, HashingEmbedder())
    store.add_documents(docs)
    return store, db, docs


def test_deleted_document_leaves_retrieval(loaded):
    store, _, docs = loaded
    bob = POLICY.resolve("bob")
    target = next(d for d in docs if "Nightjar" in d.text)
    assert any(h.chunk.doc_id == target.doc_id
               for h in store.search(bob, "Nightjar", k=20))
    assert store.delete_document(target.doc_id)
    assert all(h.chunk.doc_id != target.doc_id
               for h in store.search(bob, "Nightjar", k=20))


def test_closed_matter_is_gone_from_the_file_bytes(loaded):
    store, db, docs = loaded
    atlas_docs = [d for d in docs if d.matter_id == ATLAS]
    raw = db.read_bytes()
    assert b"Nightjar" in raw and b"nightjar" in raw  # text + FTS tokens

    assert store.close_matter(ATLAS) == len(atlas_docs)

    bob = POLICY.resolve("bob")
    assert store.search(bob, "Nightjar", k=20) == []
    assert store.stats()["matters"] == sorted(
        m.matter_id for m in MATTERS if m.matter_id != ATLAS)
    raw = db.read_bytes()
    assert b"Nightjar" not in raw and b"nightjar" not in raw


def test_deleting_missing_document_reports_false(loaded):
    store, _, _ = loaded
    assert store.delete_document("NO-SUCH-DOC") is False
