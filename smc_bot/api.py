"""Private read-only API for the MsemwaFX Android app."""
import hmac
import os
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from database import get_signal, initialize, list_signals

app = FastAPI(title="MsemwaFX Personal API", version="1.0.0")


@app.on_event("startup")
def startup():
    initialize()


def require_token(authorization: str = Header(default="")):
    expected = os.getenv("API_ACCESS_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="API_ACCESS_TOKEN is not configured")
    scheme, _, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


@app.get("/health")
def health():
    return {"status": "ok", "service": "msemwafx-api"}


@app.get("/api/v1/signals")
def signals(
    limit: int = Query(default=50, ge=1, le=200),
    symbol: str | None = None,
    _: None = Depends(require_token),
):
    rows = list_signals(limit=limit, symbol=symbol)
    return {"count": len(rows), "signals": rows}


@app.get("/api/v1/signals/{signal_id}")
def signal_detail(signal_id: int, _: None = Depends(require_token)):
    row = get_signal(signal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Signal not found")
    return row
