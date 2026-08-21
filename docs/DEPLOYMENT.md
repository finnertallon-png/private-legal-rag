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

**(2) Model weights.** Embeddings are model2vec `potion-base-8M`: ~30 MB of
static token vectors, downloaded once from Hugging Face, cached locally, and
fully offline afterward — no call leaves the host at query time. Generation
is served by Ollama on localhost; models are pulled from Ollama's registry as
content-addressed layers verified by sha256 digest (`ollama list` shows the
digest ids). The pinned demo model is `qwen3:8b` (4-bit quantization);
`llama3.2:3b` is the low-load fallback, with its capability cost measured and
recorded below.

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

Measured 2026-08-20 on a consumer laptop — deliberately not a server: AMD
Ryzen 9 8945HS, 16 GB RAM, NVIDIA RTX 4060 Laptop (8 GB VRAM), Windows 11.

- `qwen3:8b` (4-bit): **5.6 GB VRAM**, fully GPU-resident at 4k context.
  Warm end-to-end `ask` (embed query → retrieve → generate → verify
  citations): **~5 seconds**. First call after idle pays the model load
  (~1 minute worst case observed cold); the pipeline sets a 30-minute
  keep-alive, so a session pays it once.
- `llama3.2:3b` (4-bit): **2.6 GB VRAM**. Runs comfortably alongside heavy
  desktop load, but with a measured capability cost: on a question the
  evidence plainly supported, it repeatedly produced the correct answer text
  while labeling it `supported: false` with no citations — a schema-
  discipline failure the 8B model did not exhibit. It is an emergency
  fallback for constrained machines, not an equivalent choice; treat its
  refusals as unreliable.
- The two models do not fit in 8 GB VRAM together; switching models
  mid-session evicts the loaded one and repays the load time.

The 8 GB-VRAM single-GPU class is therefore a real floor for the 8B demo
configuration, with roughly 2.5 GB VRAM headroom left for a video call and
desktop compositing during a live demonstration.
