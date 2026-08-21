"""Egress: the ingest-and-query cycle runs with all non-loopback
connections blocked at the socket layer.

The control test proves the guard actually intercepts (a guard that
silently fails open is worse than none). The cycle test then runs the
real pipeline — corpus, local embedding model, store, identity-bound
query — inside it. HF_HUB_OFFLINE forces huggingface_hub to use only
its local cache; if the embedding model has never been downloaded on
this machine the test skips rather than lies.
"""

import httpx
import pytest

from private_rag.access import AccessPolicy
from private_rag.corpus import generate
from private_rag.embed import LocalEmbedder
from private_rag.ingest import load_dir
from private_rag.netguard import EgressAttempt, loopback_only
from private_rag.store import Store


def test_guard_actually_blocks():
    # TEST-NET address: no DNS involved, so the block is what raises.
    with loopback_only():
        with pytest.raises(EgressAttempt, match="non-loopback"):
            httpx.get("http://203.0.113.9", timeout=5)


def test_loopback_stays_allowed():
    # Refused or timed out by the OS — the point is the guard let the
    # attempt through instead of raising EgressAttempt.
    with loopback_only():
        with pytest.raises((httpx.ConnectError, httpx.ConnectTimeout)):
            httpx.get("http://127.0.0.1:9", timeout=2)


def _model_cached() -> bool:
    import os

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    try:
        LocalEmbedder().encode(["probe"])
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _model_cached(),
                    reason="embedding model not in local cache; run once "
                           "online to populate it")
def test_full_cycle_makes_no_external_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    generate(tmp_path / "corpus")
    docs = load_dir(tmp_path / "corpus")
    policy = AccessPolicy({"bob": ["atlas-escrow"]})
    with loopback_only():  # any egress raises, failing the test
        store = Store(tmp_path / "s.db", LocalEmbedder())
        store.add_documents(docs)
        hits = store.search(policy.resolve("bob"), "escrow release", k=5)
    assert hits
