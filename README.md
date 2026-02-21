# LibreLyrics

<div align="center">

![Logo](https://avatars.githubusercontent.com/u/260162604)

A modular, plugin-based lyrics fetcher. Fetch synced and unsynced lyrics from various sources via plugins.

</div>



## Features

- **Synced lyrics** — Line-by-line timestamps (LRC format)
- **Rich synced lyrics** — Word-by-word karaoke-style timing (Enhanced LRC)
- **Plugin architecture** — Extensible with external plugins via entry points
- **Batch downloads** — Fetch lyrics for entire albums or playlists
- **CLI & Library** — Use from the command line or import as a Python library
- **Interactive config** — Menu-driven configuration editor

## Installation

```bash
pip install librelyrics
```

## Plugins

LibreLyrics is a plugin-based system. The core package **does not include any lyrics sources** by default. You need to install plugin packages separately to fetch lyrics from different services.

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
# Fetch lyrics for a single track (requires appropriate plugin installed)
librelyrics https://open.spotify.com/track/...

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
from librelyrics import LibreLyrics

ll = LibreLyrics()

# Fetch lyrics for a track
response = ll.fetch("https://open.spotify.com/track/...")
print(response.to_lrc())
```

## Configuration

Run `librelyrics config edit` for an interactive configuration editor, or manually set values:

```bash
librelyrics config set download_path ./lyrics
librelyrics config set synced_lyrics true

# Plugin-specific configuration (example for Spotify plugin)
librelyrics config set plugins.spotify.sp_dc YOUR_SP_DC_COOKIE
```

### Config Options

| Key | Default | Description |
|-----|---------|-------------|
| `download_path` | `downloads` | Output directory for lyrics files |
| `create_folder` | `true` | Create folders for albums/playlists |
| `synced_lyrics` | `true` | Prefer synced lyrics when available |
| `enhanced_lrc` | `true` | Use Enhanced LRC format for word-level timing |
| `force_download` | `false` | Overwrite existing lyrics files |

## Plugin Development

LibreLyrics supports external plugins via Python entry points. Create a plugin by subclassing `LyricsModule`:

```python
import re
from librelyrics.modules.base import LyricsModule, ModuleMeta, ModuleCapability

class MyPlugin(LyricsModule):
    META = ModuleMeta(
        name="MyService",
        regex=re.compile(r"myservice\.com/track/"),
        capabilities=frozenset({ModuleCapability.SINGLE_TRACK}),
    )
    LIBRELYRICS_API_VERSION = 1

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
