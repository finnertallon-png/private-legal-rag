"""Regenerate the committed sample corpus (data/sample).

The sample is frozen by the same discipline as project 02's corpus: the
segregation tests are written against its planted facts, so regenerating
it invalidates them. Run this only to rebuild after a deliberate,
recorded change to the corpus module.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from private_rag.corpus import generate  # noqa: E402

if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent / "data" / "sample"
    paths = generate(root)
    print(f"wrote {len(paths)} documents under {root}")
