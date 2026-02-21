"""Typed response models for librelyrics plugins."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LyricsWord:
    """A single word with timing for rich/karaoke lyrics."""
    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class LyricsLine:
    """A single line of lyrics with optional timing."""
    text: str
    start_ms: int | None = None  # Timing in milliseconds, None for unsynced
    end_ms: int | None = None  # End timing for rich lyrics
    words: tuple[LyricsWord, ...] | None = None  # Word-by-word timing for rich lyrics


@dataclass
class LyricsResponse:
    """Standardized response from any lyrics module.

    All plugins MUST return this object from their fetch() method.
    """
    title: str
    artist: str
    lyrics: list[LyricsLine]
    source: str  # Plugin name that provided the lyrics
    album: str | None = None
    synced: bool = False
    rich_synced: bool = False  # Word-by-word timing available
    duration_ms: int | None = None
    metadata: dict = field(default_factory=dict)

    def to_lrc(self, include_metadata: bool = True, enhanced: bool = False) -> str:
        """Format lyrics as LRC file content.

        Args:
            include_metadata: Include title, artist, album tags
            enhanced: Use Enhanced LRC format with word-level timing
        """
        lines = []

        if include_metadata:
            lines.append(f'[ti:{self.title}]')
            if self.album:
                lines.append(f'[al:{self.album}]')
            lines.append(f'[ar:{self.artist}]')
            if self.duration_ms:
                minutes, seconds = divmod(self.duration_ms / 1000, 60)
                lines.append(f'[length:{minutes:0>2.0f}:{seconds:05.2f}]')

        for line in self.lyrics:
            if self.synced and line.start_ms is not None:
                minutes, seconds = divmod(line.start_ms / 1000, 60)
                timestamp = f'[{minutes:0>2.0f}:{seconds:05.2f}]'

                # Enhanced LRC with word-level timing
                if enhanced and self.rich_synced and line.words:
                    word_parts = []
                    for word in line.words:
                        w_min, w_sec = divmod(word.start_ms / 1000, 60)
                        word_parts.append(f'<{w_min:0>2.0f}:{w_sec:05.2f}>{word.word}')
                    lines.append(f'{timestamp} {" ".join(word_parts)}')
                else:
                    lines.append(f'{timestamp} {line.text}')
            else:
                lines.append(line.text)

        return '\n'.join(lines)
