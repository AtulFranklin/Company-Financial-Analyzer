"""REST API for the quarterly analyzer. Run: uvicorn api:app --reload"""

import os
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

import db
import sec_data
from financial_analysis import analyze_ticker
from sec_data import normalize_ticker

PLACEHOLDER_USER_AGENT = "Your Name your.email@example.com"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create the tables on startup."""
    db.init_db()
    yield


app = FastAPI(title="Quarterly Financial Analyzer API", lifespan=lifespan)


@app.exception_handler(psycopg.OperationalError)
async def database_down(request: Request, error: psycopg.OperationalError):
    """Turn a Postgres connection problem into a 503."""
    return JSONResponse(
        status_code=503,
        content={"detail": "Database not reachable, check DATABASE_URL and that Postgres is running"},
    )


def clean_ticker(text: str) -> str:
    """Normalize the ticker or raise a 400."""
    try:
        return normalize_ticker(text)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def user_agent_missing() -> bool:
    """True when neither the env var nor the constant is set."""
    from_env = os.environ.get("SEC_USER_AGENT", "").strip()
    return not from_env and sec_data.SEC_USER_AGENT == PLACEHOLDER_USER_AGENT


def fetch_and_save(ticker: str) -> None:
    """Pull one ticker from SEC EDGAR and save it."""
    # no prompt in a server
    if user_agent_missing():
        raise HTTPException(
            status_code=500,
            detail="SEC_USER_AGENT is not set, set it to your name and email and restart the server",
        )
    try:
        data = analyze_ticker(ticker)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error))
    db.save_company(data)


@app.get("/health")
def health() -> dict:
    """Check that the API is running."""
    return {"status": "ok"}


@app.get("/companies")
def list_companies() -> list:
    """List the companies saved in the database."""
    return db.list_companies()


@app.get("/companies/{ticker}/quarters")
def get_quarters(ticker: str) -> dict:
    """Get saved quarters, or fetch from SEC EDGAR the first time."""
    ticker = clean_ticker(ticker)
    saved = db.load_company(ticker)
    if saved:
        return {**saved, "source": "database"}
    fetch_and_save(ticker)
    return {**db.load_company(ticker), "source": "sec"}


@app.post("/companies/{ticker}/refresh")
def refresh_quarters(ticker: str) -> dict:
    """Fetch from SEC EDGAR again and overwrite the saved copy."""
    ticker = clean_ticker(ticker)
    fetch_and_save(ticker)
    return {**db.load_company(ticker), "source": "sec"}
