# v1_selenium/utils.py

from __future__ import annotations

import logging
import os
from datetime import datetime

from config import DATA_DIR, DOWNLOAD_DIR, LOG_DIR, OUTPUT_DIR


def ensure_dirs() -> None:
    for folder in [DATA_DIR, DOWNLOAD_DIR, OUTPUT_DIR, LOG_DIR]:
        os.makedirs(folder, exist_ok=True)


def setup_logging(level=logging.INFO) -> None:
    ensure_dirs()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(LOG_DIR, f"run_{timestamp}.log")

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