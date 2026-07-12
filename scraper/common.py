"""Shared helpers for parsing RO announcement pages.

Used by both parser_consumption.py (消費禮) and parser_gacha.py (轉蛋).
"""
from __future__ import annotations

import re
import sys
from typing import Optional, Tuple

from bs4 import BeautifulSoup

DATE_RE = re.compile(r"(\d{4}/\d{2}/\d{2})(?:\([^)]*\))?\s*([\d:]{4,5})?")
BRACKET_RE = re.compile(r"【(.+?)】")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def get_announcement_title(soup: BeautifulSoup) -> str:
    """The notice headline, e.g. '【端午節消費送】消費活動進行中(06/17更新)'.

    task.md is explicit that <head><title> is always the generic site name
    ("RO仙境傳說Online") and the real headline lives in
    <span class="viTop"><span class="title">主題</span><img/><span>標題</span></span>.
    """
    label = soup.select_one("span.viTop span.title")
    if label:
        value_span = label.find_next_sibling("span")
        if value_span:
            text = clean_text(value_span.get_text())
            if text:
                return text
    if soup.title and soup.title.string:
        return clean_text(soup.title.string)
    return ""


def extract_publish_date(soup: BeautifulSoup) -> Optional[str]:
    """The announcement's own publish date, e.g. '2026-06-16 14:10'.

    Distinct from period_start/period_end (the activity's own period). Lives
    in <span class="line"><span class="date"><span class="title">日期</span>
    <span>...</span></span></span>, a sibling block right after viTop.
    Returns None rather than guessing if the field isn't present.
    """
    label = soup.select_one("span.date span.title")
    if label:
        value_span = label.find_next_sibling("span")
        if value_span:
            text = clean_text(value_span.get_text())
            if text:
                return text
    return None


def extract_channel_name(soup: BeautifulSoup, source_url: Optional[str] = None) -> str:
    """Best-effort activity name, e.g. '端午節消費送'.

    消費禮 titles wrap the activity name in 【...】 (task.md). Also used as a
    last-resort fallback for 轉蛋 pages with no embedded widget block (see
    parser_gacha.py) -- per task.md's "已知限制" section, that string-split
    fallback (used when the title has no 【】) has never been confirmed
    against a real page, so it must print a [WARN] whenever actually used.
    """
    title = get_announcement_title(soup)
    match = BRACKET_RE.search(title)
    if match:
        return clean_text(match.group(1))
    if source_url:
        print(
            f"[WARN] {source_url}: channel_name 標題無「【】」標記，"
            "使用未驗證的字串切割 fallback 取得活動名稱，請人工核對結果。",
            file=sys.stderr,
        )
    return clean_text(title.split(" - ")[0].split("｜")[0])


def extract_period(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
    """Extract (period_start, period_end) from a '活動時間' <h1> + following <p>.

    e.g. "2026/06/16(二)00:00 - 2026/06/22(一)23:59" -> ("2026-06-16 00:00",
    "2026-06-22 23:59"). Returns (None, None) if the text doesn't match the
    expected two-date pattern, rather than guessing.
    """
    heading = soup.find(lambda tag: tag.name == "h1" and "活動時間" in tag.get_text())
    if not heading:
        return None, None
    p = heading.find_next("p")
    if not p:
        return None, None
    dates = DATE_RE.findall(clean_text(p.get_text()))
    if len(dates) < 2:
        return None, None
    (start_date, start_time), (end_date, end_time) = dates[0], dates[1]
    period_start = f"{start_date.replace('/', '-')} {start_time or '00:00'}"
    period_end = f"{end_date.replace('/', '-')} {end_time or '23:59'}"
    return period_start, period_end


def item_name_from_cell(cell) -> str:
    img = cell.find("img")
    if img and img.get("alt"):
        alt = clean_text(img["alt"])
        if alt:
            return alt
    return clean_text(cell.get_text(" "))
