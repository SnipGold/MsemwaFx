"""Single-process production entry point: one scanner and one API."""
import os
import threading
import time
import traceback

import uvicorn
from api import app
from database import initialize
from main import run


def scan_loop():
    interval = max(60, int(os.getenv("SCAN_INTERVAL_SECONDS", "300")))
    while True:
        started = time.monotonic()
        try:
            run()
        except Exception:
            traceback.print_exc()
        elapsed = time.monotonic() - started
        time.sleep(max(5, interval - elapsed))


if __name__ == "__main__":
    initialize()
    worker = threading.Thread(target=scan_loop, name="msemwafx-scanner", daemon=True)
    worker.start()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        log_level="info",
    )
