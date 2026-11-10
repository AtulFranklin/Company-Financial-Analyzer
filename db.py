"""Postgres storage for saved company data (plain SQL with psycopg)."""
import os
from typing import Optional

import psycopg
from psycopg.rows import dict_row

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
DEFAULT_DATABASE_URL = "postgresql://localhost/financial_analyzer"


def get_database_url() -> str:
    """Return DATABASE_URL from the environment or the local default."""
    return os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL


def get_connection() -> psycopg.Connection:
    """Open a connection that returns rows as dicts."""
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_db() -> None:
    """Create the tables if they do not exist yet."""
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        schema = f.read()
    with get_connection() as conn:
        conn.execute(schema)


def _round_money(value: Optional[float]) -> Optional[int]:
    """Round a dollar amount to a whole number, keeping None."""
    return None if value is None else int(round(value))


def save_company(data: dict) -> None:
    """Save one company and replace its saved quarters."""
    ticker = data["ticker"]
    with get_connection() as conn:
        # upsert company
        conn.execute(
            """
            INSERT INTO companies
                (ticker, cik, company_name, revenue_tag, operating_income_tag,
                 warnings, fetched_at)
            VALUES (%s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (ticker) DO UPDATE SET
                cik = EXCLUDED.cik,
                company_name = EXCLUDED.company_name,
                revenue_tag = EXCLUDED.revenue_tag,
                operating_income_tag = EXCLUDED.operating_income_tag,
                warnings = EXCLUDED.warnings,
                fetched_at = now()
            """,
            (
                ticker,
                data["cik"],
                data["company_name"],
                data.get("revenue_tag"),
                data.get("operating_income_tag"),
                list(data.get("warnings") or []),
            ),
        )
        # replace old quarters
        conn.execute("DELETE FROM quarters WHERE ticker = %s", (ticker,))
        for row in data.get("rows") or []:
            conn.execute(
                """
                INSERT INTO quarters
                    (ticker, period_end, period_start, fiscal_label, revenue,
                     operating_income, qoq_growth, yoy_growth, operating_margin,
                     margin_change_qoq, margin_change_yoy, flags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ticker,
                    row["period_end"],
                    row.get("period_start"),
                    row["fiscal_label"],
                    _round_money(row.get("revenue")),
                    _round_money(row.get("operating_income")),
                    row.get("qoq_growth"),
                    row.get("yoy_growth"),
                    row.get("operating_margin"),
                    row.get("margin_change_qoq"),
                    row.get("margin_change_yoy"),
                    list(row.get("flags") or []),
                ),
            )


def load_company(ticker: str) -> Optional[dict]:
    """Return a saved company with its quarters, or None if not saved."""
    with get_connection() as conn:
        company = conn.execute(
            """
            SELECT ticker, cik, company_name, revenue_tag, operating_income_tag,
                   warnings, fetched_at
            FROM companies WHERE ticker = %s
            """,
            (ticker,),
        ).fetchone()
        if company is None:
            return None
        quarters = conn.execute(
            """
            SELECT fiscal_label, period_start, period_end, revenue,
                   operating_income, qoq_growth, yoy_growth, operating_margin,
                   margin_change_qoq, margin_change_yoy, flags
            FROM quarters WHERE ticker = %s ORDER BY period_end
            """,
            (ticker,),
        ).fetchall()
    company["quarters"] = quarters
    return company


def list_companies() -> list:
    """Return every saved company with its quarter count."""
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT c.ticker, c.company_name, c.fetched_at,
                   COUNT(q.period_end)::int AS quarter_count
            FROM companies c
            LEFT JOIN quarters q ON q.ticker = c.ticker
            GROUP BY c.ticker, c.company_name, c.fetched_at
            ORDER BY c.ticker
            """
        ).fetchall()


def _hide_password(url: str) -> str:
    """Return the database URL with any password removed."""
    info = psycopg.conninfo.conninfo_to_dict(url)
    info.pop("password", None)
    host = info.get("host", "localhost")
    port = ":" + info["port"] if "port" in info else ""
    user = info["user"] + "@" if "user" in info else ""
    return "postgresql://" + user + host + port + "/" + info.get("dbname", "")


if __name__ == "__main__":
    init_db()
    print("Tables ready in " + _hide_password(get_database_url()))
