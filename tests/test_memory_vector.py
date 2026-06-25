"""Tests for the brute-force vector layer (pack/unpack + cosine search)."""

from __future__ import annotations

from personal_llm.memory.vector import cosine_clusters, cosine_topk, pack, unpack


def test_pack_unpack_roundtrip():
    v = [1.0, -2.5, 3.25, 0.0]
    assert unpack(pack(v)).tolist() == v


def test_cosine_topk_orders_by_similarity():
    cands = [
        (1, pack([1.0, 0.0])),   # identical to query
        (2, pack([0.0, 1.0])),   # orthogonal
        (3, pack([1.0, 1.0])),   # 45 degrees
    ]
    ranked = cosine_topk([1.0, 0.0], cands, k=3)
    assert [cid for cid, _ in ranked] == [1, 3, 2]
    assert ranked[0][1] > ranked[1][1] > ranked[2][1]
    assert abs(ranked[0][1] - 1.0) < 1e-6


def test_cosine_topk_respects_k():
    cands = [(i, pack([float(i), 1.0])) for i in range(5)]
    assert len(cosine_topk([1.0, 1.0], cands, k=2)) == 2


def test_cosine_topk_empty_inputs():
    assert cosine_topk([1.0, 0.0], [], k=3) == []
    assert cosine_topk([1.0, 0.0], [(1, pack([1.0, 0.0]))], k=0) == []


def test_cosine_topk_handles_zero_norm():
    # A zero vector (candidate or query) must not produce NaN or raise.
    cands = [(1, pack([0.0, 0.0])), (2, pack([1.0, 0.0]))]
    ranked = cosine_topk([1.0, 0.0], cands, k=2)
    assert dict(ranked)[1] == 0.0
    assert cosine_topk([0.0, 0.0], cands, k=2) == []


def test_cosine_clusters_groups_transitively():
    # 0~1 and 1~2 link transitively into one component; 3 stays a singleton.
    vectors = [[1.0, 0.0], [0.95, 0.31], [0.85, 0.53], [0.0, 1.0]]
    clusters = cosine_clusters(vectors, threshold=0.8)
    assert len(clusters) == 1
    assert set(clusters[0]) == {0, 1, 2}


def test_cosine_clusters_separates_distinct_groups():
    vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0], [0.0, 1.0]]
    clusters = sorted(cosine_clusters(vectors, threshold=0.9), key=min)
    assert [set(c) for c in clusters] == [{0, 1}, {2, 3}]


def test_cosine_clusters_no_links_or_too_few():
    assert cosine_clusters([[1.0, 0.0], [0.0, 1.0]], threshold=0.9) == []
    assert cosine_clusters([[1.0, 0.0]], threshold=0.5) == []
    assert cosine_clusters([], threshold=0.5) == []
