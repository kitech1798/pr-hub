"""KITECH 네이버 블로그(blog.naver.com/kitechblog) 수집 → data/허브-데이터셋.csv

사용 예:
    python scripts/collect_naver_blog.py --inspect       # 첫 페이지 항목 3개 구조 점검
    python scripts/collect_naver_blog.py --pages 1       # 1페이지(30건)만 시험 수집
    python scripts/collect_naver_blog.py                 # 전체 수집(약 1,225건)

목록: PostTitleListAsync.naver (JSON, 30개/페이지)
본문: m.blog.naver.com/PostView.naver (div.se-main-container)
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote_plus

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

# Windows PowerShell cp949 회피 (common.py와 동일 처리)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BLOG_ID = "kitechblog"
CHANNEL = "블로그"

LIST_URL = (
    "https://blog.naver.com/PostTitleListAsync.naver"
    "?blogId={blog_id}&viewdate=&currentPage={page}"
    "&categoryNo=0&parentCategoryNo=0&countPerPage={per}"
)
VIEW_URL = "https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
PUBLIC_URL = "https://blog.naver.com/{blog_id}/{log_no}"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATASET_CSV = DATA_DIR / "허브-데이터셋.csv"
DATA_DIR.mkdir(parents=True, exist_ok=True)

CSV_FIELDS = [
    "채널", "게시일", "제목", "주요내용",
    "링크", "id", "썸네일URL", "분야태그", "비고",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}

PER_PAGE = 30

# JSON 본문이 가끔 invalid escape를 포함해 json.loads가 실패한다.
# 안전하게 항목 단위로 정규식 추출.
_TOTAL_RE = re.compile(r'"totalCount"\s*:\s*"?(\d+)')
_ITEM_RE = re.compile(r'\{[^{}]*"logNo"\s*:\s*"(\d+)"[^{}]*\}')
_FIELD_RE = re.compile(r'"([a-zA-Z]+)"\s*:\s*"([^"]*)"')


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def fetch_text(session: requests.Session, url: str, sleep: float = 0.4) -> str:
    r = session.get(url, timeout=30)
    r.raise_for_status()
    if sleep:
        time.sleep(sleep)
    return r.text


def parse_addDate(s: str) -> str:
    # "2026. 3. 20." 또는 "2026.03.20" 또는 "10:23" 등 → "YYYY-MM-DD" (실패 시 "")
    m = re.match(r"\s*(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})\.?", s)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 당일 글은 시간만 표시되는 경우가 있음 — 오늘 날짜 사용
    if re.match(r"\s*\d{1,2}:\d{2}", s):
        return time.strftime("%Y-%m-%d")
    return ""


def parse_listing(text: str) -> list[dict]:
    items = []
    for m in _ITEM_RE.finditer(text):
        block = m.group(0)
        fields = dict(_FIELD_RE.findall(block))
        log_no = fields.get("logNo", "")
        if not log_no:
            continue
        title_raw = fields.get("title", "")
        title = unquote_plus(title_raw)
        items.append({
            "id": log_no,
            "title": title,
            "addDate": fields.get("addDate", ""),
            "categoryNo": fields.get("categoryNo", ""),
            "parentCategoryNo": fields.get("parentCategoryNo", ""),
        })
    return items


def parse_total(text: str) -> int | None:
    m = _TOTAL_RE.search(text)
    return int(m.group(1)) if m else None


def parse_post_view(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    body_el = soup.select_one("div.se-main-container") or soup.select_one("div#postViewArea")
    body = body_el.get_text(" ", strip=True) if body_el else ""
    summary = re.sub(r"\s+", " ", body)[:200].strip()

    date = ""
    date_el = soup.select_one("p.blog_date") or soup.select_one("span.se_publishDate")
    if date_el:
        txt = date_el.get_text(" ", strip=True)
        m = re.search(r"(20\d{2})\.\s*(\d{1,2})\.\s*(\d{1,2})", txt)
        if m:
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    thumb = ""
    img = None
    if body_el:
        img = body_el.find("img")
    if img and img.get("data-lazy-src"):
        thumb = img["data-lazy-src"]
    elif img and img.get("src"):
        thumb = img["src"]

    return {"date": date, "summary": summary, "thumbnail": thumb}


def load_existing() -> dict[tuple[str, str], dict]:
    if not DATASET_CSV.exists():
        return {}
    out = {}
    with DATASET_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            out[(row.get("채널", ""), row.get("id", ""))] = row
    return out


def save_dataset(records: dict[tuple[str, str], dict]) -> None:
    rows = list(records.values())
    rows.sort(
        key=lambda r: (r.get("게시일") or "", r.get("채널") or "", r.get("id") or ""),
        reverse=True,
    )
    with DATASET_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})


def crawl_listing(session, max_pages: int | None) -> list[dict]:
    """전체 목록을 끝까지 수집(페이지에서 0건 나오면 중단)."""
    listing: list[dict] = []
    seen_ids: set[str] = set()
    total = None
    page = 1
    pbar = None
    while True:
        if max_pages is not None and page > max_pages:
            break
        url = LIST_URL.format(blog_id=BLOG_ID, page=page, per=PER_PAGE)
        text = fetch_text(session, url)
        if total is None:
            total = parse_total(text)
            print(f"[블로그] totalCount={total}")
            if total:
                pbar = tqdm(total=total, desc="블로그 목록")
        items = parse_listing(text)
        new_count = 0
        for it in items:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            listing.append(it)
            new_count += 1
            if pbar:
                pbar.update(1)
        if not items or new_count == 0:
            break
        page += 1
    if pbar:
        pbar.close()
    return listing


def inspect() -> None:
    session = make_session()
    text = fetch_text(session, LIST_URL.format(blog_id=BLOG_ID, page=1, per=PER_PAGE))
    total = parse_total(text)
    items = parse_listing(text)
    print(f"[블로그] totalCount={total}, 1페이지={len(items)}건")
    for i, it in enumerate(items[:3], 1):
        print(f"\n--- 항목 {i} ---")
        for k, v in it.items():
            print(f"  {k}: {v}")
        # 본문도 한 건은 시험 추출
        if i == 1:
            html = fetch_text(session, VIEW_URL.format(blog_id=BLOG_ID, log_no=it["id"]))
            d = parse_post_view(html)
            print(f"  [본문] date={d['date']}")
            print(f"  [본문] thumbnail={d['thumbnail'][:120]}")
            print(f"  [본문] summary={d['summary'][:150]}")


def collect(max_pages: int | None) -> None:
    session = make_session()
    listing = crawl_listing(session, max_pages)
    print(f"[블로그] 목록에서 {len(listing)}건 수집(dedup 후)")

    records = load_existing()

    for item in tqdm(listing, desc="블로그 본문"):
        view_url = VIEW_URL.format(blog_id=BLOG_ID, log_no=item["id"])
        try:
            html = fetch_text(session, view_url)
            d = parse_post_view(html)
        except Exception as e:
            d = {"date": "", "summary": "", "thumbnail": ""}
            print(f"  [경고] {view_url} — {e}", file=sys.stderr)

        date = d["date"] or parse_addDate(item["addDate"])
        public_url = PUBLIC_URL.format(blog_id=BLOG_ID, log_no=item["id"])
        key = (CHANNEL, item["id"])
        prev = records.get(key, {})
        records[key] = {
            "채널": CHANNEL,
            "게시일": date,
            "제목": item["title"],
            "주요내용": d["summary"],
            "링크": public_url,
            "id": item["id"],
            "썸네일URL": d["thumbnail"],
            "분야태그": prev.get("분야태그", ""),
            "비고": prev.get("비고", f"cat={item['categoryNo']}/{item['parentCategoryNo']}"),
        }

    save_dataset(records)
    print(f"\n[블로그] {DATASET_CSV} 갱신 — 총 {len(records)}행")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pages", type=int, default=None,
                   help="최대 목록 페이지 수 (생략 시 전체). 1페이지=30건")
    p.add_argument("--inspect", action="store_true", help="첫 페이지 + 1건 본문 점검")
    args = p.parse_args()
    if args.inspect:
        inspect()
    else:
        collect(args.pages)


if __name__ == "__main__":
    main()
