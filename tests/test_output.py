"""Tests for output.py (fake numbers only)."""
import contextlib
import csv
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import output
from tests.fake_data import make_row


class TestFormatMoney(unittest.TestCase):
    def test_millions(self):
        self.assertEqual(output.format_money(94930000000), "$94,930.0M")

    def test_negative(self):
        self.assertEqual(output.format_money(-1234500000), "-$1,234.5M")

    def test_small_and_zero(self):
        self.assertEqual(output.format_money(0), "$0.0M")
        self.assertEqual(output.format_money(1500000), "$1.5M")

    def test_none(self):
        self.assertEqual(output.format_money(None), "N/A")


class TestFormatPercent(unittest.TestCase):
    def test_signed(self):
        self.assertEqual(output.format_percent(0.052), "+5.2%")
        self.assertEqual(output.format_percent(-0.03), "-3.0%")

    def test_no_sign(self):
        self.assertEqual(output.format_percent(0.302, show_sign=False), "30.2%")
        self.assertEqual(output.format_percent(-0.05, show_sign=False), "-5.0%")

    def test_none(self):
        self.assertEqual(output.format_percent(None), "N/A")
        self.assertEqual(output.format_percent(None, show_sign=False), "N/A")


class TestFormatPoints(unittest.TestCase):
    def test_points(self):
        self.assertEqual(output.format_points(0.012), "+1.2 pp")
        self.assertEqual(output.format_points(-0.012), "-1.2 pp")

    def test_none(self):
        self.assertEqual(output.format_points(None), "N/A")


def full_row():
    row = make_row("2024-06-30", 1000000000, 250000000, "FY2024 Q2")
    row.update({
        "qoq_growth": 0.1,
        "yoy_growth": 0.2,
        "operating_margin": 0.25,
        "margin_change_qoq": 0.05,
        "margin_change_yoy": -0.01,
        "flags": ["first flag", "second flag"],
    })
    return row


class TestExportToCsv(unittest.TestCase):
    def export_and_read(self, rows):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "test_output.csv")
            output.export_to_csv(rows, path)
            with open(path, newline="", encoding="utf-8") as handle:
                text = handle.read()
        reader = csv.DictReader(io.StringIO(text))
        return reader.fieldnames, list(reader)

    def test_header(self):
        header, _ = self.export_and_read([full_row()])
        self.assertEqual(header, [
            "fiscal_label", "period_start", "period_end", "revenue_usd",
            "operating_income_usd", "qoq_growth_pct", "yoy_growth_pct",
            "operating_margin_pct", "margin_change_qoq_pp", "margin_change_yoy_pp",
            "flags",
        ])

    def test_values(self):
        _, records = self.export_and_read([full_row()])
        rec = records[0]
        self.assertEqual(rec["fiscal_label"], "FY2024 Q2")
        self.assertEqual(rec["period_end"], "2024-06-30")
        self.assertEqual(rec["revenue_usd"], "1000000000")
        self.assertEqual(rec["operating_income_usd"], "250000000")
        self.assertAlmostEqual(float(rec["qoq_growth_pct"]), 10.0)
        self.assertAlmostEqual(float(rec["yoy_growth_pct"]), 20.0)
        self.assertAlmostEqual(float(rec["operating_margin_pct"]), 25.0)
        self.assertAlmostEqual(float(rec["margin_change_qoq_pp"]), 5.0)
        self.assertAlmostEqual(float(rec["margin_change_yoy_pp"]), -1.0)
        self.assertEqual(rec["flags"], "first flag | second flag")

    def test_none_values_are_blank(self):
        row = make_row("2024-06-30", None, None, "FY2024 Q2")
        _, records = self.export_and_read([row])
        rec = records[0]
        for column in ("revenue_usd", "operating_income_usd", "qoq_growth_pct",
                       "yoy_growth_pct", "operating_margin_pct",
                       "margin_change_qoq_pp", "margin_change_yoy_pp", "flags"):
            self.assertEqual(rec[column], "", column)


class TestPrinting(unittest.TestCase):
    def capture(self, function, *args):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            function(*args)
        return buffer.getvalue()

    def test_print_table(self):
        text = self.capture(output.print_table, [full_row()], "Test Co", "TEST")
        self.assertIn("Test Co", text)
        self.assertIn("FY2024 Q2", text)
        self.assertIn("$1,000.0M", text)
        self.assertIn("*", text)  # flagged row marker

    def test_print_flags_lists_flags_and_warnings(self):
        text = self.capture(output.print_flags, [full_row()], ["a test warning"])
        self.assertIn("first flag", text)
        self.assertIn("FY2024 Q2", text)
        self.assertIn("a test warning", text)

    def test_print_flags_when_clean(self):
        row = make_row("2024-06-30", 1000, 100, "FY2024 Q2")
        text = self.capture(output.print_flags, [row], [])
        self.assertIn("No data problems found.", text)


if __name__ == "__main__":
    unittest.main()
