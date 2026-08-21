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

## Hardware baseline

Record actual measured requirements here rather than estimates. A firm evaluating
this needs to know what it costs to run.
