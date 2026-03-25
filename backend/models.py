"""Pydantic models for API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class IngestGame(BaseModel):
    rank: int
    appid: str
    name: str
    icon_url: str | None = None
    tags: list[Any] | str | None = None
    developer: str | None = None


class IngestBody(BaseModel):
    date: str
    platform: str = Field(pattern="^(wx|dy)$")
    chart: str  # renqi | changwan | changxiao | xinyou
    games: list[IngestGame]


class RankingsQuery(BaseModel):
    date: str | None = None
    platform: str = "wx"
