"""Egress evidence: run the full pipeline with non-loopback sockets blocked.

    python scripts/egress_check.py

Runs ingest (local embedding), identity-bound retrieval, and — if a
local Ollama is serving — grounded generation, all inside the loopback-
only socket guard from src/private_rag/netguard.py. Any attempt by this
process to reach a non-loopback address raises and the run dies loudly;
a clean exit is therefore evidence, reproducible by an auditor on their
own hardware. Scope and caveats (Ollama is a separate process; DNS) are
recorded in docs/DEPLOYMENT.md.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # embeddings from cache only

from private_rag.access import AccessPolicy  # noqa: E402
from private_rag.answer import (  # noqa: E402
    DEFAULT_MODEL,
    OllamaAnswerer,
    answer_from_hits,
)
from private_rag.embed import LocalEmbedder  # noqa: E402
from private_rag.ingest import load_dir  # noqa: E402
from private_rag.netguard import loopback_only  # noqa: E402
from private_rag.store import Store  # noqa: E402

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"
POLICY = AccessPolicy({
    "alice": ["harborview-tower"],
    "bob": ["meridian-employment", "atlas-escrow"],
})
QUERIES = [
    ("alice", "crane inspection certification findings"),
    ("alice", "escrow release condition Nightjar"),
    ("bob", "What is the dispute over the escrow release?"),
]


def main() -> int:
    docs = load_dir(SAMPLE)
    with loopback_only(), tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "store.db", LocalEmbedder())
        store.add_documents(docs)
        print(f"ingested {len(docs)} documents "
              "(embedding model loaded from local cache, HF_HUB_OFFLINE=1)")

        answered = 0
        for user, query in QUERIES:
            identity = POLICY.resolve(user)
            hits = store.search(identity, query, k=6)
            print(f"query as {user}: {query!r} -> {len(hits)} chunks, "
                  f"matters {sorted({h.chunk.matter_id for h in hits})}")
            try:
                result = answer_from_hits(query, hits,
                                          OllamaAnswerer(DEFAULT_MODEL))
                verified = sum(c.verified for c in result.citations)
                print(f"  generated (model {result.model}): "
                      f"supported={result.supported}, "
                      f"citations {verified}/{len(result.citations)} verified")
                answered += 1
            except RuntimeError:
                print("  generation skipped (no local Ollama serving)")
        store.close()  # Windows: the temp dir cannot delete an open db

    print("\nfull cycle completed with all non-loopback connections blocked "
          "at the socket layer; any egress attempt by this process would "
          "have raised and aborted this run.")
    print(f"documents: {len(docs)}  queries: {len(QUERIES)}  "
          f"generated answers: {answered}  non-loopback attempts: 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
