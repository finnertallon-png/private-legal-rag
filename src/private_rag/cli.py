"""CLI: ingest, query, forget, close-matter, audit, stats.

Every query names a user, because the store will not search without an
identity — there is deliberately no --all-matters escape hatch. The
demo resolves users against data/access.json; a deployment resolves
them against the firm's identity systems (see access.py).

The store records which embedder built it; querying with a different
one is refused rather than silently returning nonsense similarities.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .access import AccessPolicy
from .audit import AuditLog
from .embed import DEFAULT_EMBEDDING_MODEL, HashingEmbedder, LocalEmbedder
from .ingest import IngestError, load_dir
from .store import Store

DEFAULT_DB = Path("store.db")
DEFAULT_ACCESS = Path("data/access.json")
DEFAULT_AUDIT = Path("audit.jsonl")


def _embedder(args):
    if args.hash_embedder:
        return HashingEmbedder(), "hashing"
    return LocalEmbedder(), DEFAULT_EMBEDDING_MODEL


def _open_store(args, expect_match: bool = True) -> Store:
    embedder, name = _embedder(args)
    if expect_match and not Path(args.db).exists():
        print(f"error: no store at {args.db} — run ingest first",
              file=sys.stderr)
        raise SystemExit(1)
    store = Store(args.db, embedder)
    recorded = store.get_meta("embedder")
    if expect_match and recorded and recorded != name:
        print(f"error: store was built with embedder '{recorded}' but this "
              f"run uses '{name}' — mixed embeddings return garbage, "
              "refusing", file=sys.stderr)
        raise SystemExit(1)
    if not expect_match:
        store.set_meta("embedder", name)
    return store


def _cmd_ingest(args) -> int:
    try:
        docs = load_dir(Path(args.source))
    except IngestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    store = _open_store(args, expect_match=False)
    count = store.add_documents(docs)
    print(json.dumps({"ingested": count, **store.stats()}, indent=2))
    return 0


def _cmd_query(args) -> int:
    policy = AccessPolicy.load(Path(args.access))
    identity = policy.resolve(args.user)
    store = Store(args.db, _embedder(args)[0],
                  audit=AuditLog(Path(args.audit)))
    recorded = store.get_meta("embedder")
    if recorded and recorded != _embedder(args)[1]:
        print(f"error: store built with embedder '{recorded}'",
              file=sys.stderr)
        return 1
    hits = store.search(identity, args.question, k=args.k)
    print(json.dumps({
        "user": identity.user,
        "granted_matters": sorted(identity.matters),
        "query": args.question,
        "hits": [
            {
                "chunk_id": h.chunk.chunk_id,
                "doc_id": h.chunk.doc_id,
                "matter": h.chunk.matter_id,
                "date": h.chunk.date.isoformat() if h.chunk.date else None,
                "score": round(h.score, 6),
                "text": h.chunk.text,
            }
            for h in hits
        ],
    }, indent=2, ensure_ascii=False))
    return 0


def _cmd_ask(args) -> int:
    from .answer import DEFAULT_MODEL, OllamaAnswerer, answer_from_hits

    policy = AccessPolicy.load(Path(args.access))
    identity = policy.resolve(args.user)
    store = Store(args.db, _embedder(args)[0],
                  audit=AuditLog(Path(args.audit)))
    hits = store.search(identity, args.question, k=args.k)
    try:
        result = answer_from_hits(
            args.question, hits,
            OllamaAnswerer(model=args.model or DEFAULT_MODEL))
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({
        "user": identity.user,
        "granted_matters": sorted(identity.matters),
        "question": args.question,
        "model": result.model,
        "supported": result.supported,
        "answer": result.answer,
        "citations": [
            {"doc_id": c.doc_id, "quote": c.quote, "verified": c.verified}
            for c in result.citations
        ],
        "retrieved": [h.chunk.chunk_id for h in hits],
    }, indent=2, ensure_ascii=False))
    if result.unverified_citations:
        print(f"warning: {len(result.unverified_citations)} citation(s) "
              "failed verbatim verification", file=sys.stderr)
    return 0


def _cmd_forget(args) -> int:
    store = _open_store(args)
    gone = store.delete_document(args.doc_id)
    print(json.dumps({"doc_id": args.doc_id, "deleted": gone,
                      **store.stats()}, indent=2))
    return 0 if gone else 1


def _cmd_close_matter(args) -> int:
    store = _open_store(args)
    count = store.close_matter(args.matter_id)
    print(json.dumps({"matter_id": args.matter_id,
                      "documents_deleted": count, **store.stats()}, indent=2))
    return 0


def _cmd_audit(args) -> int:
    for entry in AuditLog(Path(args.audit)).entries():
        print(json.dumps(entry, ensure_ascii=False))
    return 0


def _cmd_stats(args) -> int:
    store = _open_store(args)
    print(json.dumps({**store.stats(),
                      "embedder": store.get_meta("embedder")}, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="private-rag",
        description="Matter-segregated retrieval, entirely local.")
    # Shared flags live on a parent parser so they are valid after the
    # subcommand too (`ask ... --db x`), which is where people type them.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=DEFAULT_DB, help="store file")
    common.add_argument("--hash-embedder", action="store_true",
                        help="offline test embedder instead of the local model")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", parents=[common],
                       help="ingest a directory of .txt documents")
    p.add_argument("source")
    p.set_defaults(fn=_cmd_ingest)

    p = sub.add_parser("query", parents=[common],
                       help="search as a user; audited")
    p.add_argument("question")
    p.add_argument("--user", required=True)
    p.add_argument("--access", default=DEFAULT_ACCESS)
    p.add_argument("--audit", default=DEFAULT_AUDIT)
    p.add_argument("--k", type=int, default=8)
    p.set_defaults(fn=_cmd_query)

    p = sub.add_parser("ask", parents=[common],
                       help="retrieve as a user, then draft a "
                       "grounded answer with the local model; audited")
    p.add_argument("question")
    p.add_argument("--user", required=True)
    p.add_argument("--access", default=DEFAULT_ACCESS)
    p.add_argument("--audit", default=DEFAULT_AUDIT)
    p.add_argument("--k", type=int, default=8)
    p.add_argument("--model", default=None,
                   help="Ollama model (default qwen3:8b; llama3.2:3b is the "
                        "documented low-load fallback)")
    p.set_defaults(fn=_cmd_ask)

    p = sub.add_parser("forget", parents=[common],
                       help="delete one document and its embeddings")
    p.add_argument("doc_id")
    p.set_defaults(fn=_cmd_forget)

    p = sub.add_parser("close-matter", parents=[common],
                       help="delete every document in a matter")
    p.add_argument("matter_id")
    p.set_defaults(fn=_cmd_close_matter)

    p = sub.add_parser("audit", parents=[common],
                       help="print the audit log")
    p.add_argument("--audit", default=DEFAULT_AUDIT)
    p.set_defaults(fn=_cmd_audit)

    p = sub.add_parser("stats", parents=[common],
                       help="store contents summary")
    p.set_defaults(fn=_cmd_stats)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
