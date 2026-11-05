"""Tests for checks.py (fake numbers only)."""
import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import checks
from tests.fake_data import make_row


def d(text):
    return datetime.date.fromisoformat(text)


class TestGapHelpers(unittest.TestCase):
    def test_is_consecutive_range(self):
        self.assertTrue(checks.is_consecutive(d("2024-03-31"), d("2024-06-30")))
        base = d("2024-01-01")
        one_day = datetime.timedelta(days=1)
        self.assertTrue(checks.is_consecutive(base, base + 75 * one_day))
        self.assertTrue(checks.is_consecutive(base, base + 105 * one_day))
        self.assertFalse(checks.is_consecutive(base, base + 74 * one_day))
        self.assertFalse(checks.is_consecutive(base, base + 106 * one_day))

    def test_is_year_apart_range(self):
        base = d("2023-01-01")
        one_day = datetime.timedelta(days=1)
        self.assertTrue(checks.is_year_apart(base, base + 350 * one_day))
        self.assertTrue(checks.is_year_apart(base, base + 380 * one_day))
        self.assertFalse(checks.is_year_apart(base, base + 349 * one_day))
        self.assertFalse(checks.is_year_apart(base, base + 381 * one_day))
        self.assertTrue(checks.is_year_apart(d("2023-03-31"), d("2024-03-31")))


class TestMissingQuarters(unittest.TestCase):
    def test_gap_is_flagged_on_later_row(self):
        rows = [make_row("2024-03-31", 1000, 100), make_row("2024-12-31", 1100, 110)]
        days = (d("2024-12-31") - d("2024-03-31")).days
        checks.check_missing_quarters(rows)
        self.assertEqual(rows[0]["flags"], [])
        self.assertTrue(any("gap of {} days".format(days) in f for f in rows[1]["flags"]))

    def test_no_gap_no_flag(self):
        rows = [make_row("2024-03-31", 1000, 100), make_row("2024-06-30", 1100, 110),
                make_row("2024-09-30", 1200, 120)]
        checks.check_missing_quarters(rows)
        for row in rows:
            self.assertEqual(row["flags"], [])


class TestValueChecks(unittest.TestCase):
    def test_zero_revenue_flagged(self):
        rows = [make_row("2024-03-31", 0, 100)]
        checks.check_values(rows)
        self.assertIn("revenue is zero or negative, growth and margin not calculated",
                      rows[0]["flags"])

    def test_negative_revenue_flagged(self):
        rows = [make_row("2024-03-31", -1000, -100)]
        checks.check_values(rows)
        self.assertIn("revenue is zero or negative, growth and margin not calculated",
                      rows[0]["flags"])

    def test_operating_income_larger_than_revenue(self):
        rows = [make_row("2024-03-31", 1000, 2000), make_row("2024-06-30", 1000, -2000)]
        checks.check_values(rows)
        for row in rows:
            self.assertIn("operating income larger than revenue, check filing", row["flags"])

    def test_normal_row_not_flagged_and_numbers_unchanged(self):
        rows = [make_row("2024-03-31", 1000, 200)]
        checks.check_values(rows)
        self.assertEqual(rows[0]["flags"], [])
        self.assertEqual(rows[0]["revenue"], 1000)
        self.assertEqual(rows[0]["operating_income"], 200)

    def test_missing_values_do_not_crash(self):
        rows = [make_row("2024-03-31", None, None), make_row("2024-06-30", 1000, None)]
        checks.check_values(rows)

    def test_enough_quarters(self):
        rows = [make_row("2024-03-31", 1000, 100)]
        self.assertTrue(len(checks.check_enough_quarters(rows, 8)) >= 1)
        self.assertEqual(checks.check_enough_quarters(rows, 1), [])


class TestRunAllChecks(unittest.TestCase):
    def test_collects_warnings_and_flags(self):
        rows = [make_row("2024-03-31", 0, 100), make_row("2024-12-31", 1000, 100)]
        warnings = checks.run_all_checks(rows, 8)
        self.assertIsInstance(warnings, list)
        self.assertEqual(len(warnings), 1)  # not enough quarters
        self.assertTrue(rows[0]["flags"])  # zero revenue
        self.assertTrue(any("gap" in f for f in rows[1]["flags"]))

    def test_flags_not_duplicated_on_rerun(self):
        rows = [make_row("2024-03-31", 0, 100)]
        checks.run_all_checks(rows, 1)
        checks.run_all_checks(rows, 1)
        self.assertEqual(len(rows[0]["flags"]), 1)


if __name__ == "__main__":
    unittest.main()
