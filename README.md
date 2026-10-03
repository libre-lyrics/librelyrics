# LibreLyrics

<div align="center">

![Logo](https://avatars.githubusercontent.com/u/260162604)

A modular, plugin-based lyrics fetcher. Fetch synced and unsynced lyrics from various sources via plugins.

</div>



## Features

- **Synced lyrics** — Line-by-line timestamps (LRC format)
- **Rich synced lyrics** — Word-by-word karaoke-style timing (Enhanced LRC)
- **Plugin architecture** — External plugins via entry points, API version 2
- **Capability-based routing** — Plugins declare what they support; the core dispatches without `hasattr` checks
- **Metadata search** — Fetch by artist and title, with a user-defined source list
- **Batch downloads** — Fetch lyrics for entire albums or playlists, in parallel
- **CLI & Library** — Use from the command line or import as a Python library
- **Interactive config** — Menu-driven configuration editor driven by plugin schemas
- **Centralized retries** — Back-off lives in the core; plugins only classify failures

## Installation

```bash
pip install librelyrics
```

Requires Python 3.10+.

## Plugins

LibreLyrics is a plugin-based system. The core package **does not include any lyrics sources**. Install plugin packages separately.

Plugins must declare **API version 2** (`LIBRELYRICS_API_VERSION = 2`) and a stable `META.id` (lower-case letters and digits only). Version 1 plugins do not load. `META.name` is the display name and the key under `plugins` in config.

### Installing Plugins

Install plugins using pip or the built-in plugin manager:

```bash
# Using pip
pip install librelyrics-spotify

# Using the plugin manager
librelyrics plugin install librelyrics-spotify

# Remove a plugin
librelyrics plugin remove librelyrics-spotify

# List installed plugins
librelyrics plugin list
```

### Available Plugins

Plugin packages follow the naming convention `librelyrics-{service}`. Check the [libre-lyrics](https://github.com/libre-lyrics) organization for available plugins.

### Fetch Modes

A plugin can serve as the **URL provider** (it matches the URL, resolves metadata, lists albums) and/or the **lyrics source** (it actually returns lyrics). Which one is used depends on the flags:

| Command | URL provider | Lyrics source |
|---|---|---|
| `librelyrics <url>` | plugin matching the URL | same plugin, unless `search_priority` is set |
| `librelyrics <url> --direct` | plugin matching the URL | that plugin only |
| `librelyrics <url> --from <id>` | plugin matching the URL (via `resolve()`) | plugin with id `<id>`, via `SEARCH` |
| `librelyrics --artist A --title T` | none | first `SEARCH` plugin, or `search_priority` |

`--direct` and `--from` cannot be combined.

## Quick Start

### Command Line

```bash
# Fetch lyrics for a single track (URL plugin only when search_priority is empty)
librelyrics https://open.spotify.com/track/...

# Only the plugin that matches the URL (no search list)
librelyrics https://open.spotify.com/track/... --direct

# Resolve the URL, then fetch lyrics from a named plugin id
librelyrics https://open.spotify.com/track/... --from applemusic

# Metadata only (needs a SEARCH plugin)
librelyrics --artist "Artist" --title "Track"

# Fetch lyrics for an album
librelyrics https://open.spotify.com/album/...

# Fetch lyrics for a playlist
librelyrics https://open.spotify.com/playlist/...

# Output directory and overwriting
librelyrics <url> -d ./lyrics -f

# Configure settings
librelyrics config edit

# List installed plugins
librelyrics plugin list
```

### As a Library

```python
from librelyrics import LibreLyrics, TrackQuery

ll = LibreLyrics()

response = ll.fetch("https://open.spotify.com/track/...")
print(response.to_lrc())

response = ll.fetch_query(TrackQuery(artist="Artist", title="Track"))

# Album or playlist; per-track results stream in through on_track
responses = ll.fetch_batch(
    "https://open.spotify.com/album/...",
    on_track=lambda track, lyrics, error: print(track.title, error or "ok"),
)
```

## Configuration

Run `librelyrics config edit` for an interactive configuration editor, or manually set values:

```bash
librelyrics config set download_path ./lyrics
librelyrics config set preferred_lyrics_order RICH
librelyrics config set search_priority spotify,applemusic

# Plugin-specific configuration (section name is META.name in lower case)
librelyrics config set plugins.spotify.sp_dc YOUR_SP_DC_COOKIE
```

Plugin config sections are keyed by **`META.name` in lower case** (the Spotify plugin is `plugins.spotify`, not `plugins.Spotify`) or, as a fallback, by `META.id`. Keys are case-sensitive: a value written under the wrong case is silently ignored.

Run `librelyrics config show` to see the resolved config and `librelyrics config path` to locate the file.

### Config Options

| Key | Default | Description |
|-----|---------|-------------|
| `download_path` | `downloads` | Output directory for lyrics files |
| `create_folder` | `true` | Create folders for albums/playlists |
| `preferred_lyrics_order` | `RICH, SYNCED, UNSYNCED` | Stop at the first listed quality (RICH is best) |
| `search_priority` | `[]` | Plugin ids to try after resolve. Empty = URL plugin only. Album/playlist URLs need `list_tracks()` on the URL plugin; otherwise use `--direct`. Search uses simpler artist/title variants first (primary artist, title before `` - ``). |
| `max_search_attempts` | `5` | Cap on search plugins called per track |
| `max_concurrent_tracks` | `4` | Parallel per-track fetches in a batch |
| `force_download` | `false` | Overwrite existing lyrics files |

`search_priority` also acts as a quality filter: a plugin whose declared `lyrics_types` cannot satisfy anything in `preferred_lyrics_order` is skipped before it is called.

## Plugin Development

LibreLyrics supports external plugins via Python entry points. A plugin subclasses `LyricsModule`, declares `META`, sets `LIBRELYRICS_API_VERSION = 2`, and implements `fetch()`.

### Minimal Plugin

```python
import re

from librelyrics.models import LyricsResponse
from librelyrics.modules.base import (
    LyricsModule,
    LyricsType,
    ModuleCapability,
    ModuleMeta,
)


class MyPlugin(LyricsModule):
    META = ModuleMeta(
        id="myservice",                # stable, lower-case + digits only
        name="MyService",              # display name; config section is lower-cased
        regex=re.compile(r"myservice\.com/track/"),
        description="Fetch lyrics from MyService",
        lyrics_types=frozenset({LyricsType.PLAIN, LyricsType.SYNCED}),
        capabilities=frozenset({ModuleCapability.SINGLE_TRACK}),
        config_schema={"api_key": "API key for MyService"},
    )
    LIBRELYRICS_API_VERSION = 2

    def fetch(self) -> LyricsResponse:
        # Your implementation here
        ...
```

Register your plugin in `pyproject.toml`:

```toml
[project.entry-points."librelyrics.plugins"]
myservice = "my_plugin_package:MyPlugin"
```

### `META` Fields

| Field | Type | Purpose |
|---|---|---|
| `id` | `str` | Stable plugin id, lower-case letters and digits only. Used by `--from` and `search_priority`. |
| `name` | `str` | Human-readable name; lower-cased form is the config section key. |
| `regex` | `re.Pattern \| None` | Matches URLs this plugin can handle. `None` = search-only plugin. |
| `requires_auth` | `bool` | Marks the plugin as needing credentials. |
| `description` | `str` | Shown by `librelyrics plugin list`. |
| `lyrics_types` | `frozenset[LyricsType]` | `PLAIN`, `SYNCED`, `RICH_SYNCED`. Used to pre-filter search plugins. |
| `capabilities` | `frozenset[ModuleCapability]` | What the plugin can do (see below). |
| `config_schema` | `dict[str, str]` | Config key → description; drives the interactive editor. |

### Capabilities

Declare capabilities and the core calls the matching method — no duck-typing.

| Capability | Required method | Effect |
|---|---|---|
| `SINGLE_TRACK` | `fetch()` | Default. Handles a single-track URL. |
| `ALBUM` | `list_tracks()` | Album URLs are expanded into per-track queries. |
| `PLAYLIST` | `list_tracks()` | Playlist URLs are expanded into per-track queries. |
| `SEARCH` | `fetch()` | Usable with `--from` and in `search_priority`. |
| `RESOLVE` | `resolve()` | Fills artist, title, album, and duration from a URL before fetching. |

`fetch_album()` and `fetch_playlist()` are optional. The base class implements both as `list_tracks()` followed by a per-track `fetch_with_retry()`; override them only if the provider has a bulk lyrics endpoint.

`classify_url()` decides whether a URL is a `track`, `album`, or `playlist`. The default handles common path shapes (and Apple Music's `/album/...?i=`); override it when the service uses something else.

### URL Matching

`matches()` defaults to a regex match against `query.url`. Search-only plugins override it to accept artist/title queries instead. URL routing uses `META.regex` directly, so a search plugin cannot accidentally claim a URL it does not own.

### Retries and Failure Classification

Back-off is centralized in the core. Plugins **classify** failures; the core decides whether to retry.

```python
class MyPlugin(LyricsModule):
    MAX_RETRIES = 3
    RETRY_BACKOFF = 1.0            # seconds, doubled each attempt
    RETRYABLE_EXCEPTIONS = (ConnectionError, TimeoutError, RateLimitError, TransientProviderError)
```

| Exception | Meaning |
|---|---|
| `LyricsNotFound` | No lyrics exist; not retried, skipped in batches. |
| `RateLimitError` | HTTP 429. Retried; pass `retry_after=` to wait at least that long. |
| `TransientProviderError` | 5xx or dropped connection. Retried. |
| `ProviderError` | Any other provider error; surfaced, not retried. |
| `ConfigurationError` | Bad or missing config; the plugin is skipped. |

Do not implement your own back-off loops — call `fetch()` through `fetch_with_retry()` (or `retry_call()` for a batch), and let the core retry.

### Lifecycle Hooks

```python
MyPlugin.register_before_fetch(lambda module, response=None, error=None: ...)
MyPlugin.register_after_fetch(lambda module, response=None, error=None: ...)
```

Hooks run around `fetch_with_retry()`. A hook that raises is logged at debug level and does not break the fetch.

### Configuration

```python
    @staticmethod
    def default_config() -> dict:
        return {"api_key": ""}

    @staticmethod
    def validate_config(config: dict) -> None:
        # Raise ConfigurationError if the config is unusable
        ...
```

Defaults are merged into the plugin's config section on first run, so declare every key here.

## License

This project is licensed under the GNU General Public License v3.0 — see the [LICENSE](LICENSE) file for details.