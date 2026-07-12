"""Auto-discover candidate announcement URLs via the official notice-search AJAX API.

POST https://ro.gnjoy.com.tw/Notice/forAjax_NoticeNews (per task.md, confirmed live):
  body: {"news_catalog_id": "<code>", "search_word": "<keyword>", "row_start": "<1-based row, as string>"}
  headers: Content-Type: application/json; charset=utf-8, plus a browser User-Agent
           (Cloudflare blocks the default `requests` UA with HTTP 403).
  response: {"Table": [{"id": int, "subject": str, "publish_date_": "YYYY.MM.DD",
             "publish_time": "HH:MM", "url": str|None, ...}, ...],
             "Table1": [{"count": N}]}

row_start is a 1-based ROW NUMBER, not a page index (task.md: row_start=21
continues from row 21 of the same result set, not a second 20-row page).
Pages are fetched 20 rows at a time until `count` rows have been collected.

search_word matches the full announcement body text, not just the title, so
a catalog can return plenty of irrelevant noise -- expected (task.md), and
why downstream consumers (cli.scrape_one) must tolerate candidates that turn
out not to be 轉蛋/消費禮 rather than treating that as an error.

Known limitation (task.md "已知限制"): the API's own `url` field (used for
announcements whose real content lives on an external event microsite) is
not used here -- every candidate's URL is unconditionally built from `id`.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

import requests

from .fetch import USER_AGENT

DISCOVER_URL = "https://ro.gnjoy.com.tw/Notice/forAjax_NoticeNews"
NOTICE_URL_TEMPLATE = "https://ro.gnjoy.com.tw/Notice/Notice_View?id={id}"
PAGE_SIZE = 20

CATALOG_ALL = "0"
CATALOG_EVENT = "2"
CATALOG_NEWS = "4"
CATALOG_SYSTEM = "6"
CATALOG_PROBABILITY = "8"


def _normalize_publish_date(publish_date_: Optional[str], publish_time: Optional[str]) -> Optional[str]:
    if not publish_date_:
        return None
    date_part = publish_date_.replace(".", "-")
    return f"{date_part} {publish_time}" if publish_time else date_part


def _fetch_page(search_word: str, news_catalog_id: str, row_start: int, timeout: int = 15) -> dict:
    resp = requests.post(
        DISCOVER_URL,
        json={
            "news_catalog_id": news_catalog_id,
            "search_word": search_word,
            "row_start": str(row_start),
        },
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def discover(search_word: str, news_catalog_id: str = CATALOG_ALL) -> Iterator[Dict]:
    """Paginate a single search_word/news_catalog_id query, yielding normalized candidates.

    Each candidate dict has: id, subject, publish_date ("YYYY-MM-DD HH:MM" or None), url.
    """
    row_start = 1
    total: Optional[int] = None
    collected = 0

    while total is None or collected < total:
        payload = _fetch_page(search_word, news_catalog_id, row_start)
        rows = payload.get("Table", [])
        if total is None:
            count_rows = payload.get("Table1", [])
            total = count_rows[0]["count"] if count_rows else len(rows)
        if not rows:
            break

        for row in rows:
            yield {
                "id": row["id"],
                "subject": row.get("subject"),
                "publish_date": _normalize_publish_date(row.get("publish_date_"), row.get("publish_time")),
                "url": NOTICE_URL_TEMPLATE.format(id=row["id"]),
            }

        collected += len(rows)
        row_start += PAGE_SIZE


def discover_candidates(search_words: List[str], news_catalog_id: str = CATALOG_ALL) -> List[Dict]:
    """Run `discover()` for each search word and dedup the combined results by id."""
    seen: Dict[int, Dict] = {}
    for word in search_words:
        for candidate in discover(word, news_catalog_id=news_catalog_id):
            seen.setdefault(candidate["id"], candidate)
    return list(seen.values())
