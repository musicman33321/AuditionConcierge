"""Daily sync for AuditionConcierge.

Rules (see docs/data-storage-draft.md):
- fetch (or take postings already fetched) -> parse into role records
- upsert by stable role_id, hashing normalized fields
- embed only new or changed roles; unchanged roles are skipped and
  are never re-embedded
- remove roles whose deadline has passed, and roles that have
  disappeared from the feed (the feed lists every active audition),
  moving them to the store's archive instead of active search
"""

import argparse
import json
import sys
from datetime import date

from .parse import fetch_disney_auditions, parse_feed_xml, parse_posting
from .store import InMemoryStore, StubEmbedding


def _deadline_of(role):
    value = role.get("deadline")
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        from datetime import datetime

        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def sync_postings(postings, store, embedder, today=None, archive_missing=True):
    today = today or date.today()
    stats = {
        "added": 0, "updated": 0, "skipped": 0,
        "removed_expired": 0, "removed_disappeared": 0,
        "embedded": 0, "total_active": 0,
    }
    seen_ids = set()
    for posting in postings:
        for role in parse_posting(posting):
            role_id = role["role_id"]
            seen_ids.add(role_id)
            existing = store.get(role_id)
            role["last_seen"] = str(today)
            if existing is None:
                role["first_seen"] = str(today)
                role["embedding"] = embedder.embed(role["clean_text"])
                stats["embedded"] += 1
                store.insert(role)
                stats["added"] += 1
            elif existing.get("field_hash") != role["field_hash"]:
                role["first_seen"] = existing.get("first_seen") or str(today)
                role["embedding"] = embedder.embed(role["clean_text"])
                stats["embedded"] += 1
                store.update(role)
                stats["updated"] += 1
            else:
                stats["skipped"] += 1
    for role in list(store.all_active()):
        deadline = _deadline_of(role)
        if deadline is not None and deadline < today:
            store.remove(role["role_id"], "expired")
            stats["removed_expired"] += 1
        elif archive_missing and role["role_id"] not in seen_ids:
            store.remove(role["role_id"], "disappeared")
            stats["removed_disappeared"] += 1
    stats["total_active"] = len(store.all_active())
    return stats


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sync Disney auditions into the store.")
    parser.add_argument("--fixture", help="Path to a fixture feed XML file (no live fetch).")
    parser.add_argument("--live", action="store_true", help="Fetch the live Disney feed.")
    parser.add_argument("--today", help="Today as YYYY-MM-DD (default: real today).")
    args = parser.parse_args(argv)
    today = None
    if args.today:
        from datetime import datetime

        today = datetime.strptime(args.today, "%Y-%m-%d").date()
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as fh:
            postings = parse_feed_xml(fh.read())
    elif args.live:
        postings = fetch_disney_auditions()
    else:
        parser.error("pass --fixture <file> or --live")
    store = InMemoryStore()
    embedder = StubEmbedding()
    stats = sync_postings(postings, store, embedder, today=today)
    print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
