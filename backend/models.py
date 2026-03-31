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
    platform: str = Field(pattern="^(wx|dy|yyb)$")
    chart: str  # renqi | changwan | changxiao | xinyou
    games: list[IngestGame]


class RankingsQuery(BaseModel):
    date: str | None = None
    platform: str = "wx"


class GameplayAssignBody(BaseModel):
    appid: str
    tag_id: int
    role: str | None = None
    source: str = "manual"
    updated_by: str | None = None


class MonetizationUpsertBody(BaseModel):
    appid: str
    monetization_model: str
    mix_note: str | None = None
    confidence: float | None = None
    evidence_summary: str | None = None
    ad_placement_notes: str | None = None
    source: str = "manual"
    updated_by: str | None = None


class ViralityUpsertBody(BaseModel):
    appid: str
    hypothesis: str
    channels: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    source: str = "manual"
    updated_by: str | None = None


class InsightInferBatchBody(BaseModel):
    """Body for POST /api/insight/infer-batch (and defaults for monetization/virality run)."""

    limit: int = Field(120, ge=1, le=2000)
    batch_size: int = Field(12, ge=1, le=50)
    only_missing: bool = True
    force: bool = False
    platform: str = Field("wx", pattern="^(wx|dy|yyb)$")
    ranking_date: str | None = Field(
        None,
        description="榜单日 YYYY-MM-DD；省略则用该平台 rankings 中最新 date",
    )
    appid: str | None = Field(
        None,
        description="若填写则只推断该游戏，忽略 limit / ranking_date 的候选筛选",
    )
    top50_charts: bool = Field(
        False,
        description="为真时仅取三榜各前50名的并集（与 appid 互斥）",
    )
    insight_gap_only: bool = Field(
        True,
        description="top50 模式下仅推断至少缺一类的游戏（无变现/unknown/无玩法/无传播）；force=true 时视为 false",
    )


class InsightInferTop50Body(BaseModel):
    """Start background job: infer insights for top-50 union on three charts."""

    platform: str = Field(..., pattern="^(wx|dy|yyb)$")
    ranking_date: str | None = Field(
        None,
        description="榜单日；省略则用该平台 rankings 最新 date",
    )
    batch_size: int = Field(12, ge=1, le=50)
    insight_gap_only: bool = True
    force: bool = False
