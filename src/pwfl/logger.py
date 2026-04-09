"""
Logging helpers for the PWFL package.

The module exposes one shared logger instance and convenience functions used by
CLI and pipeline modules to adjust verbosity consistently.
"""

import logging

LOGGER = logging.getLogger("pwfl")
LOGGER.setLevel(logging.INFO)


def set_logger_level(level):
    """
    Set the PWFL logger level.

    :param level: Logging level constant from :mod:`logging`.
    :type level: int
    :returns: None
    """
    LOGGER.setLevel(level)


def debug():
    """
    Enable debug logging for the logger and attached handlers.

    :returns: None
    """
    LOGGER.setLevel(logging.DEBUG)
    for handler in LOGGER.handlers:
        handler.setLevel(logging.DEBUG)
