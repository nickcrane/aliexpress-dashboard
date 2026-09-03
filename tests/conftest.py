"""Shared test fixtures.

`live_api_base_url` runs the real FastAPI app (aliexpress_dashboard.api.app)
on a real local socket for the duration of the test session -- used by tests
that exercise the dashboard's ApiClient, which uses a synchronous
httpx.Client and so can't use httpx.ASGITransport (async-only). Session
scoped because api/app.py reads Settings() fresh via Depends(get_settings)
on every request, so each test's own monkeypatched env vars (AE_DB_PATH,
AE_API_KEY, ...) take effect per-request without needing a fresh server.
"""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn

from aliexpress_dashboard.api.app import app as api_app


@pytest.fixture(scope="session")
def live_api_base_url():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(api_app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/health", timeout=0.5)
            break
        except httpx.TransportError:
            time.sleep(0.05)
    else:
        raise RuntimeError("Test API server did not become ready in time")

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)
