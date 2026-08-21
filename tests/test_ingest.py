"""Ingest and corpus: headers decide matters; planted facts are unique.

The corpus test cross-checks the property the segregation suite depends
on: each matter's planted fact appears in that matter's files and in no
other matter's. A probe fact that leaked into two matters would make
the segregation tests pass vacuously.
"""

import pytest

from private_rag.chunk import chunk_all
from private_rag.corpus import BANNER, MATTERS, generate
from private_rag.ingest import IngestError, load_dir, parse_document

DOC = """SYNTHETIC — GENERATED TEST DATA
MATTER: meridian-employment
DOC: MERIDIAN-LTR-001
DATE: 2026-02-03
TITLE: Demand letter

Re: Whitfield v. Meridian Analytics Corp.

Counsel demands the severance payment provided under the agreement.
"""


def test_parse_reads_labeled_header():
    doc = parse_document(DOC)
    assert doc.matter_id == "meridian-employment"
    assert doc.doc_id == "MERIDIAN-LTR-001"
    assert doc.date.isoformat() == "2026-02-03"
    assert "Counsel demands" in doc.body


def test_parse_survives_dropped_blank_lines():
    squashed = "\n".join(l for l in DOC.splitlines() if l.strip())
    doc = parse_document(squashed)
    assert doc.matter_id == "meridian-employment"
    assert doc.title == "Demand letter"


def test_document_without_matter_header_is_refused():
    headerless = DOC.replace("MATTER: meridian-employment\n", "")
    with pytest.raises(IngestError, match="access boundary"):
        parse_document(headerless)


def test_generated_corpus_parses_and_carries_banner(tmp_path):
    paths = generate(tmp_path)
    docs = load_dir(tmp_path)
    assert len(docs) == len(paths) == 8 * len(MATTERS)
    assert all(BANNER in d.text for d in docs)
    assert all(c.matter_id for c in chunk_all(docs))


def test_planted_facts_are_unique_to_their_matter(tmp_path):
    generate(tmp_path)
    docs = load_dir(tmp_path)
    for spec in MATTERS:
        holders = {d.matter_id for d in docs if spec.planted_fact in d.text}
        assert holders == {spec.matter_id}
