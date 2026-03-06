import csv
import datetime as dt
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


URL = "https://www.silicondata.com/products/silicon-index"
CSV_PATH = Path("gpu_prices.csv")

# CSV columns (hyperscaler-*, neocloud-*)
CSV_COLUMNS = [
    "date",
    "hyperscaler-H100",
    "hyperscaler-A100",
    "neocloud-H100",
    "neocloud-A100",
    "neocloud-B200",
    "neocloud-MI300X",
]


def fetch_page_html_requests(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_page_html_selenium(url: str, wait_seconds: int = 20) -> tuple[str, webdriver.Chrome]:
    """
    Use a headless Chrome browser so that the page's JavaScript runs
    and populates any dynamic content before we read the HTML.
    """
    chrome_options = Options()
    # Run in a visible Chrome window so you can see what Selenium does.
    # Comment the next line back in if you want headless again:
    # chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1280,720")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    driver.get(url)
    time.sleep(wait_seconds)

    # Outer page HTML (contains the iframe shell)
    outer_html = driver.page_source

    # Try to switch into the Silicon Data portal iframe where the numbers render.
    iframe_html = None
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in iframes:
        src = frame.get_attribute("src") or ""
        if "portal.silicondata.com" in src:
            driver.switch_to.frame(frame)
            time.sleep(3)
            iframe_html = driver.page_source
            break

    html = iframe_html or outer_html

    return html, driver


def _parse_price_text(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def scrape_prices_with_selenium() -> dict:
    """
    Use Selenium to click through Hyperscaler and Neo-Cloud tabs and
    read the displayed daily USD prices for each GPU.
    """
    html, driver = fetch_page_html_selenium(URL)
    prices: dict[str, float | None] = {
        col: None for col in CSV_COLUMNS if col != "date"
    }

    try:
        # Switch into portal iframe if not already.
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            src = frame.get_attribute("src") or ""
            if "portal.silicondata.com" in src:
                driver.switch_to.frame(frame)
                break

        wait = WebDriverWait(driver, 20)

        def click_tab(text: str) -> None:
            # Click by visible text; covers buttons/divs/spans used as tabs.
            el = wait.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        f"//*[normalize-space(text())='{text}']",
                    )
                )
            )
            el.click()
            time.sleep(0.8)

        def read_price() -> float | None:
            el = wait.until(
                EC.visibility_of_element_located(
                    (
                        By.XPATH,
                        "//p[contains(@class, 'text-5xl') and contains(@class, 'text-white/90')]",
                    )
                )
            )
            return _parse_price_text(el.text)

        # Hyperscaler tab first
        click_tab("Hyperscaler(NEW)")

        for gpu, col in [
            ("H100", "hyperscaler-H100"),
            ("A100", "hyperscaler-A100"),
        ]:
            try:
                click_tab(gpu)
                val = read_price()
                if val is not None:
                    prices[col] = val
            except Exception:
                continue

        # Neo-Cloud tab
        click_tab("Neo-Cloud")

        neo_map = {
            "H100": "neocloud-H100",
            "A100": "neocloud-A100",
            "B200": "neocloud-B200",
            "MI300X": "neocloud-MI300X",
        }
        for gpu, col in neo_map.items():
            try:
                click_tab(gpu)
                val = read_price()
                if val is not None:
                    prices[col] = val
            except Exception:
                continue

    finally:
        driver.quit()

    return prices


def ensure_csv_header(path: Path) -> None:
    if path.exists():
        return

    fieldnames = CSV_COLUMNS
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()


def append_row(prices: dict) -> None:
    today = dt.date.today().isoformat()

    ensure_csv_header(CSV_PATH)

    # Do not append if we already logged a row for today.
    if CSV_PATH.exists():
        with CSV_PATH.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows:
                last_date = rows[-1].get("date")
                if last_date == today:
                    return

    row = {"date": today}
    for col in CSV_COLUMNS:
        if col == "date":
            continue
        value = prices.get(col)
        row[col] = value if value is not None else ""

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        writer.writerow(row)


def main() -> None:
    try:
        prices = scrape_prices_with_selenium()
    except Exception:
        # Fallback: empty prices row if Selenium fails.
        prices = {col: None for col in CSV_COLUMNS if col != "date"}

    append_row(prices)


if __name__ == "__main__":
    main()
