"""Tests for the G3 dedup + supersession pass.

The cluster judge is injected, so the pass runs without a live model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from personal_llm.learning.dedup import (
    cluster_facts,
    dedup_facts,
    jaccard,
    normalize_tokens,
    parse_relations,
)
from personal_llm.memory import SqliteBackend


def test_normalize_strips_boilerplate():
    assert normalize_tokens("The user is working on ZeenaStoreZ") == frozenset(
        {"working", "zeenastorez"}
    )


def test_jaccard_basics():
    assert jaccard(frozenset({"a", "b"}), frozenset({"a", "b"})) == 1.0
    assert jaccard(frozenset({"a"}), frozenset({"b"})) == 0.0
    assert jaccard(frozenset(), frozenset({"a"})) == 0.0


def _facts(*texts):
    return [{"id": i + 1, "text": t} for i, t in enumerate(texts)]


def test_cluster_groups_similar_and_drops_singletons():
    facts = _facts(
        "The user prefers h264 veryfast crf24 encoding",
        "The user likes h264 veryfast crf24 for encoding",
        "The user runs an Islamic Encyclopedia project",
    )
    clusters = cluster_facts(facts, threshold=0.5)
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


def test_dedup_merges_duplicate(backend: SqliteBackend):
    backend.append_fact("The user prefers h264 veryfast crf24 encoding", "transcript:s1")
    backend.append_fact("The user likes h264 veryfast crf24 for encoding", "transcript:s2")

    def judge(texts):
        return {"merge": [[2, 1]], "supersede": []}

    result = dedup_facts(backend, judge=judge)

    assert result.clusters == 1
    assert result.merged == 1
    active = backend.facts_for_grading()
    assert len(active) == 1
    assert active[0]["id"] == 1


def test_dedup_supersedes_outdated(backend: SqliteBackend):
    backend.append_fact("The T5 drive has about 280 GB free space", "transcript:s1")
    backend.append_fact("The T5 drive has about 146 GB free space", "transcript:s2")

    def judge(texts):
        # fact 1 (280GB) is outdated, fact 2 (146GB) keeps
        return {"merge": [], "supersede": [[1, 2]]}

    result = dedup_facts(backend, judge=judge)
    assert result.superseded == 1
    active = backend.facts_for_grading()
    assert [f["id"] for f in active] == [2]


def test_dedup_is_idempotent(backend: SqliteBackend):
    backend.append_fact("The user prefers h264 veryfast crf24 encoding", "transcript:s1")
    backend.append_fact("The user likes h264 veryfast crf24 for encoding", "transcript:s2")

    def judge(texts):
        return {"merge": [[2, 1]], "supersede": []}

    first = dedup_facts(backend, judge=judge)
    second = dedup_facts(backend, judge=judge)

    assert first.merged == 1
    assert second.clusters == 0  # only one active fact left, no cluster
    assert second.merged == 0


def test_dedup_one_outcome_per_fact(backend: SqliteBackend):
    backend.append_fact("fact alpha about encoding video files", "transcript:s1")
    backend.append_fact("fact alpha about encoding video clips", "transcript:s2")

    # judge tries to both merge AND supersede fact 2 — second relation ignored
    def judge(texts):
        return {"merge": [[2, 1]], "supersede": [[2, 1]]}

    result = dedup_facts(backend, judge=judge)
    assert result.merged == 1
    assert result.superseded == 0


def test_dedup_dry_run_writes_nothing(backend: SqliteBackend):
    backend.append_fact("The user prefers h264 veryfast crf24 encoding", "transcript:s1")
    backend.append_fact("The user likes h264 veryfast crf24 for encoding", "transcript:s2")

    result = dedup_facts(
        backend, judge=lambda t: {"merge": [[2, 1]], "supersede": []}, dry_run=True
    )
    assert result.merged == 1
    assert len(backend.facts_for_grading()) == 2  # both still active


def test_dedup_requires_config_or_judge(backend: SqliteBackend):
    backend.append_fact("x", "transcript:s1")
    with pytest.raises(ValueError):
        dedup_facts(backend)
