"""앱이 현재 data/·reports/ 로 예외 없이 그려지는가 — 주간 갱신이 앱을 깨뜨린 채 푸시하지 않게 하는 마지막 관문."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py"


def run() -> AppTest:
    return AppTest.from_file(str(APP), default_timeout=90).run()


def test_app_renders_without_exception() -> None:
    at = run()
    assert not at.exception, [e.value for e in at.exception]
    assert [t.label for t in at.tabs][:4] == ["📊 대시보드", "📈 보도성과", "🗓 월간 보고서", "🔍 통합검색"]


def test_perf_tab_respects_search_filter() -> None:
    at = run()
    at.sidebar.text_input[0].set_value("존재하지않는검색어zz").run()
    assert not at.exception, [e.value for e in at.exception]


def test_every_dimension_axis_renders() -> None:
    at = run()
    seg = [w for w in at.get("button_group") if getattr(w, "key", None) == "dim_axis"]
    if not seg:  # 보도성과 데이터가 없으면 축 선택이 없다 — 안내 화면만 확인
        return
    for opt in ["보도유형", "국가전략기술", "제조혁신 로드맵", "지역혁신 로드맵", "R&R 연계", "가시성"]:
        seg[0].set_value(opt).run()
        assert not at.exception, (opt, [e.value for e in at.exception])


def test_every_monthly_report_renders() -> None:
    at = run()
    boxes = [s for s in at.selectbox if s.label == "보고서 월"]
    if not boxes:
        return
    for opt in boxes[0].options:
        boxes[0].set_value(opt).run()
        assert not at.exception, (opt, [e.value for e in at.exception])
