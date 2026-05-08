"""KITECH 보도자료·포토뉴스 수집 → data/허브-데이터셋.csv

사용 예:
    python scripts/collect_kitech.py --board press --inspect      # 첫 페이지 항목 3개 구조 점검
    python scripts/collect_kitech.py --board press --pages 1      # 1페이지만 시험 수집
    python scripts/collect_kitech.py --board press                # 전체 수집
    python scripts/collect_kitech.py --board photo                # 포토뉴스 전체 수집
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from tqdm import tqdm

from common import (
    BASE_URL,
    absolute_url,
    fetch,
    find_date_near,
    make_session,
    parse_total_count,
)

BOARDS = {
    "press": {
        "page_id": 61,
        "channel": "보도자료",
        # 50=2026 보도자료, 49=과거(~2016), 51=아카이브 — id 중복은 dedup으로 처리
        "categories": [50, 49, 51],
    },
    "photo": {
        "page_id": 60,
        "channel": "포토뉴스",
        "categories": [None],  # 포토뉴스는 단일 목록
    },
}

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATASET_CSV = DATA_DIR / "허브-데이터셋.csv"

CSV_FIELDS = [
    "채널", "게시일", "제목", "주요내용",
    "링크", "id", "썸네일URL", "분야태그", "비고",
]

ITEM_LINK_RE = re.compile(r"[?&]id=(\d+).*menuMode=READ")
ITEMS_PER_PAGE_GUESS = 9


def list_url(page_id: int, page: int, category_id: int | None = None) -> str:
    params = []
    if category_id is not None:
        params.append(f"categoryId={category_id}")
    if page > 1:
        params.append(f"page={page}")
    if not params:
        return f"{BASE_URL}/pages/{page_id}"
    return f"{BASE_URL}/pages/{page_id}?{'&'.join(params)}"


def parse_listing(soup, page_id: int, channel: str) -> list[dict]:
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = ITEM_LINK_RE.search(href)
        if not m:
            continue
        if f"/pages/{page_id}" not in href and not href.startswith("?"):
            continue
        item_id = m.group(1)
        if item_id in seen:
            continue
        seen.add(item_id)

        title = a.get_text(" ", strip=True)
        title = re.sub(r"\s*등록일\s*20\d{2}[-./]\d{1,2}[-./]\d{1,2}\s*$", "", title).strip()
        if not title:
            img = a.find("img")
            if img and img.get("alt"):
                title = img["alt"].strip()

        img = a.find("img")
        if not img and a.parent:
            img = a.parent.find("img")
        thumbnail = absolute_url(img["src"]) if img and img.get("src") else ""

        date = find_date_near(a) or ""

        items.append({
            "id": item_id,
            "channel": channel,
            "title": title,
            "url": absolute_url(href),
            "thumbnail": thumbnail,
            "date": date,
        })
    return items


def parse_detail(soup) -> dict:
    # 등록일: <div class="info date"> 안의 텍스트
    date = ""
    info = soup.select_one("div.info.date")
    if info:
        m = re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", info.get_text(" ", strip=True))
        if m:
            date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # 본문: <div class="ck-content"> (KITECH CKEditor 컨텐츠 컨테이너)
    body_el = soup.select_one("div.ck-content")
    body = body_el.get_text(" ", strip=True) if body_el else ""

    summary = re.sub(r"\s+", " ", body)[:200].strip() if body else ""
    return {"date": date, "summary": summary}


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


def inspect(board: str) -> None:
    cfg = BOARDS[board]
    session = make_session()
    cat = cfg["categories"][0]
    soup = fetch(session, list_url(cfg["page_id"], 1, cat))
    label = f"category={cat}" if cat is not None else "no-category"
    print(f"[{cfg['channel']}/{label}] 총 {parse_total_count(soup)}건 (게시판 표시)")
    items = parse_listing(soup, cfg["page_id"], cfg["channel"])
    print(f"첫 페이지에서 {len(items)}개 항목 추출")
    for i, it in enumerate(items[:3], 1):
        print(f"\n--- 항목 {i} ---")
        for k, v in it.items():
            print(f"  {k}: {v}")


def _crawl_category(session, page_id, channel, category_id, max_pages, seen_ids, listing):
    label = f"category={category_id}" if category_id is not None else "no-category"
    first = fetch(session, list_url(page_id, 1, category_id))
    total = parse_total_count(first)
    print(f"[{channel}/{label}] 총 {total}건")

    cat_max = max_pages
    if cat_max is None:
        cat_max = ((total or 0) + ITEMS_PER_PAGE_GUESS - 1) // ITEMS_PER_PAGE_GUESS + 2
        if cat_max <= 0:
            cat_max = 200

    for page in tqdm(range(1, cat_max + 1), desc=f"{channel}/{label} 목록"):
        soup = first if page == 1 else fetch(session, list_url(page_id, page, category_id))
        page_items = parse_listing(soup, page_id, channel)
        new_count = 0
        for it in page_items:
            if it["id"] in seen_ids:
                continue
            seen_ids.add(it["id"])
            listing.append(it)
            new_count += 1
        if new_count == 0:
            break


def collect(board: str, max_pages: int | None, categories_override: list[int] | None = None) -> None:
    cfg = BOARDS[board]
    page_id, channel = cfg["page_id"], cfg["channel"]
    categories = categories_override if categories_override is not None else cfg["categories"]
    session = make_session()

    listing: list[dict] = []
    seen_ids: set[str] = set()
    for cat in categories:
        _crawl_category(session, page_id, channel, cat, max_pages, seen_ids, listing)

    print(f"[{channel}] 목록에서 총 {len(listing)}개 항목 발견 (dedup 후)")

    records = load_existing()

    for item in tqdm(listing, desc=f"{channel} 상세"):
        try:
            detail = parse_detail(fetch(session, item["url"]))
            if not item["date"] and detail["date"]:
                item["date"] = detail["date"]
            item["summary"] = detail["summary"]
        except Exception as e:
            item["summary"] = ""
            print(f"  [경고] {item['url']} — {e}", file=sys.stderr)

    for item in listing:
        key = (channel, item["id"])
        prev = records.get(key, {})
        records[key] = {
            "채널": channel,
            "게시일": item.get("date", ""),
            "제목": item.get("title", ""),
            "주요내용": item.get("summary", ""),
            "링크": item["url"],
            "id": item["id"],
            "썸네일URL": item.get("thumbnail", ""),
            "분야태그": prev.get("분야태그", ""),
            "비고": prev.get("비고", ""),
        }

    save_dataset(records)
    print(f"\n[{channel}] {DATASET_CSV} 갱신 — 총 {len(records)}행")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--board", choices=list(BOARDS), required=True)
    p.add_argument("--pages", type=int, default=None, help="카테고리당 최대 페이지 수 (생략 시 전체)")
    p.add_argument("--categories", type=str, default=None,
                   help="카테고리 ID 콤마 구분(예: 50,49). 생략 시 BOARDS 기본값")
    p.add_argument("--inspect", action="store_true", help="첫 페이지 항목 3개 구조만 출력")
    args = p.parse_args()
    cats = None
    if args.categories:
        cats = [int(x) if x.lower() != "none" else None for x in args.categories.split(",")]
    if args.inspect:
        inspect(args.board)
    else:
        collect(args.board, max_pages=args.pages, categories_override=cats)


if __name__ == "__main__":
    main()
