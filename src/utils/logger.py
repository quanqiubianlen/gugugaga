"""Logging setup for the desktop agent."""

import logging
import sys
from pathlib import Path


def setup_logger(level: str = "INFO", log_file: str = "agent.log") -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger("desktop_agent")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_path = Path(log_file)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
