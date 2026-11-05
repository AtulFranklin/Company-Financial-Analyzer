"""Download SEC EDGAR data and turn it into quarterly revenue and operating income rows."""

import datetime
import os

import requests

SEC_USER_AGENT = "Your Name your.email@example.com"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

QUARTER_MIN_DAYS = 80
QUARTER_MAX_DAYS = 100
YEAR_MIN_DAYS = 350
YEAR_MAX_DAYS = 380
ALLOWED_FORMS = ("10-Q", "10-K", "10-Q/A", "10-K/A")
# "Revenues" first, it is the total when a company tags both
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
OPERATING_INCOME_TAGS = ["OperatingIncomeLoss"]

TYPICAL_QUARTER_DAYS = 91
TYPICAL_YEAR_DAYS = 365
TICKER_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"


def get_user_agent() -> str:
    """Return the SEC User-Agent from SEC_USER_AGENT env var, the constant, or a prompt."""
    from_env = os.environ.get("SEC_USER_AGENT", "").strip()
    if from_env:
        return from_env
    if SEC_USER_AGENT != "Your Name your.email@example.com":
        return SEC_USER_AGENT
    print("The SEC asks for a name and email in every request (sent only to sec.gov).")
    while True:
        answer = input("Enter your name and email, e.g. Jane Doe jane@example.com: ").strip()
        if "@" in answer and " " in answer:
            return answer
        print("Please type a name, a space, then an email.")


def normalize_ticker(text: str) -> str:
    """Clean up a ticker (strip, upper case, '.' to '-'). Raises ValueError if invalid."""
    ticker = text.strip().upper().replace(".", "-")
    if ticker == "":
        raise ValueError("Ticker is empty")
    if len(ticker) > 10:
        raise ValueError("Ticker is too long (max 10 characters)")
    for ch in ticker:
        if ch not in TICKER_CHARS:
            raise ValueError("Ticker can only have letters, numbers and '-'")
    return ticker


def _get_json(url: str, user_agent: str) -> dict:
    """Download a URL and return the parsed JSON. Raises RuntimeError on failure."""
    headers = {"User-Agent": user_agent}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
    except requests.HTTPError as err:
        status = err.response.status_code if err.response is not None else None
        if status == 403:
            raise RuntimeError(
                "SEC refused the request (403). Check that the User-Agent has "
                "a real name and email."
            )
        raise RuntimeError("SEC returned an error (HTTP " + str(status) + ") for " + url)
    except requests.RequestException as err:
        raise RuntimeError("Could not reach the SEC website: " + str(err))
    try:
        return response.json()
    except ValueError:
        raise RuntimeError("SEC sent a reply that is not valid JSON for " + url)


def lookup_cik(ticker: str, user_agent: str) -> tuple:
    """Return (cik, company_title) for a ticker. Raises ValueError if not found."""
    ticker_map = _get_json(TICKER_URL, user_agent)
    for entry in ticker_map.values():
        if str(entry.get("ticker", "")).upper() == ticker:
            return int(entry["cik_str"]), entry.get("title", ticker)
    raise ValueError("Ticker " + ticker + " not found in SEC list")


def fetch_company_facts(cik: int, user_agent: str) -> dict:
    """Download the XBRL company facts JSON for a CIK."""
    return _get_json(FACTS_URL.format(cik=cik), user_agent)


def _get_us_gaap(facts: dict) -> dict:
    """Return the us-gaap section of company facts, or an empty dict."""
    return facts.get("facts", {}).get("us-gaap", {})


def choose_tag(facts: dict, candidate_tags: list) -> tuple:
    """Pick the candidate tag with the newest and most complete quarterly data.

    Ranks by latest end date, then by number of quarters in the last 3 years,
    then by order in candidate_tags. Returns (tag or None, warnings).
    """
    us_gaap = _get_us_gaap(facts)
    warnings = []
    best_tag = None
    best_score = None
    for tag in candidate_tags:
        if tag not in us_gaap:
            continue
        units = us_gaap[tag].get("units", {})
        if "USD" not in units:
            found = ", ".join(sorted(units.keys())) or "none"
            warnings.append("Tag " + tag + " has no USD unit, units found: " + found)
            continue
        entries, _ = _parse_entries(units["USD"])
        if not entries:
            warnings.append("Tag " + tag + " has no usable 10-K or 10-Q entries")
            continue
        latest_end = max(e["end"] for e in entries)
        recent_quarters = set()
        for e in entries:
            is_quarter = QUARTER_MIN_DAYS <= e["days"] <= QUARTER_MAX_DAYS
            if is_quarter and (latest_end - e["end"]).days <= 3 * 366:
                recent_quarters.add(e["end"])
        score = (latest_end, len(recent_quarters))
        # strict > so earlier candidate wins ties
        if best_score is None or score > best_score:
            best_tag = tag
            best_score = score
    if best_tag is None:
        warnings.append("No usable tag found among: " + ", ".join(candidate_tags))
    return best_tag, warnings


def _parse_entries(raw_entries: list) -> tuple:
    """Turn raw JSON entries into dicts with date objects. Returns (entries, warnings)."""
    entries = []
    warnings = []
    for raw in raw_entries:
        if raw.get("form") not in ALLOWED_FORMS:
            continue
        if not raw.get("start"):
            continue
        try:
            start = datetime.date.fromisoformat(raw["start"])
            end = datetime.date.fromisoformat(raw["end"])
            filed = datetime.date.fromisoformat(raw["filed"])
        except (KeyError, TypeError, ValueError):
            warnings.append("Skipped entry with bad dates: " + str(raw.get("accn")))
            continue
        try:
            val = float(raw["val"])
        except (KeyError, TypeError, ValueError):
            warnings.append("Skipped entry with non-numeric value: " + str(raw.get("accn")))
            continue
        entries.append({
            "start": start,
            "end": end,
            "val": val,
            "filed": filed,
            "form": raw["form"],
            "fy": raw.get("fy"),
            "fp": raw.get("fp"),
            "accn": raw.get("accn"),
            "days": (end - start).days,
        })
    return entries, warnings


def _group_by_period(entries: list) -> dict:
    """Group parsed entries by (start, end)."""
    groups = {}
    for entry in entries:
        key = (entry["start"], entry["end"])
        if key not in groups:
            groups[key] = []
        groups[key].append(entry)
    return groups


def _summarize_period(entries: list) -> dict:
    """Combine all filings of one period into a quarter record (latest value wins)."""
    ordered = sorted(entries, key=lambda e: e["filed"])
    first = ordered[0]
    latest = ordered[-1]

    distinct_values = set(e["val"] for e in ordered)
    was_restated = len(distinct_values) > 1
    notes = []
    if was_restated:
        notes.append(
            "restated: first reported {:,.0f} (filed {}), latest {:,.0f} (filed {})".format(
                first["val"], first["filed"].isoformat(),
                latest["val"], latest["filed"].isoformat(),
            )
        )

    first_fp = str(first.get("fp") or "").upper()
    if first_fp in ("Q1", "Q2", "Q3"):
        fiscal_period = first_fp
    else:
        fiscal_period = "Q4"
    if first.get("fy") is not None:
        fiscal_year = int(first["fy"])
    else:
        fiscal_year = first["end"].year

    return {
        "period_start": first["start"],
        "period_end": first["end"],
        "value": latest["val"],
        "filed": latest["filed"],
        "form": latest["form"],
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "is_derived": False,
        "was_restated": was_restated,
        "notes": notes,
    }


def _pick_closest(records: list, target_days: int) -> dict:
    """Return the record whose length is closest to target_days."""
    best = records[0]
    for record in records:
        gap = abs((record["period_end"] - record["period_start"]).days - target_days)
        best_gap = abs((best["period_end"] - best["period_start"]).days - target_days)
        if gap < best_gap:
            best = record
    return best


def _one_per_end(records: list, target_days: int, label: str, warnings: list) -> list:
    """Keep one record per end date (closest to target length) and warn on clashes."""
    by_end = {}
    for record in records:
        end = record["period_end"]
        if end not in by_end:
            by_end[end] = []
        by_end[end].append(record)
    kept = []
    for end in sorted(by_end):
        group = by_end[end]
        if len(group) > 1:
            warnings.append(
                label + " periods ending " + end.isoformat()
                + " have different start dates, kept the closest to "
                + str(target_days) + " days"
            )
        kept.append(_pick_closest(group, target_days))
    return kept


def _derive_q4(annual: dict, quarterly_by_end: dict):
    """Build Q4 as annual minus Q1-Q3.

    Returns None if Q4 was reported on its own or no quarters of that year exist.
    If only 1 or 2 of Q1-Q3 exist, returns a Q4 record with value None and a note,
    so the missing quarter shows up as a flagged row instead of being guessed.
    """
    if annual["period_end"] in quarterly_by_end:
        return None

    earlier = []
    for record in quarterly_by_end.values():
        if record["period_start"] >= annual["period_start"] and record["period_end"] < annual["period_end"]:
            earlier.append(record)

    if len(earlier) == 0:
        return None

    last_end = max(r["period_end"] for r in earlier)
    q4 = {
        "period_start": last_end + datetime.timedelta(days=1),
        "period_end": annual["period_end"],
        "value": None,
        "filed": annual["filed"],
        "form": annual["form"],
        "fiscal_year": annual["fiscal_year"],
        "fiscal_period": "Q4",
        "is_derived": True,
        "was_restated": False,
        "notes": [],
    }

    if len(earlier) != 3:
        q4["notes"].append(
            "Q4 not calculated, only " + str(len(earlier))
            + " of Q1-Q3 found for this fiscal year"
        )
        return q4

    q4["value"] = annual["value"] - sum(r["value"] for r in earlier)
    q4["notes"].append("derived: annual 10-K value minus Q1-Q3")
    q4["was_restated"] = annual["was_restated"]
    for note in annual["notes"]:
        q4["notes"].append("annual " + note)
    for record in sorted(earlier, key=lambda r: r["period_end"]):
        if record["was_restated"]:
            q4["was_restated"] = True
            for note in record["notes"]:
                q4["notes"].append("quarter ending " + record["period_end"].isoformat() + " " + note)
    return q4


def extract_quarters(facts: dict, tag: str) -> tuple:
    """Build {period_end: quarter_record} for one tag. Returns (records, warnings)."""
    warnings = []
    tag_data = _get_us_gaap(facts).get(tag)
    if tag_data is None or "USD" not in tag_data.get("units", {}):
        return {}, ["Tag " + str(tag) + " has no USD data"]

    entries, parse_warnings = _parse_entries(tag_data["units"]["USD"])
    warnings.extend(parse_warnings)

    quarter_records = []
    annual_records = []
    groups = _group_by_period(entries)
    for key in sorted(groups):
        record = _summarize_period(groups[key])
        days = (record["period_end"] - record["period_start"]).days
        if QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS:
            quarter_records.append(record)
        elif YEAR_MIN_DAYS <= days <= YEAR_MAX_DAYS:
            annual_records.append(record)
        # 6 and 9 month year-to-date periods fall through and are ignored

    quarters = {}
    for record in _one_per_end(quarter_records, TYPICAL_QUARTER_DAYS, "Quarter", warnings):
        quarters[record["period_end"]] = record
    annuals = _one_per_end(annual_records, TYPICAL_YEAR_DAYS, "Annual", warnings)

    # derive from reported quarters only, never from other derived ones
    reported = dict(quarters)
    for annual in annuals:
        derived = _derive_q4(annual, reported)
        if derived is not None:
            quarters[derived["period_end"]] = derived

    return quarters, warnings


def _label_for(record: dict) -> str:
    """Make a label like 'FY2025 Q3' from a quarter record."""
    return "FY" + str(record["fiscal_year"]) + " " + record["fiscal_period"]


def build_quarter_rows(revenue_records: dict, opinc_records: dict) -> list:
    """Merge revenue and operating income records into rows sorted oldest to newest."""
    all_ends = sorted(set(revenue_records) | set(opinc_records))
    rows = []
    for end in all_ends:
        revenue = revenue_records.get(end)
        opinc = opinc_records.get(end)
        main_record = revenue if revenue is not None else opinc

        flags = []
        if revenue is not None:
            for note in revenue["notes"]:
                flags.append("revenue: " + note)
        if opinc is not None:
            for note in opinc["notes"]:
                flags.append("operating income: " + note)
        if revenue is None:
            flags.append("revenue missing for this quarter")
        if opinc is None:
            flags.append("operating income missing for this quarter")

        rows.append({
            "period_start": main_record["period_start"],
            "period_end": end,
            "fiscal_label": _label_for(main_record),
            "revenue": revenue["value"] if revenue is not None else None,
            "operating_income": opinc["value"] if opinc is not None else None,
            "flags": flags,
        })
    return rows


def get_company_data(ticker: str) -> dict:
    """Run the whole download and extraction for one ticker and return a summary dict."""
    ticker = normalize_ticker(ticker)
    user_agent = get_user_agent()
    cik, company_name = lookup_cik(ticker, user_agent)
    facts = fetch_company_facts(cik, user_agent)

    warnings = []
    revenue_tag, tag_warnings = choose_tag(facts, REVENUE_TAGS)
    if revenue_tag is None:
        raise RuntimeError(
            "No revenue data found for " + ticker + ". " + " ".join(tag_warnings)
        )
    warnings.extend(tag_warnings)

    opinc_tag, opinc_tag_warnings = choose_tag(facts, OPERATING_INCOME_TAGS)
    if opinc_tag is None:
        warnings.append("No operating income tag found, operating income and margin will be missing")
    else:
        warnings.extend(opinc_tag_warnings)

    revenue_records, rev_warnings = extract_quarters(facts, revenue_tag)
    for text in rev_warnings:
        warnings.append("revenue: " + text)

    opinc_records = {}
    if opinc_tag is not None:
        opinc_records, op_warnings = extract_quarters(facts, opinc_tag)
        for text in op_warnings:
            warnings.append("operating income: " + text)

    return {
        "ticker": ticker,
        "cik": cik,
        "company_name": company_name,
        "revenue_tag": revenue_tag,
        "operating_income_tag": opinc_tag,
        "rows": build_quarter_rows(revenue_records, opinc_records),
        "warnings": warnings,
    }
