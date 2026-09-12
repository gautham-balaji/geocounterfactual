"""Earth Engine service-account authentication.

Lazy singleton: importing this module never performs network I/O, so the
FastAPI app and the test suite can import the data engine even when Earth
Engine is unreachable or the key is absent.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

import ee

from backend.config import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_initialized = False
_init_error: Optional[str] = None


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


def is_available() -> bool:
    """True when Earth Engine can serve a request, without raising.

    Used by the cache layer to decide between a live fetch and the synthetic
    fallback, so it performs a real (tiny) round-trip rather than trusting that
    initialization alone implies connectivity.
    """
    try:
        initialize_gee()
        ee.Number(1).getInfo()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Earth Engine unavailable: %s", exc)
        return False


def last_error() -> Optional[str]:
    return _init_error
