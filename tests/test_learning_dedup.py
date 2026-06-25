"""Tests for the G3 dedup + supersession pass.

The cluster judge is injected and embeddings are stored directly, so the pass
runs without a live model. Clustering is embedding-cosine based; tests control
the vectors to make clusters deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm.config import EmbeddingModelConfig
from personal_llm.learning.dedup import cluster_facts, dedup_facts, parse_relations
from personal_llm.memory import SqliteBackend

_MODEL = EmbeddingModelConfig().name  # the model name dedup_facts defaults to


def test_cluster_groups_similar_and_drops_singletons():
    facts = [
        {"id": 1, "text": "a", "vector": [1.0, 0.0]},
        {"id": 2, "text": "b", "vector": [0.98, 0.2]},   # ~0.98 cosine with #1
        {"id": 3, "text": "c", "vector": [0.0, 1.0]},     # orthogonal -> singleton
    ]
    clusters = cluster_facts(facts, threshold=0.8)
    assert len(clusters) == 1
    assert {f["id"] for f in clusters[0]} == {1, 2}


def test_parse_relations_validates_pairs():
    raw = '{"merge": [[2, 1], [9, 1]], "supersede": [[3, 1]]}'
    # [9,1] is out of range for n=3 and is dropped
    rel = parse_relations(raw, 3)
    assert rel == {"merge": [[2, 1]], "supersede": [[3, 1]]}


def test_parse_relations_garbage_is_empty():
    assert parse_relations("no json", 3) == {"merge": [], "supersede": []}
    assert parse_relations('{"merge": [[1,1]]}', 2) == {"merge": [], "supersede": []}


@pytest.fixture
def backend(tmp_path: Path) -> SqliteBackend:
    return SqliteBackend(tmp_path)


def _add(backend: SqliteBackend, text: str, source: str, vector: list[float]) -> int:
    backend.append_fact(text, source)
    fid = next(f["id"] for f in backend.facts_for_grading() if f["text"] == text)
    backend.store_fact_embedding(fid, _MODEL, vector)
    return fid


def test_dedup_merges_duplicate(backend: SqliteBackend):
    _add(backend, "The user prefers h264 veryfast crf24 encoding", "transcript:s1", [1.0, 0.0])
    _add(backend, "The user likes h264 veryfast crf24 for encoding", "transcript:s2", [0.99, 0.05])

    def judge(texts):
        return {"merge": [[2, 1]], "supersede": []}

    result = dedup_facts(backend, judge=judge)

    assert result.clusters == 1
    assert result.merged == 1
    active = backend.facts_for_grading()
    assert len(active) == 1
    assert active[0]["id"] == 1


def test_dedup_supersedes_outdated(backend: SqliteBackend):
    _add(backend, "The T5 drive has about 280 GB free space", "transcript:s1", [1.0, 0.0])
    _add(backend, "The T5 drive has about 146 GB free space", "transcript:s2", [0.98, 0.1])

    def judge(texts):
        # fact 1 (280GB) is outdated, fact 2 (146GB) keeps
        return {"merge": [], "supersede": [[1, 2]]}

    result = dedup_facts(backend, judge=judge)
    assert result.superseded == 1
    active = backend.facts_for_grading()
    assert [f["id"] for f in active] == [2]


def test_dedup_is_idempotent(backend: SqliteBackend):
    _add(backend, "The user prefers h264 veryfast crf24 encoding", "transcript:s1", [1.0, 0.0])
    _add(backend, "The user likes h264 veryfast crf24 for encoding", "transcript:s2", [0.99, 0.05])

    def judge(texts):
        return {"merge": [[2, 1]], "supersede": []}

    first = dedup_facts(backend, judge=judge)
    second = dedup_facts(backend, judge=judge)

    assert first.merged == 1
    assert second.clusters == 0  # only one embedded active fact left, no cluster
    assert second.merged == 0


def test_dedup_one_outcome_per_fact(backend: SqliteBackend):
    _add(backend, "fact alpha about encoding video files", "transcript:s1", [1.0, 0.0])
    _add(backend, "fact alpha about encoding video clips", "transcript:s2", [0.99, 0.05])

    # judge tries to both merge AND supersede fact 2 — second relation ignored
    def judge(texts):
        return {"merge": [[2, 1]], "supersede": [[2, 1]]}

    result = dedup_facts(backend, judge=judge)
    assert result.merged == 1
    assert result.superseded == 0


def test_dedup_skips_unembedded_facts(backend: SqliteBackend):
    """A fact without an embedding can't cluster yet — it's left for a later run."""
    _add(backend, "embedded fact one", "transcript:s1", [1.0, 0.0])
    backend.append_fact("unembedded near-duplicate", "transcript:s2")  # no vector stored

    result = dedup_facts(backend, judge=lambda t: {"merge": [[2, 1]], "supersede": []})
    assert result.facts_seen == 1  # only the embedded one is considered
    assert result.clusters == 0


def test_dedup_dry_run_writes_nothing(backend: SqliteBackend):
    _add(backend, "The user prefers h264 veryfast crf24 encoding", "transcript:s1", [1.0, 0.0])
    _add(backend, "The user likes h264 veryfast crf24 for encoding", "transcript:s2", [0.99, 0.05])

    result = dedup_facts(
        backend, judge=lambda t: {"merge": [[2, 1]], "supersede": []}, dry_run=True
    )
    assert result.merged == 1
    assert len(backend.facts_for_grading()) == 2  # both still active


def test_dedup_requires_config_or_judge(backend: SqliteBackend):
    backend.append_fact("x", "transcript:s1")
    with pytest.raises(ValueError):
        dedup_facts(backend)
