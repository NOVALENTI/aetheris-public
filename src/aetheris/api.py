"""Minimal content extraction service with explicit source-host allowlisting.

This is a standalone demonstration, not a copy of any private deployment.
No credential values, private service URLs, or private infrastructure are included.
"""
from __future__ import annotations

import hmac
import ipaddress
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class ExtractRequest(BaseModel):
    url: str = Field(min_length=12, max_length=2048)
    topic: str = Field(default="general", min_length=1, max_length=80)


class ExtractResponse(BaseModel):
    source_url: str
    topic: str
    headline: str
    key_facts: list[str]
    provider: str
    extracted_at: datetime


@dataclass(frozen=True)
class Settings:
    access_token: str
    allowed_hosts: frozenset[str]

    @classmethod
    def from_env(cls) -> Settings:
        hosts = frozenset(
            value.strip().lower().rstrip(".")
            for value in os.getenv("ALLOWED_SOURCE_HOSTS", "").split(",")
            if value.strip()
        )
        return cls(access_token=os.getenv("APP_ACCESS_TOKEN", ""), allowed_hosts=hosts)


class ContentProvider(Protocol):
    async def retrieve(self, url: str) -> str: ...


class JinaReader:
    """Uses a fixed external reader service; client never follows redirects."""

    async def retrieve(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
            response = await client.get("https://r.jina.ai/" + url, headers={"Accept": "text/plain"})
            response.raise_for_status()
            if len(response.content) > 200_000:
                raise ValueError("Response exceeds allowed size")
            return response.text


def validate_url(url: str, allowed_hosts: frozenset[str]) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid URL") from exc
    if parsed.scheme != "https" or not host or not parsed.netloc:
        raise ValueError("Only HTTPS URLs are supported")
    if parsed.username or parsed.password or (port is not None and port != 443):
        raise ValueError("Embedded credentials and custom ports are not accepted")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("IP address destinations are not accepted")
    if not allowed_hosts or host not in allowed_hosts:
        raise ValueError("Source host is not in the configured allowlist")
    if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host or host.startswith("-"):
        raise ValueError("Invalid source hostname")
    if parsed.fragment:
        raise ValueError("URL fragments are not accepted")
    return url


def summarize(text: str) -> tuple[str, list[str]]:
    """Extract source lines without pretending to generate AI inferences."""
    lines = [re.sub(r"\s+", " ", line).strip(" -#*\t") for line in text.splitlines()]
    lines = [line for line in lines if 20 <= len(line) <= 240 and not line.startswith("http")]
    headline = next((line for line in lines if len(line) <= 110), "Source content")
    facts = [line for line in lines if line != headline][:5]
    return headline, facts


def create_app(settings: Settings | None = None, provider: ContentProvider | None = None) -> FastAPI:
    config = settings if settings is not None else Settings.from_env()
    reader = provider if provider is not None else JinaReader()
    app = FastAPI(title="Aetheris Public API Demo", version="1.0.0")

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/extract", response_model=ExtractResponse)
    async def extract(payload: ExtractRequest, x_proxy_key: str | None = Header(default=None)) -> ExtractResponse:
        if not config.access_token or not x_proxy_key or not hmac.compare_digest(x_proxy_key, config.access_token):
            raise HTTPException(status_code=401, detail="Unauthorized")
        try:
            safe_url = validate_url(payload.url, config.allowed_hosts)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        try:
            source_text = await reader.retrieve(safe_url)
        except (httpx.HTTPError, ValueError) as exc:
            # Avoid returning upstream URLs, response bodies or internal exception messages.
            raise HTTPException(status_code=502, detail="Content provider unavailable") from exc
        headline, facts = summarize(source_text[:60_000])
        return ExtractResponse(
            source_url=safe_url,
            topic=payload.topic,
            headline=headline,
            key_facts=facts,
            provider="public-reader",
            extracted_at=datetime.now(timezone.utc),
        )

    return app


app = create_app()
