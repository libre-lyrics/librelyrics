# Plan: Metadata search pipeline (LibreLyrics core)

Language of this document: ASD-STE100 Simplified Technical English.

This plan is for the **core** package `librelyrics` only. Do not change the Spotify, Apple Music, KKBOX, or Deezer plugin repositories in this work. Those plugins must follow the API 2 contract in a later change.

---

## 1. Purpose

The program must fetch lyrics from more than one kind of source:

- A **URL source** uses a track, album, or playlist URL (example: Spotify).
- A **search source** uses artist and title (example: LRCLIB).

The user sets the source order. The URL names the track. The source list names where the program gets lyrics.

---

## 2. Scope

**In scope (core):**

- `TrackQuery` as the one input object
- Plugin API version 2
- `ModuleMeta.id`
- `RESOLVE`, `SEARCH`, `list_tracks()` on the base class
- Search pipeline and quality order
- CLI: `--artist`, `--title`, `--album`, `--direct`, `--from`
- Config: `search_priority`, `preferred_lyrics_order`, `max_search_attempts`, `plugin_directories`
- Plugin load from entry points **and** from a plugin directory
- Library methods that call the same pipeline
- Remove `synced_lyrics` from default config and from the config editor

**Out of scope:**

- Code in other plugin repositories
- Lyrics sources inside the core package (no built-in LRCLIB or Better Lyrics)
- Local file / tag scan (`fetch_files_lyrics` stays not implemented)
- Cache of metadata or quality results
- Parallel search requests for one track

---

## 3. Locked decisions

| Topic | Decision |
|---|---|
| Work area | Core only |
| Plugin API | Increment to 2 |
| Official URL plugins | Must implement `RESOLVE` and `SEARCH`. Must implement `list_tracks()` if they declare `ALBUM` or `PLAYLIST`. That work is **not** in this core change. |
| Plugin `id` | Add `ModuleMeta.id` (no space). Example: `applemusic`, `spotify`, `lrclib` |
| Built-in sources | None. Maintain plugins in a separate plugin directory and/or as installable packages. |
| CLI metadata vs `resolve()` | Call `resolve()` when a URL is present. CLI values always win for fields that the user set. |
| Missing name in `search_priority` | Skip. Write a warning. Continue. |
| Missing plugin for `--from` | Stop. Show an error. |
| Album / playlist | `list_tracks()` once, then the same single-track pipeline per track. `--direct` calls `fetch_album()` / `fetch_playlist()` on the URL plugin only. |
| `--from` | Add in this change. |
| Quality config | Remove `synced_lyrics`. Add `preferred_lyrics_order`. |

---

## 4. Source order when the user does not set a list

You said: if the user does not set priority, use the first discovered plugin.

**Do not use raw discovery order.** Discovery order can change. The first loaded plugin may not match the URL.

**Rule in this plan:**

1. If `search_priority` has one or more ids: use that list (after resolve, see section 9).
2. If `search_priority` is missing or empty **and** the user gave a URL: use **only** the plugin that matches that URL. This is the same as today’s URL fetch.
3. If `search_priority` is missing or empty **and** the user gave artist and title (no URL): use **one** plugin. Select the first plugin that declares `SEARCH`, sorted by `id` (ASCII, lower case). Do not use load order.
4. If no plugin can do the job: show a clear error.

The user can set `search_priority` when they want Apple Music before Spotify, or LRCLIB after all URL sources.

---

## 5. Core data model

Add `TrackQuery` in `librelyrics/models.py` (or a new module). Use a frozen dataclass.

Fields:

- `url: str | None`
- `artist: str | None`
- `title: str | None`
- `album: str | None`
- `duration_ms: int | None`

Do not add `isrc` in this change.

To change a query, use `dataclasses.replace`. Do not mutate the object.

This object is the one input for match, resolve, search, and fetch.

---

## 6. Plugin API version 2

Set `LIBRELYRICS_API_VERSION = 2` in `librelyrics/modules/base.py`.

The version check stays exact. A plugin with version 1 does not load. That is intended. URL plugins must ship a new release before they work with the new core.

### 6.1 `ModuleMeta`

Change `ModuleMeta`:

- Add required field `id: str`. Use lower-case letters and digits only. Do not use spaces.
- Make `regex` optional: `re.Pattern[str] | None = None`.

Do not remove other fields.

`search_priority` and `--from` use `id`, not `META.name`.

If two plugins have the same `id`, the plugin from a plugin directory replaces the entry-point plugin. Write a warning.

### 6.2 Constructor

```text
__init__(self, query: TrackQuery, config: dict) -> None
```

Store `self.query = query`. Keep property `url` that returns `self.query.url`. Plugin code that reads `self.url` continues to work after the plugin moves to API 2.

Do not accept a raw URL string in the base constructor. API 2 is a break.

### 6.3 `matches(cls, query: TrackQuery) -> bool`

Default:

1. If `query.url` is `None`, return `False`.
2. If `META.regex` is `None`, return `False`.
3. Return whether the regex matches `query.url`.

A `SEARCH` plugin must override `matches()`:

- Return `True` when `artist` and `title` are present.
- Do not require `url` to be `None`.

The orchestrator must still pass a **search copy** of the query with `url=None` into `matches()` and into search `fetch()` (see 9.2). This stops a Spotify regex from matching during search.

### 6.4 Capabilities

Keep `SINGLE_TRACK`, `ALBUM`, `PLAYLIST`, `SEARCH`.

Add `RESOLVE`.

Meanings:

- `RESOLVE`: the plugin can fill artist, title, album, duration from `query.url`.
- `SEARCH`: the plugin can fetch lyrics from artist and title (and optional album, duration).
- `ALBUM` / `PLAYLIST`: the plugin can list all tracks as `TrackQuery` objects. Pagination stays inside the plugin. Do not add a bulk-resolve capability.

Official URL plugins **must** set `RESOLVE` and `SEARCH` when they move to API 2. Core does not implement those methods for them.

### 6.5 New and changed methods

**`resolve(self) -> TrackQuery`**

- Required in the contract if `RESOLVE` is set.
- Default on the base class: raise `NotImplementedError`.
- Return a new `TrackQuery` with metadata. Keep the URL unless the plugin has a better URL.

**`list_tracks(self) -> list[TrackQuery]`**

- Required in the contract if `ALBUM` or `PLAYLIST` is set.
- Default: raise `NotImplementedError`.
- Return the full list. The plugin must do all paging inside this method.

**`fetch(self) -> LyricsResponse`**

- No change to the return type.
- For a URL plugin, `fetch()` uses `self.query` (URL or metadata).
- For a search plugin, `fetch()` uses artist and title on `self.query`.

**`fetch_album()` default**

- Call `list_tracks()`.
- For each item, construct this plugin with that `TrackQuery` and call `fetch_with_retry()`.
- A plugin can override this method for a faster bulk lyrics API.

**`fetch_playlist()` default**

- Same pattern as `fetch_album()`.

**`fetch_with_retry()`**

- Do not change retry rules.
- The orchestrator must call `fetch_with_retry()`, not `fetch()`, for single-track fetch.

---

## 7. Plugin discovery

Keep entry points group `librelyrics.plugins`.

Add a second path: **plugin directories**.

- Config key: `plugin_directories` (list of strings).
- Default: one directory next to the config file: `<config_dir>/plugins`.
- Example: `~/.config/librelyrics/plugins` on Linux.

Load each directory:

1. Import each Python module or package in that directory.
2. Find subclasses of `LyricsModule`.
3. Run the same `validate_plugin()` check (API 2, `META`, `id`).

Merge lists:

1. Entry-point plugins
2. Directory plugins (same `id` replaces the entry-point plugin)

Sort the full list by `id` for a stable order. Do not use install order for behavior.

If no valid plugin loads, raise `NoPluginsFoundError` as today.

Core must not ship lyrics source modules. The plugin directory can be empty.

---

## 8. Configuration

### 8.1 Remove

Remove `synced_lyrics` from:

- `get_default_config()`
- the interactive config editor
- README

If an old config file still has `synced_lyrics`, ignore it. Do not fail load.

### 8.2 Add

```text
preferred_lyrics_order: ["RICH", "SYNCED", "UNSYNCED"]
search_priority: []
max_search_attempts: 5
plugin_directories: []    # empty means: use the default config_dir/plugins path only
```

If `plugin_directories` is an empty list, still use the default `<config_dir>/plugins` directory if it exists.

`search_priority` is a list of plugin `id` strings.

### 8.3 Quality list

Allowed tokens: `RICH`, `SYNCED`, `UNSYNCED`.

Map to `LyricsType`:

- `RICH` → `RICH_SYNCED`
- `SYNCED` → `SYNCED`
- `UNSYNCED` → `PLAIN`

List order = most wanted to least wanted.

The user edits this list in `config.json` or in `librelyrics config edit`. Add a config-editor section for:

- preferred lyrics order
- search priority (list of installed plugin ids)

### 8.4 Quality rules

Lattice for “meets type T”:

- A `RICH` result meets `RICH`, `SYNCED`, and `UNSYNCED`.
- A `SYNCED` result meets `SYNCED` and `UNSYNCED`.
- An `UNSYNCED` result meets `UNSYNCED` only.

**Stop (“good enough”):** the result meets the **first** token in `preferred_lyrics_order`.

**Fallback:** if the result does not stop the loop, keep it when it meets **any** token in the list. Rank kept results by the earliest list token they meet. If two results meet the same token, keep the earlier plugin in `search_priority`.

**Not in the list:** do not keep the result if the list does not include a type that it meets, except: if the cap is reached and no kept result exists, return the best result you have so that the user still gets lyrics. If you have no result, raise `LyricsNotFound`.

**Pre-filter:** skip a plugin before the network call if `META.lyrics_types` cannot meet any token in `preferred_lyrics_order`. Example: the list is only `["RICH"]` and the plugin declares only `PLAIN` → skip.

`max_search_attempts` counts plugins that you **call**, not plugins that you skip in the pre-filter.

---

## 9. Single-track pipeline

One function in core (name example: `fetch_query`). All CLI and library fetch paths must call it.

Inputs: `TrackQuery`, flags `direct: bool`, `from_plugin: str | None`.

### 9.1 `--direct`

1. Require `query.url`. If no URL, error: `--direct` needs a URL.
2. Find the plugin whose default `matches()` accepts that URL. If none, error: no plugin matches this URL.
3. Construct the plugin. Call `fetch_with_retry()` (or album/playlist methods in batch).
4. Do not call `resolve()` for search. Do not walk `search_priority`.
5. Return that plugin’s error as-is (`LyricsNotFound`, `ProviderError`).

### 9.2 `--from <id>`

1. Find the plugin with that `id`. If missing, error (decision 9B).
2. If `query.url` is set and artist or title is missing: find the URL-matching plugin. If it has `RESOLVE`, call `resolve()`. Merge: user CLI fields always replace resolved fields.
3. If artist or title is still missing, error: need artist and title.
4. Build a search `TrackQuery` with `url=None` and the metadata.
5. If that plugin does not declare `SEARCH`, error.
6. Construct that plugin with the search query. Call `fetch_with_retry()`.
7. Do not walk `search_priority`. Do not fetch from the URL host unless its `id` is the `--from` id.

### 9.3 Default path (no `--direct`, no `--from`)

**Step A — Resolve**

If `query.url` is set:

1. Find the URL-matching plugin. If none, continue to Step B with the query as-is (metadata-only if the user passed tags).
2. If artist and title are already set by the CLI, still call `resolve()` when the plugin has `RESOLVE`. Then apply CLI fields on top (decision 8C).
3. If the plugin does not have `RESOLVE`, keep CLI metadata. Do not fail only because `RESOLVE` is missing (API 1 plugins will not load; API 2 official plugins must have it).

**Step B — Choose sources**

- If `search_priority` is not empty: use that id list. Skip unknown ids with a warning. Skip ids that are not `SEARCH` with a warning.
- If `search_priority` is empty and there is a URL: do **not** search. Fetch lyrics from the URL-matching plugin only (section 4, rule 2). Construct with the original URL query (not `url=None`). Call `fetch_with_retry()`. Stop. This keeps current URL behavior when the user sets no list.
- If `search_priority` is empty and there is no URL: use the first `SEARCH` plugin by sorted `id` (section 4, rule 3).

**Step C — Search loop** (only when the source list has more than the single URL fetch in rule 2)

For each plugin id in order, until `max_search_attempts` calls:

1. Pre-filter on `lyrics_types`.
2. Construct with a copy of the query where `url=None`.
3. Call `fetch_with_retry()`.
4. On `LyricsNotFound` or `ProviderError` after retries: log, continue.
5. On `ConfigurationError`: log a warning, skip that plugin, continue.
6. If the result is good enough (section 8.4): return it.
7. Else keep fallback and continue.

After the loop: return the best fallback, or raise `LyricsNotFound`.

Do not send search requests in parallel for one track.

**Important:** When `search_priority` is not empty, do **not** return lyrics from the URL plugin first only because the URL matched. The URL plugin is a lyrics source only if its `id` is in the list (or `--from` / `--direct`). The URL plugin is still used to `resolve()`.

---

## 10. Album and playlist

### 10.1 Not `--direct`

1. Match the URL to a plugin.
2. If the URL is an album and the plugin has `ALBUM`, call `list_tracks()`.
3. If the URL is a playlist and the plugin has `PLAYLIST`, call `list_tracks()`.
4. Do not add new URL-string tests like `'album' in url` if the plugin can tell the kind. If the core still cannot tell, keep the current URL path test as a temporary fallback.
5. For each `TrackQuery`, run section 9 (same flags: `direct=False`, same `--from` if set).
6. Tracks are independent. You may run them in parallel. Limit concurrency (config `max_concurrent_tracks`, default `4`). Each track still uses sequential search inside.

### 10.2 `--direct`

1. Match the URL plugin.
2. Call `fetch_album()` or `fetch_playlist()` on that plugin only.
3. Do not call `search_priority`.

The CLI progress bar must follow the orchestrator. Do not monkey-patch `_fetch_track_lyrics`.

---

## 11. CLI

Add options on the fetch command:

- `--artist`
- `--title`
- `--album`
- `--direct` / `-D`
- `--from` (plugin `id`)

`--direct` and `--from` together: error. The user must choose one.

Require `--artist` and `--title` together when there is no URL.

If there is no URL and no artist/title: keep the interactive URL prompt, unless you add a prompt for artist/title later. This change does not add a new interactive metadata prompt.

Update `main()` so that `--artist`, `--title`, `--album`, `--from` with values are not treated as a URL. Use the same skip pattern as `--directory`.

Library API:

- Keep `LibreLyrics.fetch(url: str)` as a wrapper: `TrackQuery(url=url)` then `fetch_query`.
- Add `LibreLyrics.fetch_query(query: TrackQuery, *, direct: bool = False, from_plugin: str | None = None)`.
- `fetch_batch` must use `list_tracks` + `fetch_query` when not direct.

Errors:

- No URL for `--direct`: specific message
- No plugin for URL: specific message
- No plugin for `--from`: specific message
- Search found nothing: `LyricsNotFound`

Do not use `NoMatchingModuleError` for a failed metadata search.

---

## 12. Compatibility (core)

When `search_priority` is empty, a single URL fetch must match today’s behavior: one matching plugin, its lyrics, its errors. `--direct` is the same path with an explicit flag.

Do not change `fetch_with_retry` back-off rules.

`ModuleMeta` **does** change (`id`, optional `regex`). That is part of API 2.

Plugins at API 1 do not load. Document this in README: install plugin versions that declare API 2, or keep an older core.

---

## 13. Implementation order (core)

Do the work in this order. Do not skip validation after each step.

1. Add `TrackQuery`. Add unit tests for `replace` and optional fields.
2. Set `LIBRELYRICS_API_VERSION = 2`. Add `id` and optional `regex` on `ModuleMeta`. Change constructor, `matches()`, `resolve()`, `list_tracks()`, default `fetch_album()` / `fetch_playlist()`.
3. Change `registry.py`: validate `id`; load plugin directories; merge and sort by `id`; `get_plugin_for_url` uses `TrackQuery`.
4. Change default config. Remove `synced_lyrics`. Add the new keys. Update `config edit`.
5. Implement quality helpers (meet type, pre-filter, fallback rank). Unit tests.
6. Implement `fetch_query` (direct, from, empty list, priority list). Unit tests with fake plugins (no network).
7. Wire `LibreLyrics.fetch` / `fetch_batch` to `fetch_query`.
8. Wire CLI flags and `main()` option parsing.
9. Album path: `list_tracks` + per-track `fetch_query`; `--direct` bulk fetch; progress without private hooks.
10. Update README: API 2, config keys, CLI examples, plugin directory, statement that sources are not in core.

Fake plugins for tests must live under `tests/`. They are not product sources.

---

## 14. Tests (core)

There are no tests in the repo now. Add `tests/` and pytest.

Minimum cases:

- `TrackQuery` replace and CLI override after resolve
- Default `matches()` with URL; `SEARCH` `matches()` with metadata
- API 1 plugin rejected; API 2 plugin without `id` rejected
- Directory plugin overrides entry-point plugin with same `id`
- Empty `search_priority` + URL → only URL plugin `fetch`
- Empty `search_priority` + artist/title → first `SEARCH` plugin by `id`
- Non-empty list: URL plugin used for `resolve` only; lyrics from list order
- Pre-filter skips a plain-only plugin when order is `["RICH"]`
- Stop at `RICH` when first token is `RICH`
- Fallback when first token is `RICH` but only `SYNCED` exists
- `max_search_attempts` cap
- `--direct` does not call search plugins
- `--from` missing plugin → error
- Unknown id in list → warning and skip
- `list_tracks` then two tracks each run the single-track logic (fake)

Use fake `LyricsModule` subclasses. Do not call Spotify or LRCLIB in core tests.

---

## 15. Contract for plugin repos (later, not this change)

Each official plugin must, in a later change:

1. Set `LIBRELYRICS_API_VERSION = 2`.
2. Set `META.id` (`spotify`, `applemusic`, `kkbox`, `deezer`).
3. Change `__init__` to `TrackQuery`.
4. Implement `resolve()` from the service URL.
5. Implement `SEARCH`: catalog search by artist and title, then lyrics fetch.
6. Override `matches()` so search queries match when artist and title are present.
7. Implement `list_tracks()` for album and/or playlist.
8. Keep `fetch()` working for that service’s own URL (`--direct`).

LRCLIB and Better Lyrics are separate plugin packages or modules in the plugin directory. They set `SEARCH` only. They do not set a URL regex.

---

## 16. CLI examples (after core and plugins exist)

```text
# Same as today when search_priority is empty
librelyrics https://open.spotify.com/track/...

# Only the URL host
librelyrics https://open.spotify.com/track/... --direct

# Force one search source after resolve
librelyrics https://open.spotify.com/track/... --from applemusic

# User order (config): applemusic, deezer, lrclib
librelyrics https://open.spotify.com/track/...

# No URL
librelyrics --artist "Artist" --title "Track"
```

Config example:

```text
preferred_lyrics_order: ["RICH", "SYNCED", "UNSYNCED"]
search_priority: ["applemusic", "deezer", "spotify", "lrclib"]
max_search_attempts: 5
```

---

## 17. Risks

- After this core release, current plugins do not load until they move to API 2. README must say this.
- `SEARCH` on URL plugins is not in this change. `--from applemusic` and a list that contains `applemusic` will skip or error until that plugin exists and declares `SEARCH`.
- Empty `search_priority` does not give Apple Music lyrics from a Spotify URL. The user must set the list (or `--from`) after plugins support `SEARCH`.

---

## 18. Done when

- API 2 loads only plugins with version 2 and a unique `id`.
- Empty `search_priority` + URL uses one URL plugin.
- Non-empty `search_priority` resolves the URL, then walks the list.
- `--direct` and `--from` behave as in sections 9.1 and 9.2.
- `preferred_lyrics_order` controls stop and fallback. `synced_lyrics` is gone.
- Plugin directories merge with entry points.
- Core contains no lyrics source implementation.
- Unit tests in section 14 pass.
