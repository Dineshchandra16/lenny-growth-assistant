"""
app/rag/prompt.py
─────────────────
Grounded RAG prompt templates and context construction for Lenny Growth Assistant.
"""

from __future__ import annotations

from typing import Sequence
from app.rag.retriever import RetrievedChunk

INSUFFICIENT_INFORMATION_PHRASE = (
    "I do not have sufficient information in Lenny's podcast archive to answer this."
)

SYSTEM_PROMPT_TEMPLATE = """You are the **Lenny Growth Assistant**, an expert AI advisor for product managers and growth leaders, grounded strictly in transcripts from *Lenny's Podcast*.

### Core Instructions:
1. **Strict Grounding:** Answer the user's question using ONLY the provided transcript excerpts below. Do not use prior training knowledge to invent details not present in the transcripts.
2. **Mandatory Citations:** Every key tactic, claim, or quote MUST cite its source using this exact bracket syntax:
   `[Episode: Guest Name, Timestamp]` or `[Episode Title: Guest Name, Timestamp]`
   Example: `[Elena Verna on PLG: Elena Verna, 00:01:20]`
3. **Insufficient Information Fallback:** If the provided transcript excerpts do not contain enough relevant information to answer the question accurately, you MUST respond with:
   "{fallback_phrase}"
   Do not guess, extrapolate beyond the text, or fabricate podcast episodes.
4. **Actionable & Structured:** Provide crisp, high-signal explanations with bullet points and bold anchor terms suitable for growth PMs.
5. **Follow-up Context:** If the user is asking a follow-up question, resolve pronouns and context based on previous turns in the conversation.

---
### Transcript Excerpts:
{context_chunks}
"""


def build_rag_system_prompt(chunks: Sequence[RetrievedChunk]) -> str:
    """Format retrieved transcript chunks into the grounded system prompt."""
    if not chunks:
        formatted_chunks = "No relevant transcript excerpts found."
    else:
        chunk_blocks = []
        for i, chunk in enumerate(chunks, 1):
            guest = chunk.guest_name or "Guest"
            ref = chunk.timestamp_ref or "N/A"
            block = (
                f"--- Excerpt {i} ---\n"
                f"Episode: {chunk.episode_title}\n"
                f"Guest: {guest}\n"
                f"Timestamp: {ref}\n"
                f"Citation Tag: {chunk.citation_label}\n"
                f"Content:\n{chunk.chunk_text.strip()}\n"
            )
            chunk_blocks.append(block)
        formatted_chunks = "\n".join(chunk_blocks)

    return SYSTEM_PROMPT_TEMPLATE.format(
        fallback_phrase=INSUFFICIENT_INFORMATION_PHRASE,
        context_chunks=formatted_chunks,
    )


def format_messages_with_history(
    history: Sequence[dict[str, str]],
    current_message: str,
) -> list[dict[str, str]]:
    """Format conversation history turns into standard provider message payload."""
    messages: list[dict[str, str]] = []
    # Include up to the last 10 turns of history
    for msg in history[-10:]:
        if msg.get("role") in ("user", "assistant") and msg.get("content"):
            messages.append({"role": msg["role"], "content": msg["content"]})

    # Append current turn if not already last message
    if not messages or messages[-1].get("content") != current_message:
        messages.append({"role": "user", "content": current_message})

    return messages

