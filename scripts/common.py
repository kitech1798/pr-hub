"""KITECH 홍보 허브 — 공통 유틸 (데이터셋 스키마·HTTP 세션·HTML 파싱·날짜 추출)

데이터셋 열 정의는 여기 한 곳에만 둔다. 예전엔 수집기 3개가 각자 CSV_FIELDS를 갖고 있어서,
한 수집기에만 열을 추가하면 다른 수집기가 저장할 때 그 열을 지워 버리는 구조였다.
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Windows PowerShell 콘솔 cp949에서 한자·특수문자가 UnicodeEncodeError를 내는 문제 차단
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE_URL = "https://www.kitech.re.kr"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATASET_CSV = DATA_DIR / "허브-데이터셋.csv"
METRIC_HISTORY_CSV = DATA_DIR / "지표_이력.csv"

CSV_FIELDS = [
    "채널", "게시일", "제목", "주요내용",
    "링크", "id", "썸네일URL", "분야태그", "비고",
    # 반응 지표 — collect_metrics.py가 채운다. 블로그는 조회수가 비공개라 댓글수만.
    "조회수", "댓글수", "지표기준일",
]
HISTORY_FIELDS = ["기준일", "채널", "id", "조회수", "댓글수"]


def load_dataset(path: Path = DATASET_CSV) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return {(r.get("채널", ""), r.get("id", "")): r for r in csv.DictReader(f)}


def save_dataset(records: dict[tuple[str, str], dict], path: Path = DATASET_CSV) -> None:
    rows = sorted(
        records.values(),
        key=lambda r: (r.get("게시일") or "", r.get("채널") or "", r.get("id") or ""),
        reverse=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in CSV_FIELDS})


_VIEW_RE = re.compile(r"조회수\s*([\d,]+)")


def parse_view_count(text: str) -> int | None:
    """홈페이지 게시판 상세의 '조회수 6,791' → 6791. 없으면 None."""
    m = _VIEW_RE.search(text)
    return int(m.group(1).replace(",", "")) if m else None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch(session: requests.Session, url: str, sleep: float = 0.5) -> BeautifulSoup:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    if sleep:
        time.sleep(sleep)
    return soup


def parse_total_count(soup: BeautifulSoup) -> int | None:
    m = re.search(r"총\s*([\d,]+)\s*건", soup.get_text())
    return int(m.group(1).replace(",", "")) if m else None


_DATE_RE = re.compile(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def find_date_near(node) -> str | None:
    cur = node
    for _ in range(5):
        if cur is None:
            break
        text = cur.get_text(" ", strip=True) if hasattr(cur, "get_text") else ""
        m = _DATE_RE.search(text)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        cur = cur.parent
    return None


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)
