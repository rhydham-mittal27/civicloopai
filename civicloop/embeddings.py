"""Sentence embeddings for duplicate detection.

The default backend is fastembed (ONNX, no torch) running BAAI/bge-small-en-v1.5. It is loaded
lazily on first use and, if it cannot load (not installed, offline first run), duplicate
detection quietly falls back to word-overlap similarity and says so in the match details.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections import OrderedDict
from typing import Protocol, Sequence

logger = logging.getLogger("civicloop.embeddings")

MODEL_NAME = "BAAI/bge-small-en-v1.5"

# bge-small cosine similarities cluster high even for unrelated short texts, so raw cosine is
# rescaled before it is mixed into the duplicate score: <= FLOOR counts as 0, >= CEIL as 1.
COSINE_FLOOR = 0.55
COSINE_CEIL = 0.90


class TextEmbedder(Protocol):
    name: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def text_similarity(embedder: TextEmbedder, left: str, right: str) -> float:
    """Calibrated 0..1 semantic similarity of two short descriptions."""
    if left.strip().casefold() == right.strip().casefold():
        return 1.0
    a, b = embedder.embed([left, right])
    return min(1.0, max(0.0, (cosine(a, b) - COSINE_FLOOR) / (COSINE_CEIL - COSINE_FLOOR)))


class FastEmbedder:
    name = f"fastembed:{MODEL_NAME}"

    def __init__(self, model_name: str = MODEL_NAME, cache_size: int = 2048) -> None:
        from fastembed import TextEmbedding  # imported here so the extra stays optional

        self._model = TextEmbedding(model_name)
        self._lock = threading.Lock()
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._cache_size = cache_size

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        missing: list[tuple[int, str]] = []
        with self._lock:
            for i, text in enumerate(texts):
                hit = self._cache.get(text)
                if hit is not None:
                    self._cache.move_to_end(text)
                    out[i] = hit
                else:
                    missing.append((i, text))
            if missing:
                vectors = [[float(x) for x in v] for v in self._model.embed([t for _, t in missing])]
                for (i, text), vector in zip(missing, vectors):
                    out[i] = vector
                    self._cache[text] = vector
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
        return [v for v in out if v is not None]


_lock = threading.Lock()
_state: dict[str, object] = {"embedder": None, "tried": False, "error": None}


def default_embedder(load: bool = True) -> TextEmbedder | None:
    """Process-wide embedder, or None when embeddings are off or unavailable.

    CIVICLOOP_EMBEDDINGS=off disables them. Pass load=False to only peek at what is loaded.
    """
    if os.getenv("CIVICLOOP_EMBEDDINGS", "auto").lower() == "off":
        return None
    with _lock:
        if _state["embedder"] is not None or _state["tried"] or not load:
            return _state["embedder"]  # type: ignore[return-value]
        _state["tried"] = True
        try:
            _state["embedder"] = FastEmbedder()
            logger.warning("duplicate detection: loaded %s", MODEL_NAME)
        except Exception as error:  # missing extra, no network on first run, corrupt cache...
            _state["error"] = f"{type(error).__name__}: {error}"[:300]
            logger.warning("duplicate detection: embeddings unavailable, using word overlap (%s)", _state["error"])
        return _state["embedder"]  # type: ignore[return-value]


def embedder_status() -> dict[str, object]:
    embedder = default_embedder(load=False)
    return {
        "enabled": os.getenv("CIVICLOOP_EMBEDDINGS", "auto").lower() != "off",
        "loaded": embedder is not None,
        "name": getattr(embedder, "name", None),
        "error": _state["error"],
    }


def warm_up_in_background() -> None:
    """Load the model off the request path so the first duplicate check is not slow."""
    threading.Thread(target=default_embedder, name="embedder-warmup", daemon=True).start()
