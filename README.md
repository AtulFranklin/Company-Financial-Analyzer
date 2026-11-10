<div align="center">

# Quarterly Financial Analyzer

**Pull a company's last quarters of revenue and operating income from SEC EDGAR, with growth, margins and data-quality flags. A command line tool plus a small REST API (FastAPI) with a PostgreSQL cache.**

![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![data](https://img.shields.io/badge/data-SEC%20EDGAR-informational.svg)
![fastapi](https://img.shields.io/badge/api-FastAPI-009688.svg)
![postgresql](https://img.shields.io/badge/database-PostgreSQL-336791.svg)
![dependencies](https://img.shields.io/badge/dependencies-requests%20%7C%20fastapi%20%7C%20psycopg-lightgrey.svg)
![tests](https://img.shields.io/badge/tests-unittest-green.svg)
![api key](https://img.shields.io/badge/api%20key-not%20required-brightgreen.svg)

</div>

A Python program where you type a stock ticker (like `AAPL`), it downloads the company's filings data from the SEC, works out quarterly growth and operating margin, flags anything that looks wrong, prints a table and can save it as a CSV. The same analysis is also available as a small REST API that keeps results in PostgreSQL, see [API and database](#api-and-database).

## Why

Quarterly numbers are easy to get wrong by hand: fiscal quarters differ from calendar quarters, Q4 is usually not reported on its own, and companies restate old figures. This tool does that bookkeeping for you and tells you when it is not sure, instead of quietly guessing.

## Features

- Last 8 quarters of revenue and operating income, straight from official filings
- QoQ and YoY revenue growth, operating margin, and margin change in percentage points
- Q4 worked out automatically (annual figure minus Q1-Q3) and marked as derived
- Restatements detected, the latest value is used and both numbers are shown
- Data flags for missing quarters, zero or negative revenue, and suspicious values
- Optional CSV export that opens in Excel
- REST API with 4 endpoints and interactive docs at `/docs` (FastAPI)
- PostgreSQL cache: the first request for a ticker pulls from the SEC, later ones read from the database, and a refresh endpoint pulls again
- Plain SQL with `psycopg`, no ORM
- No API key, no classes, plain readable code. The CLI still needs only `requests`, the API adds FastAPI and psycopg

## Demo output

Placeholders only, the real run prints actual values. A `*` in the last column means the row has a flag.

```
Company: <Company Name> (<TICKER>)

Quarter     Period end  Revenue      Op income   QoQ     YoY     Op margin  Margin chg QoQ  Margin chg YoY  Flag
FY20XX Q1   20XX-XX-XX  $X,XXX.XM    $XXX.XM     +X.X%   +X.X%   XX.X%      +X.X pp         +X.X pp
FY20XX Q2   20XX-XX-XX  $X,XXX.XM    $XXX.XM     -X.X%   +X.X%   XX.X%      -X.X pp         +X.X pp         *

Operating margin went from XX.X% (FY20XX Q1) to XX.X% (FY20XX Q2), +X.X pp

Flags:
1. FY20XX Q2: <what to look at>
```

## Install

Needs Python 3.9 or newer.

```
python3 -m pip install -r requirements.txt
```

Set a User-Agent for the SEC (see [Data source](#data-source)):

```
export SEC_USER_AGENT="First Last you@example.com"
```

## How to use

```
python3 financial_analysis.py
```

Example session (placeholders):

```
Enter a stock ticker (or q to quit): <TICKER>
... table, margin trend and flags are printed ...
Export to CSV? (y/n): y
Saved <TICKER>_quarterly_summary.csv
```

The CSV is saved in the folder you ran the command from.

Folder contents:

| File | What it does |
|---|---|
| `financial_analysis.py` | entry point, asks for the ticker and runs the steps. Also exposes `analyze_ticker`, used by the API |
| `sec_data.py` | ticker lookup, download, quarter extraction, Q4 derivation, restatements |
| `checks.py` | data quality checks that add flags (never change numbers) |
| `metrics.py` | QoQ, YoY, operating margin, margin change |
| `output.py` | formatting, printed table, CSV export |
| `api.py` | FastAPI app with the 4 endpoints |
| `db.py` | PostgreSQL connection, create tables, save, load, list |
| `schema.sql` | table definitions for `companies` and `quarters` |
| [`tests/`](tests/) | unittest tests with clearly fake numbers |
| `requirements.txt` | `requests` for the CLI, FastAPI, uvicorn and psycopg for the API, httpx for tests |

## API and database

A small FastAPI app on top of the same analysis code. Results are cached in a local PostgreSQL database, so a ticker is only downloaded from the SEC once until you refresh it.

### Set up PostgreSQL (macOS)

Option 1, Postgres.app: download it from <https://postgresapp.com>, open it and click Initialize.

Option 2, Homebrew:

```
brew install postgresql@16
brew services start postgresql@16
```

On Apple Silicon, Homebrew may not put `psql` and `createdb` on your PATH. If the commands are not found:

```
echo 'export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Then create the database:

```
createdb financial_analyzer
```

### Environment variables

```
export DATABASE_URL="postgresql://localhost/financial_analyzer"
export SEC_USER_AGENT="First Last you@example.com"
```

`DATABASE_URL` is optional, the value above is the default. `SEC_USER_AGENT` is required for the API, it never prompts for it like the CLI does.

### Run it

```
python3 -m pip install -r requirements.txt
python3 db.py
uvicorn api:app --reload
```

`python3 db.py` creates the tables and is optional, the API also creates them on startup, so Postgres needs to be running first. Then open <http://127.0.0.1:8000/docs> for the interactive docs.

### Endpoints

| Method | Path | What it does |
|---|---|---|
| GET | `/health` | returns `{"status": "ok"}` |
| GET | `/companies` | lists saved companies with fetch time and quarter count |
| GET | `/companies/{ticker}/quarters` | saved copy if there is one, otherwise fetches from the SEC, saves and returns it |
| POST | `/companies/{ticker}/refresh` | always fetches from the SEC, saves and returns the new data |

Errors:

| Status | Cause |
|---|---|
| 400 | invalid ticker |
| 404 | ticker not found in the SEC list |
| 500 | `SEC_USER_AGENT` is not set |
| 502 | SEC download or data problem |
| 503 | database not reachable |

### Example calls

Placeholders only, the real response has actual values. `source` is `"database"` for a cached copy and `"sec"` for a fresh fetch.

```
curl http://127.0.0.1:8000/companies/<TICKER>/quarters
```

```json
{
  "ticker": "<TICKER>",
  "cik": 0,
  "company_name": "<Company Name>",
  "revenue_tag": "<RevenueTag>",
  "operating_income_tag": "OperatingIncomeLoss",
  "fetched_at": "20XX-XX-XXTXX:XX:XXZ",
  "source": "database",
  "warnings": [],
  "quarters": [
    {
      "fiscal_label": "FY20XX Q1",
      "period_start": "20XX-XX-XX",
      "period_end": "20XX-XX-XX",
      "revenue": 0,
      "operating_income": 0,
      "qoq_growth": 0.0,
      "yoy_growth": 0.0,
      "operating_margin": 0.0,
      "margin_change_qoq": 0.0,
      "margin_change_yoy": 0.0,
      "flags": []
    }
  ]
}
```

```
curl -X POST http://127.0.0.1:8000/companies/<TICKER>/refresh
curl http://127.0.0.1:8000/companies
```

```json
[
  {"ticker": "<TICKER>", "company_name": "<Company Name>", "fetched_at": "20XX-XX-XXTXX:XX:XXZ", "quarter_count": 8}
]
```

### Database tables

Defined in [`schema.sql`](schema.sql), plain SQL with no ORM.

| Table | Columns |
|---|---|
| `companies` | `ticker` (primary key), `cik`, `company_name`, `revenue_tag`, `operating_income_tag`, `warnings`, `fetched_at` |
| `quarters` | `ticker`, `period_end`, `period_start`, `fiscal_label`, `revenue`, `operating_income`, `qoq_growth`, `yoy_growth`, `operating_margin`, `margin_change_qoq`, `margin_change_yoy`, `flags` |

`quarters` has the primary key (`ticker`, `period_end`) and a foreign key to `companies(ticker)` with `ON DELETE CASCADE`. Dollar values are stored as whole numbers, growth and margins as decimals (`0.1` means 10%).

How the cache works:

- Saving is one transaction: upsert the company row, replace that ticker's quarters. A failure never leaves half a company.
- The cache does not expire on its own. Use the refresh endpoint to update it, and check `fetched_at` to see how old a copy is.

Look at what is stored:

```
psql financial_analyzer -c "SELECT ticker, company_name, fetched_at FROM companies;"
```

## Data source

SEC EDGAR XBRL "company facts" API. It is free and needs no API key.

- Ticker to CIK map: `https://www.sec.gov/files/company_tickers.json`
- Company facts: `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (CIK padded to 10 digits)

The SEC blocks anonymous scripts, so every request must send a `User-Agent` header with a real name and email (for example `First Last you@example.com`) so they can contact you if your script misbehaves. Without it you get a 403 error. Set it one of three ways:

- macOS/Linux: `export SEC_USER_AGENT="First Last you@example.com"`
- Edit the `SEC_USER_AGENT` constant at the top of `sec_data.py`
- Do nothing and type your name and email when the program asks

The program makes 2 requests per run, well under the SEC limit of 10 per second.

## How it works

```
ticker -> CIK -> company facts -> quarters -> checks -> metrics -> table / CSV
```

1. `normalize_ticker` cleans the input, `lookup_cik` finds the company ID.
2. `fetch_company_facts` downloads all reported facts as JSON.
3. `choose_tag` picks the revenue tag, `extract_quarters` builds one record per quarter (and derives Q4).
4. `build_quarter_rows` joins revenue and operating income into rows, oldest to newest.
5. `calculate_all_metrics` runs on all rows so the oldest shown quarter still gets YoY.
6. The last 8 rows are kept, `run_all_checks` adds flags to them, then they are printed and optionally exported.

The API path reuses the same steps through `analyze_ticker`:

```
request -> load_company -> (miss) analyze_ticker -> save_company -> response
```

Row shape (growth and margins are decimals, `0.1` means 10%):

```python
{
    "period_start": date, "period_end": date,
    "fiscal_label": "FY2025 Q3",
    "revenue": float or None,            # whole US dollars
    "operating_income": float or None,
    "flags": ["..."],                    # things a reviewer should look at
    "qoq_growth": float or None,
    "yoy_growth": float or None,
    "operating_margin": float or None,
    "margin_change_qoq": float or None,  # decimal points, 0.012 = +1.2 pp
    "margin_change_yoy": float or None,
}
```

## Assumptions

- **What is a quarter:** a reported period 80-100 days long. 6-month and 9-month year-to-date values are ignored.
- **Fiscal vs calendar quarters:** labels like "FY2025 Q3" come from the company's own first filing of that period, so a company with a September year end calls its December quarter "FY Q1". Period end dates are always shown so you can see the calendar alignment.
- **52/53 week years:** some companies end their year on the last Saturday or Sunday, so a year can be 52 or 53 weeks and a quarter 91 or 98 days. The day ranges allow for this (quarters 80-100 days, years 350-380 days). Consecutive quarters are 75-105 days apart, and "same quarter last year" is 350-380 days earlier.
- **Derived Q4:** companies usually do not report Q4 on its own. It is computed as the 10-K annual figure minus exactly three quarters (Q1-Q3) and marked "derived". If one of Q1-Q3 is missing, the Q4 row still appears but with N/A and a flag, so the hole is visible instead of guessed.
- **Restatements:** if filings disagree on a value (restatement or reclassification), the latest filed value wins and the row is flagged with both numbers. The fiscal label still comes from the earliest filing.
- **Units:** values are whole US dollars as tagged in XBRL and shown in millions in the table. CSV dollars are raw integers. Non-USD facts are not used.
- **Tag choice:** one revenue tag is chosen per company from a short list (`Revenues` first, then the `RevenueFromContractWithCustomer...` tags, then `SalesRevenueNet`). The tag with the newest data wins, then the one with the most quarters in the last 3 years. The tag used is printed above the table. Operating income uses `OperatingIncomeLoss`. Banks and some others do not report it, which gets flagged.
- **Zero or negative revenue:** growth and margin are not calculated for that quarter (shown as N/A), and it is flagged.
- **Percent vs points:** growth and margin are shown as percentages, margin change as percentage points (pp), the plain difference between two margins.

## Data flags

A `*` in the table means the row has at least one flag. Flags never change the numbers. The full list is printed under the table.

| Flag | Meaning |
|---|---|
| `restated: first reported ..., latest ...` | filings disagree, the latest value is used |
| `derived: annual 10-K value minus Q1-Q3` | Q4 was computed, not reported directly |
| `revenue missing for this quarter` | no revenue found for this period |
| `operating income missing for this quarter` | no operating income found for this period |
| `gap of N days before this quarter, a quarter may be missing` | the previous row is more than 105 days earlier |
| `revenue is zero or negative, growth and margin not calculated` | growth and margin shown as N/A |
| `operating income larger than revenue, check filing` | likely a tagging or data issue |
| `Q4 not calculated, only N of Q1-Q3 found for this fiscal year` | Q4 shown as N/A, a quarter in that year is missing |

Flags starting with `revenue:` or `operating income:` come from that metric's record. Warnings (for example, fewer quarters available than requested) are listed after the flags.

## Checking the output by hand

Pick 2-3 quarters and verify them against the original filings.

1. Go to <https://www.sec.gov/edgar/search/>, search the company name or ticker and open its filing list.
2. Open a 10-Q (or 10-K) whose period matches a row's period end date.
3. Find the income statement. Compare "Revenue" (or "Net sales") and "Operating income" to the table. Remember the table is in millions.
4. Recompute with a calculator:
   - margin = operating income / revenue
   - QoQ = this quarter revenue / previous quarter revenue - 1
   - YoY = this quarter revenue / same quarter last year revenue - 1
   - margin change = this margin minus the other margin, in percentage points
5. To verify a derived Q4: take the annual figure from the 10-K and subtract the three quarterly figures from the year's three 10-Qs. It should match the Q4 row.
6. Cross-check with the company's investor relations press release for the same quarter, which usually states revenue and operating income.
7. Open the exported CSV in Excel and recompute one formula, for example `=D3/D2-1` for QoQ growth and compare it with `qoq_growth_pct / 100`.

Small differences can come from restatements: the table uses the latest filed value, while an older 10-Q shows the original one.

## Running the tests

From the project folder:

```
python3 -m unittest discover tests
```

The existing tests use only the standard library, no network, and made-up round numbers (see `tests/fake_data.py`). `test_api.py` needs the requirements installed (FastAPI `TestClient`, with the database and the SEC mocked, so no network or Postgres). `test_db.py` only runs when `TEST_DATABASE_URL` is set:

```
createdb financial_analyzer_test
TEST_DATABASE_URL="postgresql://localhost/financial_analyzer_test" python3 -m unittest discover tests
```

They cover:

- [`test_sec_data.py`](tests/test_sec_data.py): ticker cleanup, tag choice, latest value on restatement, Q4 derivation, N/A Q4 row when a quarter is missing, ignoring YTD and 8-K entries, non-USD warning, missing-metric flags
- [`test_metrics.py`](tests/test_metrics.py): percent change edge cases, QoQ skipped across gaps, YoY matched by date, zero revenue margin, margin change in points
- [`test_checks.py`](tests/test_checks.py): gap detection, zero revenue, operating income larger than revenue
- [`test_output.py`](tests/test_output.py): money, percent and points formatting, CSV header and blanks
- [`test_api.py`](tests/test_api.py): the 4 endpoints, cached read vs fetch, refresh, and the 400, 404, 502, 503 and missing User-Agent errors
- [`test_db.py`](tests/test_db.py): save then load round trip, a second save replaces quarters, company list with quarter counts (needs a real Postgres)

## Limitations

- Foreign companies that file 20-F with IFRS are not supported (US-GAAP, 10-Q and 10-K only).
- Banks and some other companies have no `OperatingIncomeLoss`, so operating income and margin will be N/A.
- A company that switches revenue tags may show a break or a different tag than expected.
- No adjustment for acquisitions, divestitures or one-off items.
- Depends on how the company tagged its filing, so always spot-check.
- Not financial advice.

## Roadmap

- Chart of the margin trend
- Compare two tickers side by side
- IFRS / 20-F support
- More metrics (net income, cash flow)
- Cache expiry so old copies refresh on their own
- Docker Compose for the API and Postgres

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your change and run the tests.
4. Commit with a clear message.
5. Open a pull request describing what changed and why.
