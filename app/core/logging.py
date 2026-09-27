"""Application logging configuration (standard library only)."""

import logging

from app.core.config import get_settings

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    """Configure root application logging based on settings.

    Safe to call multiple times: ``basicConfig`` is a no-op once the root
    logger already has handlers.
    """
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format=LOG_FORMAT,
    )
