---
name: search_library
description: Search the user's ingested book/document library for passages relevant to a query, with citations.
version: 0.1.0
tags: [library, books, search, rag, read-only]
capabilities: [retrieval]
---

# search_library

Semantic search over the documents the user has ingested into their library
(books, PDFs, notes — added via `personal-llm ingest`). Returns the most
relevant passages, each with a citation (document title + chunk number), so
answers can be grounded in and attributed to the user's own sources.

Use this when the user asks about the content of their books or documents, or
when answering would clearly benefit from grounding in their library rather than
your own training. Treat the returned passages as source material: quote or
paraphrase them and cite the title; never invent passages or citations.

## Inputs

- `query` (string, required) — what to look for, in natural language. Any
  language works; retrieval is multilingual.
- `k` (integer, optional) — how many passages to return (default 5).

## Behavior

1. Embed the query with the local embedding model.
2. Return the `k` closest document chunks by cosine similarity, each headed with
   its document title, chunk number, and a relevance score.

## Output

A text block of passages, each headed `[Title #chunk] (relevance score)`. If
nothing is ingested or the embedding model is unreachable, a plain explanatory
message is returned instead of an error, so a lookup never derails the turn.

## Not in scope

- Ingesting documents (that's the `personal-llm ingest` command).
- Searching the host filesystem or the web — only the user's ingested library.
- Returning whole books — this surfaces short relevant passages, by design.
