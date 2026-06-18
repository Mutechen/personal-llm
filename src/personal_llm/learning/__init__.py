"""Learning from existing agent transcripts — the cold-start growth source.

The personal LLM bootstraps not by waiting for conversations with the immature
model, but by observing the user's existing conversations with capable agents
(Claude Code, etc.) and distilling facts, skills, and preferences from them.

P1 slice: ingest Claude Code JSONL transcripts -> distill facts -> write to the
L4 recall store. Design in docs/LEARNING_FROM_TRANSCRIPTS.md.
"""

from __future__ import annotations
