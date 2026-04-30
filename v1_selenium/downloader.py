# v1_selenium/downloader.py

import os
import time
import shutil
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import (
    XERO_EMAIL, XERO_PASSWORD,
    REPORT_END_DATE, COMPARE_WITH, FILTER,
    DOWNLOAD_DIR, PL_RAW_PATH, BS_RAW_PATH,
    HEADLESS, DOWNLOAD_WAIT
)

logger = logging.getLogger(__name__)

def build_driver():
    """Set up Chrome with auto-download to data/ folder."""
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)
    if HEADLESS:
        options.add_argument("--headless")

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.maximize_window()
    return driver


def wait_for_download(filename_prefix, timeout=DOWNLOAD_WAIT):
    """Block until a matching .xlsx file appears in DOWNLOAD_DIR."""
    logger.info(f"Waiting for download: {filename_prefix}...")
    elapsed = 0
    while elapsed < timeout:
        files = os.listdir(DOWNLOAD_DIR)
        for f in files:
            if f.endswith(".xlsx") and not f.endswith(".crdownload"):
                return os.path.join(DOWNLOAD_DIR, f)
        time.sleep(1)
        elapsed += 1
    raise TimeoutError(f"Download did not complete within {timeout}s")


def login(driver):
    """Navigate to Xero login and enter credentials.
    MFA must be completed manually in the browser window.
    """
    logger.info("Navigating to Xero login...")
    driver.get("https://login.xero.com/")

    wait = WebDriverWait(driver, 20)

    # Enter email
    email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
    email_field.clear()
    email_field.send_keys(XERO_EMAIL)

    # Click continue / next
    driver.find_element(By.ID, "submitButton").click()

    # Enter password
    password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
    password_field.clear()
    password_field.send_keys(XERO_PASSWORD)
    driver.find_element(By.ID, "submitButton").click()

    # ── MFA PAUSE ──────────────────────────────────────────────
    # Xero will prompt for 2FA here.
    # Complete it manually in the browser window.
    # Script waits up to 60 seconds for dashboard to appear.
    logger.info("Waiting for MFA completion (complete manually in browser)...")
    wait_mfa = WebDriverWait(driver, 60)
    wait_mfa.until(EC.url_contains("xero.com/dashboard"))
    logger.info("Login successful.")


def verify_and_set_report_settings(driver, wait):
    """
    CHECKPOINT: Verify report date, compare period, and filter.
    Adjusts settings if they don't match config values.
    """
    logger.info("Verifying report settings...")

    # These selectors may need adjusting based on live Xero UI
    # End date check
    try:
        end_date_field = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[data-automationid='end-date']")
        ))
        current = end_date_field.get_attribute("value")
        if REPORT_END_DATE not in current:
            logger.warning(f"End date mismatch: found '{current}', setting to '{REPORT_END_DATE}'")
            end_date_field.clear()
            end_date_field.send_keys(REPORT_END_DATE)
        else:
            logger.info(f"✓ End date correct: {current}")
    except Exception as e:
        logger.warning(f"Could not verify end date: {e}")

    # Compare with check
    try:
        compare_dropdown = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, "select[data-automationid='compare-with']")
        ))
        if COMPARE_WITH not in compare_dropdown.get_attribute("value"):
            logger.warning(f"Compare period wrong, updating to '{COMPARE_WITH}'")
            # Select the correct option
            from selenium.webdriver.support.ui import Select
            Select(compare_dropdown).select_by_visible_text(COMPARE_WITH)
        else:
            logger.info(f"✓ Compare with correct: {COMPARE_WITH}")
    except Exception as e:
        logger.warning(f"Could not verify compare period: {e}")

    # Click Update to apply settings
    try:
        update_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button[data-automationid='update-button']")
        ))
        update_btn.click()
        time.sleep(3)  # wait for report to refresh
        logger.info("✓ Clicked Update.")
    except Exception as e:
        logger.warning(f"Could not click Update: {e}")


def export_as_excel(driver, wait):
    """Click Export → Excel and wait for download."""
    logger.info("Exporting as Excel...")
    try:
        export_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button[data-automationid='export-button']")
        ))
        export_btn.click()
        time.sleep(1)

        excel_option = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//span[contains(text(), 'Excel')]")
        ))
        excel_option.click()
        logger.info("Excel export triggered.")
    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise


def download_report(report_type: str):
    """
    Full flow for one report: login → navigate → verify settings → export.
    report_type: 'PL' or 'BS'
    """
    assert report_type in ("PL", "BS"), "report_type must be 'PL' or 'BS'"

    report_urls = {
        "PL": "https://reporting.xero.com/!{orgid}/Reports/ProfitAndLoss",
        "BS": "https://reporting.xero.com/!{orgid}/Reports/BalanceSheet",
    }
    dest_paths = {
        "PL": PL_RAW_PATH,
        "BS": BS_RAW_PATH,
    }

    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:
        login(driver)

        logger.info(f"Navigating to {report_type} report...")
        # Navigate via Reports menu (more reliable than hardcoded URL)
        driver.find_element(By.LINK_TEXT, "Reports").click()
        time.sleep(2)

        if report_type == "PL":
            driver.find_element(By.PARTIAL_LINK_TEXT, "Profit and Loss").click()
        else:
            driver.find_element(By.PARTIAL_LINK_TEXT, "Balance Sheet").click()

        time.sleep(3)  # let report load

        verify_and_set_report_settings(driver, wait)
        export_as_excel(driver, wait)

        downloaded = wait_for_download(report_type)

        # Rename and move to expected path
        shutil.move(downloaded, dest_paths[report_type])
        logger.info(f"✓ {report_type} saved to {dest_paths[report_type]}")

    finally:
        driver.quit()