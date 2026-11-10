"""앱이 현재 data/ 로 예외 없이 그려지는가 — 주간 갱신이 앱을 깨뜨린 채 푸시하지 않게 하는 마지막 관문."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def test_app_renders_without_exception() -> None:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [t.label for t in at.tabs]
    assert labels[:3] == ["📊 대시보드", "📈 보도성과", "🔍 통합검색"]


def test_perf_tab_respects_search_filter() -> None:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.sidebar.text_input[0].set_value("존재하지않는검색어zz").run()
    assert not at.exception, [e.value for e in at.exception]
