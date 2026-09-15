"""Non-clinical console events; never pass model text or patient data here."""

import logging

logger = logging.getLogger("epic_adapter.progress")


def emit(message: str) -> None:
    logger.info(message)
