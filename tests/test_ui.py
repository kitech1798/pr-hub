"""디자인 부품(app/ui.py) 단위 테스트 — Streamlit 없이 문자열만 검증한다.

핵심 불변식 두 가지:
  ① 데이터에서 온 문자열은 어떤 부품을 통과해도 HTML 로 해석되지 않는다(esc).
  ② 숫자 부품은 빈 값·같은 값·한 점짜리 입력에서도 깨지지 않는다.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import ui  # noqa: E402

XSS = "<img src=x onerror=alert(1)>"


def _no_raw_tag(markup: str) -> None:
    """이스케이프되면 '<img src=x'(원시 태그)가 남지 않고 '&lt;img src=x'로 바뀐다."""
    assert "<img src=x" not in markup and XSS not in markup


def test_all_dynamic_text_is_escaped() -> None:
    _no_raw_tag(ui.kpi(XSS, XSS, XSS, hint=XSS))
    _no_raw_tag(ui.section(XSS, XSS, XSS))
    _no_raw_tag(ui.chart_title(XSS, XSS))
    _no_raw_tag(ui.rank_panel(XSS, [(XSS, XSS, XSS)], XSS))
    _no_raw_tag(ui.word_ranking([(XSS, 3)]))
    _no_raw_tag(ui.row_html(date=XSS, title=XSS, link=XSS, summary=XSS, chips_html="", channel=XSS, thumb=XSS))
    _no_raw_tag(ui.tile_html(date=XSS, title=XSS, link=XSS, thumb=XSS, chips_html=""))
    _no_raw_tag(ui.empty_state(XSS, XSS))
    _no_raw_tag(ui.footer_html({XSS: XSS}, XSS))
    _no_raw_tag(ui.hero_html(1, 2003, 2026, {XSS: 1}, XSS, intro=True))


def test_markup_has_no_blank_lines_or_indented_lines() -> None:
    """마크다운은 빈 줄·4칸 들여쓰기를 코드블록으로 바꾼다 — 한 줄 문자열이어야 한다."""
    parts = [ui.intro_html(), ui.hero_html(2975, 2003, 2026, {"보도자료": 259, "블로그": 1230}, "2026-11-16", True),
             ui.kpi("a", "1", "건", "s", spark=[1, 2, 3]), ui.section("k", "t", "d"), ui.word_ranking([("가", 2), ("나", 1)])]
    for m in parts:
        assert "\n" not in m


def test_spark_svg_degenerate_inputs() -> None:
    assert ui.spark_svg([]) == "" and ui.spark_svg([5]) == ""
    flat = ui.spark_svg([3, 3, 3, 3])          # 값이 모두 같아도 0 나눗셈 없이 그려진다
    assert "nan" not in flat.lower() and "<polyline" in flat
    pts = [float(x) for x in re.findall(r"cy='([\d.]+)'", ui.spark_svg([0, 10, 5]))]
    assert pts and all(0 <= y <= 32 for y in pts)


def test_delta_text_uses_symbol_not_just_color() -> None:
    assert "▲" in ui.delta_text(5, 3) and "2건" in ui.delta_text(5, 3)
    assert "▼" in ui.delta_text(3, 5)
    assert "변동 없음" in ui.delta_text(4, 4)


def test_share_bar_skips_zero_and_keeps_all_in_legend() -> None:
    m = ui.share_bar({"보도자료": 259, "포토뉴스": 0, "블로그": 1230})
    assert m.count("<i style='flex:") == 2      # 막대 조각은 0건을 건너뛴다
    assert "포토뉴스" in m                        # 범례에는 0건도 남는다(없다는 사실도 정보)
    assert "1,230" in m


def test_hero_count_is_real_number_and_intro_flag() -> None:
    h = ui.hero_html(2975, 2003, 2026, {"보도자료": 1}, "2026-11-16", intro=True)
    assert "data-count='2975'" in h and ">2,975<" in h   # JS 가 막혀도 최종 숫자가 DOM 에 있다
    assert "kt-hero intro" in h and "kt-hero intro" not in ui.hero_html(1, None, None, {}, "-", intro=False)


def test_css_tokens_are_injected_and_icons_excluded_from_font_override() -> None:
    c = ui.css()
    assert "__" not in c.replace("__NOISE__", "")           # 치환 안 된 토큰 없음
    assert ui.BG in c and ui.ACCENT in c
    assert 'stIconMaterial' in c                              # 아이콘 폰트를 덮어쓰지 않는다
    assert "prefers-reduced-motion" in c                      # 모션 줄이기 대응


def test_channel_colors_cover_all_channels() -> None:
    assert set(ui.CHANNEL_COLORS) == {"보도자료", "포토뉴스", "유튜브", "블로그"}
