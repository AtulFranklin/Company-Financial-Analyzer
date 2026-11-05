# Financial analysis script - build plan

Beginner-level Python program (undergrad CS style). Asks for a ticker, pulls the last
quarters of revenue and operating income from SEC EDGAR, computes growth and margin,
flags bad data, prints a table and optionally exports CSV.

## Data source

SEC EDGAR XBRL "company facts" API (free, no API key).

- Ticker to CIK map: `https://www.sec.gov/files/company_tickers.json`
  - JSON object of `{"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}`
- Company facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (CIK zero padded to 10 digits)
  - `facts["us-gaap"][TAG]["units"]["USD"]` is a list of entries like
    `{"start": "2024-06-30", "end": "2024-09-28", "val": 94930000000, "accn": "...",
      "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2024-11-01", "frame": "CY2024Q3"}`
  - `start` missing on instant facts (balance sheet). Revenue/op income are duration facts.
  - `fy`/`fp` describe the FILING, not the fact. A prior-year comparative inside a 10-Q
    carries the newer filing's fy/fp.
- SEC requires a `User-Agent` header with a name and email. Max 10 requests/sec (we make 2).
- Only dependency: `requests`. Everything else is the standard library (csv, datetime, unittest).

## Files (folder: `Financial analysis script/`)

| File | Owner | Purpose |
|---|---|---|
| `financial_analysis.py` | Agent B | entry point, `main()`, asks for ticker, runs the steps |
| `sec_data.py` | Agent A | ticker lookup, download, extract quarterly values, Q4 derivation, restatements |
| `checks.py` | Agent B | data quality checks that add flags (never change numbers) |
| `metrics.py` | Agent B | QoQ, YoY, operating margin, margin change |
| `output.py` | Agent B | formatting, printed table, CSV export |
| `tests/test_*.py`, `tests/fake_data.py` | Agent C | unittest tests with clearly fake numbers |
| `README.md`, `requirements.txt` | Agent C | setup, source, assumptions, manual checks |

## Shared data contract (all agents must follow exactly)

### Quarter record (built in `sec_data.py`, one per period for ONE metric)
```python
{
    "period_start": datetime.date,
    "period_end": datetime.date,
    "value": float,              # whole US dollars, as reported
    "filed": datetime.date,      # filing date of the value used (latest)
    "form": str,                 # "10-Q", "10-K", "10-Q/A", "10-K/A"
    "fiscal_year": int,          # from the EARLIEST filing that reported this period
    "fiscal_period": str,        # "Q1", "Q2", "Q3", "Q4"
    "is_derived": bool,          # True only for Q4 = annual - (Q1+Q2+Q3)
    "was_restated": bool,        # True if filings disagree on the value
    "notes": list[str],          # plain text notes, e.g. restatement details
}
```

### Row (built by `sec_data.build_quarter_rows`, one per quarter, both metrics)
```python
{
    "period_start": date, "period_end": date,
    "fiscal_label": str,          # e.g. "FY2025 Q3"; take from revenue record, else op income record
    "revenue": float | None,
    "operating_income": float | None,
    "flags": list[str],           # everything a reviewer should look at
    # added by metrics.py:
    "qoq_growth": float | None,   # decimal, 0.052 = 5.2%
    "yoy_growth": float | None,
    "operating_margin": float | None,
    "margin_change_qoq": float | None,  # decimal points, 0.012 = +1.2 percentage points
    "margin_change_yoy": float | None,
}
```
Rows are always sorted oldest to newest by `period_end`.

## Constants

```python
QUARTER_MIN_DAYS = 80     # a fact counts as one quarter if 80-100 days long
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350       # a fact counts as a full fiscal year if 350-380 days long
YEAR_MAX_DAYS = 380
ALLOWED_FORMS = ("10-Q", "10-K", "10-Q/A", "10-K/A")
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]
```
Gap rules (used by checks and metrics): next quarter end 75-105 days after previous end
= consecutive. Same quarter last year = end date 350-380 days earlier.

## Agent A - `sec_data.py`

Functions (exact names and signatures):

1. `get_user_agent() -> str` - env var `SEC_USER_AGENT`, else module constant
   `SEC_USER_AGENT = "Your Name your.email@example.com"`. If still the placeholder, ask with
   `input()` for "name and email" and return it. Never hardcode a real email.
2. `normalize_ticker(text: str) -> str` - strip, upper, `.` to `-`. Raise `ValueError` if empty or
   contains chars outside A-Z 0-9 `-`, or longer than 10.
3. `lookup_cik(ticker: str, user_agent: str) -> tuple[int, str]` - download ticker map, return
   `(cik, company_title)`. Raise `ValueError("Ticker XYZ not found in SEC list")` if absent.
4. `fetch_company_facts(cik: int, user_agent: str) -> dict` - download company facts JSON.
   Shared helper `_get_json(url, user_agent)` with `timeout=30`, `raise_for_status()`.
   On 403 raise `RuntimeError` mentioning the User-Agent requirement. On other
   `requests.RequestException` raise `RuntimeError` with a friendly message.
5. `choose_tag(facts: dict, candidate_tags: list[str]) -> tuple[str | None, list[str]]` - among
   candidate tags present in `facts["facts"]["us-gaap"]` with a `"USD"` unit, pick the one whose
   latest `end` date is most recent (ties: earlier in candidate list wins). Return
   `(None, [warning])` when none. Warning when a tag exists but has no USD unit
   (list the units found).
6. `extract_quarters(facts: dict, tag: str) -> tuple[dict, list[str]]` - returns
   `({period_end_date: quarter_record}, warnings)`. Steps, each its own small helper:
   - `_parse_entries(raw_entries) -> (list of dicts with date objects + float val, warnings)`:
     skip forms not in ALLOWED_FORMS, skip entries without `start`, skip and warn on bad
     dates or non-numeric values. Keep `start, end, val, filed, form, fy, fp, accn` and `days = (end - start).days`.
   - `_group_by_period(entries)` -> dict `(start, end) -> list of entries`.
   - `_summarize_period(entries) -> dict`: sort by `filed`; use LATEST value; fiscal_year/fp
     from EARLIEST entry; `was_restated` if more than one distinct value; note text like
     `"restated: first reported 1,234,000,000 (filed 2024-05-02), latest 1,250,000,000 (filed 2025-05-01)"`.
     fiscal_period: earliest fp if in Q1/Q2/Q3, otherwise "Q4" for quarter-length periods.
   - quarterly periods: days in QUARTER range. annual periods: days in YEAR range.
     Everything else (6-month, 9-month YTD) ignored.
   - `_derive_q4(annual, quarterly_by_end) -> record | None`: if no quarter already ends on the
     annual end date, find quarters with `start >= annual start` and `end < annual end`.
     Exactly 3 needed, else return None and add warning
     `"FY2024: cannot derive Q4, found N of 3 earlier quarters"`. Q4 value = annual - sum.
     period_start = latest of the 3 ends + 1 day. `is_derived=True`, fiscal_period "Q4",
     fiscal_year from annual record, filed/form from annual, notes include
     `"derived: annual 10-K value minus Q1-Q3"`. Carry was_restated if annual or any quarter restated.
   - If two quarterly periods share an end date but different start dates, keep the one whose
     length is closest to 91 days and warn.
7. `build_quarter_rows(revenue_records: dict, opinc_records: dict) -> list[dict]` - union of
   period_end keys, sorted. Fill row per contract. Flags: copy `notes` from both records,
   prefixed `"revenue: "` / `"operating income: "`; add `"revenue missing for this quarter"` /
   `"operating income missing for this quarter"` when absent. period_start from whichever exists.
8. `get_company_data(ticker: str) -> dict` - orchestrates 1-7, returns
   `{"ticker", "cik", "company_name", "revenue_tag", "operating_income_tag", "rows", "warnings"}`.
   If no revenue tag found raise `RuntimeError`. Missing op income tag is a warning, rows still built.

## Agent B - `checks.py`, `metrics.py`, `output.py`, `financial_analysis.py`

`checks.py` (only appends to `row["flags"]` / returns warnings, never edits numbers):
- `is_consecutive(prev_end, end) -> bool` (75-105 days), `is_year_apart(old_end, new_end) -> bool` (350-380).
- `check_missing_quarters(rows) -> list[str]`: gap > 105 days between neighbours -> flag on later
  row `"gap of N days before this quarter, a quarter may be missing"` and a warning.
- `check_values(rows) -> list[str]`: revenue <= 0 -> flag `"revenue is zero or negative, growth and margin not calculated"`;
  operating income abs > revenue (revenue > 0) -> flag `"operating income larger than revenue, check filing"`;
  `check_enough_quarters(rows, needed) -> list[str]` warning if fewer than needed.
- `run_all_checks(rows, needed) -> list[str]`.

`metrics.py`:
- `percent_change(new, old) -> float | None`: None if either None or old <= 0.
- `add_growth(rows)`: qoq vs previous row only if `is_consecutive`; yoy vs row with
  `is_year_apart` (search earlier rows). Also None if current revenue <= 0.
- `add_operating_margin(rows)`: op / revenue when revenue > 0 and op not None.
- `add_margin_change(rows)`: difference vs consecutive previous quarter and vs same quarter last year.
- `calculate_all_metrics(rows) -> rows`.
- `margin_trend_summary(rows) -> str`: first vs last margin in shown rows, e.g.
  `"Operating margin went from 25.1% (FY2023 Q4) to 30.2% (FY2025 Q3), +5.1 pp"`; handles None.

`output.py`:
- `format_money(value) -> str`: millions, `"$94,930.0M"`, negatives `"-$1,234.5M"`, None `"N/A"`.
- `format_percent(value) -> str`: `"+5.2%"`, `"-3.0%"`, None `"N/A"`. (margin uses no plus sign: `format_percent(v, show_sign=False)`).
- `format_points(value) -> str`: `"+1.2 pp"`, None `"N/A"`.
- `print_table(rows, company_name, ticker)`: fixed-width columns: Quarter, Period end, Revenue,
  Op income, QoQ, YoY, Op margin, Margin chg QoQ, Margin chg YoY, Flag (`"*"` when flags non-empty).
- `print_flags(rows, warnings)`: numbered list of every flag with its quarter label, then warnings.
  Print "No data problems found." if none.
- `export_to_csv(rows, filepath)`: csv module. Columns: fiscal_label, period_start, period_end,
  revenue_usd, operating_income_usd, qoq_growth_pct, yoy_growth_pct, operating_margin_pct,
  margin_change_qoq_pp, margin_change_yoy_pp, flags (joined with " | "). Percent columns are
  value*100 rounded to 2 dp, blank when None. Dollars as raw integers.

`financial_analysis.py`:
- `QUARTERS_TO_SHOW = 8`.
- `ask_for_ticker() -> str`: loop until `normalize_ticker` succeeds; typing `q` quits.
- `main()`: ask ticker -> `get_company_data` -> `calculate_all_metrics` on ALL rows (so the
  oldest shown quarter still gets YoY) -> `run_all_checks` -> keep last `QUARTERS_TO_SHOW` rows ->
  print header (company, CIK, tags used, source) -> table -> margin trend -> flags ->
  ask `"Export to CSV? (y/n)"`, default filename `"{TICKER}_quarterly_summary.csv"` in the
  current folder. Catch `ValueError`/`RuntimeError` and print a clear message instead of a traceback.
- `if __name__ == "__main__": main()`.

## Agent C - tests, README, requirements

- `tests/fake_data.py`: helper `make_entry(start, end, val, filed, form, fy, fp)` and
  `make_facts(tag_to_entries: dict, unit="USD")` producing the company facts JSON shape.
  Module docstring says the numbers are made up for logic tests only.
- `tests/test_sec_data.py`: picks latest value on restatement and flags it; derives Q4 correctly;
  cannot derive Q4 when a quarter is missing (warning); ignores 6 and 9 month YTD entries;
  ignores 8-K; non-USD unit warning; choose_tag picks most recent tag; normalize_ticker cases;
  build_quarter_rows flags missing op income.
- `tests/test_metrics.py`: percent_change with zero/negative/None base; QoQ skipped across a gap;
  YoY matched by date; margin with zero revenue is None; margin change in points.
- `tests/test_checks.py`: missing quarter gap flagged; zero revenue flagged; op income > revenue flagged.
- `tests/test_output.py`: format helpers; CSV export writes header and blanks for None (use tempfile).
- Run with `python -m unittest discover tests` from the project folder (add `tests/__init__.py`).
- `requirements.txt`: `requests>=2.28`.
- `README.md`: what it does, setup (Python 3.9+, `pip install -r requirements.txt`,
  set `SEC_USER_AGENT`), run, data source, assumptions (see below), how to check by hand,
  running tests, limitations.

## Assumptions to document

- Quarter = a reported period 80-100 days long. 6/9 month year-to-date values are ignored.
- Fiscal year/quarter labels come from the company's own first filing of that period, so
  Apple's quarter ending late December is "FY Q1". Period end dates are always shown so
  calendar alignment is visible.
- Q4 is usually not reported on its own in a 10-K. It is computed as annual minus Q1-Q3 and
  marked "derived". If any of Q1-Q3 is missing, Q4 is left missing and flagged.
- Latest filed value wins when filings disagree (restatement or reclassification), and the
  row is flagged with both numbers.
- Values are in whole USD as tagged in XBRL, shown in millions. Non-USD facts are not used.
- Revenue tag: one tag chosen per company (most recent data). Operating income: `OperatingIncomeLoss`.
  Banks and some other companies do not report it, which gets flagged.
- Growth is not calculated when the base revenue is zero or negative.

## Comment style

Each function gets a short plain docstring (1-3 lines, what it takes and returns).
Inline comments are short dev notes, one line, 2-8 words, lowercase fine, only on
non-obvious steps. No em dashes anywhere, use "-". No "we"/"you", no mentions of AI or plans.
Beginner-readable code: plain functions, dicts and lists, no classes, no clever one-liners,
type hints ok.

## Changes made during integration

- `choose_tag` ranks by (latest end date, quarters in last 3 years), then list order. `Revenues` moved first since it is the total when both are tagged.
- `_derive_q4` no longer warns. With 1-2 of Q1-Q3 it returns a Q4 record with `value: None` and a note, so the hole shows as a flagged N/A row. With 0 it returns None.
- `check_missing_quarters` / `check_values` only add flags. `run_all_checks` returns general warnings only and runs on the shown rows.
- `get_user_agent` re-asks until the answer has a name and an email.

## Integration (lead)

Run all tests, run a fake end-to-end through `main` with patched network, fix mismatches,
copy to `/Users/atulabraham/Development/Financial analysis script/`.
