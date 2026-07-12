"""Parse a Selenium-rendered 轉蛋 (gacha) announcement page into item records.

Verified against the real example id=218485 (a "維護開機公告" maintenance
notice that embeds a gacha widget for "2026 6月轉蛋Ⅱ" -- exactly the
embedded case task.md calls out). The widget's own channel_name and sale
period are NOT in the page's overall "主題" title (that's just the
maintenance post's own generic headline) -- they live in a
`<div class="egg"><h2>{channel_name}<span>{point cost}P</span></h2>...
<p>...(販售期間 YYYY/MM/DD~MM/DD)...</p></div>` block that sits right before
the fixedItem/rndItem sections. That `<span>{point cost}P</span>` matters: a
news_catalog_id=8 機率公告 (verified against real example id=175423,
"料理箱子[轉蛋專用]") reuses the exact same fixedItem/rndItem table markup --
and even has its own div.egg -- to disclose odds for an item it isn't
selling, so its <h2> has no price <span>. fixedItem/rndItem tables alone
can't tell the two page types apart; div.egg with a span-less <h2> means
"not a sale page", and parse_gacha returns [] for it (task.md 第25行).

Item rows have 4 plain <td> cells (物品/數量/轉蛋機率/備註), so
item_name_from_cell's <img>-alt-text path is unused here -- it falls back
to the cell's own text. The column-header row is `<tr><th>物品</th>...</tr>`
(all <th>, zero <td>), so `row.find_all("td")` already skips it without any
special-case logic. fixedItem rows show an explicit probability too (e.g.
"100.000%"), not a blank odds column, so probability is always read from
the row text first and only falls back to a fixed sentinel ("必中"/"不明")
on rows where no percentage is present (per task.md's field rules).

A 轉蛋 announcement that is itself the primary subject of its own page
(rather than an embedded widget) has no real example to verify against. For
that case this parser falls back to the generic <h1>活動時間 + page-title-
bracket extraction (common.extract_period / common.extract_channel_name)
and -- per task.md's "已知限制" section -- prints a [WARN] every time that
fallback actually fires, since it has never been confirmed against a real
page.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from bs4 import BeautifulSoup

from .common import (
    clean_text,
    extract_channel_name,
    extract_period,
    extract_publish_date,
    get_announcement_title,
    item_name_from_cell,
)

PERCENT_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
EGG_PERIOD_RE = re.compile(r"販售期間\s*(\d{4})/(\d{2})/(\d{2})\s*[~-]\s*(\d{1,2})/(\d{1,2})")


def _extract_egg_channel_name(egg_div) -> Optional[str]:
    h2 = egg_div.find("h2")
    if not h2:
        return None
    # h2 is "{channel_name}<span>{point cost}</span>" -- take only the
    # direct text node so the point-cost span doesn't leak into the name.
    direct_text = h2.find(string=True, recursive=False)
    text = clean_text(direct_text) if direct_text else clean_text(h2.get_text())
    return text or None


def _extract_egg_period(egg_div) -> Tuple[Optional[str], Optional[str]]:
    p = egg_div.find("p")
    if not p:
        return None, None
    match = EGG_PERIOD_RE.search(clean_text(p.get_text()))
    if not match:
        return None, None
    start_year, start_month, start_day, end_month, end_day = match.groups()
    period_start = f"{start_year}-{start_month}-{start_day} 00:00"
    period_end = f"{start_year}-{int(end_month):02d}-{int(end_day):02d} 23:59"
    return period_start, period_end


def parse_table(table, fallback_probability: str) -> List[dict]:
    """Parse a section#fixedItem/rndItem table.table_01 into {item_name, probability} dicts."""
    results = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue  # an all-<th> header row, or a stray empty row
        if len(cells) == 1 and cells[0].has_attr("colspan"):
            continue  # defensive: a caption row, if a page happens to have one
        item_name = item_name_from_cell(cells[0])
        if not item_name:
            continue
        match = PERCENT_RE.search(clean_text(row.get_text(" ")))
        probability = match.group(0).replace(" ", "") if match else fallback_probability
        results.append({"item_name": item_name, "probability": probability})
    return results


def parse_gacha(soup: BeautifulSoup, source_url: str, publish_date: Optional[str] = None) -> List[dict]:
    """Parse a 轉蛋 page. `publish_date`, when given (e.g. from the
    notice-discovery API's own metadata), overrides parsing it from the
    page itself. Returns [] if neither fixedItem nor rndItem tables exist,
    which the caller (cli.scrape_one) uses to mean "not a 轉蛋 page".
    """
    fixed_table = soup.select_one("section#fixedItem table.table_01")
    rnd_table = soup.select_one("section#rndItem table.table_01")
    if not fixed_table and not rnd_table:
        return []

    notice_title = get_announcement_title(soup)

    egg_div = soup.select_one("div.egg")
    if egg_div:
        egg_h2 = egg_div.find("h2")
        if egg_h2 is not None and egg_h2.find("span") is None:
            # div.egg without a price <span> is a 機率公告 (e.g. news_catalog_id=8)
            # reusing the sale page's table markup to disclose odds for an
            # existing item -- it isn't selling anything, so it's not a 轉蛋
            # sale page despite having fixedItem/rndItem tables (task.md 第25行).
            return []
        channel_name = _extract_egg_channel_name(egg_div) or extract_channel_name(soup, source_url)
        period_start, period_end = _extract_egg_period(egg_div)
        if period_start is None:
            period_start, period_end = extract_period(soup)
    else:
        print(
            f"[WARN] {source_url}: 找不到 div.egg（轉蛋公告本身是主角頁面，非嵌入 widget），"
            "使用未驗證的轉蛋主角頁 fallback，請人工核對結果。",
            file=sys.stderr,
        )
        channel_name = extract_channel_name(soup, source_url)
        period_start, period_end = extract_period(soup)

    resolved_publish_date = publish_date or extract_publish_date(soup)
    scraped_at = datetime.now(timezone.utc).isoformat()

    records: List[dict] = []
    for table, fallback_probability in ((fixed_table, "必中"), (rnd_table, "不明")):
        if not table:
            continue
        for item in parse_table(table, fallback_probability=fallback_probability):
            records.append({
                "item_name": item["item_name"],
                "channel_type": "轉蛋",
                "notice_title": notice_title,
                "channel_name": channel_name,
                "probability": item["probability"],
                "acquire_condition": "",
                "period_start": period_start,
                "period_end": period_end,
                "publish_date": resolved_publish_date,
                "source_url": source_url,
                "scraped_at": scraped_at,
            })

    return records
