"""LibreLyrics exception hierarchy."""


class LibreLyricsError(Exception):
    """Base exception for all librelyrics errors."""
    pass


# === Plugin Errors ===

class NoPluginsFoundError(LibreLyricsError):
    """No plugins found in the system."""
    pass

class PluginError(LibreLyricsError):
    """Base exception for plugin-related errors."""
    pass


class PluginLoadError(PluginError):
    """Failed to load a plugin module."""
    pass


class PluginAPIVersionError(PluginError):
    """Plugin API version is incompatible with current librelyrics version."""
    def __init__(self, plugin_name: str, plugin_version: int, supported_version: int):
        self.plugin_name = plugin_name
        self.plugin_version = plugin_version
        self.supported_version = supported_version
        super().__init__(
            f"Plugin '{plugin_name}' requires API version {plugin_version}, "
            f"but librelyrics supports version {supported_version}"
        )


class NoMatchingModuleError(PluginError):
    """No plugin found that matches the given URL."""
    pass


# === Config Errors ===

class ConfigurationError(LibreLyricsError):
    """Configuration is invalid or missing required values."""
    pass


class CorruptedConfig(ConfigurationError):
    """Config file is corrupted and cannot be parsed."""
    pass


# === Provider Errors ===

class ProviderError(LibreLyricsError):
    """Base exception for provider/API errors."""
    pass


class NotValidSp_Dc(ProviderError):
    """Spotify sp_dc cookie is invalid."""
    pass


class NoSongPlaying(ProviderError):
    """No song is currently playing on user's Spotify."""
    pass


class TOTPGenerationException(ProviderError):
    """Failed to generate TOTP for Spotify authentication."""
    pass


class LyricsNotFound(ProviderError):
    """Lyrics not available for the requested track."""
    pass


class RateLimitError(ProviderError):
    """Provider returned a rate-limit (HTTP 429) response.

    Plugins should raise this so the retry infrastructure can
    apply back-off automatically.
    """
    def __init__(self, message: str = "Rate limited", retry_after: float | None = None):
        self.retry_after = retry_after
        super().__init__(message)
