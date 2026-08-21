"""Synthetic multi-matter sample corpus.

Three unrelated matters in distinct practice areas, so cross-matter
queries are meaningful rather than accidental vocabulary overlap. Each
matter carries one planted fact that appears nowhere else in the corpus
(a serial number, a severance figure, a code name) — the segregation
suite queries these across identities, because "user walled off from
matter B cannot retrieve B's unique fact" is only a meaningful test if
the fact is genuinely unique.

Every document body carries the SYNTHETIC banner and a MATTER header —
ingest refuses documents without one. Generation is deterministic
(seeded) and the sample set is committed; regenerating it after tests
are written against the planted facts would invalidate them, same
freeze discipline as project 02's corpus.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from pathlib import Path

BANNER = "SYNTHETIC — GENERATED TEST DATA"


@dataclass(frozen=True)
class MatterSpec:
    matter_id: str
    caption: str
    planted_fact: str   # unique string; segregation probes query for it


MATTERS = [
    MatterSpec(
        "harborview-tower",
        "Harborview Tower LLC v. Keystone Structural, Inc.",
        "counterweight assembly serial CW-77413",
    ),
    MatterSpec(
        "meridian-employment",
        "Whitfield v. Meridian Analytics Corp.",
        "severance payment of $418,500",
    ),
    MatterSpec(
        "atlas-escrow",
        "Atlas Partners / Northgate Holdings escrow dispute",
        "release condition designated Project Nightjar",
    ),
]

_TEMPLATES = {
    "harborview-tower": [
        ("LTR", "Notice of crane inspection findings",
         "Counsel writes regarding the tower crane inspection at the "
         "Harborview Tower project. The independent rigging survey "
         "identified the {fact} as out of certification, and demands "
         "suspension of lifts pending recertification."),
        ("MEM", "Memo on delay exposure",
         "Internal memorandum assessing schedule exposure from the crane "
         "stand-down. The critical path runs through curtain wall panel "
         "lifts; each idle day adds general conditions cost."),
        ("RPT", "Site observation report",
         "Field observation report for the Harborview Tower site. Concrete "
         "placement on level {n} completed; hoisting operations remained "
         "suspended per counsel's direction."),
        ("MIN", "Meeting minutes — owner/contractor",
         "Minutes of the weekly owner-contractor meeting. Parties discussed "
         "recovery options and reservation of rights regarding the crane "
         "stand-down and resulting delay claims."),
    ],
    "meridian-employment": [
        ("LTR", "Demand letter",
         "Counsel for the former employee asserts wrongful termination and "
         "demands the {fact} provided under the retention agreement, plus "
         "accrued incentive compensation."),
        ("MEM", "Memo on termination timeline",
         "Internal memorandum reconstructing the termination timeline from "
         "personnel records, including the performance review of {n} March "
         "and the decision meeting that followed."),
        ("AGR", "Retention agreement excerpt",
         "Excerpt of the retention agreement addressing severance "
         "eligibility upon termination without cause, including the "
         "computation basis and payment schedule."),
        ("MIN", "Interview notes",
         "Notes of interview with the human resources director regarding "
         "the separation decision and the approvals obtained before "
         "notice was delivered."),
    ],
    "atlas-escrow": [
        ("LTR", "Escrow release objection",
         "Northgate Holdings objects to release of the indemnity escrow, "
         "asserting that the {fact} was not satisfied before the release "
         "notice was issued."),
        ("MEM", "Memo on release conditions",
         "Internal memorandum mapping each escrow release condition in the "
         "purchase agreement to its supporting evidence, and identifying "
         "the disputed condition."),
        ("AGR", "Escrow agreement excerpt",
         "Excerpt of the escrow agreement setting the claim notice "
         "deadline, the joint instruction requirement, and the arbiter "
         "mechanism for disputed releases."),
        ("MIN", "Call notes — escrow agent",
         "Notes of the call with the escrow agent regarding the disputed "
         "release instruction and the agent's position pending joint "
         "direction or an arbiter award."),
    ],
}

DOCS_PER_MATTER = 8


def generate(root: Path, seed: int = 41) -> list[Path]:
    rng = random.Random(seed)
    written = []
    for spec in MATTERS:
        base = dt.date(2026, 1, 12) + dt.timedelta(days=rng.randrange(20))
        out_dir = root / spec.matter_id
        out_dir.mkdir(parents=True, exist_ok=True)
        templates = _TEMPLATES[spec.matter_id]
        for i in range(DOCS_PER_MATTER):
            kind, title, body = templates[i % len(templates)]
            doc_id = f"{spec.matter_id.split('-')[0].upper()}-{kind}-{i + 1:03d}"
            date = base + dt.timedelta(days=rng.randrange(3, 11) * (i + 1))
            text = "\n".join([
                BANNER,
                f"MATTER: {spec.matter_id}",
                f"DOC: {doc_id}",
                f"DATE: {date.isoformat()}",
                f"TITLE: {title}",
                "",
                f"Re: {spec.caption}",
                "",
                body.format(fact=spec.planted_fact, n=rng.randrange(4, 28)),
                "",
                "This document is synthetic test data generated for a "
                "deployment demonstration. It describes no real matter, "
                "person, or project.",
            ])
            path = out_dir / f"{doc_id}.txt"
            path.write_text(text + "\n", encoding="utf-8")
            written.append(path)
    return written
