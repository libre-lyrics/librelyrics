# LibreLyrics

<div align="center">

![Logo](https://avatars.githubusercontent.com/u/260162604)

A modular, plugin-based lyrics fetcher. Fetch synced and unsynced lyrics from various sources via plugins.

</div>



## Features

- **Synced lyrics** — Line-by-line timestamps (LRC format)
- **Rich synced lyrics** — Word-by-word karaoke-style timing (Enhanced LRC)
- **Plugin architecture** — External plugins via entry points
- **Metadata search** — Fetch by artist and title, with a user-defined source list
- **Batch downloads** — Fetch lyrics for entire albums or playlists
- **CLI & Library** — Use from the command line or import as a Python library
- **Interactive config** — Menu-driven configuration editor

## Installation

```bash
pip install librelyrics
```

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

# List installed plugins
librelyrics plugin list
```

### Available Plugins

Plugin packages follow the naming convention `librelyrics-{service}`. Check the [libre-lyrics](https://github.com/libre-lyrics) organization for available plugins.

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
```

## Configuration

Run `librelyrics config edit` for an interactive configuration editor, or manually set values:

```bash
librelyrics config set download_path ./lyrics
librelyrics config set preferred_lyrics_order RICH

# Plugin-specific configuration (key is META.name in lower case, example spotify)
librelyrics config set plugins.spotify.sp_dc YOUR_SP_DC_COOKIE
```

### Config Options

| Key | Default | Description |
|-----|---------|-------------|
| `download_path` | `downloads` | Output directory for lyrics files |
| `create_folder` | `true` | Create folders for albums/playlists |
| `preferred_lyrics_order` | `RICH, SYNCED, UNSYNCED` | Stop at the first listed quality (RICH is best) |
| `search_priority` | `[]` | Plugin ids to try after resolve. Empty = URL plugin only. Album/playlist URLs need `list_tracks()` on the URL plugin; otherwise use `--direct`. |
| `max_search_attempts` | `5` | Cap on search plugins called per track |
| `max_concurrent_tracks` | `4` | Parallel per-track fetches in a batch |
| `force_download` | `false` | Overwrite existing lyrics files |

## Plugin Development

LibreLyrics supports external plugins via Python entry points. Create a plugin by subclassing `LyricsModule`:

```python
import re
from librelyrics.modules.base import LyricsModule, ModuleMeta, ModuleCapability

class MyPlugin(LyricsModule):
    META = ModuleMeta(
        id="myservice",
        name="MyService",
        regex=re.compile(r"myservice\.com/track/"),
        capabilities=frozenset({ModuleCapability.SINGLE_TRACK}),
    )
    LIBRELYRICS_API_VERSION = 2

    def fetch(self):
        # Your implementation here
        ...
```

Register your plugin in `pyproject.toml`:

```toml
[project.entry-points."librelyrics.plugins"]
myservice = "my_plugin_package:MyPlugin"
```

## License

This project is licensed under the GNU General Public License v3.0 — see the [LICENSE](LICENSE) file for details.
