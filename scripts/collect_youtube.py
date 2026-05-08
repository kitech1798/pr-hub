"""KITECH 유튜브(@KITECHYOUTUBE) 수집 → data/허브-데이터셋.csv

두 단계로 분리되어 있어 블로그 수집과 병렬 실행이 안전하다.

사용 예:
    python scripts/collect_youtube.py --inspect    # 채널 영상 수만 확인
    python scripts/collect_youtube.py --fetch      # yt-dlp로 메타 → raw/유튜브-메타/videos.jsonl
    python scripts/collect_youtube.py --merge      # videos.jsonl → 허브-데이터셋.csv 병합

yt-dlp가 영상별 -j 출력을 ndjson(한 줄에 한 영상 JSON) 형태로 모은다.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

# Windows PowerShell cp949 회피
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CHANNEL = "유튜브"
CHANNEL_URL = "https://www.youtube.com/@KITECHYOUTUBE/videos"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = PROJECT_ROOT / "raw" / "유튜브-메타"
DATASET_CSV = DATA_DIR / "허브-데이터셋.csv"
VIDEOS_JSONL = RAW_DIR / "videos.jsonl"
DATA_DIR.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)

CSV_FIELDS = [
    "채널", "게시일", "제목", "주요내용",
    "링크", "id", "썸네일URL", "분야태그", "비고",
]


def inspect() -> None:
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--flat-playlist", "--skip-download",
        "--print", "%(id)s",
        CHANNEL_URL,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    ids = [x for x in out.stdout.splitlines() if x.strip()]
    print(f"[유튜브] 채널 영상 수 = {len(ids)}건 (URL: {CHANNEL_URL})")


def fetch() -> None:
    """yt-dlp 채널 페이지를 한 번만 긁어 영상 메타를 ndjson으로 떨어뜨림.

    --flat-playlist + youtubetab:approximate_date 조합을 쓰면 영상별 watch 페이지를
    돌지 않고도 id·title·timestamp(추정)·thumbnails까지 받아온다 (수십 초 / 채널).
    설명·조회수는 비어 있으나, 분야태그 일괄 생성 단계에서 필요한 영상만 보강하면 된다.
    """
    cmd = [
        sys.executable, "-m", "yt_dlp",
        "-j", "--flat-playlist", "--skip-download", "--ignore-errors",
        "--extractor-args", "youtubetab:approximate_date",
        CHANNEL_URL,
    ]
    print(f"[유튜브] yt-dlp 실행 → {VIDEOS_JSONL}")
    with VIDEOS_JSONL.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        count = 0
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            if not line.startswith("{"):
                continue
            f.write(line + "\n")
            count += 1
            if count % 20 == 0:
                print(f"  ... {count}건 누적", flush=True)
        proc.wait()
        if proc.stderr:
            err = proc.stderr.read()
            if err:
                # stderr는 진행 메시지가 많아 마지막 일부만 표시
                tail = "\n".join(err.splitlines()[-10:])
                print(f"[유튜브] stderr tail:\n{tail}", file=sys.stderr)
    print(f"[유튜브] 총 {count}건 메타 저장 → {VIDEOS_JSONL}")


def parse_upload_date(s: str | None) -> str:
    if not s or len(s) != 8 or not s.isdigit():
        return ""
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def load_existing() -> dict[tuple[str, str], dict]:
    if not DATASET_CSV.exists():
        return {}
    out = {}
    with DATASET_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
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


def merge() -> None:
    if not VIDEOS_JSONL.exists():
        print(f"[유튜브] {VIDEOS_JSONL} 없음 — --fetch 먼저 실행", file=sys.stderr)
        sys.exit(1)

    records = load_existing()
    added = 0
    updated = 0
    with VIDEOS_JSONL.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            vid = d.get("id", "")
            if not vid:
                continue
            description = d.get("description") or ""
            summary = re.sub(r"\s+", " ", description)[:200].strip()
            title = d.get("title") or ""
            url = d.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}"
            view_count = d.get("view_count")
            views_note = f"조회수={view_count}" if view_count is not None else ""

            key = (CHANNEL, vid)
            prev = records.get(key, {})
            thumb = d.get("thumbnail") or ""
            if not thumb:
                # flat-playlist 모드에서는 thumbnails 배열에서 직접 골라야 한다
                thumbs = d.get("thumbnails") or []
                if thumbs:
                    thumb = thumbs[0].get("url", "")
            new_row = {
                "채널": CHANNEL,
                "게시일": parse_upload_date(d.get("upload_date")),
                "제목": title,
                "주요내용": summary,
                "링크": url,
                "id": vid,
                "썸네일URL": thumb,
                "분야태그": prev.get("분야태그", ""),
                "비고": views_note,
            }
            if key in records:
                if records[key] != new_row:
                    updated += 1
            else:
                added += 1
            records[key] = new_row

    save_dataset(records)
    print(f"[유튜브] 신규 {added}건 / 갱신 {updated}건 → 총 {len(records)}행 ({DATASET_CSV})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inspect", action="store_true", help="채널 영상 수만 확인")
    p.add_argument("--fetch", action="store_true", help="yt-dlp로 메타 추출 → videos.jsonl")
    p.add_argument("--merge", action="store_true", help="videos.jsonl → 허브-데이터셋.csv 병합")
    args = p.parse_args()
    if args.inspect:
        inspect()
    elif args.fetch:
        fetch()
    elif args.merge:
        merge()
    else:
        p.error("--inspect / --fetch / --merge 중 하나 지정")


if __name__ == "__main__":
    main()
