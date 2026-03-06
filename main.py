import csv
import datetime as dt
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager


URL = "https://www.silicondata.com/products/silicon-index"
CSV_PATH = Path("gpu_prices.csv")

CSV_COLUMNS = [
    "date",
    "hyperscaler-H100",
    "hyperscaler-A100",
    "neocloud-H100",
    "neocloud-A100",
    "neocloud-B200",
    "neocloud-MI300X",
]


def _parse_price_text(text: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    return float(m.group(1))


def start_driver():

    options = Options()

    # comment this out if you want to see Chrome
    # options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,1000")

    service = Service(ChromeDriverManager().install())

    return webdriver.Chrome(service=service, options=options)


def wait_for_iframe(driver):

    wait = WebDriverWait(driver, 20)

    iframe = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "iframe[src*='portal.silicondata.com']")
        )
    )

    driver.switch_to.frame(iframe)


def wait_for_price(driver):

    wait = WebDriverWait(driver, 20)

    el = wait.until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "p.text-5xl")
        )
    )

    return _parse_price_text(el.text)


def click_tab(driver, text):

    wait = WebDriverWait(driver, 20)

    el = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, f"//p[normalize-space()='{text}']")
        )
    )

    driver.execute_script("arguments[0].click();", el)

    time.sleep(1)


def scrape_prices():

    driver = start_driver()

    prices = {col: None for col in CSV_COLUMNS if col != "date"}

    try:

        driver.get(URL)

        wait_for_iframe(driver)

        # wait for React to render first price
        wait_for_price(driver)

        # ----------------
        # Hyperscaler
        # ----------------

        click_tab(driver, "Hyperscaler(NEW)")

        click_tab(driver, "H100")
        prices["hyperscaler-H100"] = wait_for_price(driver)

        click_tab(driver, "A100")
        prices["hyperscaler-A100"] = wait_for_price(driver)

        # ----------------
        # NeoCloud
        # ----------------

        click_tab(driver, "Neo-Cloud")

        for gpu in ["H100", "A100", "B200", "MI300X"]:

            try:
                click_tab(driver, gpu)
                prices[f"neocloud-{gpu}"] = wait_for_price(driver)
            except:
                pass

    finally:

        driver.quit()

    return prices


def ensure_csv_header(path):

    if path.exists():
        return

    with path.open("w", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

        writer.writeheader()


def append_row(prices):

    today = dt.date.today().isoformat()

    ensure_csv_header(CSV_PATH)

    if CSV_PATH.exists():

        with CSV_PATH.open("r", newline="", encoding="utf-8") as f:

            rows = list(csv.DictReader(f))

            if rows and rows[-1]["date"] == today:
                return

    row = {"date": today}

    for col in CSV_COLUMNS:

        if col != "date":
            row[col] = prices.get(col) or ""

    with CSV_PATH.open("a", newline="", encoding="utf-8") as f:

        writer = csv.DictWriter(f, fieldnames=row.keys())

        writer.writerow(row)


def main():

    try:
        prices = scrape_prices()
    except Exception:
        prices = {col: None for col in CSV_COLUMNS if col != "date"}

    append_row(prices)


if __name__ == "__main__":
    main()