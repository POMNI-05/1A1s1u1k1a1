# v1_selenium/reconciler.py

import logging
import pandas as pd

from cleaner import (
    extract_value,
    clean_amount,
    _detect_amount_col,
    NET_PROFIT_ALIASES,
    TOTAL_ASSETS_ALIASES,
    TOTAL_LIABILITIES_ALIASES,
)
from config import TAX_RATE, OUTPUT_PATH, SHEET_RECONCILIATION

logger = logging.getLogger(__name__)


# ── 从P&L提取关键数字 ─────────────────────────────────────────────────────────
# 原版：直接 extract_value(df, "net profit")，一次匹配失败就返回0
# 新版：用alias列表，提取失败给出明确警告，不静默返回0
def extract_pl_values(pl_df: pd.DataFrame) -> dict:
    amount_col = _detect_amount_col(pl_df)
    logger.info(f"P&L amount column detected: '{amount_col}'")

    net_profit = extract_value(pl_df, NET_PROFIT_ALIASES, amount_col)

    if net_profit is None:
        logger.warning("⚠ Net profit not found by alias — attempting last-row fallback")
        # fallback：找最后一个数值非零行
        name_col = pl_df.columns[0]
        numeric_vals = pl_df[amount_col].apply(clean_amount)
        nonzero = pl_df[numeric_vals != 0.0]
        if not nonzero.empty:
            last = nonzero.iloc[-1]
            net_profit = clean_amount(last[amount_col])
            logger.warning(f"  Fallback used: row '{last[name_col]}' = {net_profit:,.2f}")
        else:
            net_profit = 0.0
            logger.error("  No numeric rows found in P&L — accounting_profit = 0.0")

    logger.info(f"Net profit (accounting): {net_profit:,.2f}")
    return {"net_profit": net_profit}


# ── 从BS提取关键数字 ──────────────────────────────────────────────────────────
def extract_bs_values(bs_df: pd.DataFrame) -> dict:
    amount_col = _detect_amount_col(bs_df)
    logger.info(f"BS amount column detected: '{amount_col}'")

    total_assets = extract_value(bs_df, TOTAL_ASSETS_ALIASES, amount_col)
    total_liabilities = extract_value(bs_df, TOTAL_LIABILITIES_ALIASES, amount_col)

    if total_assets is None:
        logger.warning("⚠ Total assets not found")
        total_assets = 0.0
    if total_liabilities is None:
        logger.warning("⚠ Total liabilities not found")
        total_liabilities = 0.0

    logger.info(f"Total assets: {total_assets:,.2f} | Total liabilities: {total_liabilities:,.2f}")
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_assets": total_assets - total_liabilities,
    }


# ── 构建对账表 ────────────────────────────────────────────────────────────────
# 原版：这个函数只在test_local_excel.py里用，实际workpaper逻辑在workpaper_builder.py
# 保留作为轻量版对账（不含tax adjustments），供测试用
def build_reconciliation(pl_df: pd.DataFrame, bs_df: pd.DataFrame) -> pd.DataFrame:
    pl_vals = extract_pl_values(pl_df)
    bs_vals = extract_bs_values(bs_df)

    net_profit = pl_vals["net_profit"]
    tax_payable = max(net_profit, 0) * TAX_RATE

    rows = [
        {"Description": "Net Profit (Accounting)",      "Amount": net_profit},
        {"Description": f"Tax Payable at {TAX_RATE:.0%}", "Amount": tax_payable},
        {"Description": "Net Assets (BS check)",         "Amount": bs_vals["net_assets"]},
    ]
    return pd.DataFrame(rows)


# ── write_workbook (test_local_excel.py用) ────────────────────────────────────
# 原版：write_workbook在这里，但main.py用的是write_workbook.py里的那个
# 保留作为测试用的简化版
def write_workbook(pl_df: pd.DataFrame, bs_df: pd.DataFrame, rec_df: pd.DataFrame):
    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        pl_df.to_excel(writer, sheet_name="Xero PL Raw", index=False, header=False)
        bs_df.to_excel(writer, sheet_name="Xero BS Raw", index=False, header=False)
        rec_df.to_excel(writer, sheet_name=SHEET_RECONCILIATION, index=False)
    logger.info(f"Test workbook written: {OUTPUT_PATH}")


# # v1_selenium/reconciler.py

# import pandas as pd
# import logging
# from config import SHEET_PL, SHEET_BS, SHEET_RECONCILIATION, OUTPUT_PATH

# logger = logging.getLogger(__name__)


# def extract_value(df: pd.DataFrame, account_keyword: str, amount_col_index: int = 1) -> float:
#     """
#     Find a row by keyword in account name column and return its amount.
    
#     Example:
#         extract_value(pl_df, "total revenue")  →  155000.0
#         extract_value(pl_df, "net profit")     →  42000.0
#     """
#     mask = df.iloc[:, 0].astype(str).str.lower().str.contains(account_keyword.lower())
#     matches = df[mask]
#     if matches.empty:
#         logger.warning(f"Could not find '{account_keyword}' in DataFrame")
#         return 0.0
#     value = matches.iloc[0, amount_col_index]
#     logger.info(f"  '{account_keyword}' → {value:,.2f}")
#     return float(value)


# def check_accounting_equation(total_assets: float, total_liabilities: float, equity: float) -> bool:
#     """
#     Fundamental accounting equation: Assets = Liabilities + Equity
#     Flags if mismatch exceeds $1 tolerance (rounding allowed).

#     Example:
#         Assets: 500,000
#         Liabilities: 300,000
#         Equity: 200,000
#         500,000 == 300,000 + 200,000  →  ✓ PASS
#     """
#     expected = total_liabilities + equity
#     diff = abs(total_assets - expected)
#     if diff > 1.0:
#         logger.error(f"⚠ Accounting equation MISMATCH: Assets={total_assets:,.2f}, "
#                      f"Liabilities + Equity={expected:,.2f}, Diff={diff:,.2f}")
#         return False
#     logger.info(f"✓ Accounting equation balanced. Assets={total_assets:,.2f}")
#     return True


# def build_reconciliation(pl_df: pd.DataFrame, bs_df: pd.DataFrame) -> pd.DataFrame:
#     """
#     Extract key figures from both reports and build reconciliation table.

#     Output looks like:
#     ┌─────────────────────────┬────────────┬──────────┐
#     │ Item                    │ Amount     │ Flag     │
#     ├─────────────────────────┼────────────┼──────────┤
#     │ Total Revenue           │ 155,000    │ ✓        │
#     │ Total Expenses          │ 113,000    │ ✓        │
#     │ Net Profit              │  42,000    │ ✓        │
#     │ Total Assets            │ 500,000    │ ✓        │
#     │ Total Liabilities       │ 300,000    │ ✓        │
#     │ Equity                  │ 200,000    │ ✓        │
#     │ Accounting Eq. Check    │       0    │ ✓ PASS   │
#     └─────────────────────────┴────────────┴──────────┘
#     """
#     logger.info("Building reconciliation sheet...")

#     # ── Extract from P&L ──────────────────────────────────────
#     total_revenue   = extract_value(pl_df, "total revenue")
#     total_expenses  = extract_value(pl_df, "total expenses")
#     net_profit      = extract_value(pl_df, "net profit")

#     # ── Extract from Balance Sheet ────────────────────────────
#     total_assets      = extract_value(bs_df, "total assets")
#     total_liabilities = extract_value(bs_df, "total liabilities")
#     equity            = extract_value(bs_df, "total equity")

#     # ── Accounting equation check ─────────────────────────────
#     eq_ok = check_accounting_equation(total_assets, total_liabilities, equity)
#     eq_flag = "✓ PASS" if eq_ok else "⚠ MISMATCH — REVIEW"

#     # ── Build output table ────────────────────────────────────
#     rows = [
#         {"Item": "── Profit & Loss ──",        "Amount ($)": "",           "Status": ""},
#         {"Item": "Total Revenue",               "Amount ($)": total_revenue,   "Status": "✓"},
#         {"Item": "Total Expenses",              "Amount ($)": total_expenses,  "Status": "✓"},
#         {"Item": "Net Profit / (Loss)",         "Amount ($)": net_profit,      "Status": "✓" if net_profit >= 0 else "⚠ LOSS"},
#         {"Item": "",                            "Amount ($)": "",           "Status": ""},
#         {"Item": "── Balance Sheet ──",         "Amount ($)": "",           "Status": ""},
#         {"Item": "Total Assets",                "Amount ($)": total_assets,    "Status": "✓"},
#         {"Item": "Total Liabilities",           "Amount ($)": total_liabilities,"Status": "✓"},
#         {"Item": "Equity",                      "Amount ($)": equity,          "Status": "✓"},
#         {"Item": "",                            "Amount ($)": "",           "Status": ""},
#         {"Item": "── Checks ──",                "Amount ($)": "",           "Status": ""},
#         {"Item": "Accounting Equation (A=L+E)", "Amount ($)": round(total_assets - (total_liabilities + equity), 2), "Status": eq_flag},
#     ]

#     rec_df = pd.DataFrame(rows)
#     logger.info("✓ Reconciliation sheet built.")
#     return rec_df


# def write_workbook(pl_df: pd.DataFrame, bs_df: pd.DataFrame, rec_df: pd.DataFrame):
#     """
#     Write all three sheets into one Excel workbook.
    
#     Final file structure:
#         xero_workpaper_FY2025.xlsx
#         ├── Sheet: "Profit and Loss"
#         ├── Sheet: "Balance Sheet"
#         └── Sheet: "Reconciliation"
#     """
#     logger.info(f"Writing workbook to {OUTPUT_PATH}...")


#     with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
#         raw_pl_df.to_excel(writer, sheet_name="Xero PL Raw", index=False)
#         raw_bs_df.to_excel(writer, sheet_name="Xero BS Raw", index=False)
#         tax_financial_df.to_excel(writer, sheet_name="Tax Workpaper", index=False)
#         tax_rec_df.to_excel(writer, sheet_name="Tax Reconciliation", index=False)
#         checks_df.to_excel(writer, sheet_name="Checks", index=False)

#     logger.info(f"✓ Workbook saved: {OUTPUT_PATH}")