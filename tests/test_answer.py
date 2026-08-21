"""Generation layer against a mocked Ollama server. No model, no network.

What these pin down: citations are verified verbatim against the
retrieved chunks and nothing else (a quote from a real but unretrieved
document is unverified by definition), fabricated quotes are flagged
rather than dropped, an empty retrieval refuses without calling the
model at all — the walled-off user's guarantee — and an unreachable
server is a clear error, not a stack trace.
"""

import json

import httpx
import pytest

from private_rag.access import AccessPolicy
from private_rag.answer import (
    OllamaAnswerer,
    answer_from_hits,
    evidence_block,
)
from private_rag.corpus import generate
from private_rag.embed import HashingEmbedder
from private_rag.ingest import load_dir
from private_rag.store import Store

POLICY = AccessPolicy({"bob": ["atlas-escrow"]})


@pytest.fixture(scope="module")
def hits(tmp_path_factory):
    root = tmp_path_factory.mktemp("corpus")
    generate(root)
    store = Store(tmp_path_factory.mktemp("db") / "s.db", HashingEmbedder())
    store.add_documents(load_dir(root))
    result = store.search(POLICY.resolve("bob"), "Nightjar escrow release",
                          k=6)
    assert result
    return result


def fake_answerer(reply: dict, capture: list | None = None) -> OllamaAnswerer:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(json.loads(request.content))
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(reply)}})

    return OllamaAnswerer(
        model="qwen3:8b",
        http=httpx.Client(base_url="http://mock",
                          transport=httpx.MockTransport(handler)))


def test_verbatim_citation_verifies(hits):
    real_quote = hits[0].chunk.text
    result = answer_from_hits("what is disputed?", hits, fake_answerer({
        "supported": True,
        "answer": "The escrow release is disputed.",
        "citations": [{"doc_id": hits[0].chunk.doc_id, "quote": real_quote}],
    }))
    assert result.supported
    [citation] = result.citations
    assert citation.verified


def test_fabricated_quote_is_flagged_not_dropped(hits):
    result = answer_from_hits("what is disputed?", hits, fake_answerer({
        "supported": True,
        "answer": "x",
        "citations": [{"doc_id": hits[0].chunk.doc_id,
                       "quote": "words that appear in no document"}],
    }))
    [citation] = result.citations
    assert not citation.verified
    assert result.unverified_citations == [citation]


def test_citing_an_unretrieved_document_is_unverified(hits):
    result = answer_from_hits("q", hits, fake_answerer({
        "supported": True, "answer": "x",
        "citations": [{"doc_id": "HARBORVIEW-LTR-001",
                       "quote": hits[0].chunk.text}],
    }))
    assert not result.citations[0].verified


def test_empty_retrieval_refuses_without_calling_the_model():
    calls = []
    result = answer_from_hits("anything", [], fake_answerer({}, calls))
    assert not result.supported
    assert result.model is None
    assert "no documents responsive" in result.answer
    assert calls == []  # the model never saw the question


def test_prompt_carries_only_retrieved_evidence(hits):
    calls = []
    answer_from_hits("what is disputed?", hits, fake_answerer({
        "supported": False, "answer": "n/a", "citations": []}, calls))
    [request] = calls
    user_msg = request["messages"][-1]["content"]
    assert evidence_block(hits) in user_msg
    assert request["options"]["temperature"] == 0
    assert request["format"]["required"] == ["supported", "answer",
                                             "citations"]
    assert request["think"] is False  # qwen3: structured answer, no trace


def test_unreachable_server_is_a_clear_error(hits):
    def down(request):
        raise httpx.ConnectError("refused")

    answerer = OllamaAnswerer(http=httpx.Client(
        base_url="http://mock", transport=httpx.MockTransport(down)))
    with pytest.raises(RuntimeError, match="is Ollama running"):
        answer_from_hits("q", hits, answerer)
