import logging

LOGGER = logging.getLogger("pwfl")
LOGGER.setLevel(logging.INFO)


def set_logger_level(level):
    LOGGER.setLevel(level)


def debug():
    LOGGER.setLevel(logging.DEBUG)
    for handler in LOGGER.handlers:
        handler.setLevel(logging.DEBUG)
