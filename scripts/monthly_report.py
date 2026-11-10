"""월간 홍보 보고서(HTML) — 2026년 10월분부터. reports/monthly_report_YYYY-MM.html + reports/index.json

    python scripts/monthly_report.py                 # 2026-10 ~ 이번 달 전부 다시 생성
    python scripts/monthly_report.py --month 2026-10 # 한 달만

원칙
- Good·Bad·시사점·개선점은 AI 작문이 아니라 숫자에서 규칙으로 뽑는다(같은 데이터 → 같은 문장, 문장마다 근거 숫자).
- 보도성과의 분야 비교는 '함께 나타난 경향'이지 원인이 아니다 — 문장도 그렇게 쓴다.
- 조회수는 기준일까지의 누적이다. 오래된 글일수록 크므로 같은 달 글끼리만 줄 세운다.
- 이번 달처럼 끝나지 않은 달은 '진행 중'으로 표시하고, 배포 60일이 안 된 보도자료는 '집계 중'으로 표시한다.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA_DIR, DATASET_CSV, METRIC_HISTORY_CSV, PROJECT_ROOT  # noqa: E402

REPORT_DIR = PROJECT_ROOT / "reports"
FIRST_MONTH = "2026-10"  # 사용자 지시: 2026년 10월 자료부터
CHANNELS = ["보도자료", "포토뉴스", "유튜브", "블로그"]
GOOD_MEDIA_RATIO = 1.3   # 전체 중앙값의 1.3배 이상이면 Good
CHANNEL_UP, CHANNEL_DOWN = 1.2, 0.5  # 12개월 월평균 대비 +20% / 절반 이하


# ---------------------------------------------------------------- 데이터 적재
def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict, pd.DataFrame]:
    hub = pd.read_csv(DATASET_CSV, encoding="utf-8-sig", dtype=str).fillna("")
    hub["게시일"] = pd.to_datetime(hub["게시일"], errors="coerce")
    hub["조회수_n"] = pd.to_numeric(hub.get("조회수", ""), errors="coerce")
    hub["댓글수_n"] = pd.to_numeric(hub.get("댓글수", ""), errors="coerce")
    perf = pd.read_csv(DATA_DIR / "보도성과.csv", encoding="utf-8-sig", dtype={"id": str})
    perf["배포일"] = pd.to_datetime(perf["배포일"], errors="coerce")
    fields = pd.read_csv(DATA_DIR / "보도성과_분야.csv", encoding="utf-8-sig")
    meta = json.loads((DATA_DIR / "보도성과_meta.json").read_text(encoding="utf-8"))
    hist = (pd.read_csv(METRIC_HISTORY_CSV, encoding="utf-8-sig", dtype={"id": str})
            if METRIC_HISTORY_CSV.exists() else pd.DataFrame(columns=["기준일", "채널", "id", "조회수", "댓글수"]))
    return hub, perf, fields, meta, hist


# ---------------------------------------------------------------- 계산
@dataclass
class Report:
    month: str
    in_progress: bool
    basis: str
    kpis: list[tuple[str, str, str]] = field(default_factory=list)      # (라벨, 값, 보조)
    channels: list[dict] = field(default_factory=list)
    releases: list[dict] = field(default_factory=list)
    top_views: dict[str, list[dict]] = field(default_factory=dict)
    fields_mix: list[tuple[str, int]] = field(default_factory=list)
    good: list[str] = field(default_factory=list)
    bad: list[str] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def month_range(ym: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(f"{ym}-01")
    return start, start + pd.offsets.MonthBegin(1)


def months_from(first: str, today: date) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(first, today.strftime("%Y-%m"), freq="M")]


def channel_table(hub: pd.DataFrame, ym: str) -> list[dict]:
    s, e = month_range(ym)
    prev_s, _ = month_range((s - pd.offsets.MonthBegin(1)).strftime("%Y-%m"))
    base_s = s - pd.DateOffset(months=12)
    out = []
    for ch in CHANNELS:
        d = hub[hub["채널"] == ch]["게시일"]
        n = int(((d >= s) & (d < e)).sum())
        prev = int(((d >= prev_s) & (d < s)).sum())
        avg12 = float(((d >= base_s) & (d < s)).sum()) / 12
        out.append({"채널": ch, "이달": n, "전월": prev, "12개월 월평균": round(avg12, 1)})
    return out


def short(title: str, n: int = 36) -> str:
    """단어 중간에서 자르지 않는다."""
    if len(title) <= n:
        return title
    cut = title[:n].rsplit(" ", 1)[0]
    return (cut if len(cut) >= n // 2 else title[:n]) + "…"


def fmt_ratio(r: float) -> str:
    return f"{r:.1f}배"


def _field_row(fields: pd.DataFrame, axis: str, item: str) -> pd.Series | None:
    m = fields[(fields["축"] == axis) & (fields["항목"] == item)]
    return m.iloc[0] if not m.empty else None


def build(ym: str, hub: pd.DataFrame, perf: pd.DataFrame, fields: pd.DataFrame, meta: dict,
          hist: pd.DataFrame, today: date) -> Report:
    s, e = month_range(ym)
    in_progress = today < e.date()
    rep = Report(month=ym, in_progress=in_progress, basis=meta.get("기준일", today.isoformat()))

    # --- 채널 게시량
    rep.channels = channel_table(hub, ym)
    total_posts = sum(c["이달"] for c in rep.channels)

    # --- 보도성과
    settled = perf[perf["집계 상태"] == "확정"]
    med_all = float(settled["매체 수"].median()) if not settled.empty else 0.0
    p25 = float(settled["매체 수"].quantile(0.25)) if not settled.empty else 0.0
    mon = perf[(perf["배포일"] >= s) & (perf["배포일"] < e)].sort_values("배포일")
    # 열 이름에 공백·&가 있어 itertuples 속성명이 _4 같은 위치 번호가 된다 — 열 순서가 바뀌면 조용히 틀리므로 이름으로 읽는다
    for _, r in mon.iterrows():
        rep.releases.append({
            "배포일": r["배포일"].strftime("%m.%d"), "제목": r["제목"], "매체 수": int(r["매체 수"]),
            "기사 수": int(r["기사 수"]), "집계 상태": r["집계 상태"], "보도유형": r.get("보도유형", ""),
            "연구분야": r.get("연구분야", ""), "R&R": r.get("R&R 연계", ""), "가시성": r.get("가시성", ""),
            "링크": r["링크"], "검토대기": int(r["검토대기 기사"]),
        })
    n_media_total = int(mon["매체 수"].sum()) if not mon.empty else 0
    n_articles = int(mon["기사 수"].sum()) if not mon.empty else 0
    med_mon = float(mon["매체 수"].median()) if not mon.empty else float("nan")

    # --- 조회수(그달 게시물, 기준일 누적)
    for ch in ("보도자료", "포토뉴스", "유튜브"):
        d = hub[(hub["채널"] == ch) & (hub["게시일"] >= s) & (hub["게시일"] < e) & hub["조회수_n"].notna()]
        rep.top_views[ch] = [
            {"제목": x.제목, "조회수": int(x.조회수_n), "게시일": x.게시일.strftime("%m.%d"), "링크": x.링크}
            for x in d.sort_values("조회수_n", ascending=False).head(3).itertuples(index=False)
        ]
    month_posts = hub[(hub["게시일"] >= s) & (hub["게시일"] < e)]
    # 채널을 합치면 영상 한 편(광고 집행 영상 등)이 전체를 덮는다 — 홈페이지와 유튜브를 나눠 보인다
    home_views = int(month_posts[month_posts["채널"].isin(["보도자료", "포토뉴스"])]["조회수_n"].sum(skipna=True))
    yt_views = int(month_posts[month_posts["채널"] == "유튜브"]["조회수_n"].sum(skipna=True))

    rep.kpis = [
        ("콘텐츠 발행", f"{total_posts}건", "보도자료·포토뉴스·유튜브·블로그"),
        ("보도자료", f"{len(mon)}건", f"기사 {n_articles}건"),
        ("보도 매체(연인원)", f"{n_media_total}곳", f"건당 중앙값 {med_mon:.0f}곳 · 전체 {med_all:.0f}곳" if len(mon) else "—"),
        ("이달 게시물 조회", f"{home_views:,}회", f"홈페이지 · 유튜브 {yt_views:,}회 별도 ({rep.basis} 누적)"),
    ]
    if not mon.empty:
        mix = mon["연구분야"].where(~mon["연구분야"].isin(["분류 대기"]), "분류 대기").value_counts()
        rep.fields_mix = [(str(k), int(v)) for k, v in mix.items()]

    # --- Good
    if not mon.empty:
        best = mon.loc[mon["매체 수"].idxmax()]
        if med_all and best["매체 수"] >= med_all * GOOD_MEDIA_RATIO:
            rep.good.append(f"「{best['제목']}」 매체 {int(best['매체 수'])}곳 — 전체 보도자료 중앙값({med_all:.0f}곳)의 "
                            f"{fmt_ratio(best['매체 수'] / med_all)}")
    for c in rep.channels:
        if c["12개월 월평균"] >= 1 and c["이달"] >= c["12개월 월평균"] * CHANNEL_UP:
            rep.good.append(f"{c['채널']} {c['이달']}건 발행 — 최근 12개월 월평균({c['12개월 월평균']}건)보다 많음")
    yt = rep.top_views.get("유튜브") or []
    if yt:
        rep.good.append(f"유튜브 조회 1위 「{yt[0]['제목']}」 {yt[0]['조회수']:,}회 ({rep.basis} 기준)")
    direct = mon[mon["R&R 연계"] == "직접 연계"] if "R&R 연계" in mon else mon.iloc[0:0]
    if len(direct):
        rep.good.append(f"기관 R&R(미래비전 2035 로드맵)에 직접 연계된 보도 {len(direct)}건 / 이달 {len(mon)}건")

    # --- Bad
    for _, r in mon.iterrows():
        days = (pd.Timestamp(today) - r["배포일"]).days
        if days >= 14 and r["매체 수"] <= p25:
            rep.bad.append(f"「{r['제목']}」 매체 {int(r['매체 수'])}곳 — 전체 하위 25% 기준({p25:.0f}곳) 이하")
    for c in rep.channels:
        if c["12개월 월평균"] >= 1 and c["이달"] <= c["12개월 월평균"] * CHANNEL_DOWN and not in_progress:
            rep.bad.append(f"{c['채널']} {c['이달']}건 발행 — 최근 12개월 월평균 {c['12개월 월평균']}건의 절반 이하")
    pending = int(mon["검토대기 기사"].sum()) if not mon.empty else 0
    if pending:
        rep.bad.append(f"사람 확인을 기다리는 기사 {pending}건 — 확인 전이라 위 매체·기사 수는 하한값")

    # --- 시사점 (전체 기간 경향 + 이달 위치)
    hi, lo = _field_row(fields, "가시성", "높음"), _field_row(fields, "가시성", "낮음")
    if hi is not None and lo is not None:
        n_hi = int((mon.get("가시성", pd.Series(dtype=str)) == "높음").sum())
        rep.insights.append(
            f"전체 기간에 '사진 한 장으로 이해되는'(가시성 높음) 보도자료는 평균 {hi['매체 수 평균']}곳, 낮은 보도자료는 "
            f"{lo['매체 수 평균']}곳에 실렸다({fmt_ratio(hi['매체 수 평균'] / lo['매체 수 평균'])}). 이달 보도자료 중 가시성 높음은 {n_hi}건.")
    for _, r in mon.iterrows():
        fr = _field_row(fields, "연구분야", r.get("연구분야", ""))
        if fr is not None and fr["보도자료 수"] >= 5 and fr["항목"] != "해당 없음":  # 비기술 보도는 아래 문장이 따로 다룬다
            rep.insights.append(f"「{short(r['제목'], 24)}」의 분야({fr['항목']})는 전체 기간 평균 대비 {fmt_ratio(fr['전체 평균 대비'])} "
                                f"실린 분야(표본 {int(fr['보도자료 수'])}건)")
    nt = _field_row(fields, "R&R 연계", "기술 보도 아님")
    if nt is not None and (mon.get("R&R 연계", pd.Series(dtype=str)) == "기술 보도 아님").any():
        rep.insights.append(f"인사·행사 등 기술 내용이 없는 보도는 전체 기간 평균 대비 {fmt_ratio(nt['전체 평균 대비'])} 실렸다 — "
                            "이달에도 해당 보도가 있었다.")

    # --- 개선점 (Bad → 행동)
    if any("하위 25%" in b for b in rep.bad) and hi is not None and lo is not None:
        rep.actions.append(f"매체가 적었던 보도는 첫 사진·제목에 '눈에 보이는 장면'을 앞세워 다시 쓸 후보로 — 전체 기간 가시성 높음이 낮음보다 "
                           f"{fmt_ratio(hi['매체 수 평균'] / lo['매체 수 평균'])} 많이 실렸다(경향이며 인과는 미검증).")
    # 진행 중인 달엔 '발행 부족' 판정을 하지 않는다 — Bad와 같은 조건을 써야 개선점만 홀로 뜨지 않는다
    low_ch = [] if in_progress else [
        c for c in rep.channels if c["12개월 월평균"] >= 1 and c["이달"] <= c["12개월 월평균"] * CHANNEL_DOWN]
    for c in low_ch:
        rep.actions.append(f"{c['채널']} 발행 주기 회복: 최근 12개월 월평균 {c['12개월 월평균']}건 대비 이달 {c['이달']}건. "
                           "이달 보도자료를 블로그·영상으로 재가공하는 것이 가장 빠른 공급원.")
    if pending:
        rep.actions.append(f"확인 대기 기사 {pending}건을 O/X로 판정(보도성과 검토 시트) — 판정하면 이달 매체·기사 수가 확정된다.")
    top_any = [v for ch in ("보도자료", "포토뉴스", "유튜브") for v in rep.top_views.get(ch, [])[:1]]
    if top_any:
        best_v = max(top_any, key=lambda v: v["조회수"])
        rep.actions.append(f"조회 상위 콘텐츠 「{short(best_v['제목'])}」({best_v['조회수']:,}회)의 주제를 다음 달 후속 콘텐츠"
                           "(블로그·쇼츠) 후보로.")

    # --- 주석
    if in_progress:
        rep.notes.append(f"진행 중인 달 — {rep.basis}까지의 데이터. 달이 끝나면 매주 자동 갱신으로 다시 작성된다.")
    if (mon["집계 상태"] != "확정").any() if not mon.empty else False:
        rep.notes.append("배포 60일이 안 된 보도자료는 '집계 중' — 매체·기사 수가 아직 늘어날 수 있다.")
    first_hist = hist["기준일"].min() if not hist.empty else None
    rep.notes.append(
        "조회수는 기준일까지의 누적값(홈페이지 게시판·유튜브). 네이버 블로그는 조회수가 비공개라 댓글 수만 수집한다."
        + (f" 월별 증가분은 조회수 이력({first_hist}부터)이 한 달 이상 쌓이면 추가된다." if first_hist else ""))
    rep.notes.append(meta.get("집계 기준", ""))
    return rep


# ---------------------------------------------------------------- 렌더링
CSS = """
:root{--bg:#F6F8FB;--surface:#FFFFFF;--ink:#0F172A;--sub:#475569;--muted:#64748B;--line:#E2E8F0;
--accent:#0E7490;--accent-2:#0891B2;--good:#047857;--bad:#B91C1C;--insight:#6D28D9;--action:#B45309;
--good-bg:#ECFDF5;--bad-bg:#FEF2F2;--insight-bg:#F5F3FF;--action-bg:#FFFBEB}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 'Pretendard','Apple SD Gothic Neo','Malgun Gothic',system-ui,sans-serif;
word-break:keep-all;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto;padding:48px 24px 64px}
header{position:relative;padding:40px 40px 32px;border-radius:24px;color:#fff;overflow:hidden;
background:radial-gradient(600px 300px at 90% -20%,rgba(34,211,238,.45),transparent 60%),
radial-gradient(500px 260px at -10% 120%,rgba(56,189,248,.35),transparent 60%),#0B1220}
.eyebrow{font-size:13px;letter-spacing:.14em;text-transform:uppercase;color:#67E8F9;font-weight:700}
h1{margin:8px 0 6px;font-size:36px;line-height:1.25;letter-spacing:-.02em}
.meta{color:#CBD5E1;font-size:14px}
.chip{display:inline-block;margin-left:8px;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:700;
background:rgba(251,191,36,.18);color:#FCD34D;vertical-align:middle}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:-28px 16px 0;position:relative}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:16px 18px;box-shadow:0 8px 24px rgba(15,23,42,.06)}
.kpi .l{font-size:13px;color:var(--muted)}.kpi .v{font-size:26px;font-weight:800;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.kpi .s{font-size:12px;color:var(--muted)}
section{margin-top:40px}
h2{font-size:20px;margin:0 0 16px;letter-spacing:-.01em;display:flex;align-items:center;gap:10px}
h2 .n{font-size:12px;color:var(--accent);font-weight:800;letter-spacing:.12em}
table{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--line);border-radius:16px;overflow:hidden;font-size:15px}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:13px;color:var(--muted);font-weight:600;background:#F8FAFC}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.bar{height:8px;border-radius:99px;background:linear-gradient(90deg,var(--accent-2),#67E8F9);min-width:2px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:20px}
.card h3{margin:0 0 10px;font-size:15px}
.card ol{margin:0;padding-left:18px}.card li{margin:4px 0}
.pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;background:#F1F5F9;color:var(--sub);margin-right:4px}
.pill.open{background:#FEF3C7;color:#92400E}
.verdicts{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.v{border-radius:16px;padding:20px 22px;border:1px solid transparent}
.v h3{margin:0 0 8px;font-size:16px;display:flex;gap:8px;align-items:center}
.v ul{margin:0;padding-left:18px}.v li{margin:6px 0}
.v.good{background:var(--good-bg);border-color:#A7F3D0}.v.good h3{color:var(--good)}
.v.bad{background:var(--bad-bg);border-color:#FECACA}.v.bad h3{color:var(--bad)}
.v.insight{background:var(--insight-bg);border-color:#DDD6FE}.v.insight h3{color:var(--insight)}
.v.action{background:var(--action-bg);border-color:#FDE68A}.v.action h3{color:var(--action)}
.empty{color:var(--muted)}
.notes{margin-top:40px;font-size:13px;color:var(--muted);border-top:1px solid var(--line);padding-top:16px}
.notes li{margin:4px 0}
@media (max-width:720px){.kpis{grid-template-columns:repeat(2,1fr);margin:-20px 0 0}.grid2,.verdicts{grid-template-columns:1fr}
h1{font-size:28px}header{padding:28px 22px 40px}}
@media print{body{background:#fff}.wrap{padding:0}header{-webkit-print-color-adjust:exact;print-color-adjust:exact}
section,.v,.card{break-inside:avoid}.kpi{box-shadow:none}}
"""


def _e(x: object) -> str:
    return html.escape(str(x))


def _verdict(cls: str, icon: str, title: str, items: list[str], empty: str) -> str:
    body = "".join(f"<li>{_e(i)}</li>" for i in items) if items else f"<li class='empty'>{_e(empty)}</li>"
    return f"<div class='v {cls}'><h3><span aria-hidden='true'>{icon}</span>{title}</h3><ul>{body}</ul></div>"


def render(rep: Report) -> str:
    y, m = rep.month.split("-")
    status = "<span class='chip'>진행 중</span>" if rep.in_progress else ""
    kpis = "".join(f"<div class='kpi'><div class='l'>{_e(l)}</div><div class='v'>{_e(v)}</div><div class='s'>{_e(s)}</div></div>"
                   for l, v, s in rep.kpis)
    ch_max = max([c["이달"] for c in rep.channels] + [1])
    ch_rows = "".join(
        f"<tr><td>{_e(c['채널'])}</td><td class='num'>{c['이달']}</td>"
        f"<td style='width:34%'><div class='bar' style='width:{100 * c['이달'] / ch_max:.0f}%'></div></td>"
        f"<td class='num'>{c['전월']}</td><td class='num'>{c['12개월 월평균']}</td></tr>" for c in rep.channels)
    if rep.releases:
        def pills(r: dict) -> str:
            tags = list(dict.fromkeys(t for t in (r["보도유형"], r["연구분야"]) if t and t != "해당 없음"))  # 중복·빈 값 제거
            out = "".join(f"<span class='pill'>{_e(t)}</span>" for t in tags)
            return out + f"<span class='pill {'open' if r['집계 상태'] != '확정' else ''}'>{_e(r['집계 상태'])}</span>"

        rel_rows = "".join(
            f"<tr><td class='num'>{_e(r['배포일'])}</td><td><a href='{_e(r['링크'])}'>{_e(r['제목'])}</a><br>{pills(r)}</td>"
            f"<td class='num'>{r['매체 수']}</td><td class='num'>{r['기사 수']}</td></tr>" for r in rep.releases)
    else:
        rel_rows = "<tr><td colspan='4' class='empty'>이달 배포한 보도자료가 없습니다.</td></tr>"
    view_cards = ""
    for ch, items in rep.top_views.items():
        lis = "".join(f"<li><a href='{_e(v['링크'])}'>{_e(short(v['제목'], 38))}</a> · <b>{v['조회수']:,}</b>회</li>" for v in items)
        view_cards += f"<div class='card'><h3>{_e(ch)} 조회 상위</h3><ol>{lis or '<li class=empty>이달 게시물 없음</li>'}</ol></div>"
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KITECH 홍보 월간 보고서 {y}년 {int(m)}월</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css">
<style>{CSS}</style></head><body><div class="wrap">
<header><div class="eyebrow">KITECH 전략홍보실 · Monthly PR Report</div>
<h1>{y}년 {int(m)}월 홍보 월간 보고서{status}</h1>
<div class="meta">기준일 {_e(rep.basis)} · 보도자료·포토뉴스·유튜브·블로그 + 언론 보도성과 · 규칙 기반 자동 작성</div></header>
<div class="kpis">{kpis}</div>
<section><h2><span class="n">01</span>채널별 발행</h2>
<table><thead><tr><th>채널</th><th class="num">이달</th><th></th><th class="num">전월</th><th class="num">12개월 월평균</th></tr></thead>
<tbody>{ch_rows}</tbody></table></section>
<section><h2><span class="n">02</span>보도자료 언론 보도성과</h2>
<table><thead><tr><th class="num">배포</th><th>보도자료</th><th class="num">매체</th><th class="num">기사</th></tr></thead>
<tbody>{rel_rows}</tbody></table></section>
<section><h2><span class="n">03</span>조회 반응 (기준일 누적)</h2><div class="grid2">{view_cards}</div></section>
<section><h2><span class="n">04</span>평가</h2><div class="verdicts">
{_verdict('good', '▲', 'Good', rep.good, '기준을 넘은 항목이 없습니다.')}
{_verdict('bad', '▼', 'Bad', rep.bad, '기준에 걸린 항목이 없습니다.')}
{_verdict('insight', '◆', '시사점', rep.insights, '이달 데이터로 도출할 시사점이 없습니다.')}
{_verdict('action', '→', '개선점', rep.actions, '이달 조치 항목이 없습니다.')}
</div></section>
<ul class="notes">{''.join(f'<li>{_e(n)}</li>' for n in rep.notes if n)}
<li>판정 기준: Good = 전체 중앙값의 {GOOD_MEDIA_RATIO}배 이상 실린 보도·12개월 평균 +20% 이상 발행 / Bad = 배포 14일 이상 지났는데 하위 25% 이하·평균의 절반 이하 발행.</li></ul>
</div></body></html>"""


def write(rep: Report, out_dir: Path = REPORT_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"monthly_report_{rep.month}.html"
    p.write_text(render(rep), encoding="utf-8-sig")  # BOM: 내려받아 더블클릭해도 한글이 안 깨지게
    return p


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM (생략 시 2026-10부터 이번 달까지 전부)")
    a = ap.parse_args()
    today = date.today()
    hub, perf, fields, meta, hist = load_inputs()
    months = [a.month] if a.month else months_from(FIRST_MONTH, today)
    index = []
    for ym in months:
        rep = build(ym, hub, perf, fields, meta, hist, today)
        p = write(rep)
        index.append({"month": ym, "file": p.name, "in_progress": rep.in_progress, "basis": rep.basis,
                      "good": len(rep.good), "bad": len(rep.bad)})
        print(f"✓ {ym} → {p.name} (Good {len(rep.good)} · Bad {len(rep.bad)}{' · 진행 중' if rep.in_progress else ''})")
    if not a.month:
        (REPORT_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
