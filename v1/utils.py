# v1/utils.py
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from config import DATA_DIR, INPUT_DIR, PROCESSED_DIR, LOG_DIR, OUTPUT_DIR


def ensure_dirs() -> None:
    for folder in [DATA_DIR, INPUT_DIR, PROCESSED_DIR, OUTPUT_DIR, LOG_DIR]:
        Path(folder).mkdir(parents=True, exist_ok=True)


def setup_logging(level: int = logging.INFO) -> None:
    ensure_dirs()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(LOG_DIR) / f"run_{timestamp}.log"

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
        force=True,
    )

    logging.info("Logging started: %s", log_file)