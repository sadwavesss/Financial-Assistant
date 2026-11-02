"""Temporary storage of an uploaded file between the preview and the confirmation steps."""

import re
import time
import uuid
from pathlib import Path

from app.config import IMPORTS_DIR
from app.importers import IMPORTERS
from app.services.errors import NotFoundError

STORE_DIR: Path = IMPORTS_DIR  # replaced by a temporary folder in tests
MAX_AGE_SECONDS = 24 * 60 * 60
# Only our own tokens are accepted, so a request cannot point to an arbitrary file.
TOKEN_PATTERN = re.compile(r"[0-9a-f]{32}")


def save_upload(content: bytes, file_format: str) -> str:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    _remove_stale()
    token = uuid.uuid4().hex
    (STORE_DIR / f"{token}.{file_format}").write_bytes(content)
    return token


def load_upload(token: str) -> tuple[bytes, str]:
    """Return (content, format) of a stored upload."""
    path = _find(token)
    return path.read_bytes(), path.suffix.removeprefix(".")


def delete_upload(token: str) -> None:
    _find(token).unlink(missing_ok=True)


def _find(token: str) -> Path:
    if TOKEN_PATTERN.fullmatch(token):
        for file_format in IMPORTERS:
            path = STORE_DIR / f"{token}.{file_format}"
            if path.is_file():
                return path
    raise NotFoundError("Файл для импорта не найден или устарел. Загрузите его заново.")


def _remove_stale() -> None:
    deadline = time.time() - MAX_AGE_SECONDS
    for path in STORE_DIR.iterdir():
        if path.is_file() and path.stat().st_mtime < deadline:
            path.unlink(missing_ok=True)
