"""Tests for the AuditionConcierge production store slice.

Run from the repo root:  python3 -m unittest discover -s tests -v
No network, database, or paid API is used. Embeddings are the
deterministic stub in app.store.StubEmbedding.
"""

import os
import unittest
from datetime import date

from app.heights import parse_height_range, parse_single_height, to_cm
from app.parse import clean_html_description, parse_feed_xml, parse_posting
from app.query import llm_context, search_roles
from app.store import InMemoryStore, StubEmbedding
from app.sync import sync_postings

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
TODAY = date(2026, 10, 30)


def load_fixture(name):
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return parse_feed_xml(fh.read())


class TestHeights(unittest.TestCase):
    def test_feet_inches(self):
        self.assertEqual(parse_single_height("5'4\""), 64)
        self.assertEqual(parse_height_range("5'2\"-5'6\""), (62, 66))

    def test_plain_inches(self):
        self.assertEqual(parse_single_height("64 in"), 64)
        self.assertEqual(parse_height_range("60-66 inches"), (60, 66))

    def test_centimeters(self):
        self.assertEqual(parse_single_height("162 cm"), 63.8)
        self.assertEqual(parse_height_range("152-168 cm"), (59.8, 66.1))

    def test_mixed_units_range(self):
        self.assertEqual(parse_height_range("5'4\" to 162 cm"), (63.8, 64.0))

    def test_missing_height(self):
        self.assertEqual(parse_height_range("No height listed here"), (None, None))
        self.assertIsNone(parse_single_height(""))

    def test_cm_display_conversion(self):
        self.assertEqual(to_cm(64), 162.6)


class TestParsing(unittest.TestCase):
    def test_clean_html_matches_notebook(self):
        cleaned = clean_html_description("<p>Hello</p><script>bad()</script><p>World</p>")
        self.assertIn("Hello", cleaned)
        self.assertIn("World", cleaned)
        self.assertNotIn("bad()", cleaned)

    def test_role_splitting_different_heights(self):
        postings = load_fixture("feed_v1.xml")
        roles = []
        for posting in postings:
            if posting["audition_id"] == "aud-1":
                roles = parse_posting(posting)
        self.assertEqual(len(roles), 2)
        by_name = {r["role_name"]: r for r in roles}
        self.assertEqual(
            (by_name["Mickey Mouse"]["height_min_in"], by_name["Mickey Mouse"]["height_max_in"]),
            (60, 66),
        )
        self.assertEqual(
            (by_name["Goofy"]["height_min_in"], by_name["Goofy"]["height_max_in"]),
            (72, 75),
        )
        self.assertEqual(by_name["Mickey Mouse"]["posting_id"], by_name["Goofy"]["posting_id"])
        self.assertEqual(by_name["Goofy"]["equity_status"], "equity")
        self.assertEqual(by_name["Mickey Mouse"]["equity_status"], "non-equity")

    def test_centimeter_posting_becomes_inches(self):
        postings = load_fixture("feed_v1.xml")
        roles = [r for p in postings if p["audition_id"] == "aud-2" for r in parse_posting(p)]
        self.assertEqual(len(roles), 1)
        self.assertEqual((roles[0]["height_min_in"], roles[0]["height_max_in"]), (63.8, 63.8))
        self.assertEqual(roles[0]["parse_confidence"], "high")


class TestSync(unittest.TestCase):
    def test_fixture_sync_add_update_skip_expire_disappear(self):
        store = InMemoryStore()
        embedder = StubEmbedding()
        stats1 = sync_postings(load_fixture("feed_v1.xml"), store, embedder, today=TODAY)
        # 4 roles parsed; the 2026-10-01 role expires on the same run.
        self.assertEqual(stats1["added"], 4)
        self.assertEqual(stats1["removed_expired"], 1)
        self.assertEqual(stats1["total_active"], 3)
        self.assertEqual(embedder.calls, 4)

        stats2 = sync_postings(load_fixture("feed_v2.xml"), store, embedder, today=TODAY)
        # Goofy changed (re-embedded), new singer added, Mickey + dancer skipped.
        self.assertEqual(stats2["added"], 1)
        self.assertEqual(stats2["updated"], 1)
        self.assertEqual(stats2["skipped"], 2)
        self.assertEqual(stats2["embedded"], 2)
        self.assertEqual(embedder.calls, 6)
        self.assertEqual(stats2["total_active"], 4)
        goofy = store.get("aud-1-role-goofy")
        self.assertEqual(goofy["height_max_in"], 76)  # 6'4"
        self.assertIsNone(store.get("aud-3-role-old-audition"))

    def test_disappeared_role_removed(self):
        store = InMemoryStore()
        embedder = StubEmbedding()
        sync_postings(load_fixture("feed_v1.xml"), store, embedder, today=TODAY)
        # Feed with only aud-2: everything else has disappeared.
        postings = [p for p in load_fixture("feed_v1.xml") if p["audition_id"] == "aud-2"]
        stats = sync_postings(postings, store, embedder, today=TODAY)
        self.assertEqual(stats["removed_disappeared"], 2)
        self.assertEqual([r["role_name"] for r in store.all_active()], ["Dancer Auditions"])
        self.assertEqual(len(store.archived), 3)  # expired + 2 disappeared


class TestQuery(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStore()
        self.embedder = StubEmbedding()
        sync_postings(load_fixture("feed_v1.xml"), self.store, self.embedder, today=TODAY)

    def test_height_overlap(self):
        names = [r["role_name"] for r in search_roles(self.store, height_in=64)]
        self.assertIn("Mickey Mouse", names)
        self.assertIn("Dancer Auditions", names)
        self.assertNotIn("Goofy", names)

    def test_equity_filter(self):
        names = [r["role_name"] for r in search_roles(self.store, equity="equity")]
        self.assertEqual(names, ["Goofy"])

    def test_deadline_filter(self):
        names = [
            r["role_name"]
            for r in search_roles(self.store, deadline_after=date(2026, 11, 15))
        ]
        self.assertEqual(names, ["Dancer Auditions"])

    def test_only_filtered_records_reach_llm(self):
        results = search_roles(self.store, height_in=64, equity="non-equity")
        context = llm_context(results)
        self.assertIn("Mickey Mouse", context)
        self.assertIn("Dancer Auditions", context)
        self.assertNotIn("Goofy", context)


class TestEndToEndFixture(unittest.TestCase):
    def test_fixture_sync_then_query_no_network(self):
        store = InMemoryStore()
        embedder = StubEmbedding()
        stats = sync_postings(load_fixture("feed_v1.xml"), store, embedder, today=TODAY)
        self.assertEqual(stats["total_active"], 3)
        results = search_roles(
            store, height_in=64, equity="non-equity", deadline_after=TODAY
        )
        self.assertEqual(len(results), 2)
        self.assertIn("60-66 in", llm_context(results))


if __name__ == "__main__":
    unittest.main()
