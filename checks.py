"""Data quality checks. Only add flags to rows or return warnings, never change numbers."""

# gap rules, shared with metrics.py
CONSECUTIVE_MIN_DAYS = 75
CONSECUTIVE_MAX_DAYS = 105
YEAR_APART_MIN_DAYS = 350
YEAR_APART_MAX_DAYS = 380


def is_consecutive(prev_end, end) -> bool:
    """True if end is 75-105 days after prev_end (next quarter)."""
    days = (end - prev_end).days
    return CONSECUTIVE_MIN_DAYS <= days <= CONSECUTIVE_MAX_DAYS


def is_year_apart(old_end, new_end) -> bool:
    """True if old_end is 350-380 days before new_end (same quarter last year)."""
    days = (new_end - old_end).days
    return YEAR_APART_MIN_DAYS <= days <= YEAR_APART_MAX_DAYS


def add_flag(row: dict, text: str) -> None:
    """Add a flag to the row unless it is already there."""
    if text not in row["flags"]:
        row["flags"].append(text)


def check_missing_quarters(rows: list) -> None:
    """Flag rows that come after a gap bigger than 105 days."""
    for i in range(1, len(rows)):
        days = (rows[i]["period_end"] - rows[i - 1]["period_end"]).days
        if days > CONSECUTIVE_MAX_DAYS:
            add_flag(rows[i], f"gap of {days} days before this quarter, a quarter may be missing")


def check_values(rows: list) -> None:
    """Flag missing revenue, zero or negative revenue, and operating income bigger than revenue."""
    for row in rows:
        revenue = row["revenue"]
        op_income = row["operating_income"]
        if revenue is not None and revenue <= 0:
            add_flag(row, "revenue is zero or negative, growth and margin not calculated")
        if revenue is not None and revenue > 0 and op_income is not None:
            if abs(op_income) > revenue:
                add_flag(row, "operating income larger than revenue, check filing")


def check_enough_quarters(rows: list, needed: int) -> list:
    """Return a warning if there are fewer rows than needed."""
    if len(rows) < needed:
        return [f"only {len(rows)} quarters of data found, {needed} wanted"]
    return []


def run_all_checks(rows: list, needed: int) -> list:
    """Run every check. Problems go on row flags, returns general warnings only."""
    check_missing_quarters(rows)
    check_values(rows)
    return check_enough_quarters(rows, needed)
