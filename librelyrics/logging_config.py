"""Centralized logging configuration for librelyrics."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

# Module-level logger instance
_logger: logging.Logger | None = None


def setup_logging(
    verbose: bool = False,
    name: str = "librelyrics",
    *,
    console: Console | None = None,
) -> logging.Logger:
    """Configure and return the librelyrics logger.

    Args:
        verbose: If True, enables DEBUG level with detailed format.
                 If False, uses WARNING level (quiet CLI output).
        name: Logger name, defaults to 'librelyrics'.
        console: Optional Rich console for verbose RichHandler output.

    Returns:
        Configured logger instance.
    """
    global _logger

    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.WARNING
    logger.setLevel(level)

    if verbose and console is not None:
        from rich.logging import RichHandler

        handler: logging.Handler = RichHandler(
            console=console,
            show_time=True,
            show_path=True,
            markup=False,
            rich_tracebacks=True,
        )
        handler.setLevel(logging.DEBUG)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        if verbose:
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)

    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    _logger = logger
    return logger


def get_logger(name: str = "librelyrics") -> logging.Logger:
    """Get a logger instance for a specific module.

    Args:
        name: Module name, will be prefixed with 'librelyrics.'.

    Returns:
        Logger instance.
    """
    if name == "librelyrics":
        return logging.getLogger("librelyrics")
    return logging.getLogger(f"librelyrics.{name}")
