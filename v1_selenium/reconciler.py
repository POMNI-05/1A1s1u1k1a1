# v1_selenium/reconciler.py
"""Small extraction/check helpers for parsed Xero reports."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from cleaner import (
    NET_PROFIT_ALIASES,
    NET_ASSETS_ALIASES,
    TOTAL_ASSETS_ALIASES,
    TOTAL_EQUITY_ALIASES,
    TOTAL_LIABILITIES_ALIASES,
    clean_amount,
    extract_value,
    get_current_amount_col,
)
from config import TAX_RATE

logger = logging.getLogger(__name__)


def _fallback_last_total(df: pd.DataFrame, aliases: list[str], amount_col: str) -> Optional[float]:
    if "Account" not in df.columns:
        return None

    names = df["Account"].astype(str).str.lower().str.strip()
    pattern = "|".join(aliases)
    matches = df[names.str.contains(pattern, regex=True, na=False)]
    if not matches.empty:
        return clean_amount(matches.iloc[-1][amount_col])
    return None


def extract_pl_values(pl_df: pd.DataFrame) -> dict:
    """Extract reported net profit/loss from the original Xero total row where possible."""
    amount_col = get_current_amount_col(pl_df)
    net_profit = extract_value(pl_df, NET_PROFIT_ALIASES, amount_col=amount_col, prefer_total=True)
    method = "alias match"

    if net_profit is None:
        net_profit = _fallback_last_total(pl_df, ["net profit", "profit", "loss"], amount_col)
        method = "fallback total search"

    if net_profit is None:
        net_profit = 0.0
        method = "not found - defaulted to zero"
        logger.error("Could not find net profit/loss row in P&L. Defaulted to zero.")

    return {
        "net_profit": net_profit,
        "amount_col": amount_col,
        "extraction_method": method,
    }


def extract_bs_values(bs_df: pd.DataFrame) -> dict:
    amount_col = get_current_amount_col(bs_df)

    total_assets = extract_value(bs_df, TOTAL_ASSETS_ALIASES, amount_col=amount_col)
    total_liabilities = extract_value(bs_df, TOTAL_LIABILITIES_ALIASES, amount_col=amount_col)
    total_equity = extract_value(bs_df, TOTAL_EQUITY_ALIASES, amount_col=amount_col)
    net_assets = extract_value(bs_df, NET_ASSETS_ALIASES, amount_col=amount_col)

    missing = []
    if total_assets is None:
        missing.append("total_assets")
        total_assets = 0.0
    if total_liabilities is None:
        missing.append("total_liabilities")
        total_liabilities = 0.0
    if total_equity is None:
        missing.append("total_equity")
        total_equity = 0.0
    if net_assets is None:
        net_assets = total_assets - total_liabilities

    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "net_assets": net_assets,
        "equation_diff": round(total_assets - (total_liabilities + total_equity), 2),
        "missing": missing,
        "amount_col": amount_col,
    }