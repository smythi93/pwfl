"""Logging configuration for test purification."""

import logging
import sys

# Create logger
LOGGER = logging.getLogger("test_purification")
LOGGER.setLevel(logging.INFO)

# Create console handler
handler = logging.StreamHandler(sys.stderr)
handler.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# Add handler to logger
if not LOGGER.handlers:
    LOGGER.addHandler(handler)
