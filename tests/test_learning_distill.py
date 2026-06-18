"""Tests for fact distillation parsing and the extractor wiring."""

from __future__ import annotations

from personal_llm.learning.distill import extract_facts, parse_facts


def test_parse_plain_json_array():
    assert parse_facts('["a fact", "another"]') == ["a fact", "another"]


def test_parse_strips_think_block_and_prose():
    raw = '<think>let me reason</think>\nHere you go:\n["fact one", "fact two"]\nhope that helps'
    assert parse_facts(raw) == ["fact one", "fact two"]


def test_parse_accepts_objects_with_fact_or_text_key():
    raw = '[{"fact": "from fact key"}, {"text": "from text key"}, {"other": "ignored"}]'
    assert parse_facts(raw) == ["from fact key", "from text key"]


def test_parse_drops_empties_and_non_strings():
    assert parse_facts('["keep", "", "  ", 5, null]') == ["keep"]


def test_parse_returns_empty_on_garbage():
    assert parse_facts("no json here") == []
    assert parse_facts("") == []
    assert parse_facts("[broken") == []


def test_extract_facts_empty_session_skips_model():
    class Boom:
        def complete(self, messages):
            raise AssertionError("model should not be called for empty input")

    assert extract_facts(Boom(), "   ") == []


def test_extract_facts_passes_transcript_and_parses():
    captured = {}

    class FakeClient:
        def complete(self, messages):
            captured["messages"] = messages
            return '["user runs Linux", "user prefers uv"]'

    facts = extract_facts(FakeClient(), "user: I use uv on Linux")
    assert facts == ["user runs Linux", "user prefers uv"]
    assert "user: I use uv on Linux" in captured["messages"][1]["content"]
