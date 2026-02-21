"""LibreLyrics - Fetch lyrics from various sources.

A modular, plugin-based lyrics fetcher supporting multiple providers.
"""
from importlib.metadata import version

from librelyrics.core import LibreLyrics
from librelyrics.exceptions import (
                                    LibreLyricsError,
                                    LyricsNotFound,
                                    NoMatchingModuleError,
)
from librelyrics.models import LyricsLine, LyricsResponse
from librelyrics.modules.base import LyricsType, ModuleCapability

__version__ = version("librelyrics")

__all__ = [
    'LibreLyrics',
    'LyricsResponse',
    'LyricsLine',
    'LyricsType',
    'ModuleCapability',
    'LibreLyricsError',
    'NoMatchingModuleError',
    'LyricsNotFound',
    '__version__',
]
