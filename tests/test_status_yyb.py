import pytest


class TestRunAnalysisBugFix:
    def _setup_db(self, tmp_path, monkeypatch):
        import backend.db as db_mod

        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "test.db"))
        db_mod.init_db()
        return db_mod

    def test_run_analysis_with_yyb_charts_does_not_produce_empty_target(self, tmp_path, monkeypatch):
        db_mod = self._setup_db(tmp_path, monkeypatch)
        from backend.analyzer import status as st

        yyb_charts = {("yyb", "popular"), ("yyb", "bestseller"), ("yyb", "new_game")}

        date = "2026-03-25"
        with db_mod.get_conn() as conn:
            conn.execute(
                "INSERT INTO games (appid, platform, name, first_seen, updated_at) VALUES ('wx001','yyb','G','2026-03-25','2026-03-25')"
            )
            conn.execute(
                "INSERT INTO rankings (date, platform, chart, rank, appid) VALUES (?,?,?,1,'wx001')",
                (date, "yyb", "popular"),
            )

        st.run_analysis(date, charts=yyb_charts)

        with db_mod.get_conn() as conn:
            rows = conn.execute(
                "SELECT platform, chart FROM daily_status WHERE date=?", (date,)
            ).fetchall()
        processed_charts = [(r["platform"], r["chart"]) for r in rows]

        assert ("yyb", "popular") in processed_charts

    def test_run_analysis_none_uses_required_charts(self, tmp_path, monkeypatch):
        db_mod = self._setup_db(tmp_path, monkeypatch)
        from backend.analyzer import status as st

        date = "2026-03-25"
        st.run_analysis(date, charts=None)


class TestYybGate:
    def _setup_db(self, tmp_path, monkeypatch):
        import backend.db as db_mod

        monkeypatch.setattr(db_mod, "DB_PATH", str(tmp_path / "test.db"))
        db_mod.init_db()
        return db_mod

    def _insert_snapshot(self, db_mod, date, platform, chart, status):
        with db_mod.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO snapshots (date, platform, chart, fetched_at, status, game_count)
                VALUES (?, ?, ?, '2026-03-25T11:00:00+08:00', ?, 0)
                """,
                (date, platform, chart, status),
            )

    def test_yyb_gate_fires_when_all_three_ok(self, tmp_path, monkeypatch):
        db_mod = self._setup_db(tmp_path, monkeypatch)
        from backend.analyzer import status as st

        date = "2026-03-25"
        for chart in ("popular", "bestseller", "new_game"):
            self._insert_snapshot(db_mod, date, "yyb", chart, "ok")

        run_analysis_calls = []
        tag_analysis_calls = []
        monkeypatch.setattr(st, "run_analysis", lambda d, charts=None: run_analysis_calls.append((d, charts)))
        monkeypatch.setattr(st, "_run_yyb_tag_analysis", lambda d: tag_analysis_calls.append(d))

        st.maybe_run_analysis_after_snapshot(date)

        assert any(charts == st.YYB_REQUIRED_CHARTS for _, charts in run_analysis_calls)
        assert date in tag_analysis_calls

    def test_yyb_gate_does_not_fire_if_incomplete(self, tmp_path, monkeypatch):
        db_mod = self._setup_db(tmp_path, monkeypatch)
        from backend.analyzer import status as st

        date = "2026-03-25"
        for chart in ("popular", "new_game"):
            self._insert_snapshot(db_mod, date, "yyb", chart, "ok")

        tag_analysis_calls = []
        monkeypatch.setattr(st, "run_analysis", lambda d, charts=None: None)
        monkeypatch.setattr(st, "_run_yyb_tag_analysis", lambda d: tag_analysis_calls.append(d))

        st.maybe_run_analysis_after_snapshot(date)
        assert tag_analysis_calls == []

    def test_yyb_gate_independent_from_wx_dy(self):
        from backend.analyzer import status as st

        assert st.YYB_REQUIRED_CHARTS.isdisjoint(st.REQUIRED_CHARTS)

    def test_wx_gate_not_affected_by_yyb_only_snapshots(self, tmp_path, monkeypatch):
        db_mod = self._setup_db(tmp_path, monkeypatch)
        from backend.analyzer import status as st

        date = "2026-03-25"
        for chart in ("popular", "bestseller", "new_game"):
            self._insert_snapshot(db_mod, date, "yyb", chart, "ok")

        wx_dy_analysis_called = []

        def spy_run_analysis(d, charts=None):
            if charts is None:
                wx_dy_analysis_called.append(d)

        monkeypatch.setattr(st, "run_analysis", spy_run_analysis)
        monkeypatch.setattr(st, "_run_yyb_tag_analysis", lambda d: None)

        st.maybe_run_analysis_after_snapshot(date)
        assert wx_dy_analysis_called == []
