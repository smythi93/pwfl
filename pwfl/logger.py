import logging
import sys

LOGGER = logging.getLogger("pwfl")
LOGGER.setLevel(logging.INFO)

# Add console handler if not already present
if not LOGGER.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    LOGGER.addHandler(handler)


def set_logger_level(level):
    LOGGER.setLevel(level)


def debug():
    LOGGER.setLevel(logging.DEBUG)
