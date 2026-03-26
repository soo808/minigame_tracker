import pytest
from pydantic import ValidationError

from backend.ingest_service import map_ingest_chart
from backend.models import IngestBody


class TestIngestBodyYyb:
    def test_yyb_platform_accepted(self):
        body = IngestBody(
            date="2026-03-25",
            platform="yyb",
            chart="popular",
            games=[],
        )
        assert body.platform == "yyb"

    def test_invalid_platform_rejected(self):
        with pytest.raises(ValidationError):
            IngestBody(date="2026-03-25", platform="tiktok", chart="popular", games=[])


class TestMapIngestChartYyb:
    @pytest.mark.parametrize(
        "chart,expected",
        [
            ("popular", "popular"),
            ("bestseller", "bestseller"),
            ("new_game", "new_game"),
        ],
    )
    def test_yyb_chart_mapping(self, chart, expected):
        assert map_ingest_chart("yyb", chart) == expected

    def test_yyb_invalid_chart_raises(self):
        with pytest.raises(ValueError):
            map_ingest_chart("yyb", "unknown_chart")
