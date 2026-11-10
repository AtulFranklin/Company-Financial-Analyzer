-- saved companies
CREATE TABLE IF NOT EXISTS companies (
    ticker               TEXT PRIMARY KEY,
    cik                  INTEGER NOT NULL,
    company_name         TEXT NOT NULL,
    revenue_tag          TEXT,
    operating_income_tag TEXT,
    warnings             TEXT[] NOT NULL DEFAULT '{}',
    fetched_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one row per quarter
CREATE TABLE IF NOT EXISTS quarters (
    ticker            TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
    period_end        DATE NOT NULL,
    period_start      DATE,
    fiscal_label      TEXT NOT NULL,
    revenue           BIGINT,
    operating_income  BIGINT,
    qoq_growth        DOUBLE PRECISION,
    yoy_growth        DOUBLE PRECISION,
    operating_margin  DOUBLE PRECISION,
    margin_change_qoq DOUBLE PRECISION,
    margin_change_yoy DOUBLE PRECISION,
    flags             TEXT[] NOT NULL DEFAULT '{}',
    PRIMARY KEY (ticker, period_end)
);
