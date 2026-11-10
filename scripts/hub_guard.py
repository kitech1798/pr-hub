"""주간 갱신 안전장치 — 공개 앱에 깨진 데이터가 올라가지 않게 막는다.

1) import-perf : 보도자료 성과분석이 내보낸 output/hub/*.csv 를 검사한 뒤 data/ 로 복사
2) check       : 허브-데이터셋.csv 의 채널별 건수가 직전 커밋보다 크게 줄었으면 실패(수집 실패로 데이터가 지워진 경우)

    python scripts/hub_guard.py import-perf
    python scripts/hub_guard.py check

종료 코드 0=통과, 1=막음. weekly_update.ps1 은 1이면 커밋·푸시하지 않는다.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATASET = DATA / "허브-데이터셋.csv"
PERF_SRC = ROOT.parent / "보도자료 성과분석" / "output" / "hub"
PERF_FILES = ("보도성과.csv", "보도성과_매체.csv", "보도성과_meta.json")

RELEASE_COLS = ["id", "배포일", "제목", "기사 수", "매체 수", "등급별 매체 수", "매체명",
                "첫 기사일", "검토대기 기사", "집계 상태", "링크"]
MEDIA_COLS = ["매체", "등급", "보도한 보도자료 수", "기사 수"]
# 공개 저장소로 나가면 안 되는 열 — 성과분석 쪽 내보내기가 바뀌어도 여기서 한 번 더 막는다
FORBIDDEN_COLS = {"기자", "매체(기자)", "관련 연구자", "연구자", "reporter", "researchers"}
MAX_SHRINK = 0.05  # 채널 건수가 5% 넘게 줄면 막는다


def read_csv_text(text: str) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
    rows = list(reader)
    return list(reader.fieldnames or []), rows


def validate_perf(rel_text: str, media_text: str, meta: dict, prev_rel_rows: int) -> list[str]:
    """문제 목록(비어 있으면 통과)."""
    problems: list[str] = []
    rcols, rrows = read_csv_text(rel_text)
    mcols, _ = read_csv_text(media_text)
    if rcols != RELEASE_COLS:
        problems.append(f"보도성과.csv 열이 다릅니다: {rcols}")
    if mcols != MEDIA_COLS:
        problems.append(f"보도성과_매체.csv 열이 다릅니다: {mcols}")
    leaked = FORBIDDEN_COLS & (set(rcols) | set(mcols))
    if leaked:
        problems.append(f"공개 금지 열 포함: {sorted(leaked)}")
    if not meta.get("기준일"):
        problems.append("meta에 기준일이 없습니다")
    if prev_rel_rows and len(rrows) < prev_rel_rows * (1 - MAX_SHRINK):
        problems.append(f"보도자료 행이 {prev_rel_rows}→{len(rrows)}로 줄었습니다")
    for r in rrows:
        if not str(r.get("링크", "")).startswith("https://www.kitech.re.kr/"):
            problems.append(f"홈페이지 링크가 아닌 행(수기 추가분 유출?): id={r.get('id')}")
            break
    return problems


def channel_counts(text: str) -> Counter[str]:
    _, rows = read_csv_text(text)
    return Counter(r.get("채널", "") for r in rows)


def shrink_problems(prev: Counter[str], cur: Counter[str]) -> list[str]:
    out = []
    for ch, n in prev.items():
        if n and cur.get(ch, 0) < n * (1 - MAX_SHRINK):
            out.append(f"{ch}: {n}→{cur.get(ch, 0)}건")
    return out


def _git_head_text(path: Path) -> str:
    rel = path.relative_to(ROOT).as_posix()
    r = subprocess.run(["git", "-C", str(ROOT), "show", f"HEAD:{rel}"], capture_output=True)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""


def cmd_import_perf() -> int:
    missing = [f for f in PERF_FILES if not (PERF_SRC / f).exists()]
    if missing:
        print(f"✗ 성과분석 내보내기 파일 없음: {missing} ({PERF_SRC}) — 보도자료 성과분석에서 run.ps1 weekly 먼저")
        return 1
    rel_text = (PERF_SRC / PERF_FILES[0]).read_text(encoding="utf-8-sig")
    media_text = (PERF_SRC / PERF_FILES[1]).read_text(encoding="utf-8-sig")
    meta = json.loads((PERF_SRC / PERF_FILES[2]).read_text(encoding="utf-8"))
    prev = DATA / PERF_FILES[0]
    prev_rows = len(read_csv_text(prev.read_text(encoding="utf-8-sig"))[1]) if prev.exists() else 0
    problems = validate_perf(rel_text, media_text, meta, prev_rows)
    if problems:
        print("✗ 보도성과 가져오기 막음:\n  " + "\n  ".join(problems))
        return 1
    for f in PERF_FILES:
        shutil.copy2(PERF_SRC / f, DATA / f)
    print(f"✓ 보도성과 가져옴 — 기준일 {meta['기준일']} · 보도자료 {meta.get('보도자료 수')}건 · 기사 {meta.get('기사 수')}건")
    return 0


def cmd_check() -> int:
    prev_text = _git_head_text(DATASET)
    cur = channel_counts(DATASET.read_text(encoding="utf-8-sig"))
    if not prev_text:
        print(f"직전 커밋 없음 — 현재 {dict(cur)}")
        return 0
    prev = channel_counts(prev_text)
    problems = shrink_problems(prev, cur)
    diff = {ch: cur.get(ch, 0) - prev.get(ch, 0) for ch in set(prev) | set(cur)}
    print(f"채널별 증감: {diff} · 현재 {dict(cur)}")
    if problems:
        print("✗ 데이터가 크게 줄어 막음(수집 실패 의심): " + ", ".join(problems))
        return 1
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["import-perf", "check"])
    a = p.parse_args()
    return cmd_import_perf() if a.cmd == "import-perf" else cmd_check()


if __name__ == "__main__":
    sys.exit(main())
