"""Extraction of untrusted artifact blocks from LLM responses."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ExtractedArtifact:
    """An artifact extracted from an assistant response."""

    artifact_type: str
    title: str | None
    content: str


_ARTIFACT_RE = re.compile(
    r"<artifact\b(?P<attrs>[^>]*)>(?P<content>.*?)</artifact\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(
    r"(?P<name>type|title)\s*=\s*(?P<quote>[\"'])(?P<value>.*?)(?P=quote)",
    re.IGNORECASE | re.DOTALL,
)
_SUPPORTED_TYPES = {"markdown", "html"}


def extract_artifacts(response: str) -> tuple[str, list[ExtractedArtifact]]:
    """Return response text with artifact wrappers removed and extracted artifacts.

    Unknown artifact types are left in the response rather than silently
    discarding model output.
    """
    artifacts: list[ExtractedArtifact] = []
    spans_to_remove: list[tuple[int, int]] = []

    for match in _ARTIFACT_RE.finditer(response):
        attributes = {
            item.group("name").lower(): item.group("value").strip()
            for item in _ATTR_RE.finditer(match.group("attrs"))
        }
        artifact_type = attributes.get("type", "").lower()
        if artifact_type not in _SUPPORTED_TYPES:
            continue

        content = match.group("content").strip()
        if not content:
            continue

        artifacts.append(
            ExtractedArtifact(
                artifact_type=artifact_type,
                title=attributes.get("title") or None,
                content=content,
            )
        )
        spans_to_remove.append(match.span())

    cleaned = response
    for start, end in reversed(spans_to_remove):
        cleaned = cleaned[:start] + cleaned[end:]

    return cleaned.strip(), artifacts
