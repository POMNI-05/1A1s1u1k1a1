# v1/job_config.py

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from tax_calculators.registry import normalise_income_year


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
    "company_tax_rate_category": "review_required",
    "base_rate_entity_assessment": {},
    "reviewed_tax_depreciation": {
        "amount": None,
        "approved_for_posting": False,
    },
    "retain_job_files": False,
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
            if isinstance(loaded, dict) and "job_options" in loaded:
                loaded = loaded["job_options"]

            if not isinstance(loaded, dict):
                raise ValueError("Job configuration must be an object")

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
    return normalise_income_year(year)


def table_requested(table_key: str) -> bool:
    config = load_job_config()
    return bool((config.get("requested_tables") or {}).get(table_key, False))


def get_tax_rate_category(default: str = "review_required") -> str:
    value = str(load_job_config().get("company_tax_rate_category", default)).strip().lower()
    return value if value in {"base_rate_entity", "general"} else default
