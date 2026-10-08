"""Earth Engine service-account authentication.

Lazy singleton: importing this module never performs network I/O, so the
FastAPI app and the test suite can import the data engine even when Earth
Engine is unreachable or the key is absent.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

import ee

from backend.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_init_error: Optional[str] = None

# (monotonic timestamp, result) of the last liveness probe.
_avail_cache: Optional[Tuple[float, bool]] = None
AVAIL_TTL_S = 60.0


class GEEAuthError(RuntimeError):
    """Raised when Earth Engine cannot be initialized."""


def _read_client_email(key_path: Path) -> str:
    """Pull the service-account email out of the key rather than hardcoding it."""
    with key_path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    email = payload.get("client_email")
    if not email:
        raise GEEAuthError(f"'client_email' missing from key file: {key_path}")
    return email


def initialize_gee(force: bool = False) -> None:
    """Initialize the Earth Engine client. Idempotent and thread-safe."""
    global _initialized, _init_error

    if _initialized and not force:
        return

    with _lock:
        if _initialized and not force:
            return

        key_path = Path(settings.gee_key_path)
        if not key_path.is_file():
            _init_error = f"Service-account key not found at {key_path}"
            raise GEEAuthError(_init_error)

        try:
            credentials = ee.ServiceAccountCredentials(
                email=_read_client_email(key_path),
                key_file=str(key_path),
            )
            ee.Initialize(credentials=credentials, project=settings.gee_project_id)
        except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the caller
            _init_error = f"Earth Engine initialization failed: {exc}"
            raise GEEAuthError(_init_error) from exc

        _initialized = True
        _init_error = None
        logger.info("Earth Engine initialized for project %s", settings.gee_project_id)


def is_available(max_age_s: float = AVAIL_TTL_S) -> bool:
    """True when Earth Engine can serve a request, without raising.

    Performs a real (tiny) round-trip rather than trusting that
    initialization alone implies connectivity -- but caches the answer.
    /api/health calls this and the frontend polls every 20 s; uncached, each
    poll was a live EE call taking 1.5-3.4 s against a project already in
    restricted-quota mode, and the latency alone tripped the client's
    health timeout. Pass max_age_s=0 to force a fresh probe.
    """
    global _avail_cache
    now = time.monotonic()
    if _avail_cache is not None and now - _avail_cache[0] < max_age_s:
        return _avail_cache[1]

    try:
        initialize_gee()
        ee.Number(1).getInfo()
        ok = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Earth Engine unavailable: %s", exc)
        ok = False
    _avail_cache = (now, ok)
    return ok


def last_error() -> Optional[str]:
    return _init_error
