from utils import setup_logging, ensure_dirs
from cleaner import load_clean_reports
from reconciler import build_reconciliation, write_workbook
from utils import format_workbook

setup_logging()
ensure_dirs()

pl_df, bs_df = load_clean_reports()
rec_df = build_reconciliation(pl_df, bs_df)
write_workbook(pl_df, bs_df, rec_df)
format_workbook()

print("Local Excel test complete.")