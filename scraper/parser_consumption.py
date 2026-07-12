"""Parse a server-rendered 消費禮 (consumption gift) announcement page into item records.

Two known page templates, both confirmed against real examples:

1. id=218484: each spending threshold is introduced by an <h2> (e.g. "『單一
   伺服器』每日累積消費達500：") and followed by a reward <table>.
2. id=217839/217684: there's no <h2> per threshold at all -- thresholds live
   as individual <p> paragraphs (same exact wording as the <h2> version)
   under an <h1>獎勵道具 : </h1> heading, each immediately followed by its
   own reward <table>. The page's "活動方式" intro section, earlier on the
   page, also has <p> prose mentioning 消費+數字, but that's harmless: it's
   followed by another <h1> (活動範例) before any <table>, and any <h1>
   unconditionally clears the current threshold state (see below), so that
   intro text never gets attached to a table.

Because of template 2, threshold-heading detection (contains "消費" and a
digit) must run on <h2> AND <p> elements, not just <h2>. The two element
types differ in how a *non-matching* occurrence affects the current
threshold, though: a non-matching <h2> clears it (this is how the unrelated
"相關內容" <h2>+<table> in 218484 stays excluded), but a non-matching <p>
must NOT clear it -- 217839/217684's bundle items have their own descriptive
<p> paragraphs (and even literal "<p> </p>" spacers) sitting between bundle
tables, and clearing on those would silently drop every bundle table that
follows. Instead, <h1> is the explicit section boundary: every <h1> always
clears the current threshold, which is what excludes 217839/217684's
trailing "相關道具" reference table (and also means accidentally matching
some unrelated "消費"+digit prose, like the 活動方式 intro, is harmless as
long as no <table> sits between it and the next <h1>).

Every table starts with two rows that are NOT items: a colspan="2" caption
row (e.g. "每日累積500獎勵") and a plain two-cell column-header row ("獎勵" /
"能力效果") -- real item rows only start after that. The highest threshold
is sometimes "pick one of N": colspan="2" rows like "組合A" appear *after*
the header row to divide the table into bundles, and items are recorded
with which bundle they belong to rather than "everyone gets all of them".
217839/217684 push this further: the last couple of bundles (e.g. "組合F",
"組合G") aren't colspan rows inside that same table at all -- they're each
their own separate <table>, whose very first row *is* the "組合X" colspan
row (with no header row of its own, since it's a continuation of the same
threshold rather than a new one). parse_consumption tracks whether a table
is the first one seen for the current threshold or a continuation of it,
and passes that through to _parse_threshold_table as `continuation`: a
continuation table treats its first colspan row as a real bundle divider
immediately, rather than mistaking it for an ignorable leading caption.

The column-header row is identified by STRUCTURE (neither cell has an
<img>, and it appears before any item row), not by matching its exact
text -- a future announcement could reword "獎勵"/"能力效果" and text
matching alone would either misfile the header as a fake item, or drop
the bundle-divider rows that follow it.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional

from bs4 import BeautifulSoup

from .common import (
    clean_text,
    extract_channel_name,
    extract_period,
    extract_publish_date,
    get_announcement_title,
    item_name_from_cell,
)

THRESHOLD_DIGIT_RE = re.compile(r"\d")


def _is_threshold_heading(text: str) -> bool:
    return "消費" in text and bool(THRESHOLD_DIGIT_RE.search(text))


def _looks_like_header_row(cells) -> bool:
    return len(cells) == 2 and cells[0].find("img") is None and cells[1].find("img") is None


def _parse_threshold_table(table, condition_text: str, *, continuation: bool = False) -> List[dict]:
    items: List[dict] = []
    seen_header = continuation
    current_group: Optional[str] = None

    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if not cells:
            continue

        if len(cells) == 1 and cells[0].has_attr("colspan"):
            label = clean_text(cells[0].get_text())
            if seen_header:
                current_group = label  # a real "組合X" bundle divider
            # else: this is the table's leading caption row, not a real
            # item group -- ignore it.
            continue

        if not seen_header and not items and _looks_like_header_row(cells):
            seen_header = True
            continue

        if len(cells) < 2:
            continue

        item_name = item_name_from_cell(cells[0])
        if not item_name:
            continue

        condition = condition_text
        if current_group:
            condition = f"{condition_text}，多選一－{current_group}"
        items.append({"item_name": item_name, "acquire_condition": condition})

    return items


def parse_consumption(soup: BeautifulSoup, source_url: str, publish_date: Optional[str] = None) -> List[dict]:
    """Parse a 消費禮 page. `publish_date`, when given (e.g. from the
    notice-discovery API's own metadata), overrides parsing it from the
    page itself -- see common.extract_publish_date for the manual-input
    fallback. Returns [] if the page has no spending-threshold structure at
    all, which the caller (cli.scrape_one) uses to mean "not a 消費禮 page".
    """
    records: List[dict] = []
    current_condition: Optional[str] = None
    continuation_table = False

    for el in soup.find_all(["h1", "h2", "p", "table"]):
        if el.name == "h1":
            current_condition = None
            continuation_table = False
            continue

        if el.name in ("h2", "p"):
            text = clean_text(el.get_text())
            if _is_threshold_heading(text):
                current_condition = text.rstrip("：:")
                continuation_table = False
            elif el.name == "h2":
                current_condition = None
                continuation_table = False
            # a non-matching <p> leaves current_condition untouched -- see
            # module docstring on why <p> and <h2> must behave differently here.
            continue

        # el.name == "table"
        if current_condition:
            for item in _parse_threshold_table(el, current_condition, continuation=continuation_table):
                records.append(item)
            continuation_table = True

    if not records:
        return []

    notice_title = get_announcement_title(soup)
    channel_name = extract_channel_name(soup, source_url)
    period_start, period_end = extract_period(soup)
    resolved_publish_date = publish_date or extract_publish_date(soup)
    scraped_at = datetime.now(timezone.utc).isoformat()

    return [
        {
            "item_name": item["item_name"],
            "channel_type": "消費禮",
            "notice_title": notice_title,
            "channel_name": channel_name,
            "probability": None,
            "acquire_condition": item["acquire_condition"],
            "period_start": period_start,
            "period_end": period_end,
            "publish_date": resolved_publish_date,
            "source_url": source_url,
            "scraped_at": scraped_at,
        }
        for item in records
    ]
