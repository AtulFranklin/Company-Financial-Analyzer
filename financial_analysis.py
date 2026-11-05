"""Quarterly revenue and operating income summary from SEC EDGAR. Run: python financial_analysis.py"""

import sys

from sec_data import normalize_ticker, get_company_data
from checks import run_all_checks
from metrics import calculate_all_metrics, margin_trend_summary
from output import print_table, print_flags, export_to_csv

QUARTERS_TO_SHOW = 8


def ask_for_ticker() -> str:
    """Ask until a valid ticker is typed. Typing q quits."""
    while True:
        try:
            text = input("Enter a stock ticker (or q to quit): ")
        except EOFError:
            sys.exit(0)
        if text.strip().lower() == "q":
            sys.exit(0)
        try:
            return normalize_ticker(text)
        except ValueError as error:
            print(f"Invalid ticker: {error}")


def ask_to_export(rows: list, ticker: str) -> None:
    """Ask if the user wants a CSV file and write it."""
    try:
        answer = input("Export to CSV? (y/n): ")
    except EOFError:
        return
    if answer.strip().lower() not in ("y", "yes"):
        return
    filename = f"{ticker}_quarterly_summary.csv"
    try:
        export_to_csv(rows, filename)
    except OSError as error:
        print(f"Could not write {filename}: {error}")
        return
    print(f"Saved {filename}")


def main() -> None:
    """Ask for a ticker, load data, print the table, optionally export CSV."""
    ticker = ask_for_ticker()
    print(f"Loading {ticker} from SEC EDGAR...")
    try:
        data = get_company_data(ticker)
    except (ValueError, RuntimeError) as error:
        print(f"Error: {error}")
        return

    all_rows = data["rows"]
    calculate_all_metrics(all_rows)  # all rows, so oldest shown quarter still gets YoY
    rows = all_rows[-QUARTERS_TO_SHOW:]
    check_warnings = run_all_checks(rows, QUARTERS_TO_SHOW)
    warnings = list(data["warnings"]) + check_warnings

    print()
    print(f"Company: {data['company_name']} ({data['ticker']}), CIK {data['cik']}")
    print("Source: SEC EDGAR company facts (data.sec.gov XBRL API), US-GAAP values in USD")
    print(f"Revenue tag: {data['revenue_tag']}")
    print(f"Operating income tag: {data['operating_income_tag'] or 'not found'}")
    print()
    print_table(rows, data["company_name"], data["ticker"])
    print()
    print(margin_trend_summary(rows))
    print()
    print_flags(rows, warnings)
    print()
    ask_to_export(rows, data["ticker"])


if __name__ == "__main__":
    main()
