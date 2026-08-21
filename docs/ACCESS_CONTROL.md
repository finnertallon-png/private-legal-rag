# Matter-level access segregation

## Why this exists

Firms operate ethical walls: attorneys working one matter may be formally barred
from access to another. A retrieval system that ignores this is not deployable
regardless of its quality, and a system that filters only at the answer layer has
already leaked — retrieval itself reveals that responsive material exists.

## Model

Access is enforced at retrieval, before ranking. The vector store query carries
the requesting identity's permitted matter set as a hard filter. Documents
outside that set are never candidates, never ranked, and never appear in any
intermediate state.

## Threat model

Addressed:
- A user querying content in a matter they are walled off from
- Inference of walled content through retrieval behavior or result counts
- Leakage through cached or logged intermediate results

Not addressed:
- A compromised administrator account
- Physical access to the host
- A user who legitimately has access misusing it

## Testing

Segregation is verified by test, not by inspection. The suite includes a user
with access to matter A querying content that exists only in matter B, and
asserts nothing responsive is retrieved, ranked, logged as retrievable, or
inferable from result metadata.

## Implementation (2026-08-20)

The enforcement point is `Store.search` (`src/private_rag/store.py`): it
accepts only an `Identity`, which is constructible in practice only through
`AccessPolicy.resolve` — deny by default, unknown users resolve to an empty
matter set and retrieve nothing, indistinguishably from querying an empty
store. The identity's matter set bounds the candidate universe before either
ranking channel runs: the keyword channel filters in SQL, the vector channel
never loads an embedding from an ungranted matter. There is no search API
without an identity and no all-matters flag.

Two design consequences worth naming:

- Chunks are never grouped or deduplicated across matters. Project 02
  collapses repeated text across its record; here a cross-matter group would
  be a data structure whose existence relates walled documents.
- Zero-similarity chunks are not results. Without that rule, the vector
  channel pads every query's result list from whatever the user can see,
  which turns "how many results did I get" into noise; with it, a query that
  matches nothing a user can see returns an honest empty list.

The test suite (`tests/test_access_segregation.py`) holds retrieval to a
stronger standard than "filtered": a store containing the walled matter and a
store that never ingested it must return byte-identical results — ids, scores,
and per-channel ranks — to the walled-off user. Probes query planted facts
that are unique to one matter by construction (uniqueness itself asserted in
`tests/test_ingest.py`, so the wall tests cannot pass on vocabulary luck).
The audit log is asserted never to record walled material, because a log is
itself a leakage channel if the filtering is ever wrong. All segregation
tests run on the offline hashing embedder: the wall is the store's property,
not the embedding model's, and the suite must run air-gapped.

## Known gaps

Record honestly as they are found. A gap documented is a gap a firm can decide
about. A gap discovered by their security review is a credibility problem.

- The demo policy file (`data/access.json`) is plaintext and unauthenticated:
  anyone who can edit it can grant themselves access, and the CLI trusts the
  `--user` argument without authentication. The enforcement point is real;
  the identity *source* is a stub for the firm's IdP and ethical-wall
  systems, and swapping it in is the deployment integration named in
  `access.py`.
