"""Tests for api.py and analyze_ticker (db and SEC are mocked, fake numbers only)."""
import datetime
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg
from fastapi.testclient import TestClient

import api
import financial_analysis
import sec_data
from tests.fake_data import make_row

ENV = {"SEC_USER_AGENT": "Test User test@example.com"}
PLACEHOLDER = "Your Name your.email@example.com"


def saved_company(ticker="TEST"):
    """Build what db.load_company returns (fake numbers)."""
    return {
        "ticker": ticker,
        "cik": 1,
        "company_name": "Test Co",
        "revenue_tag": "Revenues",
        "operating_income_tag": None,
        "warnings": [],
        "fetched_at": datetime.datetime(2025, 1, 2, 3, 4, 5),
        "quarters": [{
            "fiscal_label": "FY2024 Q2",
            "period_start": datetime.date(2024, 4, 1),
            "period_end": datetime.date(2024, 6, 30),
            "revenue": 1000,
            "operating_income": 250,
            "flags": [],
        }],
    }


class TestApi(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)  # no startup db call

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_list_companies(self):
        rows = [{"ticker": "TEST", "company_name": "Test Co", "quarter_count": 8}]
        with patch("api.db.list_companies", return_value=rows):
            response = self.client.get("/companies")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), rows)

    def test_cached_read_skips_sec(self):
        with patch("api.db.load_company", return_value=saved_company()), \
                patch("api.analyze_ticker") as analyze:
            response = self.client.get("/companies/test/quarters")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "database")
        self.assertEqual(response.json()["ticker"], "TEST")
        analyze.assert_not_called()

    def test_dates_are_iso_strings(self):
        with patch("api.db.load_company", return_value=saved_company()):
            body = self.client.get("/companies/TEST/quarters").json()
        self.assertEqual(body["fetched_at"], "2025-01-02T03:04:05")
        self.assertEqual(body["quarters"][0]["period_end"], "2024-06-30")

    def test_first_read_fetches_and_saves(self):
        data = {"ticker": "TEST"}
        with patch.dict(os.environ, ENV), \
                patch("api.db.load_company", side_effect=[None, saved_company()]), \
                patch("api.db.save_company") as save, \
                patch("api.analyze_ticker", return_value=data) as analyze:
            response = self.client.get("/companies/TEST/quarters")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "sec")
        analyze.assert_called_once_with("TEST")
        save.assert_called_once_with(data)

    def test_refresh_always_fetches(self):
        with patch.dict(os.environ, ENV), \
                patch("api.db.load_company", return_value=saved_company()), \
                patch("api.db.save_company") as save, \
                patch("api.analyze_ticker", return_value={"ticker": "TEST"}) as analyze:
            response = self.client.post("/companies/TEST/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "sec")
        analyze.assert_called_once()
        save.assert_called_once()

    def test_bad_ticker_is_400(self):
        response = self.client.get("/companies/BAD$/quarters")
        self.assertEqual(response.status_code, 400)

    def test_unknown_ticker_is_404(self):
        with patch.dict(os.environ, ENV), \
                patch("api.db.load_company", return_value=None), \
                patch("api.analyze_ticker", side_effect=ValueError("not found")):
            response = self.client.get("/companies/ZZZZ/quarters")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "not found")

    def test_sec_failure_is_502(self):
        with patch.dict(os.environ, ENV), \
                patch("api.db.load_company", return_value=None), \
                patch("api.analyze_ticker", side_effect=RuntimeError("download failed")):
            response = self.client.get("/companies/TEST/quarters")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["detail"], "download failed")

    def test_database_down_is_503(self):
        with patch("api.db.load_company", side_effect=psycopg.OperationalError("no connection")):
            response = self.client.get("/companies/TEST/quarters")
        self.assertEqual(response.status_code, 503)
        self.assertIn("Database not reachable", response.json()["detail"])

    def test_missing_user_agent_is_500(self):
        with patch.dict(os.environ, {"SEC_USER_AGENT": ""}), \
                patch.object(sec_data, "SEC_USER_AGENT", PLACEHOLDER), \
                patch("api.db.load_company", return_value=None), \
                patch("api.analyze_ticker") as analyze:
            response = self.client.get("/companies/TEST/quarters")
        self.assertEqual(response.status_code, 500)
        self.assertIn("SEC_USER_AGENT", response.json()["detail"])
        analyze.assert_not_called()


def fake_company_data(count):
    """Build fake get_company_data output with count quarterly rows."""
    rows = []
    for i in range(count):
        month = (i % 4) * 3 + 3
        year = 2020 + i // 4
        day = 31 if month in (3, 12) else 30
        rows.append(make_row(f"{year}-{month:02d}-{day}", 1000 + i * 100, 200 + i * 10))
    return {
        "ticker": "TEST",
        "cik": 1,
        "company_name": "Test Co",
        "revenue_tag": "Revenues",
        "operating_income_tag": "OperatingIncomeLoss",
        "rows": rows,
        "warnings": ["sec warning"],
    }


class TestAnalyzeTicker(unittest.TestCase):
    def test_keeps_last_eight_rows_with_metrics(self):
        with patch("financial_analysis.get_company_data", return_value=fake_company_data(12)):
            data = financial_analysis.analyze_ticker("TEST")
        self.assertEqual(len(data["rows"]), 8)
        self.assertEqual(data["rows"][-1]["revenue"], 2100)
        self.assertIsNotNone(data["rows"][0]["yoy_growth"])  # older rows feed YoY

    def test_merges_warnings(self):
        with patch("financial_analysis.get_company_data", return_value=fake_company_data(3)), \
                patch("financial_analysis.run_all_checks", return_value=["check warning"]):
            data = financial_analysis.analyze_ticker("TEST")
        self.assertEqual(data["warnings"], ["sec warning", "check warning"])


if __name__ == "__main__":
    unittest.main()
