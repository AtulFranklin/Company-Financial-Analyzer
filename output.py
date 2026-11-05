"""Formatting, printed table and CSV export."""

import csv

CSV_COLUMNS = [
    "fiscal_label", "period_start", "period_end", "revenue_usd", "operating_income_usd",
    "qoq_growth_pct", "yoy_growth_pct", "operating_margin_pct",
    "margin_change_qoq_pp", "margin_change_yoy_pp", "flags",
]

# (header, width) for each table column
TABLE_COLUMNS = [
    ("Quarter", 9), ("Period end", 10), ("Revenue", 13), ("Op income", 13),
    ("QoQ", 7), ("YoY", 7), ("Op margin", 9),
    ("Margin chg QoQ", 14), ("Margin chg YoY", 14), ("Flag", 4),
]


def format_money(value) -> str:
    """Dollars in millions like $94,930.0M, negatives as -$1,234.5M, None as N/A."""
    if value is None:
        return "N/A"
    millions = round(value / 1_000_000, 1)
    text = f"${abs(millions):,.1f}M"
    if millions < 0:
        return "-" + text
    return text


def format_percent(value, show_sign: bool = True) -> str:
    """Decimal as percent like +5.2%. Set show_sign=False for margins. None as N/A."""
    if value is None:
        return "N/A"
    if show_sign:
        return f"{value * 100:+.1f}%"
    return f"{value * 100:.1f}%"


def format_points(value) -> str:
    """Decimal difference as percentage points like +1.2 pp. None as N/A."""
    if value is None:
        return "N/A"
    return f"{value * 100:+.1f} pp"


def format_row_line(cells: list) -> str:
    """Join cells into one fixed-width line (text left, numbers right)."""
    parts = []
    for i, (cell, (_, width)) in enumerate(zip(cells, TABLE_COLUMNS)):
        if i < 2:
            parts.append(cell.ljust(width))
        else:
            parts.append(cell.rjust(width))
    return "  ".join(parts)


def print_table(rows: list, company_name: str, ticker: str) -> None:
    """Print the quarterly table with a short legend underneath."""
    print(f"{company_name} ({ticker}) - quarterly results")
    header = format_row_line([name for name, _ in TABLE_COLUMNS])
    print(header)
    print("-" * len(header))
    for row in rows:
        cells = [
            row["fiscal_label"],
            row["period_end"].isoformat(),
            format_money(row["revenue"]),
            format_money(row["operating_income"]),
            format_percent(row.get("qoq_growth")),
            format_percent(row.get("yoy_growth")),
            format_percent(row.get("operating_margin"), show_sign=False),
            format_points(row.get("margin_change_qoq")),
            format_points(row.get("margin_change_yoy")),
            "*" if row["flags"] else "",
        ]
        print(format_row_line(cells))
    print("-" * len(header))
    print("QoQ = vs previous quarter, YoY = vs same quarter last year, "
          "pp = percentage points, * = see flags below")


def print_flags(rows: list, warnings: list) -> None:
    """Print a numbered list of row flags, then general warnings."""
    count = 0
    for row in rows:
        for flag in row["flags"]:
            if count == 0:
                print("Flags:")
            count += 1
            print(f"  {count}. {row['fiscal_label']}: {flag}")
    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")
    if count == 0 and not warnings:
        print("No data problems found.")


def csv_dollars(value):
    """Whole-dollar integer for CSV, blank when None."""
    if value is None:
        return ""
    return int(round(value))


def csv_percent(value):
    """Decimal as percent number rounded to 2 dp, blank when None."""
    if value is None:
        return ""
    return round(value * 100, 2)


def export_to_csv(rows: list, filepath: str) -> None:
    """Write the rows to a CSV file."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow([
                row["fiscal_label"],
                row["period_start"].isoformat() if row.get("period_start") else "",
                row["period_end"].isoformat(),
                csv_dollars(row["revenue"]),
                csv_dollars(row["operating_income"]),
                csv_percent(row.get("qoq_growth")),
                csv_percent(row.get("yoy_growth")),
                csv_percent(row.get("operating_margin")),
                csv_percent(row.get("margin_change_qoq")),
                csv_percent(row.get("margin_change_yoy")),
                " | ".join(row["flags"]),
            ])
