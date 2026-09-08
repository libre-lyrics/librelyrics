from librelyrics.models import LyricsLine, LyricsResponse, _escape_lrc_tag


def test_to_lrc_escapes_brackets_in_metadata() -> None:
    response = LyricsResponse(
        title="Song [Live]",
        artist="Artist",
        album="Album [Deluxe]",
        lyrics=[LyricsLine(text="hello")],
        source="Test",
    )
    text = response.to_lrc()
    assert "[ti:Song (Live)]" in text
    assert "[al:Album (Deluxe)]" in text
    assert _escape_lrc_tag("a]b") == "a)b"
    assert _escape_lrc_tag("[Live]") == "(Live)"


def test_to_lrc_positive_duration_emits_length_tag() -> None:
    response = LyricsResponse(
        title="T",
        artist="A",
        lyrics=[LyricsLine(text="hello")],
        source="Test",
        duration_ms=180000,
    )
    assert "[length:03:00.00]" in response.to_lrc()


def test_to_lrc_omits_length_tag_for_zero_and_negative_duration() -> None:
    for duration in (0, -100):
        response = LyricsResponse(
            title="T",
            artist="A",
            lyrics=[LyricsLine(text="hello")],
            source="Test",
            duration_ms=duration,
        )
        assert "length" not in response.to_lrc()
