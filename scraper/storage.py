"""JSON-backed storage for scraped item and notice records, keyed by notice_id."""
from __future__ import annotations

import json
import os
from typing import Dict, List


def load_records(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    return json.loads(content) if content else []


def save_records(path: str, records: List[Dict]) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def upsert_items_by_notice_id(existing: List[Dict], notice_id: int, new_items: List[Dict]) -> List[Dict]:
    """Replace all item records for `notice_id` with `new_items`.

    Re-scraping the same notice overwrites its previous items (the official
    post may have corrected a probability or item list), while items from
    other notice_ids are left untouched.
    """
    kept = [r for r in existing if r.get("notice_id") != notice_id]
    kept.extend(new_items)
    return kept


def upsert_by_notice_id(existing: List[Dict], notice_id: int, new_record: Dict) -> List[Dict]:
    """Replace the analyzed-notice record for `notice_id` with `new_record`.

    notices.json tracks one outcome per announcement, so there's at most one
    record per notice_id -- re-analyzing always overwrites it.
    """
    kept = [r for r in existing if r.get("notice_id") != notice_id]
    kept.append(new_record)
    return kept
