"""
Ship 30 for 30 essay skill.

Builds a grounded essay prompt and validates the model's completed essay before
it is returned to the caller. The skill deliberately does not create or
persist artifacts; that belongs to Phase 5.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from app.rag.retriever import RetrievedChunk


SHIP30_SECTION_HEADERS: tuple[str, ...] = (
    "## The Hook",
    "## The Core Idea",
    "## The Framework",
    "## How to Apply It",
    "## A Practical Example",
    "## Your Next Step",
)

SHIP30_MIN_WORDS = 1_000
SHIP30_MAX_WORDS = 1_500
_CITATION_PATTERN = re.compile(r"\[[^\[\]\n]+:\s*[^\[\]\n]+,\s*\d{2}:\d{2}:\d{2}\]")


@dataclass(frozen=True)
class Ship30Validation:
    """Result of validating a completed Ship 30 essay."""

    valid: bool
    word_count: int
    citation_count: int
    missing_sections: tuple[str, ...] = ()
    invalid_citations: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def build_ship30_system_prompt(chunks: Sequence[RetrievedChunk]) -> str:
    """Build a grounded prompt for a structured Ship 30 for 30 essay."""
    context_lines = []
    for index, chunk in enumerate(chunks, 1):
        context_lines.append(
            f"--- Source {index} ---\n"
            f"Episode: {chunk.episode_title}\n"
            f"Guest: {chunk.guest_name or 'Guest'}\n"
            f"Timestamp: {chunk.timestamp_ref or 'N/A'}\n"
            f"Citation: {chunk.citation_label}\n"
            f"Content:\n{chunk.chunk_text.strip()}"
        )

    context = "\n\n".join(context_lines)
    sections = "\n".join(f"- {header}" for header in SHIP30_SECTION_HEADERS)
    return f"""You are writing a Ship 30 for 30 essay for a product or growth leader.

Use ONLY the transcript sources below. Do not add outside facts, invented
examples, or unsupported claims. Every factual claim and recommendation must
end with a citation copied exactly from one of the source Citation values.

Write approximately 1,250 words (between {SHIP30_MIN_WORDS} and
{SHIP30_MAX_WORDS} words). Use exactly these Markdown section headings:
{sections}

Make the essay practical, specific, and coherent. The Hook should establish
the problem, the Core Idea should state one thesis, the Framework should name
the reusable model, How to Apply It should give concrete steps, the Practical
Example should apply only the sourced ideas, and Your Next Step should end
with an actionable experiment.

Transcript sources:
{context}
"""


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def validate_ship30_essay(
    essay: str,
    source_labels: Sequence[str],
    *,
    min_words: int = SHIP30_MIN_WORDS,
    max_words: int = SHIP30_MAX_WORDS,
) -> Ship30Validation:
    """Validate length, required structure, and source-backed citations."""
    word_count = _word_count(essay)
    missing_sections = tuple(
        header for header in SHIP30_SECTION_HEADERS if header not in essay
    )
    citations = _CITATION_PATTERN.findall(essay)
    allowed_labels = {label.strip("[]") for label in source_labels}
    invalid_citations = tuple(
        citation
        for citation in citations
        if citation.strip("[]") not in allowed_labels
    )

    errors: list[str] = []
    if word_count < min_words or word_count > max_words:
        errors.append(
            f"word count must be between {min_words} and {max_words}; got {word_count}"
        )
    if missing_sections:
        errors.append("missing required sections: " + ", ".join(missing_sections))
    if not citations:
        errors.append("essay must contain at least one timestamped source citation")
    if invalid_citations:
        errors.append("essay contains citations not present in retrieved sources")

    return Ship30Validation(
        valid=not errors,
        word_count=word_count,
        citation_count=len(citations),
        missing_sections=missing_sections,
        invalid_citations=invalid_citations,
        errors=tuple(errors),
    )
