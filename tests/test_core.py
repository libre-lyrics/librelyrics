from librelyrics.config import get_default_config
from librelyrics.core import LibreLyrics
from librelyrics.models import TrackQuery
from tests.fakes import SearchAlpha, UrlPlugin


def test_librelyrics_fetch_query_with_injected_plugins() -> None:
    ll = LibreLyrics(
        config=get_default_config(),
        plugins=[UrlPlugin, SearchAlpha],
    )
    response = ll.fetch_query(
        TrackQuery(url="https://example.com/track/1"),
        from_plugin="alpha",
    )
    assert response.source == "Alpha"
    assert response.title == "Resolved Title"


def test_librelyrics_fetch_url_wrapper() -> None:
    ll = LibreLyrics(
        config=get_default_config(),
        plugins=[UrlPlugin],
    )
    response = ll.fetch("https://example.com/track/1")
    assert response.source == "UrlPlug"
