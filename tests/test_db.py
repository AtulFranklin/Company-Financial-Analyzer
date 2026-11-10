"""Tests for db.py (needs a real Postgres, set TEST_DATABASE_URL to run)."""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db
from tests.fake_data import make_row

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
TEST_TICKERS = ["TESTA", "TESTB"]


def make_data(ticker="TESTA", rows=None):
    """Build a fake analyze_ticker() result."""
    if rows is None:
        first = make_row("2024-03-31", 1000.4, 100.6, "FY2024 Q1")
        second = make_row("2024-06-30", 1100, None, "FY2024 Q2")
        second["qoq_growth"] = 0.1
        second["flags"] = ["revenue jump", "check margin"]
        rows = [second, first]
    return {
        "ticker": ticker,
        "cik": 1,
        "company_name": "Test Co",
        "revenue_tag": "Revenues",
        "operating_income_tag": None,
        "rows": rows,
        "warnings": ["warning one", "warning two"],
    }


def delete_test_rows():
    """Remove the fake tickers from the test database."""
    with db.get_connection() as conn:
        conn.execute("DELETE FROM companies WHERE ticker = ANY(%s)", (TEST_TICKERS,))


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL not set")
class TestDatabase(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DATABASE_URL": TEST_DATABASE_URL})
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()
        delete_test_rows()

    def tearDown(self):
        delete_test_rows()

    def test_round_trip(self):
        db.save_company(make_data())
        loaded = db.load_company("TESTA")
        self.assertEqual(loaded["ticker"], "TESTA")
        self.assertEqual(loaded["cik"], 1)
        self.assertEqual(loaded["company_name"], "Test Co")
        self.assertEqual(loaded["revenue_tag"], "Revenues")
        self.assertIsNone(loaded["operating_income_tag"])
        self.assertEqual(loaded["warnings"], ["warning one", "warning two"])
        self.assertIsInstance(loaded["fetched_at"], datetime.datetime)
        self.assertEqual(len(loaded["quarters"]), 2)

    def test_quarters_oldest_first_with_types(self):
        db.save_company(make_data())
        first, second = db.load_company("TESTA")["quarters"]
        self.assertEqual(first["period_end"], datetime.date(2024, 3, 31))
        self.assertEqual(first["period_start"], datetime.date(2024, 1, 1))
        self.assertIsInstance(first["period_end"], datetime.date)
        self.assertEqual(second["period_end"], datetime.date(2024, 6, 30))
        self.assertEqual(first["fiscal_label"], "FY2024 Q1")
        self.assertEqual(second["flags"], ["revenue jump", "check margin"])
        self.assertEqual(first["flags"], [])
        self.assertEqual(second["qoq_growth"], 0.1)

    def test_none_values_stay_none(self):
        db.save_company(make_data())
        first, second = db.load_company("TESTA")["quarters"]
        self.assertIsNone(first["qoq_growth"])
        self.assertIsNone(first["operating_margin"])
        self.assertIsNone(second["operating_income"])

    def test_money_rounded_to_int(self):
        db.save_company(make_data())
        first = db.load_company("TESTA")["quarters"][0]
        self.assertEqual(first["revenue"], 1000)
        self.assertEqual(first["operating_income"], 101)
        self.assertIsInstance(first["revenue"], int)

    def test_missing_metric_keys(self):
        row = {
            "period_end": datetime.date(2024, 3, 31),
            "fiscal_label": "FY2024 Q1",
            "revenue": 1000,
        }
        db.save_company(make_data(rows=[row]))
        quarter = db.load_company("TESTA")["quarters"][0]
        self.assertEqual(quarter["revenue"], 1000)
        self.assertIsNone(quarter["period_start"])
        self.assertIsNone(quarter["operating_income"])
        self.assertEqual(quarter["flags"], [])

    def test_second_save_replaces_quarters(self):
        db.save_company(make_data())
        newer = make_row("2024-09-30", 1200, 120, "FY2024 Q3")
        data = make_data(rows=[newer])
        data["company_name"] = "Test Co Renamed"
        data["warnings"] = []
        db.save_company(data)
        loaded = db.load_company("TESTA")
        self.assertEqual(len(loaded["quarters"]), 1)
        self.assertEqual(loaded["quarters"][0]["fiscal_label"], "FY2024 Q3")
        self.assertEqual(loaded["company_name"], "Test Co Renamed")
        self.assertEqual(loaded["warnings"], [])

    def test_second_save_updates_fetched_at(self):
        db.save_company(make_data())
        before = db.load_company("TESTA")["fetched_at"]
        db.save_company(make_data())
        after = db.load_company("TESTA")["fetched_at"]
        self.assertGreater(after, before)

    def test_load_unknown_ticker(self):
        self.assertIsNone(db.load_company("TESTZ"))

    def test_list_companies(self):
        db.save_company(make_data("TESTB", rows=[make_row("2024-03-31", 1000, 100)]))
        db.save_company(make_data("TESTA"))
        db.save_company(make_data("TESTC", rows=[]))
        try:
            listed = [c for c in db.list_companies() if c["ticker"].startswith("TEST")]
        finally:
            with db.get_connection() as conn:
                conn.execute("DELETE FROM companies WHERE ticker = 'TESTC'")
        self.assertEqual([c["ticker"] for c in listed], ["TESTA", "TESTB", "TESTC"])
        self.assertEqual([c["quarter_count"] for c in listed], [2, 1, 0])
        self.assertEqual(listed[0]["company_name"], "Test Co")
        self.assertIsInstance(listed[0]["fetched_at"], datetime.datetime)


class TestDatabaseUrl(unittest.TestCase):
    def test_default(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("DATABASE_URL", None)
            self.assertEqual(db.get_database_url(), db.DEFAULT_DATABASE_URL)

    def test_from_env(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://example/x"}):
            self.assertEqual(db.get_database_url(), "postgresql://example/x")


if __name__ == "__main__":
    unittest.main()
