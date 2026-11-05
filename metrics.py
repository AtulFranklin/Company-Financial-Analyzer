"""Growth and margin calculations. Adds keys to each row, uses the gap rules from checks.py."""

from checks import is_consecutive, is_year_apart


def percent_change(new, old):
    """Change from old to new as a decimal. None if either is None or old <= 0."""
    if new is None or old is None or old <= 0:
        return None
    return (new - old) / old


def find_year_ago_row(rows: list, index: int):
    """Return the earlier row about one year before rows[index], or None."""
    for j in range(index - 1, -1, -1):
        if is_year_apart(rows[j]["period_end"], rows[index]["period_end"]):
            return rows[j]
    return None


def add_growth(rows: list) -> list:
    """Add qoq_growth and yoy_growth (decimals, None when not comparable)."""
    for i, row in enumerate(rows):
        row["qoq_growth"] = None
        row["yoy_growth"] = None
        revenue = row["revenue"]
        if revenue is None or revenue <= 0:
            continue
        if i > 0 and is_consecutive(rows[i - 1]["period_end"], row["period_end"]):
            row["qoq_growth"] = percent_change(revenue, rows[i - 1]["revenue"])
        year_ago = find_year_ago_row(rows, i)
        if year_ago is not None:
            row["yoy_growth"] = percent_change(revenue, year_ago["revenue"])
    return rows


def add_operating_margin(rows: list) -> list:
    """Add operating_margin = operating income / revenue when revenue > 0."""
    for row in rows:
        row["operating_margin"] = None
        revenue = row["revenue"]
        if revenue is not None and revenue > 0 and row["operating_income"] is not None:
            row["operating_margin"] = row["operating_income"] / revenue
    return rows


def add_margin_change(rows: list) -> list:
    """Add margin_change_qoq and margin_change_yoy (decimal points, None if not comparable)."""
    for i, row in enumerate(rows):
        row["margin_change_qoq"] = None
        row["margin_change_yoy"] = None
        margin = row["operating_margin"]
        if margin is None:
            continue
        if i > 0 and is_consecutive(rows[i - 1]["period_end"], row["period_end"]):
            prev_margin = rows[i - 1]["operating_margin"]
            if prev_margin is not None:
                row["margin_change_qoq"] = margin - prev_margin
        year_ago = find_year_ago_row(rows, i)
        if year_ago is not None and year_ago["operating_margin"] is not None:
            row["margin_change_yoy"] = margin - year_ago["operating_margin"]
    return rows


def calculate_all_metrics(rows: list) -> list:
    """Run every metric step and return the same rows."""
    add_growth(rows)
    add_operating_margin(rows)  # margin must come before margin change
    add_margin_change(rows)
    return rows


def margin_trend_summary(rows: list) -> str:
    """One line comparing first and last operating margin in the given rows."""
    with_margin = [r for r in rows if r.get("operating_margin") is not None]
    if len(with_margin) < 2:
        return "Operating margin trend: not enough data to compare"
    first = with_margin[0]
    last = with_margin[-1]
    change_pp = (last["operating_margin"] - first["operating_margin"]) * 100
    return (
        f"Operating margin went from {first['operating_margin'] * 100:.1f}% "
        f"({first['fiscal_label']}) to {last['operating_margin'] * 100:.1f}% "
        f"({last['fiscal_label']}), {change_pp:+.1f} pp"
    )
