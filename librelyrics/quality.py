"""Lyrics quality ranking for the search pipeline."""
from __future__ import annotations

from librelyrics.models import LyricsResponse
from librelyrics.modules.base import LyricsModule, LyricsType

QUALITY_TOKENS = ("RICH", "SYNCED", "UNSYNCED")
_RANK = {"UNSYNCED": 0, "SYNCED": 1, "RICH": 2}


def normalize_order(preferred_order: list[str] | None) -> list[str]:
    if not preferred_order:
        return ["RICH", "SYNCED", "UNSYNCED"]
    cleaned: list[str] = []
    for token in preferred_order:
        upper = str(token).upper()
        if upper in _RANK and upper not in cleaned:
            cleaned.append(upper)
    return cleaned or ["RICH", "SYNCED", "UNSYNCED"]


def response_token(response: LyricsResponse) -> str:
    if response.rich_synced:
        return "RICH"
    if response.synced:
        return "SYNCED"
    return "UNSYNCED"


def token_meets(result_token: str, required: str) -> bool:
    return _RANK[result_token] >= _RANK[required]


def is_good_enough(response: LyricsResponse, preferred_order: list[str]) -> bool:
    order = normalize_order(preferred_order)
    return token_meets(response_token(response), order[0])


def meets_any_listed(response: LyricsResponse, preferred_order: list[str]) -> bool:
    order = normalize_order(preferred_order)
    token = response_token(response)
    return any(token_meets(token, listed) for listed in order)


def fallback_sort_key(
    response: LyricsResponse,
    preferred_order: list[str],
    plugin_id: str,
    priority: list[str],
) -> tuple[int, int]:
    """Lower is better. Prefer earlier tokens in the user list, then earlier plugins."""
    order = normalize_order(preferred_order)
    token = response_token(response)
    token_index = len(order)
    for i, listed in enumerate(order):
        if token_meets(token, listed):
            token_index = i
            break
    try:
        plugin_index = priority.index(plugin_id)
    except ValueError:
        plugin_index = len(priority)
    return (token_index, plugin_index)


def plugin_can_satisfy(
    plugin_cls: type[LyricsModule],
    preferred_order: list[str],
) -> bool:
    """True if declared lyrics_types can meet any token in the user list."""
    order = normalize_order(preferred_order)
    declared: list[str] = []
    types = plugin_cls.META.lyrics_types
    if LyricsType.RICH_SYNCED in types:
        declared.append("RICH")
    if LyricsType.SYNCED in types:
        declared.append("SYNCED")
    if LyricsType.PLAIN in types:
        declared.append("UNSYNCED")
    for listed in order:
        if any(token_meets(token, listed) for token in declared):
            return True
    return False
