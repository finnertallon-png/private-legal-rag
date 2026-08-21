"""Access policy: who may retrieve from which matters. Deny by default.

The policy file maps users to matter ids (data/access.json in the demo).
``resolve`` is the only way to obtain an ``Identity``, and an Identity is
the only thing the store's search accepts — there is no code path that
retrieves without first passing through this resolution. An unknown user
resolves to an Identity with no matters, which retrieves nothing; it does
not error, because "you get nothing" must be indistinguishable from "there
is nothing" (see the inference-channel threat in docs/ACCESS_CONTROL.md).

In a real deployment this file is replaced by the firm's identity and
matter-intake systems (Entra group claims, DMS ethical-wall API). The
enforcement point — the store query — does not change; only where the
matter set comes from does. That seam is the reason this module is
deliberately thin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Identity:
    user: str
    matters: frozenset[str]


class AccessPolicy:
    def __init__(self, grants: dict[str, list[str]]):
        self._grants = {user: frozenset(matters)
                        for user, matters in grants.items()}

    @classmethod
    def load(cls, path: Path) -> "AccessPolicy":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data["users"])

    def resolve(self, user: str) -> Identity:
        """The only constructor of authority. Unknown users get nothing."""
        return Identity(user=user, matters=self._grants.get(user, frozenset()))
