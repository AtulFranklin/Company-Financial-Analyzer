"""Fake data helpers for the unit tests.

All numbers here are made up round values (1000, 1100, ...) and are for
logic tests only. They are not real company figures.
"""
import datetime


def make_entry(start, end, val, filed, form="10-Q", fy=2024, fp="Q1"):
    """Build one SEC companyfacts entry (dates are ISO strings)."""
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": "0000000001-24-000001",
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def make_facts(tag_to_entries, unit="USD"):
    """Build a fake companyfacts dict. tag_to_entries maps tag -> list of entries."""
    us_gaap = {}
    for tag, entries in tag_to_entries.items():
        us_gaap[tag] = {"label": tag, "units": {unit: entries}}
    return {"cik": 1, "entityName": "Test Co", "facts": {"us-gaap": us_gaap}}


def make_record(period_end, value, fiscal_year=2024, fiscal_period="Q1",
                notes=None, is_derived=False, was_restated=False):
    """Build a quarter record (the sec_data contract) for build_quarter_rows tests."""
    end = datetime.date.fromisoformat(period_end)
    return {
        "period_start": end - datetime.timedelta(days=90),
        "period_end": end,
        "value": float(value),
        "filed": end + datetime.timedelta(days=30),
        "form": "10-Q",
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "is_derived": is_derived,
        "was_restated": was_restated,
        "notes": notes or [],
    }


def make_row(period_end, revenue, operating_income, label=None):
    """Build a row dict (period_end is an ISO string). Metric fields start as None."""
    end = datetime.date.fromisoformat(period_end)
    return {
        "period_start": end - datetime.timedelta(days=90),
        "period_end": end,
        "fiscal_label": label or ("FY" + str(end.year) + " Q?"),
        "revenue": revenue,
        "operating_income": operating_income,
        "flags": [],
        "qoq_growth": None,
        "yoy_growth": None,
        "operating_margin": None,
        "margin_change_qoq": None,
        "margin_change_yoy": None,
    }


def standard_year_entries():
    """Q1-Q3 10-Q entries plus the 10-K annual entry for a fake calendar 2024.

    Q1 900, Q2 1000, Q3 1100, annual 4000, so derived Q4 should be 1000.
    """
    return [
        make_entry("2024-01-01", "2024-03-31", 900, "2024-05-01", "10-Q", 2024, "Q1"),
        make_entry("2024-04-01", "2024-06-30", 1000, "2024-08-01", "10-Q", 2024, "Q2"),
        make_entry("2024-07-01", "2024-09-30", 1100, "2024-11-01", "10-Q", 2024, "Q3"),
        make_entry("2024-01-01", "2024-12-31", 4000, "2025-02-01", "10-K", 2024, "FY"),
    ]
