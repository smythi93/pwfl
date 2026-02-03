import logging

LOGGER = logging.getLogger("tcp")
logging.basicConfig(
    level=logging.INFO, format="%(name)s :: %(levelname)-8s :: %(message)s"
)


def debug():
    LOGGER.setLevel(logging.DEBUG)
    for handler in LOGGER.handlers:
        handler.setLevel(logging.DEBUG)
