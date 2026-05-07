import logging
import pandas as pd

from itr_rules import WORKSHEET_2, validate_adjustment_label
from config import TAX_RATE, TAX_ADJUSTMENTS
from cleaner import load_clean_reports
from reconciler import extract_pl_values

logger = logging.getLogger(__name__)


def build_tax_reconciliation(raw_pl_df: pd.DataFrame, raw_bs_df: pd.DataFrame) -> pd.DataFrame:
    logger.info("Building simplified tax reconciliation...")

    clean_pl_df, clean_bs_df = load_clean_reports()

    pl_vals = extract_pl_values(clean_pl_df)
    accounting_profit = pl_vals["net_profit"]

    rows = []

    rows.append({
        "Section": "Base",
        "Description": "Accounting Profit / (Loss) per Xero P&L",
        "Amount": accounting_profit,
        "Direction": "Base",
        "ITR Ref": "7T",
        "Logic": "Starting point from Xero P&L Net Profit / Loss.",
        "Source": "Xero Profit and Loss",
    })

    taxable_income = accounting_profit

    for category, adjustments in TAX_ADJUSTMENTS.items():
        rule = WORKSHEET_2.get(category)

        if rule is None:
            logger.warning(f"Unknown adjustment category skipped: {category}")
            continue

        itr_label = rule["label"]
        direction = rule["direction"]
        heading = rule["heading"]

        if not adjustments:
            continue

        for adj in adjustments:
            description = adj.get("description", heading)
            amount = float(adj.get("amount", 0.0))

            validate_adjustment_label({
                "description": description,
                "itr_label": itr_label,
            })

            if direction == "add":
                taxable_income += amount
                logic = "Added back because this category increases taxable income."
            elif direction == "subtract":
                taxable_income -= amount
                logic = "Subtracted because this category reduces taxable income."
            else:
                logic = "No direction applied."

            rows.append({
                "Section": "Add back" if direction == "add" else "Subtract",
                "Description": description,
                "Amount": amount,
                "Direction": direction,
                "ITR Ref": itr_label,
                "Logic": logic,
                "Source": adj.get("source", "Manual config"),
            })

    tax_payable = max(taxable_income, 0) * TAX_RATE

    rows.append({
        "Section": "Result",
        "Description": "Taxable Income / (Loss)",
        "Amount": taxable_income,
        "Direction": "Calculated",
        "ITR Ref": "",
        "Logic": "Accounting profit plus add-backs less deductions.",
        "Source": "Calculated",
    })

    rows.append({
        "Section": "Result",
        "Description": f"Estimated Tax Payable at {TAX_RATE:.0%}",
        "Amount": tax_payable,
        "Direction": "Calculated",
        "ITR Ref": "",
        "Logic": "Only applies if taxable income is positive.",
        "Source": "Calculated",
    })

    return pd.DataFrame(rows)