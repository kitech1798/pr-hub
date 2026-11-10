"""반응 지표 — 조회수 파싱, 갱신 대상, 이력 중복 방지, 열 보존(스키마 한 곳)."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import collect_metrics as cm  # noqa: E402
import common  # noqa: E402

TODAY = date(2026, 11, 10)


def test_parse_view_count() -> None:
    assert common.parse_view_count("등록일 2003-09-17 조회수 6,791 [2003]") == 6791
    assert common.parse_view_count("등록일 2026-11-09 조회수 54 첨부파일") == 54
    assert common.parse_view_count("조회 없음") is None


def rec(ch: str, i: str, d: str, views: str = "", basis: str = "") -> dict:
    return {"채널": ch, "id": i, "게시일": d, "링크": f"https://www.kitech.re.kr/x?id={i}", "조회수": views, "지표기준일": basis}


def test_board_targets_recent_or_missing() -> None:
    records = {
        ("보도자료", "1"): rec("보도자료", "1", "2026-10-01", "50"),   # 최근 → 다시
        ("포토뉴스", "2"): rec("포토뉴스", "2", "2020-01-01", "900"),  # 오래됨·값 있음 → 건너뜀
        ("포토뉴스", "3"): rec("포토뉴스", "3", "2019-01-01", ""),     # 값 없음 → 다시
        ("유튜브", "4"): rec("유튜브", "4", "2026-10-01", ""),         # 홈페이지 아님
    }
    assert sorted(cm.board_targets(records, TODAY, 400, False)) == [("보도자료", "1"), ("포토뉴스", "3")]
    assert len(cm.board_targets(records, TODAY, 400, True)) == 3


def test_history_only_today_and_no_duplicates(tmp_path: Path) -> None:
    records = {("보도자료", "1"): rec("보도자료", "1", "2026-10-01", "50", "2026-11-10"),
               ("보도자료", "2"): rec("보도자료", "2", "2026-10-01", "70", "2026-11-03")}
    rows = cm.history_rows(records, TODAY)
    assert [r["id"] for r in rows] == ["1"]
    p = tmp_path / "h.csv"
    assert cm.append_history(rows, p) == 1
    assert cm.append_history(rows, p) == 0  # 같은 날 두 번 돌려도 한 줄


def test_save_keeps_metric_columns(tmp_path: Path) -> None:
    """수집기가 조회수 열을 모르더라도 저장 때 지워지지 않아야 한다(예전 구조의 함정)."""
    p = tmp_path / "d.csv"
    common.save_dataset({("보도자료", "1"): rec("보도자료", "1", "2026-10-01", "50", "2026-11-10")}, p)
    back = common.load_dataset(p)[("보도자료", "1")]
    assert back["조회수"] == "50" and back["지표기준일"] == "2026-11-10"
