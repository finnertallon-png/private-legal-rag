"""Embedding seam: a Protocol, the pinned local model, and a test double.

Same decision as project 02, and doubly load-bearing here: model2vec's
potion-base-8M is static token embeddings in pure numpy — no PyTorch, no
GPU requirement, ~30 MB, cached by huggingface_hub after one download and
fully offline afterward. For a deployment whose whole claim is "nothing
leaves the network", an embedding model that phones nothing home after
install is a requirement, not a convenience. The one-time download and
its verification are recorded in docs/DEPLOYMENT.md.

HashingEmbedder is the offline test double: deterministic bag-of-tokens
hashing, no network, no model file. The access-segregation suite runs on
it — segregation is a property of the store's filtering, not of
embedding quality, and the tests must run air-gapped.
"""

from __future__ import annotations

import re
import zlib
from typing import Protocol

import numpy as np

DEFAULT_EMBEDDING_MODEL = "minishlab/potion-base-8M"


class Embedder(Protocol):
    def encode(self, texts: list[str]) -> np.ndarray: ...


class LocalEmbedder:
    """model2vec static-embedding model, loaded lazily."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._model is None:
            from model2vec import StaticModel

            self._model = StaticModel.from_pretrained(self.model_name)
        return np.asarray(self._model.encode(texts), dtype=np.float32)


class HashingEmbedder:
    """Deterministic offline stand-in for tests: hashed bag of tokens."""

    def __init__(self, dim: int = 512):
        self.dim = dim

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for token in re.findall(r"[a-z0-9]+", text.lower()):
                out[i, zlib.crc32(token.encode()) % self.dim] += 1.0
        return out
