"""Web UI app layer: document listing honors the wall, ask flows through
the same store enforcement as the CLI. No browser, no model, no server
socket — the handler's state object is exercised directly, and the
answerer is the same mock transport the answer tests use.
"""

import json

import httpx
import pytest

from private_rag.access import AccessPolicy
from private_rag.answer import OllamaAnswerer
from private_rag.corpus import MATTERS, generate
from private_rag.embed import HashingEmbedder
from private_rag.ingest import load_dir
from private_rag.store import Store
from private_rag.webui import _App

HARBOR = "harborview-tower"
POLICY = AccessPolicy({"alice": [HARBOR],
                       "bob": ["meridian-employment", "atlas-escrow"]})


def canned(reply: dict) -> OllamaAnswerer:
    def handler(request):
        return httpx.Response(200, json={
            "message": {"content": json.dumps(reply)}})

    return OllamaAnswerer(http=httpx.Client(
        base_url="http://mock", transport=httpx.MockTransport(handler)))


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    generate(root)
    store = Store(tmp_path_factory.mktemp("db") / "s.db", HashingEmbedder())
    store.add_documents(load_dir(root))
    return _App(store, POLICY, canned({
        "supported": True, "answer": "x", "citations": []}))


def test_document_listing_honors_the_wall(app):
    docs = app.documents("alice")
    assert len(docs) == 8
    assert {d["matter"] for d in docs} == {HARBOR}
    assert app.documents("mallory") == []  # unknown user sees nothing


def test_users_come_from_the_policy(app):
    assert app.users() == ["alice", "bob"]


def test_ask_flows_through_store_enforcement(app):
    result = app.ask("alice", MATTERS[2].planted_fact.split()[-1])  # Nightjar
    assert result["granted_matters"] == [HARBOR]
    assert result["supported"] is False  # no evidence -> refusal, no model
    assert result["model"] is None
