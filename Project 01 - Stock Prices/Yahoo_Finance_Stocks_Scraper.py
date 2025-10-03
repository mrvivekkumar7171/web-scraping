#!/usr/bin/env python3
"""
yahoo_most_active_scraper.py

Scrapes "Most Active" stocks from Yahoo Finance.

Features:
- Directly visits https://finance.yahoo.com/most-active for stability
- Maps table columns by header text (robust to column reordering)
- Handles paging until the Next button is disabled (or until pages_limit reached)
- Parses Price, Change, Volume, Market Cap, PE
- Saves to Excel, CSV, and JSON (raw)
- Supports headless mode and basic CLI options

Dependencies:
- selenium
- pandas
- openpyxl (for Excel)
"""

import time
import random
import logging
import argparse
import json
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)

# -------------------------
# Logging configuration
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# -------------------------
# Helpers for parsing
# -------------------------
def _clean_text(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    return s.strip()


def parse_number_with_suffix(s: str) -> Optional[float]:
    """
    Parse numbers like "1.23M", "4,567", "2.1B", "0.45T", "—" etc.
    Returns float value in base units (for volume we keep as raw units unless caller multiplies).
    """
    if not s:
        return None
    s = s.strip().replace(",", "")
    if s in {"-", "—", "N/A", ""}:
        return None
    try:
        # Handle percentages or values with % (used rarely for the change column)
        if s.endswith("%"):
            return float(s[:-1])
        # Suffix handling
        mult = 1.0
        if s.endswith("K"):
            mult = 1e3
            s = s[:-1]
        elif s.endswith("M"):
            mult = 1e6
            s = s[:-1]
        elif s.endswith("B"):
            mult = 1e9
            s = s[:-1]
        elif s.endswith("T"):
            mult = 1e12
            s = s[:-1]
        # handle +/- signs
        s = s.replace("+", "")
        return float(s) * mult
    except ValueError:
        # Last resort: try to parse as float
        try:
            return float(s)
        except Exception:
            return None


def parse_price(s: str) -> Optional[float]:
    # sometimes price contains commas or other chars
    if not s:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return parse_number_with_suffix(s)


def parse_change(s: str) -> Optional[float]:
    # might be like "+1.23" or "-0.45" or "+1.23 (+0.25%)" — we take the first numeric part
    if not s:
        return None
    parts = s.split()
    # prefer the plain numeric token (with + or -)
    for token in parts:
        token = token.strip().replace(",", "")
        if token.endswith("%"):
            token = token[:-1]
        try:
            return float(token.replace("+", ""))
        except Exception:
            continue
    return None


# -------------------------
# Scraper class
# -------------------------
class YahooMostActiveScraper:
    MOST_ACTIVE_URL = "https://finance.yahoo.com/most-active"

    def __init__(self, driver: webdriver.Chrome, wait_timeout: int = 10, polite: bool = True):
        self.driver = driver
        self.wait = WebDriverWait(self.driver, wait_timeout)
        self.data: List[Dict] = []
        self.polite = polite

    def open_page(self, url: str):
        logger.info("Opening URL: %s", url)
        self.driver.get(url)
        self._wait_for_ready_state()
        # small polite wait for dynamic content
        time.sleep(0.5 + random.random() * 0.5)

    def _wait_for_ready_state(self, timeout: int = 10):
        try:
            self.wait.until(lambda d: d.execute_script("return document.readyState === 'complete'"))
        except TimeoutException:
            logger.warning("Page did not reach readyState 'complete' within timeout")

    def _find_table_and_headers(self):
        # wait for table presence
        try:
            table = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        except TimeoutException:
            raise RuntimeError("No table found on the page")
        # find headers
        header_elems = table.find_elements(By.CSS_SELECTOR, "thead th")
        headers = [h.text.strip() for h in header_elems]
        # mapping header name (lowercase) -> index
        header_map = {}
        for idx, h in enumerate(headers):
            key = h.lower()
            header_map[key] = idx
        return table, header_map

    def _extract_rows_by_header_map(self, table, header_map) -> List[Dict]:
        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        page_records = []
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                # safe-get helper
                def g(idx):
                    try:
                        return _clean_text(cells[idx].text)
                    except Exception:
                        return None

                # Attempt to find by common header names (fallback to indices if present)
                # The header_map keys are whole header text lowercased; we check substrings for robustness
                def find_index_by_keyword(keywords):
                    for k, idx in header_map.items():
                        for kw in keywords:
                            if kw in k:
                                return idx
                    return None

                symbol_idx = find_index_by_keyword(["symbol"]) or 0
                name_idx = find_index_by_keyword(["name", "title"]) or 1
                price_idx = find_index_by_keyword(["price", "last"]) or None
                change_idx = find_index_by_keyword(["change", "% change"]) or None
                volume_idx = find_index_by_keyword(["volume"]) or None
                marketcap_idx = find_index_by_keyword(["market cap", "marketcap"]) or None
                pe_idx = find_index_by_keyword(["pe", "pe ratio"]) or None

                # Build record gracefully
                symbol = g(symbol_idx) if symbol_idx is not None else None
                name = g(name_idx) if name_idx is not None else None
                price_raw = g(price_idx) if price_idx is not None else None
                change_raw = g(change_idx) if change_idx is not None else None
                volume_raw = g(volume_idx) if volume_idx is not None else None
                marketcap_raw = g(marketcap_idx) if marketcap_idx is not None else None
                pe_raw = g(pe_idx) if pe_idx is not None else None

                record = {
                    "symbol": symbol,
                    "name": name,
                    "price_raw": price_raw,
                    "change_raw": change_raw,
                    "volume_raw": volume_raw,
                    "market_cap_raw": marketcap_raw,
                    "pe_raw": pe_raw,
                    "scraped_at": datetime.utcnow().isoformat() + "Z",
                }

                # parsed numeric values
                record["price_usd"] = parse_price(price_raw) if price_raw else None
                record["change"] = parse_change(change_raw) if change_raw else None
                record["volume"] = parse_number_with_suffix(volume_raw) if volume_raw else None
                record["market_cap"] = parse_number_with_suffix(marketcap_raw) if marketcap_raw else None
                # PE ratio may contain '-' for N/A
                try:
                    record["pe_ratio"] = float(pe_raw.replace(",", "")) if pe_raw and pe_raw not in {"-", "—", "N/A"} else None
                except Exception:
                    record["pe_ratio"] = None

                page_records.append(record)
            except StaleElementReferenceException:
                logger.debug("Stale row skipped")
                continue
        return page_records

    def _click_next_if_available(self) -> bool:
        """
        Return True if we clicked next and more pages are expected; False if Next is absent/disabled.
        """
        # There may be a pagination control under a div with buttons; try common attributes for Next
        try:
            next_btn = self.driver.find_element(By.XPATH, "//button[contains(@aria-label,'Next') or contains(., 'Next')]")
        except NoSuchElementException:
            logger.info("Next button not found on page.")
            return False

        # check if disabled
        disabled_attr = next_btn.get_attribute("disabled")
        classes = (next_btn.get_attribute("class") or "")
        aria_disabled = next_btn.get_attribute("aria-disabled")
        if disabled_attr or "disabled" in classes or aria_disabled == "true":
            logger.info("Next button is disabled - reached last page.")
            return False

        # attempt to click with retry
        try:
            next_btn.click()
            # wait a bit for the next page to load content
            self._wait_for_ready_state()
            time.sleep(0.5 + random.random() * 0.7)
            return True
        except (ElementClickInterceptedException, StaleElementReferenceException) as e:
            logger.warning("Could not click Next directly (%s). Trying JS click...", e)
            try:
                self.driver.execute_script("arguments[0].click();", next_btn)
                self._wait_for_ready_state()
                time.sleep(0.5 + random.random() * 0.7)
                return True
            except Exception:
                logger.exception("JS click on Next failed.")
                return False

    def scrape(self, pages_limit: Optional[int] = None):
        """
        Scrape pages until Next disabled or until pages_limit is reached (if provided).
        """
        # Open the target page
        self.open_page(self.MOST_ACTIVE_URL)

        pages_scraped = 0
        while True:
            pages_scraped += 1
            logger.info("Scraping page %d ...", pages_scraped)
            try:
                table, header_map = self._find_table_and_headers()
            except RuntimeError as e:
                logger.error("Could not find table: %s", e)
                break

            page_records = self._extract_rows_by_header_map(table, header_map)
            logger.info("Found %d rows on page %d", len(page_records), pages_scraped)
            self.data.extend(page_records)

            if pages_limit and pages_scraped >= pages_limit:
                logger.info("Reached pages_limit (%s). Stopping.", pages_limit)
                break

            # Try to move to the next page
            has_next = self._click_next_if_available()
            if not has_next:
                break

        logger.info("Scraping completed. Total rows collected: %d", len(self.data))

    def save(self, output_basename: str):
        if not self.data:
            logger.warning("No data to save.")
            return
        df = pd.DataFrame(self.data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = f"{output_basename}_{timestamp}.xlsx"
        csv_path = f"{output_basename}_{timestamp}.csv"
        json_path = f"{output_basename}_{timestamp}_raw.json"

        # reorder columns sensibly
        cols = [
            "scraped_at", "symbol", "name",
            "price_raw", "price_usd",
            "change_raw", "change",
            "volume_raw", "volume",
            "market_cap_raw", "market_cap",
            "pe_raw", "pe_ratio"
        ]
        cols = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
        df = df[cols]

        df.to_excel(excel_path, index=False)
        df.to_csv(csv_path, index=False)
        # save raw json
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, ensure_ascii=False, indent=2)

        logger.info("Saved Excel -> %s", excel_path)
        logger.info("Saved CSV   -> %s", csv_path)
        logger.info("Saved JSON  -> %s", json_path)


# -------------------------
# CLI Entrypoint
# -------------------------
def build_driver(headless: bool = True, window_size: str = "1280,1024"):
    options = ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument(f"--window-size={window_size}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--disable-gpu")  # usually not necessary on modern chrome
    driver = webdriver.Chrome(options=options)
    return driver


def main():
    parser = argparse.ArgumentParser(description="Scrape Yahoo Finance - Most Active stocks")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--pages", type=int, default=None, help="Max pages to scrape (default: all)")
    parser.add_argument("--out", type=str, default="yahoo_most_active", help="Output filename base (no ext)")
    args = parser.parse_args()

    driver = build_driver(headless=args.headless)
    try:
        scraper = YahooMostActiveScraper(driver, wait_timeout=12)
        scraper.scrape(pages_limit=args.pages)
        scraper.save(args.out)
    except Exception:
        logger.exception("Unhandled exception during scraping.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
