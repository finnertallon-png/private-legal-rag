# Example runs

Unedited output of real runs against the committed sample corpus
(three synthetic matters), on the hardware recorded in
`docs/DEPLOYMENT.md`, with generation by a local `qwen3:8b` via Ollama.
All three `ask` runs pose the **same question** — *"What is the dispute
over the escrow release?"* — which belongs to the `atlas-escrow` matter.
What changes is who asks, and with which model.

## `ask_bob_escrow.json` — granted access, default model

bob's grant includes `atlas-escrow`. Retrieval returns only atlas
chunks, and the model answers with a citation quoted verbatim from
`ATLAS-LTR-001` — `"verified": true` means the quote survived a
character-level containment check against the retrieved text, done in
code after generation, not taken on the model's word.

## `ask_alice_walled.json` — walled off

alice's grant is `harborview-tower` only. Note `retrieved`: every chunk
is harborview material — the atlas documents were never candidates, so
nothing about them could enter the model's prompt. The model honestly
reports that the accessible record does not show an answer. To alice,
the escrow matter is indistinguishable from one that does not exist;
`tests/test_access_segregation.py` asserts that equivalence literally.

## `ask_bob_fallback_3b.json` — same access, smaller model

Same user and question as the first run, but generated with the
`llama3.2:3b` fallback. Read it closely: the answer text is *correct* —
and the model labeled it `"supported": false` with zero citations. This
is the measured capability cost of the 3B tier (recorded in
`docs/LIMITATIONS.md`), committed here rather than papered over,
because it is the concrete argument for both the 8B default and the
mechanical citation verifier.

## `audit_excerpt.jsonl` — the trail the three runs left

One line per retrieval, written by the store at its enforcement point —
a query cannot retrieve without leaving one. Each records who asked,
what they asked, what their identity resolved to, and exactly which
chunks came back. alice's line contains no atlas document ids: the log
records what retrieval returned, and retrieval never crossed the wall.

## `egress_check.txt` — data residency evidence

Output of `python scripts/egress_check.py`: the full cycle — local
embedding, ingest, all three identities' retrievals, live generation —
run with every non-loopback socket connection blocked in-process. Any
egress attempt would have raised and aborted the run; the clean summary
is the evidence, and an auditor can re-run it on their own hardware.
Scope and caveats are in `docs/DEPLOYMENT.md`.
