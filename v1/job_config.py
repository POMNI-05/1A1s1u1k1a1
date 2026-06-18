# v1/job_config.py

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_JOB_CONFIG = {
    "ato_policy_year": "2026",
    "itr_policy_year": "2026",
    "requested_tables": {
        "carry_forward_losses": False,
        "rd_tax_incentive": False,
        "div7a": False,
        "fbt_entertainment": False,
        "depreciation": False,
        "superannuation": False,
        "gst_reconciliation": False,
        "related_party_loans": False,
        "psi": False,
    },
    "reviewer_notes": "",
    "company_profile": "",
    "document_description": "",
    "client_name": "",
}


def _default_config_path() -> Path:
    return Path(__file__).resolve().parent / "job_config.json"


def load_job_config() -> dict[str, Any]:
    path = Path(os.getenv("TAX_JOB_CONFIG_PATH", _default_config_path()))

    config = DEFAULT_JOB_CONFIG.copy()
    config["requested_tables"] = DEFAULT_JOB_CONFIG["requested_tables"].copy()

    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))

            for key, value in loaded.items():
                if key == "requested_tables" and isinstance(value, dict):
                    config["requested_tables"].update(value)
                else:
                    config[key] = value

        except Exception:
            # Backend should not crash just because frontend config failed.
            pass

    env_year = os.getenv("ATO_POLICY_YEAR") or os.getenv("ITR_POLICY_YEAR")
    if env_year:
        config["ato_policy_year"] = str(env_year)
        config["itr_policy_year"] = str(env_year)

    return config


def get_policy_year(default: str = "2026") -> str:
    config = load_job_config()
    year = str(config.get("ato_policy_year") or config.get("itr_policy_year") or default)

    if year not in {"2024", "2025", "2026"}:
        return default

    return year


def table_requested(table_key: str) -> bool:
    config = load_job_config()
    return bool((config.get("requested_tables") or {}).get(table_key, False))