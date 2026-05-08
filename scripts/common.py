"""KITECH 홍보 허브 — 공통 유틸 (HTTP 세션·HTML 파싱·날짜 추출)"""
from __future__ import annotations

import re
import sys
import time
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
