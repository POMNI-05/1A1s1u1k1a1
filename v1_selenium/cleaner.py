# v1_selenium/cleaner.py
# For now: preserve raw Xero files.
# Do NOT restructure, clean, rename, or alter columns yet.

import pandas as pd
import logging
from config import PL_RAW_PATH, BS_RAW_PATH

logger = logging.getLogger(__name__)


def load_raw_reports():
    """
    Load the original Xero-exported Excel files as raw DataFrames.

    We intentionally do not clean/restructure here because:
    - Xero export layout is already useful for review
    - accountant needs audit trail
    - reconciliation should be built separately
    """

    logger.info(f"Loading raw P&L from {PL_RAW_PATH}")
    raw_pl_df = pd.read_excel(PL_RAW_PATH, header=None)

    logger.info(f"Loading raw Balance Sheet from {BS_RAW_PATH}")
    raw_bs_df = pd.read_excel(BS_RAW_PATH, header=None)

    return raw_pl_df, raw_bs_df


def load_clean_reports():
    """
    Temporary compatibility function.

    For now, clean = raw.
    Later we can add proper extraction/mapping without destroying the raw sheets.
    """

    logger.info("Using raw reports as working data for now")
    return load_raw_reports()

# # v1_selenium/cleaner.py

# import pandas as pd
# import logging
# from config import PL_RAW_PATH, BS_RAW_PATH

# logger = logging.getLogger(__name__)


# def find_data_start_row(filepath: str) -> int:
#     """
#     Scan the raw Excel and find which row the actual data table begins.
#     Xero exports typically have junk rows before headers.
#     We look for the row containing 'Account' or common header keywords.
#     """
#     preview = pd.read_excel(filepath, header=None, nrows=20)

#     for i, row in preview.iterrows():
#         row_values = [str(x).lower() for x in row.tolist()]

#         if any(kw in val for val in row_values for kw in ["account", "description"]):
#             logger.info(f"Data starts at row {i} in {filepath}")
#             return i

#     logger.warning("Could not detect header row, defaulting to row 0")
#     return 0


# def clean_amount_column(series: pd.Series) -> pd.Series:
#     """
#     Convert messy amount strings to float.
#     Handles: '$1,234.56', '(1,234.56)', '-', '', NaN
#     Brackets mean negative in accounting notation.
#     """
#     s = series.astype(str).str.strip()
#     s = s.str.replace(r'[\$,]', '', regex=True)   # remove $ and commas
#     s = s.str.replace(r'^\((.+)\)$', r'-\1', regex=True)  # (1234) → -1234
#     s = s.replace({'-': '0', '': '0', 'nan': '0'})
#     return pd.to_numeric(s, errors='coerce').fillna(0.0)


# def standardise_account_names(series: pd.Series) -> pd.Series:
#     """Strip whitespace and normalise casing on account name column."""
#     return series.astype(str).str.strip().str.title()


# def validate_totals(df: pd.DataFrame, amount_col: str, label: str):
#     """
#     Basic sanity check: warn if any subtotal rows don't add up.
#     Xero exports often include a 'Total' row — we verify it roughly matches.
#     """
#     total_rows = df[df.iloc[:, 0].astype(str).str.lower().str.startswith("total")]
#     if total_rows.empty:
#         logger.warning(f"{label}: No 'Total' rows found to validate.")
#         return
#     logger.info(f"{label}: Found {len(total_rows)} total row(s) — manual review recommended.")


# def clean_report(filepath: str, report_label: str) -> pd.DataFrame:
#     """
#     Master cleaning function for one report (PL or BS).
#     Returns a clean DataFrame ready for reconciliation.
#     """
#     logger.info(f"Cleaning {report_label} from {filepath}...")

#     start_row = find_data_start_row(filepath)

#     df = pd.read_excel(filepath, header=start_row)

#     df.dropna(how="all", inplace=True)
#     df.dropna(axis=1, how="all", inplace=True)
#     df.reset_index(drop=True, inplace=True)

#     # Standardise first column as account/description names
#     first_col = df.columns[0]
#     df[first_col] = standardise_account_names(df[first_col])

#     # Clean all columns except first column as potential amount columns
#     for col in df.columns[1:]:
#         df[col] = clean_amount_column(df[col])

#     validate_totals(df, df.columns[1], report_label)

#     logger.info(f"✓ {report_label} cleaned — {len(df)} rows")
#     return df


# def load_clean_reports():
#     """
#     Load and clean both Xero reports.
#     """
#     pl_df = clean_report(PL_RAW_PATH, "Profit and Loss")
#     bs_df = clean_report(BS_RAW_PATH, "Balance Sheet")
#     return pl_df, bs_df