"""Centralised logging configuration for the scraper pipeline.

Usage:
    from src.utils.logging import get_logger
    logger = get_logger(__name__)
    logger.info("Fetched %d items", count)
    logger.exception("Unexpected error")   # includes full traceback
"""
from __future__ import annotations

import logging
import sys


def _build_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _configure_root() -> None:
    root = logging.getLogger()
    if root.handlers:
        return  # already configured (e.g. called twice or inside Streamlit)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_build_formatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a logger for *name*, ensuring the root handler is set up."""
    _configure_root()
    return logging.getLogger(name)
