# v1_selenium/reconciler.py

import pandas as pd
import logging
from config import SHEET_PL, SHEET_BS, SHEET_RECONCILIATION, OUTPUT_PATH

logger = logging.getLogger(__name__)


def extract_value(df: pd.DataFrame, account_keyword: str, amount_col_index: int = 1) -> float:
    """
    Find a row by keyword in account name column and return its amount.
    
    Example:
        extract_value(pl_df, "total revenue")  →  155000.0
        extract_value(pl_df, "net profit")     →  42000.0
    """
    mask = df.iloc[:, 0].astype(str).str.lower().str.contains(account_keyword.lower())
    matches = df[mask]
    if matches.empty:
        logger.warning(f"Could not find '{account_keyword}' in DataFrame")
        return 0.0
    value = matches.iloc[0, amount_col_index]
    logger.info(f"  '{account_keyword}' → {value:,.2f}")
    return float(value)


def check_accounting_equation(total_assets: float, total_liabilities: float, equity: float) -> bool:
    """
    Fundamental accounting equation: Assets = Liabilities + Equity
    Flags if mismatch exceeds $1 tolerance (rounding allowed).

    Example:
        Assets: 500,000
        Liabilities: 300,000
        Equity: 200,000
        500,000 == 300,000 + 200,000  →  ✓ PASS
    """
    expected = total_liabilities + equity
    diff = abs(total_assets - expected)
    if diff > 1.0:
        logger.error(f"⚠ Accounting equation MISMATCH: Assets={total_assets:,.2f}, "
                     f"Liabilities + Equity={expected:,.2f}, Diff={diff:,.2f}")
        return False
    logger.info(f"✓ Accounting equation balanced. Assets={total_assets:,.2f}")
    return True


def build_reconciliation(pl_df: pd.DataFrame, bs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Extract key figures from both reports and build reconciliation table.

    Output looks like:
    ┌─────────────────────────┬────────────┬──────────┐
    │ Item                    │ Amount     │ Flag     │
    ├─────────────────────────┼────────────┼──────────┤
    │ Total Revenue           │ 155,000    │ ✓        │
    │ Total Expenses          │ 113,000    │ ✓        │
    │ Net Profit              │  42,000    │ ✓        │
    │ Total Assets            │ 500,000    │ ✓        │
    │ Total Liabilities       │ 300,000    │ ✓        │
    │ Equity                  │ 200,000    │ ✓        │
    │ Accounting Eq. Check    │       0    │ ✓ PASS   │
    └─────────────────────────┴────────────┴──────────┘
    """
    logger.info("Building reconciliation sheet...")

    # ── Extract from P&L ──────────────────────────────────────
    total_revenue   = extract_value(pl_df, "total revenue")
    total_expenses  = extract_value(pl_df, "total expenses")
    net_profit      = extract_value(pl_df, "net profit")

    # ── Extract from Balance Sheet ────────────────────────────
    total_assets      = extract_value(bs_df, "total assets")
    total_liabilities = extract_value(bs_df, "total liabilities")
    equity            = extract_value(bs_df, "total equity")

    # ── Accounting equation check ─────────────────────────────
    eq_ok = check_accounting_equation(total_assets, total_liabilities, equity)
    eq_flag = "✓ PASS" if eq_ok else "⚠ MISMATCH — REVIEW"

    # ── Build output table ────────────────────────────────────
    rows = [
        {"Item": "── Profit & Loss ──",        "Amount ($)": "",           "Status": ""},
        {"Item": "Total Revenue",               "Amount ($)": total_revenue,   "Status": "✓"},
        {"Item": "Total Expenses",              "Amount ($)": total_expenses,  "Status": "✓"},
        {"Item": "Net Profit / (Loss)",         "Amount ($)": net_profit,      "Status": "✓" if net_profit >= 0 else "⚠ LOSS"},
        {"Item": "",                            "Amount ($)": "",           "Status": ""},
        {"Item": "── Balance Sheet ──",         "Amount ($)": "",           "Status": ""},
        {"Item": "Total Assets",                "Amount ($)": total_assets,    "Status": "✓"},
        {"Item": "Total Liabilities",           "Amount ($)": total_liabilities,"Status": "✓"},
        {"Item": "Equity",                      "Amount ($)": equity,          "Status": "✓"},
        {"Item": "",                            "Amount ($)": "",           "Status": ""},
        {"Item": "── Checks ──",                "Amount ($)": "",           "Status": ""},
        {"Item": "Accounting Equation (A=L+E)", "Amount ($)": round(total_assets - (total_liabilities + equity), 2), "Status": eq_flag},
    ]

    rec_df = pd.DataFrame(rows)
    logger.info("✓ Reconciliation sheet built.")
    return rec_df


def write_workbook(pl_df: pd.DataFrame, bs_df: pd.DataFrame, rec_df: pd.DataFrame):
    """
    Write all three sheets into one Excel workbook.
    
    Final file structure:
        xero_workpaper_FY2025.xlsx
        ├── Sheet: "Profit and Loss"
        ├── Sheet: "Balance Sheet"
        └── Sheet: "Reconciliation"
    """
    logger.info(f"Writing workbook to {OUTPUT_PATH}...")


    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        raw_pl_df.to_excel(writer, sheet_name="Xero PL Raw", index=False)
        raw_bs_df.to_excel(writer, sheet_name="Xero BS Raw", index=False)
        tax_financial_df.to_excel(writer, sheet_name="Tax Workpaper", index=False)
        tax_rec_df.to_excel(writer, sheet_name="Tax Reconciliation", index=False)
        checks_df.to_excel(writer, sheet_name="Checks", index=False)

    logger.info(f"✓ Workbook saved: {OUTPUT_PATH}")