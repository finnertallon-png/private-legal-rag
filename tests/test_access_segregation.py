"""Access segregation, verified by test — never by inspection.

The standard these tests hold the store to: to a walled-off user, a
matter must be indistinguishable from a matter that was never ingested.
Not "filtered out of the answer", not "ranked low" — absent from
results, result counts, scores, and the audit trail. The equivalence
test builds two stores, one with the walled matter and one without, and
asserts the walled user's results are byte-for-byte identical.

Probes query each matter's planted fact (unique to that matter by
construction, asserted in test_ingest) so a leak cannot hide behind
vocabulary overlap. Everything runs on the offline HashingEmbedder:
segregation is the store's property, not the embedding model's.
"""

import pytest

from private_rag.access import AccessPolicy, Identity
from private_rag.audit import AuditLog
from private_rag.corpus import MATTERS, generate
from private_rag.embed import HashingEmbedder
from private_rag.ingest import load_dir
from private_rag.store import Store

HARBOR, MERIDIAN, ATLAS = [m.matter_id for m in MATTERS]
FACT = {m.matter_id: m.planted_fact for m in MATTERS}

POLICY = AccessPolicy({
    "alice": [HARBOR],
    "bob": [MERIDIAN, ATLAS],
})


@pytest.fixture(scope="module")
def docs(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    generate(root)
    return load_dir(root)


@pytest.fixture(scope="module")
def store(tmp_path_factory, docs):
    s = Store(tmp_path_factory.mktemp("db") / "store.db", HashingEmbedder())
    s.add_documents(docs)
    return s


def test_walled_user_never_retrieves_walled_content(store):
    alice = POLICY.resolve("alice")
    for walled in (MERIDIAN, ATLAS):
        hits = store.search(alice, FACT[walled], k=20)
        assert all(h.chunk.matter_id == HARBOR for h in hits)
        assert all(FACT[walled] not in h.chunk.text for h in hits)


def test_walled_matter_is_indistinguishable_from_nonexistent(
        tmp_path_factory, docs):
    """The core guarantee, asserted literally: identical results from a
    store that contains the walled matter and one that never did."""
    alice = POLICY.resolve("alice")
    with_b = Store(tmp_path_factory.mktemp("w") / "s.db", HashingEmbedder())
    with_b.add_documents(docs)
    without_b = Store(tmp_path_factory.mktemp("wo") / "s.db", HashingEmbedder())
    without_b.add_documents([d for d in docs if d.matter_id == HARBOR])

    for query in ["crane inspection findings", FACT[MERIDIAN], FACT[ATLAS],
                  "settlement escrow severance", "meeting minutes"]:
        a = [(h.chunk.chunk_id, round(h.score, 9), h.keyword_rank,
              h.vector_rank) for h in with_b.search(alice, query, k=20)]
        b = [(h.chunk.chunk_id, round(h.score, 9), h.keyword_rank,
              h.vector_rank) for h in without_b.search(alice, query, k=20)]
        assert a == b


def test_result_counts_reveal_nothing(store):
    # A query matching only walled content returns zero hits, not a
    # truncated or padded list a user could count. ("Nightjar" exists
    # only in the walled matter; a query with common words like
    # "Project" legitimately matches in-grant material instead.)
    alice = POLICY.resolve("alice")
    assert store.search(alice, "Nightjar", k=20) == []
    common = store.search(alice, "Project Nightjar", k=20)
    assert all(h.chunk.matter_id == HARBOR for h in common)


def test_unknown_user_gets_nothing(store):
    stranger = POLICY.resolve("mallory")
    assert stranger.matters == frozenset()
    assert store.search(stranger, FACT[HARBOR], k=20) == []


def test_multi_matter_grant_stays_inside_the_grant(store):
    bob = POLICY.resolve("bob")
    hits = store.search(bob, "agreement excerpt deadline", k=20)
    assert hits, "granted matters should retrieve"
    assert {h.chunk.matter_id for h in hits} <= {MERIDIAN, ATLAS}
    assert all(FACT[HARBOR] not in h.chunk.text for h in hits)


def test_audit_log_never_records_walled_material(tmp_path, docs):
    audit = AuditLog(tmp_path / "audit.jsonl")
    s = Store(tmp_path / "s.db", HashingEmbedder(), audit=audit)
    s.add_documents(docs)
    alice = POLICY.resolve("alice")
    s.search(alice, "Nightjar", k=20)  # walled-only token
    s.search(alice, "crane inspection", k=20)

    entries = audit.entries()
    assert len(entries) == 2  # retrieval cannot happen unlogged
    for entry in entries:
        assert entry["user"] == "alice"
        assert entry["granted_matters"] == [HARBOR]
        assert all(doc.doc_id not in entry["result_docs"]
                   for doc in docs if doc.matter_id != HARBOR)
    # the walled-fact query logged an honest empty result
    assert entries[0]["result_docs"] == []


def test_identity_only_comes_from_the_policy():
    # Deny-by-default: an identity built by hand with no matters — the
    # only kind constructible without the policy granting it — sees nothing.
    assert Identity("anyone", frozenset()).matters == frozenset()
    assert POLICY.resolve("alice").matters == frozenset({HARBOR})
