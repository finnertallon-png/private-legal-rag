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

## Known gaps

Record honestly as they are found. A gap documented is a gap a firm can decide
about. A gap discovered by their security review is a credibility problem.
