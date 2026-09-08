from librelyrics.models import TrackQuery
from librelyrics.search_query import search_query_variants


def test_amsham_spotify_blob_starts_with_primary_and_latin_title() -> None:
    query = TrackQuery(
        artist="Aksomaniac, M.H.R, Bhumi, Circle Tone",
        title="Amsham - അംശം",
        album="Amsham - അംശം",
        duration_ms=180000,
    )
    variants = search_query_variants(query)
    first = variants[0]
    assert first.artist == "Aksomaniac"
    assert first.title == "Amsham"
    assert first.url is None
    assert first.album == query.album
    artists = [item.artist for item in variants]
    titles = [item.title for item in variants]
    assert "Aksomaniac, M.H.R, Bhumi, Circle Tone" in artists
    assert "Amsham - അംശം" in titles
    assert "അംശം" in titles


def test_feat_and_parens_are_stripped_on_first_variant() -> None:
    query = TrackQuery(
        artist="Artist ft. Guest",
        title="Song (Official Video)",
    )
    first = search_query_variants(query)[0]
    assert first.artist == "Artist"
    assert first.title == "Song"


def test_simple_query_is_single_variant() -> None:
    query = TrackQuery(artist="Adele", title="Hello")
    variants = search_query_variants(query)
    assert len(variants) == 1
    assert variants[0].artist == "Adele"
    assert variants[0].title == "Hello"


def test_whitespace_only_artist_or_title_does_not_crash() -> None:
    variants = search_query_variants(TrackQuery(artist="   ", title="   "))
    assert variants == [TrackQuery(url=None, artist="   ", title="   ")]

    variants = search_query_variants(TrackQuery(artist="A", title="   "))
    assert len(variants) == 1
    assert variants[0].artist == "A"
