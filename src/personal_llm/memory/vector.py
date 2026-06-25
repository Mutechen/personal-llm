"""Vector packing + brute-force cosine search.

The first cut of the L4 vector layer. The architecture's rule is *file-based
until >10k chunks, a real index only after* (PRIOR_ART.md "premature vector
DBs"); at that scale a brute-force cosine over float32 blobs in sqlite is faster
to reason about than a loadable extension, and avoids the exFAT/extension-load
risk. sqlite-vec is the documented upgrade once the corpus outgrows this.

Vectors are stored as raw little-endian float32 (`array('f')`), so packing needs
no numpy; only the search math does.
"""

from __future__ import annotations

from array import array
from collections.abc import Sequence

import numpy as np


def pack(vector: Sequence[float]) -> bytes:
    """Serialize a vector to float32 bytes for a BLOB column."""
    return array("f", vector).tobytes()


def unpack(blob: bytes) -> np.ndarray:
    """Inverse of `pack` — a 1-D float32 array."""
    return np.frombuffer(blob, dtype=np.float32)


def cosine_topk(
    query: Sequence[float], candidates: list[tuple[int, bytes]], k: int
) -> list[tuple[int, float]]:
    """Return the `k` highest-cosine candidates as `(id, score)`, best first.

    `candidates` is `(id, packed_vector)`. Empty input yields an empty list.
    Zero-norm vectors score 0 rather than dividing by zero.
    """
    if not candidates or k <= 0:
        return []

    q = np.asarray(query, dtype=np.float32)
    q_norm = float(np.linalg.norm(q))
    if q_norm == 0.0:
        return []

    matrix = np.vstack([unpack(blob) for _, blob in candidates])
    norms = np.linalg.norm(matrix, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        scores = matrix @ q / (norms * q_norm)
    scores = np.nan_to_num(scores, nan=0.0)  # zero-norm rows -> 0, not NaN

    ids = [cid for cid, _ in candidates]
    order = np.argsort(-scores)[:k]
    return [(ids[i], float(scores[i])) for i in order]
