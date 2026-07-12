"""Fetch announcement pages -- static HTML via requests, or JS-rendered HTML via headless Chrome."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

# ro.gnjoy.com.tw sits behind Cloudflare and blocks requests with no
# browser-like User-Agent (HTTP 403, confirmed) -- every request (requests
# or Selenium) must carry a real browser UA string.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch_static(url: str, timeout: int = 15) -> BeautifulSoup:
    """Fetch a page as plain server-rendered HTML (no JS execution)."""
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_rendered(url: str, timeout: int = 15) -> BeautifulSoup:
    """Fetch a page after letting headless Chrome execute its JS (for gacha widgets).

    Waits for the fixedItem/rndItem tables specifically (per task.md), not
    just <body>, since the gacha widget's content is loaded asynchronously
    by the page's own JS after initial load.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument(f"user-agent={USER_AGENT}")

    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        try:
            WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "section#fixedItem table.table_01, section#rndItem table.table_01")
                )
            )
        except Exception:
            # Not a gacha page at all (discovery noise, 消費禮, 系統公告...) --
            # fall through with whatever HTML loaded; parse_gacha() will
            # correctly find nothing and the caller treats that as a normal
            # "not a match", not an error.
            pass
        html = driver.page_source
    finally:
        driver.quit()

    return BeautifulSoup(html, "html.parser")
