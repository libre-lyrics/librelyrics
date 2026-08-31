import logging

import pytest

from librelyrics.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _reset_librelyrics_logging() -> None:
    yield
    logger = logging.getLogger("librelyrics")
    logger.handlers.clear()
    logger.propagate = True
    logger.setLevel(logging.NOTSET)


def test_default_logging_is_warning() -> None:
    logger = setup_logging(verbose=False)
    assert logger.level == logging.WARNING
    assert logger.handlers
    assert logger.handlers[0].level == logging.WARNING


def test_verbose_logging_is_debug() -> None:
    logger = setup_logging(verbose=True)
    assert logger.level == logging.DEBUG
    assert logger.handlers[0].level == logging.DEBUG
