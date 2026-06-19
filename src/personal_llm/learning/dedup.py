"""G3 fact consolidation — semantic dedup + supersession.

Distillation produced the same fact phrased many ways, and stale values that a
newer fact replaces. G3 collapses them:

- **Cluster** active facts by lexical overlap (cheap Jaccard, no embeddings — the
  vector store is a later chunk). Only multi-fact clusters are examined.
- **Judge** each cluster with the local model, which returns `[loser, keeper]`
  relations: a `merge` (the loser is a duplicate of the keeper) or a `supersede`
  (the loser is an outdated version of the keeper).

Nothing is deleted — losers become `merged`/`superseded` and point at their
keeper. Idempotent: consolidated facts leave the active set, so a re-run with no
new duplicates is a no-op.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from personal_llm.config import VaultConfig
from personal_llm.memory import MemoryBackend

DEFAULT_THRESHOLD = 0.5

# Boilerplate that every distilled fact shares ("The user...") — stripped before
# similarity so it doesn't inflate overlap.
_STOPWORDS = frozenset(
    """a an the this that these those and or but to of in on for with at by from as is are
    was were be been being has have had do does did will would can could should may might
    their them they it its he she his her you your we our us i my me user users system also
    including such over more most into out up down""".split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Returns merge/supersede relations as [loser, keeper] 1-based index pairs.
ClusterJudge = Callable[[list[str]], dict[str, list[list[int]]]]

_SYSTEM = "You consolidate a user's memory. You output only JSON."

_PROMPT = """\
These numbered facts about ONE user are similar. Identify two relationships:
- merge: two facts state the SAME thing; one is redundant.
- supersede: one fact is an OUTDATED version of another (same subject, changed
  value or status).

Return ONLY JSON: {{"merge": [[loser, keeper]], "supersede": [[loser, keeper]]}}
where each pair is [the redundant-or-outdated number, the number to keep].
Use empty lists if there are none. Do not invent relationships.

FACTS:
{facts}
"""


class _Completer(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


def normalize_tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster_facts(facts: list[dict], threshold: float) -> list[list[dict]]:
    """Group facts into connected components where pairwise Jaccard >= threshold.

    Returns only clusters with >= 2 facts (singletons need no consolidation).
    """
    tokens = [normalize_tokens(f["text"]) for f in facts]
    n = len(facts)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            if jaccard(tokens[i], tokens[j]) >= threshold:
                parent[find(i)] = find(j)

    groups: dict[int, list[dict]] = {}
    for i, fact in enumerate(facts):
        groups.setdefault(find(i), []).append(fact)
    return [g for g in groups.values() if len(g) >= 2]


def parse_relations(raw: str, n: int) -> dict[str, list[list[int]]]:
    """Parse the judge's JSON into validated 1-based [loser, keeper] pairs."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        return {"merge": [], "supersede": []}
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return {"merge": [], "supersede": []}

    out: dict[str, list[list[int]]] = {"merge": [], "supersede": []}
    for kind in out:
        for pair in data.get(kind, []) or []:
            if (
                isinstance(pair, list)
                and len(pair) == 2
                and all(isinstance(x, int) for x in pair)
                and 1 <= pair[0] <= n
                and 1 <= pair[1] <= n
                and pair[0] != pair[1]
            ):
                out[kind].append(pair)
    return out


def judge_cluster(client: _Completer, texts: list[str]) -> dict[str, list[list[int]]]:
    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, start=1))
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _PROMPT.format(facts=numbered)},
    ]
    return parse_relations(client.complete(messages), len(texts))


def _default_judge(config: VaultConfig) -> ClusterJudge:
    from personal_llm.inference.local import LocalModelClient

    client = LocalModelClient(config.local_model.name, config.local_model.endpoint)
    return lambda texts: judge_cluster(client, texts)


@dataclass
class DedupChange:
    kind: str  # "merge" | "supersede"
    loser_text: str
    keeper_text: str


@dataclass
class DedupResult:
    facts_seen: int = 0
    clusters: int = 0
    merged: int = 0
    superseded: int = 0
    dry_run: bool = False
    changes: list[DedupChange] = field(default_factory=list)


def dedup_facts(
    backend: MemoryBackend,
    config: VaultConfig | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    dry_run: bool = False,
    judge: ClusterJudge | None = None,
) -> DedupResult:
    """Cluster active facts and apply the local model's merge/supersede decisions."""
    if judge is None:
        if config is None:
            raise ValueError("dedup_facts needs a config or an injected judge")
        judge = _default_judge(config)

    facts = backend.facts_for_grading()
    result = DedupResult(facts_seen=len(facts), dry_run=dry_run)

    for cluster in cluster_facts(facts, threshold):
        result.clusters += 1
        relations = judge([f["text"] for f in cluster])
        consumed: set[int] = set()  # one outcome per fact per run

        for kind in ("merge", "supersede"):
            for loser_pos, keeper_pos in relations[kind]:
                loser, keeper = cluster[loser_pos - 1], cluster[keeper_pos - 1]
                if loser["id"] in consumed or keeper["id"] in consumed:
                    continue
                consumed.add(loser["id"])

                result.changes.append(
                    DedupChange(kind, loser["text"], keeper["text"])
                )
                if kind == "merge":
                    result.merged += 1
                    if not dry_run:
                        backend.merge_fact(loser["id"], keeper["id"])
                else:
                    result.superseded += 1
                    if not dry_run:
                        backend.supersede_fact(loser["id"], keeper["id"])

    return result
