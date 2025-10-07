#!/usr/bin/env python3
"""
yahoo_most_active_scraper_enhanced.py

Enhanced scraper for Yahoo Finance "Most Active" with optional enrichment
from yfinance for technical indicators (Bollinger Bands, SMA, RSI) and
additional fields. Also improves robustness when headers change.

Dependencies:
- selenium
- pandas
- openpyxl
- yfinance

Usage:
    python yahoo_most_active_scraper_enhanced.py --out outbase --enrich --pages 2

Notes:
- yfinance enrichment can be slow and may hit rate limits; use --yf-delay to
  increase delay between ticker requests.
- This script tries to be robust to column reordering on the Yahoo table.
"""

import time
import random
import logging
import argparse
import json
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
import yfinance as yf
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
    if not s:
        return None
    s = s.strip().replace(",", "")
    if s in {"-", "—", "N/A", ""}:
        return None
    try:
        if s.endswith("%"):
            return float(s[:-1])
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
        s = s.replace("+", "")
        return float(s) * mult
    except ValueError:
        try:
            return float(s)
        except Exception:
            return None


def parse_price(s: str) -> Optional[float]:
    if not s:
        return None
    s = s.replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return parse_number_with_suffix(s)


def parse_change(s: str) -> Optional[float]:
    if not s:
        return None
    parts = s.split()
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
# Technical indicator helpers (using pandas / yfinance data)
# -------------------------

def compute_sma(series: pd.Series, window: int) -> Optional[float]:
    if series is None or len(series) < window:
        return None
    return float(series.rolling(window=window).mean().iloc[-1])


def compute_bollinger(series: pd.Series, window: int = 20, num_std: int = 2):
    if series is None or len(series) < window:
        return (None, None, None)
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    last_mean = float(rolling_mean.iloc[-1])
    last_std = float(rolling_std.iloc[-1])
    upper = last_mean + num_std * last_std
    lower = last_mean - num_std * last_std
    return last_mean, upper, lower


def compute_rsi(series: pd.Series, window: int = 14) -> Optional[float]:
    if series is None or len(series) < window + 1:
        return None
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=window).mean()
    avg_loss = loss.rolling(window=window).mean()
    # Avoid division by zero
    rs = avg_gain / (avg_loss.replace(0, 1e-8))
    rsi = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1])


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
        self._yf_cache: Dict[str, Dict] = {}

    def open_page(self, url: str):
        logger.info("Opening URL: %s", url)
        self.driver.get(url)
        self._wait_for_ready_state()
        time.sleep(0.5 + random.random() * 0.5)

    def _wait_for_ready_state(self, timeout: int = 10):
        try:
            self.wait.until(lambda d: d.execute_script("return document.readyState === 'complete'"))
        except TimeoutException:
            logger.warning("Page did not reach readyState 'complete' within timeout")

    def _find_table_and_headers(self):
        try:
            table = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))
        except TimeoutException:
            raise RuntimeError("No table found on the page")
        header_elems = table.find_elements(By.CSS_SELECTOR, "thead th")
        headers = [h.text.strip() for h in header_elems]
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

                def g(idx):
                    try:
                        return _clean_text(cells[idx].text)
                    except Exception:
                        return None

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

                record["price_usd"] = parse_price(price_raw) if price_raw else None
                record["change"] = parse_change(change_raw) if change_raw else None
                record["volume"] = parse_number_with_suffix(volume_raw) if volume_raw else None
                record["market_cap"] = parse_number_with_suffix(marketcap_raw) if marketcap_raw else None
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
        try:
            next_btn = self.driver.find_element(By.XPATH, "//button[contains(@aria-label,'Next') or contains(., 'Next')]")
        except NoSuchElementException:
            logger.info("Next button not found on page.")
            return False

        disabled_attr = next_btn.get_attribute("disabled")
        classes = (next_btn.get_attribute("class") or "")
        aria_disabled = next_btn.get_attribute("aria-disabled")
        if disabled_attr or "disabled" in classes or aria_disabled == "true":
            logger.info("Next button is disabled - reached last page.")
            return False

        try:
            next_btn.click()
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

            has_next = self._click_next_if_available()
            if not has_next:
                break

        logger.info("Scraping completed. Total rows collected: %d", len(self.data))

    # -------------------------
    # yFinance enrichment
    # -------------------------
    def _fetch_yf_data(self, symbol: str, period: str = "1y", interval: str = "1d") -> Dict:
        """Fetch historical data for symbol and compute indicators. Results cached per-run."""
        if not symbol:
            return {}
        if symbol in self._yf_cache:
            return self._yf_cache[symbol]

        result = {}
        try:
            logger.debug("Fetching yfinance data for %s", symbol)
            tk = yf.Ticker(symbol)
            info = tk.info if hasattr(tk, "info") else {}
            # attempt safe extractions
            result["yf_market_cap"] = info.get("marketCap") if isinstance(info, dict) else None
            result["yf_beta"] = info.get("beta") if isinstance(info, dict) else None
            # trailingPE if available
            result["yf_trailingPE"] = info.get("trailingPE") if isinstance(info, dict) else None

            hist = tk.history(period=period, interval=interval, auto_adjust=False)
            if hist is None or hist.empty:
                logger.debug("No history for %s", symbol)
                self._yf_cache[symbol] = result
                return result

            close = hist["Close"].dropna()
            # compute SMA20, SMA50, SMA200
            result["sma20"] = compute_sma(close, 20)
            result["sma50"] = compute_sma(close, 50)
            result["sma200"] = compute_sma(close, 200)
            # bollinger
            ma20, bb_upper, bb_lower = compute_bollinger(close, window=20, num_std=2)
            result["bb_ma20"] = ma20
            result["bb_upper"] = bb_upper
            result["bb_lower"] = bb_lower
            # rsi
            result["rsi14"] = compute_rsi(close, window=14)

        except Exception as e:
            logger.debug("yfinance fetch failed for %s: %s", symbol, e)
        finally:
            self._yf_cache[symbol] = result
            return result

    def enrich_with_yfinance(self, delay: float = 1.0, period: str = "1y", interval: str = "1d"):
        """Enrich collected records with yfinance-derived fields. This is optional and
        slow for many tickers; respects a delay between requests to be polite.
        """
        if not self.data:
            logger.warning("No scraped data to enrich.")
            return

        logger.info("Enriching %d records via yfinance (delay=%s) ...", len(self.data), delay)
        for i, rec in enumerate(self.data, start=1):
            sym = rec.get("symbol")
            try:
                yf_data = self._fetch_yf_data(sym, period=period, interval=interval)
                rec.update(yf_data)
            except Exception:
                logger.exception("Failed to enrich %s", sym)
            # polite delay
            time.sleep(delay + random.random() * 0.3)
            if i % 20 == 0:
                logger.info("Enriched %d/%d", i, len(self.data))

        logger.info("Enrichment completed.")

    def save(self, output_basename: str):
        if not self.data:
            logger.warning("No data to save.")
            return
        df = pd.DataFrame(self.data)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = f"{output_basename}_{timestamp}.xlsx"
        csv_path = f"{output_basename}_{timestamp}.csv"
        json_path = f"{output_basename}_{timestamp}_raw.json"

        # sensible column ordering: include new yfinance columns if present
        cols = [
            "scraped_at", "symbol", "name",
            "price_raw", "price_usd",
            "change_raw", "change",
            "volume_raw", "volume",
            "market_cap_raw", "market_cap",
            "pe_raw", "pe_ratio",
            # yfinance enrichment
            "yf_market_cap", "yf_beta", "yf_trailingPE",
            "sma20", "sma50", "sma200",
            "bb_ma20", "bb_upper", "bb_lower",
            "rsi14",
        ]
        cols = [c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]
        df = df[cols]

        df.to_excel(excel_path, index=False)
        df.to_csv(csv_path, index=False)
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
    driver = webdriver.Chrome(options=options)
    return driver


def main():
    parser = argparse.ArgumentParser(description="Scrape Yahoo Finance - Most Active stocks (enhanced)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--pages", type=int, default=None, help="Max pages to scrape (default: all)")
    parser.add_argument("--out", type=str, default="yahoo_most_active", help="Output filename base (no ext)")
    parser.add_argument("--enrich", action="store_true", help="Enrich results using yfinance (slower)")
    parser.add_argument("--yf-delay", type=float, default=1.0, help="Delay (seconds) between yfinance requests")
    parser.add_argument("--yf-period", type=str, default="1y", help="Period for yfinance history (eg '6mo','1y')")
    parser.add_argument("--yf-interval", type=str, default="1d", help="Interval for yfinance history (eg '1d')")
    args = parser.parse_args()

    driver = build_driver(headless=args.headless)
    try:
        scraper = YahooMostActiveScraper(driver, wait_timeout=12)
        scraper.scrape(pages_limit=args.pages)
        if args.enrich:
            scraper.enrich_with_yfinance(delay=args.yf_delay, period=args.yf_period, interval=args.yf_interval)
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
