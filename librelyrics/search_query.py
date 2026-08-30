"""Build simpler artist/title variants for metadata search."""
from __future__ import annotations

import re
from dataclasses import replace

from librelyrics.models import TrackQuery

_FEAT_SPLIT = re.compile(r"\s+(?:feat\.?|ft\.?)\s+", re.IGNORECASE)
_DASH_SPLIT = re.compile(r"\s+-\s+")
_PARENS = re.compile(r"\s*[\(\[][^)\]]*[\)\]]")


def search_query_variants(query: TrackQuery) -> list[TrackQuery]:
    """Ordered TrackQuery copies for SEARCH plugins.

    Spotify-style credits (many artists, bilingual ``Name - ലിപി`` titles)
    fail Apple Music / AMP as one blob. Try a short query first, then
    progressively closer to the original strings. URL is always cleared.
    """
    base = replace(query, url=None)
    if not query.artist or not query.title:
        return [base]

    artists = _artist_variants(query.artist)
    titles = _title_variants(query.title)
    pairs: list[tuple[str, str]] = [
        (artists[0], titles[0]),
        (artists[0], titles[-1]),
        (artists[-1], titles[0]),
        (artists[-1], titles[-1]),
    ]
    for extra_title in titles[1:-1]:
        pairs.append((artists[0], extra_title))

    variants: list[TrackQuery] = []
    seen: set[tuple[str, str]] = set()
    for artist, title in pairs:
        key = (artist, title)
        if key in seen:
            continue
        seen.add(key)
        variants.append(replace(base, artist=artist, title=title))
    return variants


def _artist_variants(artist: str) -> list[str]:
    artist = artist.strip()
    primary = artist.split(",", 1)[0].strip()
    primary = _FEAT_SPLIT.split(primary, maxsplit=1)[0].strip()
    out: list[str] = []
    if primary:
        out.append(primary)
    if artist not in out:
        out.append(artist)
    return out


def _title_variants(title: str) -> list[str]:
    title = title.strip()
    parts = [part.strip() for part in _DASH_SPLIT.split(title) if part.strip()]
    ordered: list[str] = []
    if len(parts) >= 2:
        ordered.extend(sorted(parts, key=_latin_letter_count, reverse=True))
    stripped = _PARENS.sub("", title).strip()
    if stripped:
        ordered.append(stripped)
    ordered.append(title)
    return _unique_keep_order(ordered)


def _latin_letter_count(text: str) -> int:
    return sum(ch.isascii() and ch.isalpha() for ch in text)


def _unique_keep_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out
