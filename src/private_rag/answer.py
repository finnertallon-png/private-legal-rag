"""Local generation: draft a grounded answer from retrieved evidence.

The model is served by Ollama on localhost — the same machine as the
store — and receives only what retrieval already returned for this
identity. Segregation therefore does not depend on the model at all: a
walled matter's text can no more appear in the prompt than in the
results, and an identity whose retrieval came back empty gets a refusal
without the model ever being called.

Trust discipline is project 02's, ported to a smaller model where it
matters more: the model must quote its citations verbatim, and every
quote is mechanically checked against the retrieved chunk text after
generation. A citation that fails the check is marked unverified in the
output rather than silently dropped — with a local 8B-class model the
verification layer, not model quality, is what makes answers safe to
rely on, and LIMITATIONS says so.

Generation is JSON-schema-constrained (Ollama structured outputs),
temperature 0. The model name is a parameter: qwen3:8b is the demo
default sized to an 8 GB consumer GPU; llama3.2:3b is the documented
low-load fallback (docs/DEPLOYMENT.md records the measured footprint of
both).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import httpx

from .store import Hit

DEFAULT_MODEL = "qwen3:8b"
FALLBACK_MODEL = "llama3.2:3b"
OLLAMA_HOST = "http://localhost:11434"

_SCHEMA = {
    "type": "object",
    "properties": {
        "supported": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["doc_id", "quote"],
            },
        },
    },
    "required": ["supported", "answer", "citations"],
}

_SYSTEM = (
    "You answer questions about legal matters using ONLY the evidence "
    "excerpts provided. If the evidence does not establish an answer, set "
    "supported to false and say what the accessible record does not show. "
    "Every citation quote must be copied verbatim, character for "
    "character, from an excerpt. Never cite a document that is not in the "
    "evidence. Never use outside knowledge."
)

_NO_EVIDENCE = ("The accessible record contains no documents responsive "
                "to this question.")


@dataclass
class VerifiedCitation:
    doc_id: str
    quote: str
    verified: bool


@dataclass
class AnswerResult:
    question: str
    supported: bool
    answer: str
    citations: list[VerifiedCitation]
    model: str | None  # None when the model was never called

    @property
    def unverified_citations(self) -> list[VerifiedCitation]:
        return [c for c in self.citations if not c.verified]


class OllamaAnswerer:
    """Structured-output chat against a local Ollama server."""

    def __init__(self, model: str = DEFAULT_MODEL, host: str = OLLAMA_HOST,
                 http: httpx.Client | None = None):
        self.model = model
        self._http = http or httpx.Client(base_url=host, timeout=120.0)
        self._host = host

    def answer(self, question: str, evidence: str) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": _SCHEMA,
            "options": {"temperature": 0, "num_ctx": 4096},
            "keep_alive": "30m",  # stay warm between demo questions
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user",
                 "content": f"Evidence excerpts:\n\n{evidence}\n\n"
                            f"Question: {question}"},
            ],
        }
        if self.model.startswith("qwen3"):
            body["think"] = False  # structured output, not a reasoning trace
        try:
            resp = self._http.post("/api/chat", json=body)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"local model server unreachable at {self._host} — is "
                f"Ollama running? ({exc})") from exc
        return json.loads(resp.json()["message"]["content"])


def _normalize(text: str) -> str:
    return " ".join(text.split())


def evidence_block(hits: list[Hit]) -> str:
    return "\n\n".join(
        f"[{h.chunk.doc_id}] ({h.chunk.date.isoformat() if h.chunk.date else 'undated'})\n"
        f"{h.chunk.text}"
        for h in hits)


def verify_citations(raw: list[dict], hits: list[Hit]) -> list[VerifiedCitation]:
    """Verbatim containment check against the retrieved chunks only.

    The evidence the model saw is the entire universe a quote may come
    from; citing anything else — including a real document that was not
    retrieved — is unverified by definition.
    """
    by_doc: dict[str, list[str]] = {}
    for h in hits:
        by_doc.setdefault(h.chunk.doc_id, []).append(_normalize(h.chunk.text))
    out = []
    for c in raw:
        quote = _normalize(str(c.get("quote", "")))
        texts = by_doc.get(str(c.get("doc_id", "")), [])
        verified = bool(quote) and any(quote in t for t in texts)
        out.append(VerifiedCitation(doc_id=str(c.get("doc_id", "")),
                                    quote=str(c.get("quote", "")),
                                    verified=verified))
    return out


def answer_from_hits(question: str, hits: list[Hit],
                     answerer: OllamaAnswerer) -> AnswerResult:
    if not hits:
        # Nothing retrievable for this identity — refuse without ever
        # putting the question to the model. For a walled-off user this
        # is also a guarantee: no evidence, no prompt, no model output.
        return AnswerResult(question=question, supported=False,
                            answer=_NO_EVIDENCE, citations=[], model=None)
    raw = answerer.answer(question, evidence_block(hits))
    return AnswerResult(
        question=question,
        supported=bool(raw.get("supported")),
        answer=str(raw.get("answer", "")),
        citations=verify_citations(raw.get("citations") or [], hits),
        model=answerer.model,
    )
