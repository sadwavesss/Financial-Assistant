"""Shared FastAPI dependencies."""

from collections.abc import Iterator
from typing import Annotated

import httpx
from fastapi import Depends, UploadFile
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import get_db
from app.integrations.exchange_rates import RateProvider, default_providers


def get_rate_providers() -> Iterator[list[RateProvider]]:
    """Online exchange rate sources sharing one HTTP client, closed after the request."""
    with httpx.Client(
        timeout=get_settings().rate_request_timeout_seconds,
        headers={"User-Agent": f"FinancialAssistant/{__version__}"},
        follow_redirects=True,
    ) as client:
        yield default_providers(client)


async def read_upload(file: UploadFile) -> bytes:
    """Read at most the allowed size + 1 byte, so huge uploads are rejected without loading them."""
    return await file.read(get_settings().import_max_bytes + 1)


DbSession = Annotated[Session, Depends(get_db)]
RateProviders = Annotated[list[RateProvider], Depends(get_rate_providers)]
