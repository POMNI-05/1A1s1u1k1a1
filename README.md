# Tax Workpaper Generator

## First-time setup

1. Install Python 3.11 or 3.12.
2. Unzip this folder.
3. Double-click `run_app.bat`.
4. Wait for the browser app to open.
5. Upload the Xero Excel workbook(s).
6. Click Generate workpaper.
7. Download the generated Excel file.

## Notes

- VS Code is not required.
- Do not close the command window while using the app.
- If the app does not open automatically, copy the local URL shown in the command window into Chrome.
- Xero automatic download is not required for normal use. Upload exported Excel reports manually.

**PL / BS -> Tax return - automation project introduction**:
Automated tax workpaper pipeline for Australian accounting practices


This project automatically prepares working draft for tax return result, given two Xero exported BS and P&L excel forms. 

- The system reads Xero P&L and Balance Sheet exports, labels accounts against ATO ITR rules, and generates a formatted Excel working paper with tax reconciliation (Item 7), balance sheet checks, and review flags ready for manual check.

- The output will generate a new excel file that contains three sheets, as first two is just the original forms, the third one will annotate each row of account entry mapping each account to the relevant ATO ITR reference (Item 6 / Item 7), therefore calculate the taxable income and amount.

**What it does**

1. Loads raw Xero Excel exports (P&L and Balance Sheet)
2. Cleans and parses the reports — detects header rows, amount columns, and row types automatically
3. Labels each account line against ATO ITR references (6C, 7W, 7F, etc.)
4. Builds a tax reconciliation working paper:
- Accounting profit → taxable income (Item 7 adjustments)
- Auto add-backs for book depreciation, entertainment, R&D
- Manual adjustment inputs via config.py
- Tax payable calculation at 25% or 30% company rate

5. Writes a formatted Excel workbook with:
- Raw Xero sheets (preserved, untouched)
- Reconciliation sheet with labelled P&L and BS side-by-side
- Tax Reconciliation table
- Balance Sheet equation checks
- Carry Forward Losses and R&D Breakdown input tables
- Review Items flagged for accountant attention
