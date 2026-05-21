# Tax Workpaper Generator

Automated tax workpaper pipeline for Australian accounting practices.

This tool generates a structured tax workpaper from Profit & Loss and Balance Sheet reports. 

It maps account lines to ATO ITR references and produces a reconciliation from accounting profit to taxable income, ready for review.

---

## Project scope

This tool is designed to generate a working draft for tax return preparation. :P

All outputs should be reviewed by a qualified accountant before use.
<img width="613" height="708" alt="image" src="https://github.com/user-attachments/assets/13838326-f0c9-4524-8890-6b14128d03de" />

## What this tool does

- Loads 2 raw Xero Excel exports (P&L and Balance Sheet)  
- Cleans and parses reports (detects headers, amount columns, and row types automatically)  
- Labels each account line against ATO ITR references (e.g. 6C, 7W, 7F)  
- Builds a tax reconciliation:
  - Accounting profit → taxable income (Item 7 adjustments)  
  - Automatic add-backs (depreciation, entertainment, R&D)  
      - If needed, manual adjustments via `config.py`  
  - Tax payable calculation (25% / 30% company rate)  

---
## Output

The tool generates a formatted Excel workbook containing:

1. Two Original Reports (preserved and unchanged)
2. Reconciliation sheet with labelled P&L and Balance Sheet
3. Tax reconciliation table (Item 7) and also: 
- Balance sheet equation checks  
- Carry-forward losses and R&D input tables (where needed) 
- Review items flagged for accountant attention  

---
## How to use

1. Export P&L and Balance Sheet reports from Xero (Excel format)  
2. Upload the Excel file(s) in the web interface  
3. Click **Generate Workpaper**  
4. Download the generated Excel file


## First-time setup

1. Install Python 3.11 or 3.12  
2. Unzip this folder  
3. Double-click `run_app.bat`  
4. Wait for the browser app to open

---
## Notes for setting up

- VS Code is not required  
- Do not close the command window while the app is running  
- If the browser does not open automatically, copy the local URL into Chrome  
- Xero API integration is not required — manual Excel export is sufficient  
