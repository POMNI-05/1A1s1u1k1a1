# v1/downloader.py
"""
Selenium download layer for V1.

Keep this file only responsible for Xero UI download. 
Cleaning, tax logic and workbook construction should 
    remain in cleaner.py / workpaper_builder.py.

Comment: give up on trying to abstract the selenium layer, 
    Xero's UI is too volatile and brittle for that to be effective.
"""

from __future__ import annotations

import logging
import os
import shutil
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import (
    BS_RAW_PATH,
    DOWNLOAD_DIR,
    DOWNLOAD_WAIT,
    HEADLESS,
    PL_RAW_PATH,
    REPORT_END_DATE,
    XERO_EMAIL,
    XERO_PASSWORD,
)

logger = logging.getLogger(__name__)


def build_driver():
    options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    options.add_experimental_option("prefs", prefs)
    if HEADLESS:
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.maximize_window()
    return driver


def wait_for_download(timeout: int = DOWNLOAD_WAIT) -> str:
    logger.info("Waiting for Xero Excel download...")
    before = set(os.listdir(DOWNLOAD_DIR)) if os.path.exists(DOWNLOAD_DIR) else set()
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith(".xlsx") and not f.endswith(".crdownload")]
        new_files = [f for f in files if f not in before]
        candidates = new_files or files
        if candidates:
            candidates.sort(key=lambda f: os.path.getmtime(os.path.join(DOWNLOAD_DIR, f)), reverse=True)
            return os.path.join(DOWNLOAD_DIR, candidates[0])
        time.sleep(1)

    raise TimeoutError(f"Download did not complete within {timeout} seconds.")


def login(driver):
    if not XERO_EMAIL or not XERO_PASSWORD:
        raise ValueError("XERO_EMAIL and XERO_PASSWORD must be set when USE_SELENIUM=True.")

    logger.info("Navigating to Xero login")
    driver.get("https://login.xero.com/")
    wait = WebDriverWait(driver, 30)

    email_field = wait.until(EC.presence_of_element_located((By.ID, "email")))
    email_field.clear()
    email_field.send_keys(XERO_EMAIL)
    driver.find_element(By.ID, "submitButton").click()

    password_field = wait.until(EC.presence_of_element_located((By.ID, "password")))
    password_field.clear()
    password_field.send_keys(XERO_PASSWORD)
    driver.find_element(By.ID, "submitButton").click()

    logger.info("Complete MFA manually if prompted.")
    WebDriverWait(driver, 120).until(lambda d: "xero.com" in d.current_url.lower())


def open_report(driver, report_type: str):
    if report_type == "PL":
        url = "https://go.xero.com/Reports/ProfitAndLoss.aspx"
    elif report_type == "BS":
        url = "https://go.xero.com/Reports/BalanceSheet.aspx"
    else:
        raise ValueError("report_type must be 'PL' or 'BS'.")

    logger.info("Opening report %s", report_type)
    driver.get(url)
    time.sleep(5)


def verify_report_settings(driver):
    """Best-effort setting check. Xero UI selectors change often, so keep this defensive."""
    wait = WebDriverWait(driver, 15)
    try:
        date_fields = driver.find_elements(By.CSS_SELECTOR, "input")
        for field in date_fields:
            value = field.get_attribute("value") or ""
            if "Jun" in value or "June" in value or "202" in value:
                logger.info("Report date field currently shows: %s", value)
                break
        logger.info("Expected report end date: %s", REPORT_END_DATE)
    except Exception as exc:
        logger.warning("Could not verify report date settings: %s", exc)

    try:
        update_buttons = driver.find_elements(By.XPATH, "//button[contains(., 'Update')]")
        if update_buttons:
            wait.until(EC.element_to_be_clickable(update_buttons[0])).click()
            time.sleep(4)
    except Exception as exc:
        logger.warning("Could not click Update button: %s", exc)


def export_as_excel(driver):
    wait = WebDriverWait(driver, 30)
    logger.info("Exporting report as Excel")

    export_candidates = [
        (By.XPATH, "//button[contains(., 'Export')]") ,
        (By.XPATH, "//*[contains(text(), 'Export')]") ,
    ]

    export_btn = None
    for locator in export_candidates:
        try:
            export_btn = wait.until(EC.element_to_be_clickable(locator))
            break
        except Exception:
            continue

    if export_btn is None:
        raise RuntimeError("Could not find Xero Export button.")

    export_btn.click()
    time.sleep(1)

    excel_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Excel') or contains(text(), 'XLSX')]") ))
    excel_option.click()


def download_report(report_type: str):
    dest_path = PL_RAW_PATH if report_type == "PL" else BS_RAW_PATH if report_type == "BS" else None
    if dest_path is None:
        raise ValueError("report_type must be 'PL' or 'BS'.")

    driver = build_driver()
    try:
        login(driver)
        open_report(driver, report_type)
        verify_report_settings(driver)
        export_as_excel(driver)
        downloaded = wait_for_download()
        shutil.move(downloaded, dest_path)
        logger.info("%s report saved to %s", report_type, dest_path)
    finally:
        driver.quit()
