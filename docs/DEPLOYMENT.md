# Deployment and data residency

## Claim being made

No document content, query text, embedding, or derived artifact leaves the host
network at any point in normal operation.

## Data flow

Document → local parser → local embedding model → local vector store
Query → local embedding → local vector store → local model → response

Every stage runs on hardware the operator controls. There is no external
inference call and no telemetry.

## Stack

- Model serving: Ollama or vLLM, local weights
- Embeddings: local model, no hosted embedding API
- Vector store: local, file-backed
- Everything containerized, runnable air-gapped after initial image pull

## What an auditor would ask for

1. Network egress evidence during a full ingest-and-query cycle
2. Where model weights came from and how they were verified
3. Audit log retention and who can read it
4. Access control enforcement point and how it is tested
5. What happens to embeddings when a matter is closed or a document is deleted

Each of these is answered in this document as implementation lands. Deletion is
the one most systems handle badly, since an embedding derived from a deleted
document usually survives it.

Answered so far (2026-08-20):

**(2) Model weights, partially.** Embeddings are model2vec `potion-base-8M`:
~30 MB of static token vectors, downloaded once from Hugging Face, cached
locally, and fully offline afterward — no call leaves the host at query time.
The generation model is not yet wired (Ollama/vLLM per the stack above); its
weight provenance will be recorded here when it lands.

**(3) Audit log.** Append-only JSONL, written by the store at its enforcement
point — a query cannot retrieve without leaving a record of who asked, what
they asked, what their identity resolved to, and exactly which chunks came
back. Retention and readership are the operator's policy; the format is
line-per-event JSON so existing log tooling applies.

**(4) Access control enforcement point.** `Store.search`, documented and
tested in `ACCESS_CONTROL.md` — including the store-vs-store equivalence test
that a security reviewer can re-run (`pytest tests/test_access_segregation.py`).

**(5) Deletion.** Deleting a document removes its rows, its full-text index
entries, and its embeddings in one transaction, then forces an FTS5 segment
merge (`optimize`) and a `VACUUM`. Both steps are load-bearing: SQLite's
DELETE leaves row images in free pages, and FTS5 keeps deleted terms in index
segments until merged — without them, "deleted" text remains recoverable from
the store file with a hex editor. The test suite greps the raw database bytes
after a matter close and asserts the planted content is gone
(`tests/test_deletion.py`). Closing a matter is the same operation applied to
every document in it.

## Hardware baseline

Record actual measured requirements here rather than estimates. A firm evaluating
this needs to know what it costs to run.
