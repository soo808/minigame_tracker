"""Pydantic models for API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.analyzer.insight_infer import insight_batch_size_default


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
    batch_size: int = Field(default_factory=insight_batch_size_default, ge=1, le=50)
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
        description="为真时仅取三榜各前 N 名（INSIGHT_CHART_TOP_N，默认 100）的并集（与 appid 互斥）",
    )
    chart_top_n: int | None = Field(
        None,
        ge=1,
        le=200,
        description="并集模式下每榜深度；省略则读环境 INSIGHT_CHART_TOP_N",
    )
    insight_gap_only: bool = Field(
        True,
        description="并集模式下仅推断至少缺一类的游戏（无变现/unknown/无玩法/无传播）；force=true 时视为 false",
    )


class InsightInferTop50Body(BaseModel):
    """Start background job: infer insights for three-chart union (top N per chart)."""

    platform: str = Field(..., pattern="^(wx|dy|yyb)$")
    ranking_date: str | None = Field(
        None,
        description="榜单日；省略则用该平台 rankings 最新 date",
    )
    batch_size: int = Field(default_factory=insight_batch_size_default, ge=1, le=50)
    chart_top_n: int | None = Field(
        None,
        ge=1,
        le=200,
        description="每榜深度；省略则读环境 INSIGHT_CHART_TOP_N",
    )
    insight_gap_only: bool = True
    force: bool = False


class AdxInsightsAnalyzeBody(BaseModel):
    """POST /api/adx/insights/analyze — LLM 解读榜单侧特征（可选落库）。"""

    appid: str
    platform: str = Field("wx", pattern="^(wx|dy|yyb)$")
    end_date: str | None = Field(
        None,
        description="YYYY-MM-DD；省略用该平台 rankings 最新日",
    )
    days: int = Field(30, ge=7, le=90)
    persist: bool = Field(False, description="为真时写入 adx_llm_reports（复用 ADX 报告表）")


class InsightInferFullBody(BaseModel):
    """POST /api/insight/infer-full — full-coverage: infer ALL chart games, no rank cutoff."""

    platform: str = Field(..., pattern="^(wx|dy|yyb)$")
    ranking_date: str | None = Field(
        None,
        description="榜单日 YYYY-MM-DD；省略则用该平台 rankings 中最新 date",
    )
    batch_size: int = Field(default_factory=insight_batch_size_default, ge=1, le=50)
    insight_gap_only: bool = Field(
        True,
        description="仅推断至少缺一类的游戏；force=true 时视为 false",
    )
    force: bool = False


class PlatformTrendReportBody(BaseModel):
    """POST /api/trend/report — platform-wide trend analysis via LLM."""

    platform: str = Field("wx", pattern="^(wx|dy|yyb)$")
    end_date: str | None = Field(None, description="YYYY-MM-DD；省略用最新")
    days: int = Field(30, ge=7, le=90)
    persist: bool = Field(True, description="写入 adx_llm_reports")


class AdxSyncBody(BaseModel):
    """POST /api/adx/sync — trigger creative sync from colleague site."""

    dry_run: bool = Field(False, description="仅拉第一页预览，不写库")
    page_size: int = Field(50, ge=1, le=200)


class QARequest(BaseModel):
    """POST /api/qa — AI question answering."""

    question: str
    platform: str = Field("wx", pattern="^(wx|dy|yyb)$")
    date: str | None = Field(None, description="YYYY-MM-DD; omit for latest")
