"""Single SQLite store for MsemwaFX signal history and current status."""
import json
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.getenv("DATABASE_PATH", "msemwafx.sqlite3")


def connect():
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    return conn


def initialize():
    with connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                setup_key TEXT NOT NULL UNIQUE,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                generated_at TEXT,
                status TEXT NOT NULL,
                instruction TEXT,
                entry REAL,
                entry_low REAL,
                entry_high REAL,
                sl REAL,
                tp1 REAL,
                tp2 REAL,
                tp3 REAL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")


def save_signal(symbol, setup, status, instruction):
    initialize()
    setup_key = "|".join((
        symbol,
        str(setup.get("direction", "")),
        str(setup.get("signal_candle", "")),
        str(setup.get("entry", "")),
    ))
    now = datetime.now(timezone.utc).isoformat()
    values = (
        setup_key, symbol, setup.get("direction", ""), setup.get("generated_at"),
        status, instruction, setup.get("entry"), setup.get("entry_low"),
        setup.get("entry_high"), setup.get("sl"), setup.get("tp1"),
        setup.get("tp2"), setup.get("tp3"),
        json.dumps(setup, separators=(",", ":"), default=str), now, now,
    )
    with connect() as conn:
        conn.execute("""
            INSERT INTO signals (
                setup_key, symbol, direction, generated_at, status, instruction,
                entry, entry_low, entry_high, sl, tp1, tp2, tp3,
                payload_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(setup_key) DO UPDATE SET
                generated_at=excluded.generated_at,
                status=excluded.status,
                instruction=excluded.instruction,
                entry=excluded.entry,
                entry_low=excluded.entry_low,
                entry_high=excluded.entry_high,
                sl=excluded.sl,
                tp1=excluded.tp1,
                tp2=excluded.tp2,
                tp3=excluded.tp3,
                payload_json=excluded.payload_json,
                updated_at=excluded.updated_at
        """, values)


def list_signals(limit=50, symbol=None):
    initialize()
    limit = max(1, min(int(limit), 200))
    with connect() as conn:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM signals WHERE symbol=? ORDER BY created_at DESC LIMIT ?",
                (symbol.upper().replace("-", "/"), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM signals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(row) for row in rows]


def get_signal(signal_id):
    initialize()
    with connect() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id=?", (int(signal_id),)).fetchone()
    return dict(row) if row else None
