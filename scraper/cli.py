"""CLI entry point: scrape RO item-acquisition-channel announcements into items.json.

channel_type is never guessed from a title keyword ("轉蛋"/"消費") -- task.md
calls that approach unreliable. Instead each candidate is tried
structurally: parse_consumption() against a cheap static fetch first, and
only if that finds nothing, a Selenium-rendered parse_gacha(). A candidate
matching neither shape (a plain 系統公告, or noise from a full-text
discovery search) yields [] so the caller logs a skip and moves on without
aborting the whole run (task.md's auto-discovery fault-tolerance rule).

Output is split across two normalized files:
  items.json  -- one slim record per item (notice_id, item_name, probability,
                 acquire_condition, scraped_at); all notice-level metadata
                 lives in notices.json instead.
  notices.json -- one record per notice_id (notice_id, notice_title,
                 source_url, channel_type, channel_name, period_start,
                 period_end, publish_date, analyzed_at). This also tracks
                 every notice_id ever analyzed regardless of items outcome.

--discover candidates already recorded in notices.json are skipped entirely
(no fetch at all) so repeat runs only pay for genuinely new candidates;
manual positional-arg input always bypasses that check and force-overwrites
the notice's record, since naming an id explicitly means "analyze this one
now" regardless of history (task.md's 已分析公告記錄檔 section). A candidate
that raises is never written to notices.json, so a transient failure gets
retried on the next --discover run instead of being treated as analyzed.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from . import discover as discover_module
from .common import extract_publish_date, get_announcement_title
from .fetch import fetch_rendered, fetch_static
from .parser_consumption import parse_consumption
from .parser_gacha import parse_gacha
from .storage import load_records, save_records, upsert_by_notice_id, upsert_items_by_notice_id

DEFAULT_SEARCH_WORDS = ["轉蛋", "消費", "維護開機公告"]

NOTICE_URL_TEMPLATE = "https://ro.gnjoy.com.tw/Notice/Notice_View?id={id}"
ID_FROM_URL_RE = re.compile(r"id=(\d+)")


def resolve_url(url_or_id: str) -> str:
    return url_or_id if url_or_id.startswith("http") else NOTICE_URL_TEMPLATE.format(id=url_or_id)


def extract_numeric_id(url_or_id: str) -> int:
    """Pull out the numeric announcement id for sort purposes.

    task.md requires processing candidates newest-id-first; manual input
    may mix bare numeric ids and full URLs, so both forms need to resolve
    to the same comparable number.
    """
    if url_or_id.isdigit():
        return int(url_or_id)
    match = ID_FROM_URL_RE.search(url_or_id)
    return int(match.group(1)) if match else -1


def scrape_one(url_or_id: str, publish_date: Optional[str] = None) -> Tuple[List[dict], dict]:
    """Try consumption parsing first (cheap), then gacha.

    Returns (records, notice_meta). notice_meta always has notice_title,
    publish_date, channel_type ("轉蛋"/"消費禮"/"無"), channel_name,
    period_start, period_end -- all read from whichever page was already
    fetched while determining channel_type, so no extra request is issued
    just to learn the notice's own metadata (task.md's 已分析公告記錄檔
    section is explicit about this).
    """
    url = resolve_url(url_or_id)

    soup = fetch_static(url)
    records = parse_consumption(soup, url, publish_date=publish_date)
    if records:
        return records, {
            "notice_title": records[0]["notice_title"],
            "publish_date": records[0]["publish_date"],
            "channel_type": "消費禮",
            "channel_name": records[0]["channel_name"],
            "period_start": records[0]["period_start"],
            "period_end": records[0]["period_end"],
        }

    rendered_soup = fetch_rendered(url)
    records = parse_gacha(rendered_soup, url, publish_date=publish_date)
    if records:
        return records, {
            "notice_title": records[0]["notice_title"],
            "publish_date": records[0]["publish_date"],
            "channel_type": "轉蛋",
            "channel_name": records[0]["channel_name"],
            "period_start": records[0]["period_start"],
            "period_end": records[0]["period_end"],
        }

    return records, {
        "notice_title": get_announcement_title(rendered_soup),
        "publish_date": publish_date or extract_publish_date(rendered_soup),
        "channel_type": "無",
        "channel_name": None,
        "period_start": None,
        "period_end": None,
    }


def _scrape_candidates(
    candidates: List[Tuple[str, Optional[str], Optional[str]]],
    items_existing: List[dict],
    notices_existing: List[dict],
    items_output_path: str,
    notices_output_path: str,
    *,
    treat_empty_as_failure: bool,
) -> Tuple[List[dict], List[dict], bool]:
    """Scrape a batch of (url_or_id, publish_date, notice_title_hint) triples,
    sorted newest-id-first.

    notice_title_hint, when given (the auto-discovery API's own `subject`
    field), is used as notices.json's notice_title as-is instead of
    scrape_one's page-parsed title -- a discovery candidate already carries a
    title, so there's no reason to prefer the page-parsed one. Manual input
    has no such hint (None), so it falls back to whatever scrape_one parsed
    from the page itself.

    Saves both items.json and notices.json progressively after every
    candidate (success/skip/error) so a mid-batch interruption doesn't lose
    already-processed results (task.md's progressive-save requirement). A
    candidate that raises is NOT written to notices_existing, so the next
    --discover run retries it instead of treating a transient failure as
    permanently analyzed. Returns (items_existing, notices_existing, had_failure).
    """
    ordered = sorted(candidates, key=lambda triple: extract_numeric_id(triple[0]), reverse=True)
    total = len(ordered)
    had_failure = False

    for index, (url_or_id, publish_date, notice_title_hint) in enumerate(ordered, start=1):
        url = resolve_url(url_or_id)
        notice_id = extract_numeric_id(url_or_id)
        prefix = f"[{index}/{total}]"
        try:
            records, notice_meta = scrape_one(url_or_id, publish_date=publish_date)
        except Exception as exc:
            print(f"{prefix} [ERROR] {url}: {exc}", file=sys.stderr)
            had_failure = True
            save_records(items_output_path, items_existing)
            save_records(notices_output_path, notices_existing)
            continue

        # Strip parser-output records down to item-only fields and tag with
        # notice_id. Always upsert even when records is empty: a notice
        # previously stored as 轉蛋/消費禮 that this run reclassifies as
        # neither must have its old item records overwritten too -- an empty
        # result here is a correction to apply, not noise to ignore
        # (task.md 第41行).
        item_records = [
            {
                "notice_id": notice_id,
                "item_name": r["item_name"],
                "probability": r.get("probability"),
                "acquire_condition": r.get("acquire_condition", ""),
                "scraped_at": r.get("scraped_at"),
            }
            for r in records
        ]
        items_existing = upsert_items_by_notice_id(items_existing, notice_id, item_records)
        notices_existing = upsert_by_notice_id(notices_existing, notice_id, {
            "notice_id": notice_id,
            "notice_title": notice_title_hint or notice_meta["notice_title"],
            "source_url": url,
            "channel_type": notice_meta["channel_type"],
            "channel_name": notice_meta["channel_name"],
            "period_start": notice_meta["period_start"],
            "period_end": notice_meta["period_end"],
            "publish_date": notice_meta["publish_date"],
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        })

        if not records:
            print(f"{prefix} [SKIP] {url}: 非轉蛋/消費禮，略過", file=sys.stderr)
            if treat_empty_as_failure:
                had_failure = True
        else:
            print(f"{prefix} [OK] {url}: {len(records)} 筆")
        save_records(items_output_path, items_existing)
        save_records(notices_output_path, notices_existing)

    return items_existing, notices_existing, had_failure


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scrape RO item-acquisition-channel announcements.")
    parser.add_argument("urls", nargs="*", help="Announcement URLs or numeric IDs to scrape (manual input).")
    parser.add_argument(
        "--discover", action="store_true",
        help="Also auto-discover candidates via the notice-search API (forAjax_NoticeNews).",
    )
    parser.add_argument(
        "--search-word", action="append", dest="search_words",
        help="Search keyword for --discover (repeatable). Defaults to 轉蛋, 消費, and 維護開機公告.",
    )
    parser.add_argument(
        "--catalog", default=discover_module.CATALOG_ALL,
        help="news_catalog_id for --discover (default: 0 = all catalogs).",
    )
    parser.add_argument("--output", default="docs/data/items.json", help="Path to the items.json data file.")
    parser.add_argument(
        "--notices-output", default="docs/data/notices.json",
        help="Path to the notices.json analyzed-notice record file (tracks every notice_id ever analyzed).",
    )
    args = parser.parse_args(argv)

    if not args.urls and not args.discover:
        print("[ERROR] No URLs/IDs given and --discover not set.", file=sys.stderr)
        return 1

    items_existing = load_records(args.output)
    notices_existing = load_records(args.notices_output)
    had_failure = False

    if args.urls:
        # Manual input: never checked against notices_existing and always
        # force-reanalyzed -- naming an id explicitly means "analyze this one
        # now", regardless of whether it was already analyzed before.
        items_existing, notices_existing, manual_failure = _scrape_candidates(
            [(url_or_id, None, None) for url_or_id in args.urls],
            items_existing,
            notices_existing,
            args.output,
            args.notices_output,
            treat_empty_as_failure=True,
        )
        had_failure = had_failure or manual_failure

    if args.discover:
        search_words = args.search_words or DEFAULT_SEARCH_WORDS
        candidates = discover_module.discover_candidates(search_words, news_catalog_id=args.catalog)
        analyzed_ids = {notice["notice_id"] for notice in notices_existing}
        triples = [(candidate["url"], candidate["publish_date"], candidate.get("subject")) for candidate in candidates]
        new_triples = [triple for triple in triples if extract_numeric_id(triple[0]) not in analyzed_ids]
        skipped_count = len(triples) - len(new_triples)
        print(
            f"[DISCOVER] 候選公告共 {len(triples)} 筆，已跳過(已分析) {skipped_count} 筆，"
            f"新候選 {len(new_triples)} 筆 (search_word={search_words})",
            file=sys.stderr,
        )
        # search_word matches full announcement text, so plenty of candidates are
        # expected to turn out irrelevant -- that's normal noise, not a failure.
        items_existing, notices_existing, discover_failure = _scrape_candidates(
            new_triples,
            items_existing,
            notices_existing,
            args.output,
            args.notices_output,
            treat_empty_as_failure=False,
        )
        had_failure = had_failure or discover_failure

    save_records(args.output, items_existing)
    save_records(args.notices_output, notices_existing)
    return 1 if had_failure else 0


if __name__ == "__main__":
    sys.exit(main())
