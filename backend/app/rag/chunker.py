"""
app/rag/chunker.py
──────────────────
Recursive character text chunker for podcast transcripts.

Splits long transcripts into chunks of 500–800 tokens with 100-token overlap,
preserving metadata (guest name, episode title, publish date) and tracing
each chunk to its nearest section timestamp reference (e.g., "[00:12:34]").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


@dataclass
class ParsedTranscript:
    episode_title: str
    guest_name: str | None
    publish_date: str | None
    raw_text: str


@dataclass
class TranscriptChunkItem:
    episode_title: str
    guest_name: str | None
    publish_date: str | None
    timestamp_ref: str | None
    chunk_text: str
    token_count: int


# Regex to match timestamps like [01:23:45], (12:34), 00:15:20
TIMESTAMP_PATTERN = re.compile(r"\[?(\d{1,2}:\d{2}(?::\d{2})?)\]?")


def estimate_token_count(text: str) -> int:
    """
    Approximate token count based on whitespace & punctuation splits.
    Rule of thumb for English: ~1 token per 0.75 words / 4 characters.
    """
    words = len(text.split())
    # Blend word count (1.33 tokens/word) and char count (0.25 tokens/char)
    return max(1, int((words * 1.33 + len(text) / 4.0) / 2.0))


class TranscriptChunker:
    """
    Splits transcript texts using a recursive hierarchy of separators
    (paragraphs -> sentences -> words) to produce chunks with target token bounds.
    """

    def __init__(
        self,
        chunk_size_tokens: int = 600,
        chunk_overlap_tokens: int = 100,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        self.separators = separators or ["\n\n", "\n", ". ", "? ", "! ", " ", ""]

    def chunk_transcript(self, transcript: ParsedTranscript) -> list[TranscriptChunkItem]:
        """Split a parsed transcript into structured chunk items with timestamps."""
        text = transcript.raw_text.strip()
        if not text:
            return []

        raw_chunks = self._recursive_split(text, self.separators)
        merged_chunks = self._merge_splits(raw_chunks)

        chunk_items: list[TranscriptChunkItem] = []
        current_timestamp = None

        for chunk_text in merged_chunks:
            # Check if this chunk contains a new timestamp reference
            match = TIMESTAMP_PATTERN.search(chunk_text)
            if match:
                current_timestamp = match.group(1)

            token_cnt = estimate_token_count(chunk_text)
            chunk_items.append(
                TranscriptChunkItem(
                    episode_title=transcript.episode_title,
                    guest_name=transcript.guest_name,
                    publish_date=transcript.publish_date,
                    timestamp_ref=current_timestamp,
                    chunk_text=chunk_text,
                    token_count=token_cnt,
                )
            )

        return chunk_items

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using the best available separator."""
        final_splits: list[str] = []
        separator = separators[-1]
        new_separators = []

        for i, sep in enumerate(separators):
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        splits = text.split(separator) if separator != "" else list(text)

        good_splits: list[str] = []
        for s in splits:
            if not s.strip():
                continue
            if estimate_token_count(s) <= self.chunk_size_tokens:
                good_splits.append(s)
            elif new_separators:
                # Sub-split larger piece
                sub_splits = self._recursive_split(s, new_separators)
                good_splits.extend(sub_splits)
            else:
                good_splits.append(s)

        return good_splits

    def _merge_splits(self, splits: list[str]) -> list[str]:
        """Merge smaller splits up to the target token window with overlap."""
        docs: list[str] = []
        current_doc: list[str] = []
        total_tokens = 0

        for piece in splits:
            piece_tokens = estimate_token_count(piece)
            if total_tokens + piece_tokens > self.chunk_size_tokens and current_doc:
                doc_text = " ".join(current_doc).strip()
                if doc_text:
                    docs.append(doc_text)

                # Keep overlap items from the end of current_doc
                overlap_doc: list[str] = []
                overlap_tokens = 0
                for prev_piece in reversed(current_doc):
                    t = estimate_token_count(prev_piece)
                    if overlap_tokens + t <= self.chunk_overlap_tokens:
                        overlap_doc.insert(0, prev_piece)
                        overlap_tokens += t
                    else:
                        break

                current_doc = overlap_doc
                total_tokens = overlap_tokens

            current_doc.append(piece)
            total_tokens += piece_tokens

        if current_doc:
            doc_text = " ".join(current_doc).strip()
            if doc_text:
                docs.append(doc_text)

        return docs

