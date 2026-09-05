"""Phase 4 tests for the Ship 30 for 30 skill."""

from app.rag.retriever import RetrievedChunk
from app.skills.ship30_writer import (
    SHIP30_SECTION_HEADERS,
    build_ship30_system_prompt,
    validate_ship30_essay,
)


def _source() -> RetrievedChunk:
    return RetrievedChunk(
        id=__import__("uuid").uuid4(),
        episode_title="Elena Verna on PLG",
        guest_name="Elena Verna",
        publish_date="2023-04-12",
        timestamp_ref="00:01:20",
        chunk_text="A PQL is based on meaningful product activation.",
        token_count=12,
        score=0.9,
    )


def _essay(word_count: int = 1_200) -> str:
    source = "[Elena Verna on PLG: Elena Verna, 00:01:20]"
    body = " ".join(["PQL activation creates a measurable growth signal " + source] * 20)
    draft = "\n\n".join([*SHIP30_SECTION_HEADERS, body])
    current_words = len(draft.split())
    return draft + " " + "useful " * max(0, word_count - current_words)


def test_ship30_prompt_requires_structure_and_grounding():
    prompt = build_ship30_system_prompt([_source()])

    assert "approximately 1,250 words" in prompt
    assert "Elena Verna on PLG: Elena Verna, 00:01:20" in prompt
    for header in SHIP30_SECTION_HEADERS:
        assert header in prompt


def test_ship30_validation_accepts_structured_cited_essay():
    source = _source()
    result = validate_ship30_essay(_essay(), [source.citation_label])

    assert result.valid
    assert result.citation_count > 0
    assert 1_000 <= result.word_count <= 1_500


def test_ship30_validation_rejects_short_or_unknown_citations():
    source = _source()
    result = validate_ship30_essay(
        "\n".join(SHIP30_SECTION_HEADERS)
        + "\nA short claim [Unknown: Person, 00:00:01].",
        [source.citation_label],
    )

    assert not result.valid
    assert any("word count" in error for error in result.errors)
    assert result.invalid_citations == ("[Unknown: Person, 00:00:01]",)
