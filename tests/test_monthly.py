"""월간 보고서 — 규칙 경계, 진행 중 달, 이스케이프."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import monthly_report as mr  # noqa: E402

DIMS = {"보도유형": "연구성과·기술개발", "연구분야": "로봇·드론", "전략기술": "x", "제조혁신 로드맵": "x",
        "지역혁신 로드맵": "x", "R&R 연계": "직접 연계", "가시성": "높음"}


def perf_row(i: int, d: str, media: int, status: str = "확정", title: str | None = None, pending: int = 0) -> dict:
    return {"id": str(i), "배포일": pd.Timestamp(d), "제목": title or f"보도 {i}", "기사 수": media, "매체 수": media,
            "검토대기 기사": pending, "집계 상태": status, "링크": f"https://www.kitech.re.kr/pages/61?id={i}", **DIMS}


def inputs(perf_rows: list[dict], hub_rows: list[dict] | None = None):
    perf = pd.DataFrame(perf_rows)
    hub = pd.DataFrame(hub_rows or [{"채널": "보도자료", "게시일": "2026-10-05", "제목": "a", "링크": "", "조회수": "10"}])
    hub["게시일"] = pd.to_datetime(hub["게시일"])
    hub["조회수_n"] = pd.to_numeric(hub["조회수"], errors="coerce")
    hub["댓글수_n"] = float("nan")
    fields = pd.DataFrame([
        {"축": "가시성", "항목": "높음", "보도자료 수": 20, "매체 수 중앙값": 16, "매체 수 평균": 16.0, "전체 평균 대비": 1.4, "기사 수 합계": 1},
        {"축": "가시성", "항목": "낮음", "보도자료 수": 80, "매체 수 중앙값": 9, "매체 수 평균": 8.0, "전체 평균 대비": 0.8, "기사 수 합계": 1},
        {"축": "연구분야", "항목": "로봇·드론", "보도자료 수": 14, "매체 수 중앙값": 16, "매체 수 평균": 16.0, "전체 평균 대비": 1.4, "기사 수 합계": 1},
    ])
    return hub, perf, fields, {"기준일": "2026-11-10"}, pd.DataFrame(columns=["기준일", "채널", "id", "조회수", "댓글수"])


BASE = [perf_row(i, "2025-01-01", 10) for i in range(1, 9)]  # 전체 중앙값 10, 하위 25% 10


def test_months_from_starts_october_2026() -> None:
    assert mr.months_from("2026-10", date(2026, 12, 3)) == ["2026-10", "2026-11", "2026-12"]


def test_good_threshold_is_1_3x_median() -> None:
    hit = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-14", 13)]), today=date(2026, 12, 20))
    miss = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-14", 12)]), today=date(2026, 12, 20))
    assert any("매체 13곳" in g and "1.3배" in g for g in hit.good)
    assert not any("매체 12곳" in g for g in miss.good)


def test_bad_needs_14_days_since_release() -> None:
    fresh = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-30", 2, "집계 중 (D+5)")]), today=date(2026, 11, 4))
    old = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-01", 2)]), today=date(2026, 11, 4))
    assert not any("하위 25%" in b for b in fresh.bad)  # 막 나간 보도자료를 '나쁨'으로 찍지 않는다
    assert any("하위 25%" in b for b in old.bad)
    assert any("가시성" in a for a in old.actions)  # Bad가 있으면 그에 맞는 개선점이 붙는다


YT_HISTORY = [{"채널": "유튜브", "게시일": f"{(pd.Timestamp('2025-11-15') + pd.DateOffset(months=k)):%Y-%m-%d}",
               "제목": f"v{k}", "링크": "", "조회수": "1"} for k in range(12) for _ in range(2)]  # 12개월 매달 2건


def test_in_progress_month_flagged_and_no_channel_bad() -> None:
    done = mr.build("2026-11", *inputs(BASE, YT_HISTORY), today=date(2026, 12, 2))
    assert any("유튜브" in b and "절반 이하" in b for b in done.bad)  # 끝난 달이면 잡힌다(대조군)
    assert any("유튜브 발행 주기" in a for a in done.actions)
    rep = mr.build("2026-11", *inputs(BASE, YT_HISTORY), today=date(2026, 11, 10))
    assert rep.in_progress
    assert any("진행 중" in n for n in rep.notes)
    assert not any("절반 이하" in b for b in rep.bad)  # 달 중간에 '발행 부족'이라 하지 않는다
    assert not any("발행 주기" in a for a in rep.actions)  # 개선점도 같은 조건 — 실측 버그(11월 진행 중에 떴음)


def test_pending_reviews_reported_as_lower_bound() -> None:
    rep = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-14", 12, pending=3)]), today=date(2026, 12, 1))
    assert any("3건" in b and "하한값" in b for b in rep.bad)


def test_render_escapes_titles() -> None:
    rep = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-14", 13, title="<script>x</script>")]),
                   today=date(2026, 12, 1))
    out = mr.render(rep)
    assert "<script>x" not in out and "&lt;script&gt;" in out


def test_report_has_no_commands_or_paths() -> None:
    """보고서는 홍보실·기관장이 읽는다 — 실행 명령·파일 경로가 화면에 나오면 안 된다."""
    rep = mr.build("2026-10", *inputs(BASE + [perf_row(50, "2026-10-01", 2, pending=3)]), today=date(2026, 12, 1))
    out = mr.render(rep)
    for bad in ("run.ps1", "`", ".py", "C:\\", "review-export"):
        assert bad not in out, bad


def test_short_does_not_cut_mid_word() -> None:
    assert mr.short("The History of Agriculture Encountered in Jeonju", 30) == "The History of Agriculture…"
    assert mr.short("짧은 제목", 30) == "짧은 제목"
