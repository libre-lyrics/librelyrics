"""Abstract base class for all lyrics modules (plugins).

All librelyrics plugins must inherit from LyricsModule and implement the required
interface. Plugins declare their capabilities via the META class attribute.
"""
from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import Any, ClassVar

from librelyrics.exceptions import RateLimitError
from librelyrics.models import LyricsResponse

logger = logging.getLogger('librelyrics.modules.base')

# Current API version - plugins must match this to be loaded
LIBRELYRICS_API_VERSION = 1


class LyricsType(Enum):
    """Types of lyrics a module can provide.

    Attributes:
        PLAIN: Unsynced lyrics (just text, no timestamps).
        SYNCED: Line-synced lyrics (timestamp per line).
        RICH_SYNCED: Word-synced lyrics (timestamp per word, karaoke-style).
    """
    PLAIN = auto()
    SYNCED = auto()
    RICH_SYNCED = auto()


class ModuleCapability(Flag):
    """Capabilities a module can declare, beyond just lyrics types.

    Use this to declare batch-fetch support so the orchestrator can
    dispatch without duck-typing or ``hasattr`` checks.

    Attributes:
        SINGLE_TRACK: Can fetch a single track.
        ALBUM: Can fetch an entire album.
        PLAYLIST: Can fetch an entire playlist.
        SEARCH: Can search for a track by metadata.
    """
    SINGLE_TRACK = auto()
    ALBUM = auto()
    PLAYLIST = auto()
    SEARCH = auto()


@dataclass(frozen=True)
class ModuleMeta:
    """Metadata describing a lyrics module's capabilities.

    Attributes:
        name: Human-readable name for the module.
        regex: Compiled pattern to match URLs this module can handle.
        requires_auth: Whether this module requires authentication config.
        description: Optional description of the module.
        lyrics_types: Set of lyrics types this module can provide.
        capabilities: Set of capabilities this module supports.
        config_schema: Mapping of config key to a human-readable description.
                       Used by the interactive config editor so the CLI
                       never needs to hardcode plugin-specific fields.
    """
    name: str
    regex: re.Pattern[str]
    requires_auth: bool = False
    description: str = ""
    lyrics_types: frozenset[LyricsType] = field(
        default_factory=lambda: frozenset({LyricsType.PLAIN, LyricsType.SYNCED})
    )
    capabilities: frozenset[ModuleCapability] = field(
        default_factory=lambda: frozenset({ModuleCapability.SINGLE_TRACK})
    )
    config_schema: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Lifecycle hooks type
# ---------------------------------------------------------------------------
FetchHook = Callable[["LyricsModule", "LyricsResponse | None", Exception | None], None]


class LyricsModule(ABC):
    """Abstract base class for all lyrics provider plugins.

    Plugins must:
    1. Define a META class attribute of type ModuleMeta
    2. Set LIBRELYRICS_API_VERSION to match the current API version
    3. Implement the fetch() method
    4. Optionally implement fetch_album() / fetch_playlist() and
       declare the corresponding ModuleCapability in META.

    Example:
        class MyModule(LyricsModule):
            META = ModuleMeta(
                name="MyService",
                regex=re.compile(r"myservice\\.com/track/"),
                capabilities=frozenset({
                    ModuleCapability.SINGLE_TRACK,
                    ModuleCapability.ALBUM,
                }),
                config_schema={
                    'api_key': 'API key for MyService',
                },
            )
            LIBRELYRICS_API_VERSION = 1

            def fetch(self) -> LyricsResponse:
                # ... implementation
    """

    # Class attributes to be defined by subclasses
    META: ClassVar[ModuleMeta]
    LIBRELYRICS_API_VERSION: ClassVar[int] = LIBRELYRICS_API_VERSION

    # --- Retry defaults (override per-module if needed) ---
    MAX_RETRIES: ClassVar[int] = 3
    RETRY_BACKOFF: ClassVar[float] = 1.0  # seconds, doubled each retry
    RETRYABLE_EXCEPTIONS: ClassVar[tuple[type[Exception], ...]] = (
        ConnectionError,
        TimeoutError,
        RateLimitError,
    )

    # --- Lifecycle hooks (class-level, per-subclass) ---
    _before_fetch_hooks: ClassVar[list[FetchHook]] = []
    _after_fetch_hooks: ClassVar[list[FetchHook]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Ensure each subclass gets its own hook lists."""
        super().__init_subclass__(**kwargs)
        cls._before_fetch_hooks = []
        cls._after_fetch_hooks = []

    def __init__(self, url: str, config: dict) -> None:
        """Initialize module with target URL and configuration.

        Args:
            url: The URL to fetch lyrics from.
            config: Plugin-specific configuration dictionary.
        """
        self.url = url
        self.config = config

    # ------------------------------------------------------------------
    # Lifecycle hook registration
    # ------------------------------------------------------------------
    @classmethod
    def register_before_fetch(cls, hook: FetchHook) -> None:
        """Register a hook to be called before every fetch().

        Args:
            hook: Callable(module, response=None, error=None).
        """
        cls._before_fetch_hooks.append(hook)

    @classmethod
    def register_after_fetch(cls, hook: FetchHook) -> None:
        """Register a hook to be called after every fetch().

        Args:
            hook: Callable(module, response, error).
        """
        cls._after_fetch_hooks.append(hook)

    # ------------------------------------------------------------------
    # URL matching
    # ------------------------------------------------------------------
    @classmethod
    def matches(cls, url: str) -> bool:
        """Check if this module can handle the given URL.

        Args:
            url: URL to check.

        Returns:
            True if this module can handle the URL.
        """
        return cls.META.regex.search(url) is not None

    @classmethod
    def has_capability(cls, cap: ModuleCapability) -> bool:
        """Check whether this module declares a given capability.

        Args:
            cap: The capability to check.

        Returns:
            True if the module declares *cap*.
        """
        return cap in cls.META.capabilities

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------
    @staticmethod
    def default_config() -> dict:
        """Return default configuration for this module.

        Override to provide module-specific defaults that will be
        merged into the main configuration.

        Returns:
            Dictionary of default configuration values.
        """
        return {}

    @staticmethod  # noqa: B027
    def validate_config(config: dict) -> None:
        """Validate the configuration for this module.

        Override to check that required config keys are present
        and have valid values.

        Args:
            config: Configuration dictionary to validate.

        Raises:
            ConfigurationError: If configuration is invalid.
        """

    # ------------------------------------------------------------------
    # Core fetch (must override)
    # ------------------------------------------------------------------
    @abstractmethod
    def fetch(self) -> LyricsResponse:
        """Fetch lyrics for the configured URL.

        Returns:
            LyricsResponse containing the fetched lyrics.

        Raises:
            LyricsNotFound: If lyrics are not available.
            ProviderError: For any provider-specific errors.
        """
        ...

    # ------------------------------------------------------------------
    # Batch fetch (optional — declare capability to enable)
    # ------------------------------------------------------------------
    def fetch_album(self) -> list[LyricsResponse]:
        """Fetch lyrics for all tracks in an album.

        Override this method and add ``ModuleCapability.ALBUM`` to
        ``META.capabilities`` to enable album-level fetching.

        Returns:
            List of LyricsResponse objects.

        Raises:
            NotImplementedError: If the module does not support album fetch.
        """
        raise NotImplementedError(
            f"{self.META.name} does not support album-level fetching."
        )

    def fetch_playlist(self) -> list[LyricsResponse]:
        """Fetch lyrics for all tracks in a playlist.

        Override this method and add ``ModuleCapability.PLAYLIST`` to
        ``META.capabilities`` to enable playlist-level fetching.

        Returns:
            List of LyricsResponse objects.

        Raises:
            NotImplementedError: If the module does not support playlist fetch.
        """
        raise NotImplementedError(
            f"{self.META.name} does not support playlist-level fetching."
        )

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------
    def fetch_with_retry(self) -> LyricsResponse:
        """Call ``fetch()`` with automatic retry and exponential back-off.

        Uses ``MAX_RETRIES``, ``RETRY_BACKOFF``, and
        ``RETRYABLE_EXCEPTIONS`` class attributes for configuration.

        Returns:
            LyricsResponse on success.

        Raises:
            The last exception if all retries are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._run_hooks(self._before_fetch_hooks)
                response = self.fetch()
                self._run_hooks(self._after_fetch_hooks, response=response)
                return response
            except self.RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                wait = self.RETRY_BACKOFF * (2 ** (attempt - 1))
                logger.warning(
                    "%s: attempt %d/%d failed (%s), retrying in %.1fs",
                    self.META.name, attempt, self.MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            except Exception as exc:
                self._run_hooks(self._after_fetch_hooks, error=exc)
                raise
        # All retries exhausted
        assert last_exc is not None
        self._run_hooks(self._after_fetch_hooks, error=last_exc)
        raise last_exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run_hooks(
        self,
        hooks: list[FetchHook],
        response: LyricsResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        for hook in hooks:
            try:
                hook(self, response, error)
            except Exception:  # noqa: BLE001
                logger.debug("Lifecycle hook %s failed", hook, exc_info=True)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} url={self.url!r}>"
