"""Tests for sec_data.py (no network, fake numbers only)."""
import datetime
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sec_data
from tests import fake_data
from tests.fake_data import make_entry, make_facts, make_record


def d(text):
    return datetime.date.fromisoformat(text)


class TestNormalizeTicker(unittest.TestCase):
    def test_strips_and_uppercases(self):
        self.assertEqual(sec_data.normalize_ticker("  aapl "), "AAPL")

    def test_dot_becomes_dash(self):
        self.assertEqual(sec_data.normalize_ticker("brk.b"), "BRK-B")

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            sec_data.normalize_ticker("")
        with self.assertRaises(ValueError):
            sec_data.normalize_ticker("   ")

    def test_bad_characters_raise(self):
        for bad in ("AA PL", "AAPL!", "A/B", "$AAPL"):
            with self.assertRaises(ValueError, msg=bad):
                sec_data.normalize_ticker(bad)

    def test_too_long_raises(self):
        with self.assertRaises(ValueError):
            sec_data.normalize_ticker("ABCDEFGHIJK")  # 11 chars
        self.assertEqual(sec_data.normalize_ticker("ABCDEFGHIJ"), "ABCDEFGHIJ")


class TestUserAgent(unittest.TestCase):
    def test_env_var_used(self):
        with mock.patch.dict(os.environ, {"SEC_USER_AGENT": "Test Person test@example.com"}):
            self.assertEqual(sec_data.get_user_agent(), "Test Person test@example.com")


class TestNetworkHelpers(unittest.TestCase):
    def test_lookup_cik_found(self):
        ticker_map = {"0": {"cik_str": 1, "ticker": "TEST", "title": "Test Co"}}
        with mock.patch.object(sec_data, "_get_json", return_value=ticker_map):
            self.assertEqual(sec_data.lookup_cik("TEST", "Test Person test@example.com"),
                             (1, "Test Co"))

    def test_lookup_cik_missing(self):
        ticker_map = {"0": {"cik_str": 1, "ticker": "TEST", "title": "Test Co"}}
        with mock.patch.object(sec_data, "_get_json", return_value=ticker_map):
            with self.assertRaises(ValueError):
                sec_data.lookup_cik("NOPE", "Test Person test@example.com")

    def test_fetch_company_facts_pads_cik(self):
        with mock.patch.object(sec_data, "_get_json", return_value={"facts": {}}) as fake_get:
            result = sec_data.fetch_company_facts(1, "Test Person test@example.com")
        self.assertEqual(result, {"facts": {}})
        self.assertIn("CIK0000000001.json", str(fake_get.call_args))


class TestChooseTag(unittest.TestCase):
    def test_picks_most_recent_tag(self):
        facts = make_facts({
            "Revenues": [make_entry("2022-01-01", "2022-03-31", 1000, "2022-05-01")],
            "SalesRevenueNet": [make_entry("2024-01-01", "2024-03-31", 1000, "2024-05-01")],
        })
        tag, warnings = sec_data.choose_tag(facts, ["Revenues", "SalesRevenueNet"])
        self.assertEqual(tag, "SalesRevenueNet")

    def test_tie_goes_to_earlier_candidate(self):
        entry = make_entry("2024-01-01", "2024-03-31", 1000, "2024-05-01")
        facts = make_facts({"Revenues": [entry], "SalesRevenueNet": [dict(entry)]})
        tag, _ = sec_data.choose_tag(facts, ["Revenues", "SalesRevenueNet"])
        self.assertEqual(tag, "Revenues")

    def test_no_candidates_present(self):
        facts = make_facts({"Other": [make_entry("2024-01-01", "2024-03-31", 1000, "2024-05-01")]})
        tag, warnings = sec_data.choose_tag(facts, ["Revenues"])
        self.assertIsNone(tag)
        self.assertTrue(len(warnings) >= 1)

    def test_non_usd_unit_warns(self):
        facts = make_facts(
            {"Revenues": [make_entry("2024-01-01", "2024-03-31", 1000, "2024-05-01")]},
            unit="EUR",
        )
        tag, warnings = sec_data.choose_tag(facts, ["Revenues"])
        self.assertIsNone(tag)
        self.assertTrue(any("EUR" in w for w in warnings))


class TestChooseTagCompleteness(unittest.TestCase):
    def test_prefers_tag_with_more_recent_quarters_on_tie(self):
        # same latest end, but only the second tag has quarterly data
        annual_only = [make_entry("2024-01-01", "2024-12-31", 4000, "2025-02-01", "10-K", 2024, "FY")]
        quarterly = fake_data.standard_year_entries()
        facts = make_facts({"Revenues": annual_only, "SalesRevenueNet": quarterly})
        tag, _ = sec_data.choose_tag(facts, ["Revenues", "SalesRevenueNet"])
        self.assertEqual(tag, "SalesRevenueNet")


class TestExtractQuarters(unittest.TestCase):
    def test_plain_quarters(self):
        facts = make_facts({"Revenues": fake_data.standard_year_entries()})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        q1 = records[d("2024-03-31")]
        self.assertEqual(q1["value"], 900)
        self.assertEqual(q1["period_start"], d("2024-01-01"))
        self.assertEqual(q1["fiscal_year"], 2024)
        self.assertEqual(q1["fiscal_period"], "Q1")
        self.assertFalse(q1["is_derived"])
        self.assertFalse(q1["was_restated"])

    def test_derives_q4(self):
        facts = make_facts({"Revenues": fake_data.standard_year_entries()})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        q4 = records[d("2024-12-31")]
        self.assertEqual(q4["value"], 1000)  # 4000 - (900 + 1000 + 1100)
        self.assertTrue(q4["is_derived"])
        self.assertEqual(q4["fiscal_period"], "Q4")
        self.assertEqual(q4["fiscal_year"], 2024)
        self.assertEqual(q4["period_start"], d("2024-10-01"))
        self.assertTrue(any("derived" in n for n in q4["notes"]))

    def test_cannot_derive_q4_when_quarter_missing(self):
        entries = [e for e in fake_data.standard_year_entries() if e["end"] != "2024-06-30"]
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        q4 = records[d("2024-12-31")]
        self.assertIsNone(q4["value"])  # flagged, never guessed
        self.assertEqual(q4["fiscal_period"], "Q4")
        self.assertTrue(any("Q4 not calculated" in n for n in q4["notes"]))

    def test_no_q4_row_when_year_has_no_quarters(self):
        annual = [e for e in fake_data.standard_year_entries() if e["form"] == "10-K"]
        facts = make_facts({"Revenues": annual})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        self.assertEqual(records, {})

    def test_missing_q4_row_flows_through(self):
        entries = [e for e in fake_data.standard_year_entries() if e["end"] != "2024-06-30"]
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        rows = sec_data.build_quarter_rows(records, {})
        last = rows[-1]
        self.assertIsNone(last["revenue"])
        self.assertTrue(any("Q4 not calculated" in f for f in last["flags"]))

    def test_restatement_uses_latest_value_and_earliest_label(self):
        entries = fake_data.standard_year_entries()
        # same Q1 period shown again as a comparative in a later filing, new value
        entries.append(make_entry("2024-01-01", "2024-03-31", 950, "2025-05-01",
                                  "10-Q", 2025, "Q1"))
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        q1 = records[d("2024-03-31")]
        self.assertEqual(q1["value"], 950)
        self.assertEqual(q1["filed"], d("2025-05-01"))
        self.assertEqual(q1["fiscal_year"], 2024)
        self.assertEqual(q1["fiscal_period"], "Q1")
        self.assertTrue(q1["was_restated"])
        self.assertTrue(any("restated" in n for n in q1["notes"]))

    def test_same_value_in_later_filing_is_not_restated(self):
        entries = fake_data.standard_year_entries()
        entries.append(make_entry("2024-01-01", "2024-03-31", 900, "2025-05-01",
                                  "10-Q", 2025, "Q1"))
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        self.assertFalse(records[d("2024-03-31")]["was_restated"])

    def test_ignores_six_and_nine_month_ytd(self):
        entries = fake_data.standard_year_entries()
        entries.append(make_entry("2024-01-01", "2024-06-30", 1900, "2024-08-01", "10-Q", 2024, "Q2"))
        entries.append(make_entry("2024-01-01", "2024-09-30", 3000, "2024-11-01", "10-Q", 2024, "Q3"))
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        self.assertEqual(sorted(records.keys()),
                         [d("2024-03-31"), d("2024-06-30"), d("2024-09-30"), d("2024-12-31")])
        self.assertEqual(records[d("2024-06-30")]["value"], 1000)
        self.assertEqual(records[d("2024-09-30")]["value"], 1100)

    def test_ignores_8k(self):
        entries = fake_data.standard_year_entries()
        entries.append(make_entry("2025-01-01", "2025-03-31", 1200, "2025-04-15", "8-K", 2025, "Q1"))
        facts = make_facts({"Revenues": entries})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        self.assertNotIn(d("2025-03-31"), records)

    def test_skips_entries_without_start(self):
        entry = make_entry("2024-01-01", "2024-03-31", 900, "2024-05-01")
        del entry["start"]
        facts = make_facts({"Revenues": [entry]})
        records, _ = sec_data.extract_quarters(facts, "Revenues")
        self.assertEqual(records, {})

    def test_bad_value_skipped_with_warning(self):
        entry = make_entry("2024-01-01", "2024-03-31", "not a number", "2024-05-01")
        facts = make_facts({"Revenues": [entry]})
        records, warnings = sec_data.extract_quarters(facts, "Revenues")
        self.assertEqual(records, {})
        self.assertTrue(len(warnings) >= 1)


class TestBuildQuarterRows(unittest.TestCase):
    def test_flags_missing_operating_income(self):
        revenue = {d("2024-03-31"): make_record("2024-03-31", 1000)}
        rows = sec_data.build_quarter_rows(revenue, {})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["revenue"], 1000)
        self.assertIsNone(rows[0]["operating_income"])
        self.assertIn("operating income missing for this quarter", rows[0]["flags"])
        self.assertEqual(rows[0]["fiscal_label"], "FY2024 Q1")

    def test_flags_missing_revenue(self):
        opinc = {d("2024-03-31"): make_record("2024-03-31", 100)}
        rows = sec_data.build_quarter_rows({}, opinc)
        self.assertIsNone(rows[0]["revenue"])
        self.assertIn("revenue missing for this quarter", rows[0]["flags"])

    def test_union_sorted_and_notes_prefixed(self):
        revenue = {
            d("2024-06-30"): make_record("2024-06-30", 1100, fiscal_period="Q2",
                                         notes=["restated: test note"]),
            d("2024-03-31"): make_record("2024-03-31", 1000),
        }
        opinc = {d("2024-09-30"): make_record("2024-09-30", 200, fiscal_period="Q3")}
        rows = sec_data.build_quarter_rows(revenue, opinc)
        self.assertEqual([r["period_end"] for r in rows],
                         [d("2024-03-31"), d("2024-06-30"), d("2024-09-30")])
        self.assertIn("revenue: restated: test note", rows[1]["flags"])
        self.assertEqual(rows[2]["fiscal_label"], "FY2024 Q3")


class TestGetCompanyData(unittest.TestCase):
    def test_end_to_end_with_patched_network(self):
        facts = make_facts({"Revenues": fake_data.standard_year_entries()})
        with mock.patch.object(sec_data, "get_user_agent", return_value="Test Person test@example.com"), \
             mock.patch.object(sec_data, "lookup_cik", return_value=(1, "Test Co")), \
             mock.patch.object(sec_data, "fetch_company_facts", return_value=facts):
            data = sec_data.get_company_data("TEST")
        for key in ("ticker", "cik", "company_name", "revenue_tag",
                    "operating_income_tag", "rows", "warnings"):
            self.assertIn(key, data)
        self.assertEqual(data["revenue_tag"], "Revenues")
        self.assertIsNone(data["operating_income_tag"])
        self.assertEqual(len(data["rows"]), 4)

    def test_no_revenue_tag_raises(self):
        facts = make_facts({"Other": [make_entry("2024-01-01", "2024-03-31", 1000, "2024-05-01")]})
        with mock.patch.object(sec_data, "get_user_agent", return_value="Test Person test@example.com"), \
             mock.patch.object(sec_data, "lookup_cik", return_value=(1, "Test Co")), \
             mock.patch.object(sec_data, "fetch_company_facts", return_value=facts):
            with self.assertRaises(RuntimeError):
                sec_data.get_company_data("TEST")


if __name__ == "__main__":
    unittest.main()
