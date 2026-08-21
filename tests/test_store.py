"""Store mechanics: hybrid retrieval works and the file persists.

Segregation has its own suite; this one pins down that the store is a
functioning retrieval system at all (a store that returns nothing would
pass every wall test) and that reopening the file finds the same data.
"""

import pytest

from private_rag.access import AccessPolicy
from private_rag.corpus import MATTERS, generate
from private_rag.embed import HashingEmbedder
from private_rag.ingest import load_dir
from private_rag.store import Store

POLICY = AccessPolicy({"root": [m.matter_id for m in MATTERS]})


@pytest.fixture(scope="module")
def db_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    generate(root)
    db = tmp_path_factory.mktemp("db") / "store.db"
    store = Store(db, HashingEmbedder())
    store.add_documents(load_dir(root))
    store.close()
    return db


def test_planted_facts_retrieve_for_a_full_grant(db_path):
    store = Store(db_path, HashingEmbedder())
    ident = POLICY.resolve("root")
    for spec in MATTERS:
        hits = store.search(ident, spec.planted_fact, k=8)
        assert hits and hits[0].chunk.matter_id == spec.matter_id
        assert spec.planted_fact in hits[0].chunk.text


def test_hits_carry_both_channel_ranks(db_path):
    store = Store(db_path, HashingEmbedder())
    [top, *_] = store.search(POLICY.resolve("root"),
                             "crane inspection certification", k=8)
    assert top.keyword_rank is not None and top.vector_rank is not None


def test_store_persists_across_reopen(db_path):
    stats = Store(db_path, HashingEmbedder()).stats()
    assert stats["documents"] == 8 * len(MATTERS)
    assert stats["matters"] == sorted(m.matter_id for m in MATTERS)


def test_empty_query_returns_nothing(db_path):
    store = Store(db_path, HashingEmbedder())
    assert store.search(POLICY.resolve("root"), "", k=8) == []
