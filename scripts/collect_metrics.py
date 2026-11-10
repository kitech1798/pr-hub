"""반응 지표(조회수·댓글수) 갱신 → data/허브-데이터셋.csv + data/지표_이력.csv

채널별로 공개된 지표만 모은다(2026-11-10 확인):
    보도자료·포토뉴스 : 홈페이지 게시판 상세의 '조회수'(누적)
    유튜브            : yt-dlp가 주는 view_count — collect_youtube.py --merge 가 채운다(여기선 이력만)
    블로그            : 조회수 비공개(readCount 빈 값) → 목록 API의 commentCount(댓글 수)만

    python scripts/collect_metrics.py              # 최근 400일 게시물 조회수 + 블로그 댓글 + 이력
    python scripts/collect_metrics.py --all        # 홈페이지 전체(약 1,370건, 15분 내외)

이력은 '그달 늘어난 조회수'를 계산하려고 쌓는다. 누적 조회수는 오래된 글일수록 크므로
월간 보고서에서 글끼리 비교할 때는 같은 기준일·비슷한 경과일끼리만 비교한다.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_naver_blog as blog  # noqa: E402
from common import (  # noqa: E402
    HISTORY_FIELDS,
    METRIC_HISTORY_CSV,
    fetch,
    load_dataset,
    make_session,
    parse_view_count,
    save_dataset,
)

BOARD_CHANNELS = ("보도자료", "포토뉴스")
RECENT_DAYS = 400  # 1년 넘은 글의 조회수는 거의 안 움직인다 — 매주 다시 읽을 이유가 적다


def board_targets(records: dict, today: date, recent_days: int, everything: bool) -> list[tuple[str, str]]:
    """조회수를 다시 읽을 (채널, id). 최근 글 + 아직 조회수가 비어 있는 글."""
    cut = (today - timedelta(days=recent_days)).isoformat()
    out = []
    for key, r in records.items():
        if r.get("채널") not in BOARD_CHANNELS or not r.get("링크"):
            continue
        if everything or not r.get("조회수") or (r.get("게시일") or "") >= cut:
            out.append(key)
    return out


def history_rows(records: dict, today: date) -> list[dict]:
    """오늘 갱신된 지표만 이력에 남긴다(같은 날 두 번 돌려도 append_history가 중복을 막는다)."""
    t = today.isoformat()
    return [
        {"기준일": t, "채널": r["채널"], "id": r["id"], "조회수": r.get("조회수", ""), "댓글수": r.get("댓글수", "")}
        for r in records.values()
        if r.get("지표기준일") == t and (r.get("조회수") or r.get("댓글수"))
    ]


def append_history(rows: list[dict], path: Path = METRIC_HISTORY_CSV) -> int:
    seen: set[tuple[str, str, str]] = set()
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            seen = {(r["기준일"], r["채널"], r["id"]) for r in csv.DictReader(f)}
    new = [r for r in rows if (r["기준일"], r["채널"], r["id"]) not in seen]
    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig" if write_header else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HISTORY_FIELDS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    return len(new)


def refresh_board(records: dict, today: date, recent_days: int, everything: bool) -> tuple[int, int]:
    s = make_session()
    ok = fail = 0
    for key in board_targets(records, today, recent_days, everything):
        r = records[key]
        try:
            views = parse_view_count(fetch(s, r["링크"], sleep=0.3).get_text(" ", strip=True))
        except Exception as e:  # 한 글이 안 열려도 나머지는 진행 — 실패 수를 마지막에 보고
            print(f"  [경고] {r['링크']} — {e}", file=sys.stderr)
            fail += 1
            continue
        if views is None:
            fail += 1
            continue
        r["조회수"], r["지표기준일"] = str(views), today.isoformat()
        ok += 1
    return ok, fail


def refresh_blog_comments(records: dict, today: date) -> int:
    listing = blog.crawl_listing(blog.make_session(), None)
    n = 0
    for it in listing:
        r = records.get((blog.CHANNEL, it["id"]))
        if r is None or it.get("commentCount", "") == "":
            continue
        r["댓글수"], r["지표기준일"] = it["commentCount"], today.isoformat()
        n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--all", action="store_true", help="홈페이지 게시물 전체 조회수")
    p.add_argument("--recent-days", type=int, default=RECENT_DAYS)
    a = p.parse_args()
    today = date.today()
    records = load_dataset()
    ok, fail = refresh_board(records, today, a.recent_days, a.all)
    print(f"[조회수] 홈페이지 {ok}건 갱신 · 실패 {fail}건")
    print(f"[댓글수] 블로그 {refresh_blog_comments(records, today)}건 갱신")
    save_dataset(records)
    print(f"[이력] {append_history(history_rows(records, today))}행 추가 → {METRIC_HISTORY_CSV.name}")
    total = ok + fail
    return 1 if total and fail / total > 0.2 else 0  # 20% 넘게 실패하면 마크업 변경 의심 — 스케줄러 로그에 경고


if __name__ == "__main__":
    sys.exit(main())
