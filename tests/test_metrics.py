"""Tests for metrics.py (fake numbers only)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import metrics
from tests.fake_data import make_row


class TestPercentChange(unittest.TestCase):
    def test_basic_growth_is_decimal(self):
        self.assertAlmostEqual(metrics.percent_change(1100, 1000), 0.1)
        self.assertAlmostEqual(metrics.percent_change(900, 1000), -0.1)

    def test_zero_base_is_none(self):
        self.assertIsNone(metrics.percent_change(1000, 0))

    def test_negative_base_is_none(self):
        self.assertIsNone(metrics.percent_change(1000, -500))

    def test_none_inputs(self):
        self.assertIsNone(metrics.percent_change(None, 1000))
        self.assertIsNone(metrics.percent_change(1000, None))


class TestGrowth(unittest.TestCase):
    def test_qoq_consecutive(self):
        rows = [make_row("2024-03-31", 1000, 100), make_row("2024-06-30", 1100, 110)]
        metrics.add_growth(rows)
        self.assertIsNone(rows[0]["qoq_growth"])
        self.assertAlmostEqual(rows[1]["qoq_growth"], 0.1)

    def test_qoq_skipped_across_gap(self):
        rows = [make_row("2024-03-31", 1000, 100), make_row("2024-12-31", 1500, 150)]
        metrics.add_growth(rows)
        self.assertIsNone(rows[1]["qoq_growth"])

    def test_yoy_matched_by_date(self):
        rows = [
            make_row("2023-03-31", 1000, 100),
            make_row("2023-06-30", 1100, 110),
            make_row("2023-09-30", 1200, 120),
            make_row("2023-12-31", 1300, 130),
            make_row("2024-03-31", 1500, 150),
        ]
        metrics.add_growth(rows)
        self.assertAlmostEqual(rows[4]["yoy_growth"], 0.5)  # vs 2023-03-31
        self.assertAlmostEqual(rows[4]["qoq_growth"], 1500 / 1300 - 1)
        self.assertIsNone(rows[0]["yoy_growth"])

    def test_yoy_none_without_matching_quarter(self):
        # missing 2023-03-31, so the newest row has no year-ago match
        rows = [make_row("2023-06-30", 1100, 110), make_row("2024-03-31", 1500, 150)]
        metrics.add_growth(rows)
        self.assertIsNone(rows[1]["yoy_growth"])

    def test_zero_current_revenue_gives_none(self):
        rows = [make_row("2024-03-31", 1000, 100), make_row("2024-06-30", 0, -50)]
        metrics.add_growth(rows)
        self.assertIsNone(rows[1]["qoq_growth"])

    def test_zero_base_revenue_gives_none(self):
        rows = [make_row("2024-03-31", 0, -50), make_row("2024-06-30", 1000, 100)]
        metrics.add_growth(rows)
        self.assertIsNone(rows[1]["qoq_growth"])


class TestMargin(unittest.TestCase):
    def test_margin_is_decimal(self):
        rows = [make_row("2024-03-31", 1000, 250)]
        metrics.add_operating_margin(rows)
        self.assertAlmostEqual(rows[0]["operating_margin"], 0.25)

    def test_negative_operating_income(self):
        rows = [make_row("2024-03-31", 1000, -100)]
        metrics.add_operating_margin(rows)
        self.assertAlmostEqual(rows[0]["operating_margin"], -0.1)

    def test_zero_revenue_is_none(self):
        rows = [make_row("2024-03-31", 0, 100)]
        metrics.add_operating_margin(rows)
        self.assertIsNone(rows[0]["operating_margin"])

    def test_missing_values_are_none(self):
        rows = [make_row("2024-03-31", 1000, None), make_row("2024-06-30", None, 100)]
        metrics.add_operating_margin(rows)
        self.assertIsNone(rows[0]["operating_margin"])
        self.assertIsNone(rows[1]["operating_margin"])


class TestMarginChange(unittest.TestCase):
    def test_change_in_decimal_points(self):
        rows = [make_row("2024-03-31", 1000, 200), make_row("2024-06-30", 1000, 250)]
        metrics.calculate_all_metrics(rows)
        self.assertIsNone(rows[0]["margin_change_qoq"])
        self.assertAlmostEqual(rows[1]["margin_change_qoq"], 0.05)  # +5 points

    def test_negative_change(self):
        rows = [make_row("2024-03-31", 1000, 300), make_row("2024-06-30", 1000, 250)]
        metrics.calculate_all_metrics(rows)
        self.assertAlmostEqual(rows[1]["margin_change_qoq"], -0.05)

    def test_yoy_change(self):
        rows = [
            make_row("2023-03-31", 1000, 100),
            make_row("2023-06-30", 1000, 100),
            make_row("2023-09-30", 1000, 100),
            make_row("2023-12-31", 1000, 100),
            make_row("2024-03-31", 1000, 200),
        ]
        metrics.calculate_all_metrics(rows)
        self.assertAlmostEqual(rows[4]["margin_change_yoy"], 0.10)
        self.assertAlmostEqual(rows[4]["margin_change_qoq"], 0.10)

    def test_skipped_across_gap(self):
        rows = [make_row("2024-03-31", 1000, 200), make_row("2024-12-31", 1000, 250)]
        metrics.calculate_all_metrics(rows)
        self.assertIsNone(rows[1]["margin_change_qoq"])

    def test_returns_rows(self):
        rows = [make_row("2024-03-31", 1000, 200)]
        self.assertIs(metrics.calculate_all_metrics(rows), rows)


class TestTrendSummary(unittest.TestCase):
    def test_summary_text(self):
        rows = [
            make_row("2023-12-31", 1000, 250, "FY2023 Q4"),
            make_row("2024-03-31", 1000, 275, "FY2024 Q1"),
            make_row("2024-06-30", 1000, 300, "FY2024 Q2"),
        ]
        metrics.calculate_all_metrics(rows)
        text = metrics.margin_trend_summary(rows)
        self.assertIn("25.0%", text)
        self.assertIn("30.0%", text)
        self.assertIn("FY2023 Q4", text)
        self.assertIn("FY2024 Q2", text)
        self.assertIn("+5.0 pp", text)

    def test_handles_missing_margins(self):
        rows = [make_row("2024-03-31", None, None), make_row("2024-06-30", 0, 10)]
        metrics.calculate_all_metrics(rows)
        self.assertIsInstance(metrics.margin_trend_summary(rows), str)
        self.assertIsInstance(metrics.margin_trend_summary([]), str)


if __name__ == "__main__":
    unittest.main()
