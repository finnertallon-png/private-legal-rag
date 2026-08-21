# Private Legal RAG

The retrieval system from `02-construction-claim-rag`, deployed entirely on local
infrastructure. No document, query, or embedding leaves the network.

## The problem

The barrier to AI adoption inside law firms is rarely capability. It is that
client documents are privileged, outside counsel guidelines frequently restrict
where client data may be processed, and clients increasingly audit their firms'
security posture directly. A tool that requires sending documents to a third
party API is a non-starter for a large share of a firm's matters regardless of
how well it performs.

## Who this is for

Firm IT and security teams evaluating whether AI over client documents can be
done inside their own perimeter.

## What this demonstrates

- Local model serving and local embedding, no external inference calls
- Local vector store, no hosted index
- Query and retrieval audit logging sufficient for an internal review
- **Matter-level access segregation** — retrieval is filtered by the requesting
  user's matter access before ranking, so a user cannot retrieve from a matter
  they are walled off from

That last item is the part most retrieval systems get wrong. Ethical walls are
not a preference, and a system that enforces them only in its answer layer while
retrieving across everything has already failed.

## Deployment and data residency

See `docs/DEPLOYMENT.md` — architecture, data flow, and what an auditor would
want to see.

## Access control

See `docs/ACCESS_CONTROL.md` — the segregation model, its threat model, and its
known gaps.

## Running it

```sh
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"

# Ingest the sample corpus (three synthetic matters; embeds locally)
python -m private_rag ingest data/sample

# Query as a user — every query is identity-bound and audited
python -m private_rag query "crane inspection findings" --user alice
python -m private_rag query "escrow release condition" --user alice   # walled: nothing responsive
python -m private_rag query "escrow release condition" --user bob

# Deletion that means it
python -m private_rag forget ATLAS-LTR-001
python -m private_rag close-matter atlas-escrow

python -m private_rag audit
pytest   # includes the segregation suite; runs fully offline
```

Retrieval, segregation, deletion, and audit are implemented and tested. The
local *generation* layer (Ollama/vLLM per `docs/DEPLOYMENT.md`) is the next
stage and is not yet wired — what exists today retrieves and cites; it does
not draft answers.

## Limitations

See `docs/LIMITATIONS.md`.

## License

MIT. See `LICENSE`.
