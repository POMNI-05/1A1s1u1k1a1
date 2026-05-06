# v1_selenium/workpaper_builder.py

import logging
import pandas as pd

from config import TAX_RATE, RD_ELIGIBLE, RD_OFFSET_RATE, TAX_ADJUSTMENTS
from cleaner import _detect_amount_col, NET_PROFIT_ALIASES
from reconciler import extract_pl_values

logger = logging.getLogger(__name__)


def build_workpaper(raw_pl_df: pd.DataFrame, raw_bs_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger.info("Building tax workpaper...")

    # ── 原版：accounting_profit = 0.0（TODO未填）─────────────────────────────
    # 新版：从P&L里真正提取，提取失败给出明确的FAIL check而不是静默返回零
    pl_vals = extract_pl_values(raw_pl_df)
    accounting_profit = pl_vals["net_profit"]
    profit_extracted = accounting_profit != 0.0   # 用于checks

    source_note = (
        "Extracted from P&L via alias match"
        if profit_extracted
        else "⚠ Could not extract — check P&L format"
    )
    logger.info(f"Accounting profit: {accounting_profit:,.2f} | {source_note}")

    # ── 对账行构建（逻辑和原版相同，只是accounting_profit现在有真实值）────────
    rows = []
    rows.append({
        "Section":     "Base",
        "Description": "Accounting Profit / (Loss) Before Tax",
        "Amount":      accounting_profit,
        "ITR Ref":     "7T",
        "Source":      source_note,
    })

    taxable_income = accounting_profit

    # Tax adjustments — 原版逻辑保持不变
    for category, adjustments in TAX_ADJUSTMENTS.items():
        for adj in adjustments:
            description = adj.get("description", category)
            amount      = float(adj.get("amount", 0))
            itr_label   = adj.get("itr_label", "")
            direction   = adj.get("direction", "")

            if direction == "add":
                taxable_income += amount
            elif direction == "subtract":
                taxable_income -= amount

            rows.append({
                "Section":     "Add back" if direction == "add" else "Subtract",
                "Description": description,
                "Amount":      amount,
                "ITR Ref":     itr_label,
                "Source":      adj.get("source", "Manual config"),
            })

    tax_payable = max(taxable_income, 0) * TAX_RATE
    rd_offset   = 0.0  # R&D计算留作后续实现

    rows.extend([
        {
            "Section":     "Result",
            "Description": "Taxable Income / (Loss)",
            "Amount":      taxable_income,
            "ITR Ref":     "",
            "Source":      "Calculated",
        },
        {
            "Section":     "Result",
            "Description": f"Tax Payable at {TAX_RATE:.0%}",
            "Amount":      tax_payable,
            "ITR Ref":     "",
            "Source":      "Calculated",
        },
        {
            "Section":     "Result",
            "Description": f"R&D Offset at {RD_OFFSET_RATE:.1%}",
            "Amount":      rd_offset,
            "ITR Ref":     "",
            "Source":      "Calculated",
        },
        {
            "Section":     "Result",
            "Description": "Tax Payable / (Refund Due)",
            "Amount":      tax_payable - rd_offset,
            "ITR Ref":     "",
            "Source":      "Calculated",
        },
    ])

    tax_rec_df = pd.DataFrame(rows)

    # ── checks_df ─────────────────────────────────────────────────────────────
    # 原版：只有3条check，没有检查accounting_profit是否真正提取成功
    # 新版：加第4条，明确告诉会计师提取是否成功
    checks_df = pd.DataFrame([
        {
            "Check":  "Raw P&L loaded",
            "Status": "✓ PASS" if raw_pl_df is not None and len(raw_pl_df) > 0 else "⚠ FAIL",
            "Value":  f"{len(raw_pl_df)} rows" if raw_pl_df is not None else "N/A",
        },
        {
            "Check":  "Raw Balance Sheet loaded",
            "Status": "✓ PASS" if raw_bs_df is not None and len(raw_bs_df) > 0 else "⚠ FAIL",
            "Value":  f"{len(raw_bs_df)} rows" if raw_bs_df is not None else "N/A",
        },
        {
            "Check":  "Accounting profit extracted",       # 新增
            "Status": "✓ PASS" if profit_extracted else "⚠ FAIL — check P&L format",
            "Value":  f"{accounting_profit:,.2f}",
        },
        {
            "Check":  "Tax reconciliation built",
            "Status": "✓ PASS",
            "Value":  f"{len(rows)} rows",
        },
    ])

    logger.info("✓ Tax workpaper built")
    return tax_rec_df, checks_df

# # v1_selenium/workpaper_builder.py
# # Builds tax reconciliation working papers

# import logging
# import pandas as pd

# from config import TAX_RATE, RD_ELIGIBLE, RD_OFFSET_RATE, TAX_ADJUSTMENTS

# logger = logging.getLogger(__name__)


# def build_workpaper(raw_pl_df, raw_bs_df):
#     """
#     Build tax reconciliation and checks.

#     For now this is a starter version:
#     - uses manual adjustment config
#     - does not yet auto-extract from Xero
#     """

#     logger.info("Building tax workpaper...")

#     accounting_profit = 0.0  # TODO: later extract Net Profit from raw P&L

#     rows = []

#     rows.append({
#         "Section": "Base",
#         "Description": "Accounting Profit / (Loss) Before Tax",
#         "Amount": accounting_profit,
#         "ITR Ref": "7T",
#         "Source": "TODO: extract from Xero P&L",
#     })

#     taxable_income = accounting_profit

#     for category, adjustments in TAX_ADJUSTMENTS.items():
#         for adj in adjustments:
#             description = adj.get("description", category)
#             amount = float(adj.get("amount", 0))
#             itr_label = adj.get("itr_label", "")
#             direction = adj.get("direction", "")

#             if direction == "add":
#                 taxable_income += amount
#             elif direction == "subtract":
#                 taxable_income -= amount

#             rows.append({
#                 "Section": "Add back" if direction == "add" else "Subtract",
#                 "Description": description,
#                 "Amount": amount,
#                 "ITR Ref": itr_label,
#                 "Source": adj.get("source", "Manual config"),
#             })

#     tax_payable = max(taxable_income, 0) * TAX_RATE

#     rd_offset = 0.0
#     if RD_ELIGIBLE:
#         rd_offset = 0.0  # TODO: calculate from R&D spend later

#     refund_or_payable = tax_payable - rd_offset

#     rows.extend([
#         {
#             "Section": "Result",
#             "Description": "Taxable Income / (Loss)",
#             "Amount": taxable_income,
#             "ITR Ref": "",
#             "Source": "Calculated",
#         },
#         {
#             "Section": "Result",
#             "Description": f"Tax Payable at {TAX_RATE:.0%}",
#             "Amount": tax_payable,
#             "ITR Ref": "",
#             "Source": "Calculated",
#         },
#         {
#             "Section": "Result",
#             "Description": f"R&D Offset at {RD_OFFSET_RATE:.1%}",
#             "Amount": rd_offset,
#             "ITR Ref": "",
#             "Source": "Calculated",
#         },
#         {
#             "Section": "Result",
#             "Description": "Tax Payable / (Refund Due)",
#             "Amount": refund_or_payable,
#             "ITR Ref": "",
#             "Source": "Calculated",
#         },
#     ])

#     tax_rec_df = pd.DataFrame(rows)

#     checks_df = pd.DataFrame([
#         {
#             "Check": "Raw P&L loaded",
#             "Status": "✓ PASS" if raw_pl_df is not None and len(raw_pl_df) > 0 else "⚠ FAIL",
#         },
#         {
#             "Check": "Raw Balance Sheet loaded",
#             "Status": "✓ PASS" if raw_bs_df is not None and len(raw_bs_df) > 0 else "⚠ FAIL",
#         },
#         {
#             "Check": "Tax reconciliation built",
#             "Status": "✓ PASS",
#         },
#     ])

#     logger.info("✓ Tax workpaper built")

#     return tax_rec_df, checks_df