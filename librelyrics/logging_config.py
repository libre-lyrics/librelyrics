"""Centralized logging configuration for librelyrics."""
import logging
import sys

# Module-level logger instance
_logger: logging.Logger | None = None


def setup_logging(verbose: bool = False, name: str = 'librelyrics') -> logging.Logger:
    """Configure and return the librelyrics logger.

    Args:
        verbose: If True, enables DEBUG level with detailed format.
                 If False, uses INFO level with minimal format.
        name: Logger name, defaults to 'librelyrics'.

    Returns:
        Configured logger instance.
    """
    global _logger

    logger = logging.getLogger(name)

    # Avoid adding handlers multiple times
    if logger.handlers:
        logger.handlers.clear()

    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    if verbose:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    else:
        # Clean output for normal usage
        formatter = logging.Formatter('%(message)s')

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    _logger = logger
    return logger


def get_logger(name: str = 'librelyrics') -> logging.Logger:
    """Get a logger instance for a specific module.

    Args:
        name: Module name, will be prefixed with 'librelyrics.'.

    Returns:
        Logger instance.
    """
    if name == 'librelyrics':
        return logging.getLogger('librelyrics')
    return logging.getLogger(f'librelyrics.{name}')
