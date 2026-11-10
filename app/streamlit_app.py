"""KITECH 홍보 허브 — 4채널 아카이브 + 언론 보도성과 + 월간 보고서.

실행:
    streamlit run "C:\\Users\\admin\\Desktop\\교육\\기관-홍보-허브\\app\\streamlit_app.py"

탭:
    📊 대시보드   — 채널별 발행·반응(조회수·댓글) 통계
    📈 보도성과   — 보도자료별 보도 매체·기사 수, 분야·R&R별 경향(보도자료 성과분석이 주 1회 내보냄)
    🗓 월간 보고서 — 2026년 10월분부터. 통계·Good·Bad·시사점·개선점, HTML 내려받기
    🔍 통합검색   — 4채널 동시 검색
    채널별 4탭    — 보도자료 / 포토뉴스 / 유튜브 / 블로그

데이터는 매주 월요일 scripts/weekly_update.ps1 이 갱신한다.
"""
from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
DATA_PATH = DATA_DIR / "허브-데이터셋.csv"
PERF_PATH = DATA_DIR / "보도성과.csv"
PERF_MEDIA_PATH = DATA_DIR / "보도성과_매체.csv"
PERF_META_PATH = DATA_DIR / "보도성과_meta.json"
CHANNELS = ["보도자료", "포토뉴스", "유튜브", "블로그"]

# ── 디자인 토큰 ─────────────────────────────────────────────────
BG = "#070B14"
SURFACE = "rgba(17,26,46,0.62)"
BORDER = "rgba(148,163,184,0.16)"
TEXT = "#E6EDF7"
MUTED = "#94A3B8"          # BG 대비 7.4:1
# 색 하나 = 뜻 하나. 화면(UI) 색과 데이터 색을 섞지 않는다 — 시안 한 색이 강조·포토뉴스·평균 이상을 겸하던 문제를 끊는다.
ACCENT = "#7AA2FF"         # UI 전용: 탭·링크 hover·포커스·소제목 (블루 계열 = 기관 톤)
DATA = "#22D3EE"           # 데이터 전용: 단일 계열 막대·히트맵 상단·평균 이상
GOOD, BAD, WARN = "#34D399", "#F87171", "#FCD34D"  # 상태 전용
CHANNEL_COLORS = {"보도자료": "#FB923C", "포토뉴스": "#B794F6", "유튜브": "#F472B6", "블로그": "#8FCB5A"}
POS, NEG = DATA, "#64748B"  # 평균 이상 / 이하
DIM_AXES = {
    "보도유형": "보도유형", "연구분야": "연구분야", "국가전략기술": "전략기술",
    "제조혁신 로드맵": "제조혁신 로드맵", "지역혁신 로드맵": "지역혁신 로드맵", "R&R 연계": "R&R 연계", "가시성": "가시성",
}
PENDING = "분류 대기"
SMALL_N = 5  # 표본이 이보다 적은 항목은 흐리게 — 평균이 한두 건에 휘둘린다

STOPWORDS = {
    "생기원", "한국생산기술연구원", "kitech", "기술", "개발", "연구원", "연구",
    "위해", "통해", "관련", "대한", "이번", "지난", "최근", "원장", "통한",
    "위한", "대해", "함께", "기반", "이를", "있는", "있다", "있어", "있도록",
    "또한", "이상", "이하", "올해", "내년", "지난해",
    # 영문 영상 제목의 기능어
    "the", "and", "for", "with", "what", "how", "from", "this", "that", "are", "you", "your", "its", "into", "who", "why",
}

st.set_page_config(page_title="KITECH 홍보 허브", page_icon="📰", layout="wide")

# ── 전역 스타일: 앰비언트 라이트 · 그레인 · 유리 카드 ─────────────────
# 움직임은 배경 빛의 느린 흐름(36s)과 진입 페이드(240ms)만 — 읽기를 방해하지 않게. 모션 줄이기 설정이면 끈다.
NOISE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>"
         "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/>"
         "</filter><rect width='100%' height='100%' filter='url(%23n)' opacity='.55'/></svg>")
st.markdown(f"""<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
:root {{ --bg:{BG}; --surface:{SURFACE}; --border:{BORDER}; --ink:{TEXT}; --muted:{MUTED};
  --accent:{ACCENT}; --data:{DATA}; --good:{GOOD}; --warn:{WARN}; --r:16px; --ease:cubic-bezier(.2,.7,.2,1); }}
.stApp, .stApp * {{ font-family:'Pretendard',-apple-system,BlinkMacSystemFont,system-ui,'Malgun Gothic',sans-serif !important; }}
.stApp {{ background:var(--bg); color:var(--ink); word-break:keep-all; }}
/* 앰비언트 라이트 — 화면 뒤에서 천천히 움직이는 세 개의 빛 */
.stApp::before {{ content:""; position:fixed; inset:-25vmax; z-index:0; pointer-events:none;
  background:
    radial-gradient(38vmax 38vmax at 18% 12%, rgba(122,162,255,.18), transparent 62%),
    radial-gradient(32vmax 32vmax at 86% 18%, rgba(79,70,229,.16), transparent 62%),
    radial-gradient(44vmax 44vmax at 58% 105%, rgba(56,132,248,.10), transparent 62%);
  filter:blur(24px); animation:drift 36s ease-in-out infinite alternate; }}
/* 필름 그레인 — 평평한 다크 배경에 질감 */
.stApp::after {{ content:""; position:fixed; inset:0; z-index:0; pointer-events:none; opacity:.06;
  background-image:url("{NOISE}"); mix-blend-mode:overlay; }}
@keyframes drift {{ 0%{{transform:translate3d(0,0,0) rotate(0)}} 50%{{transform:translate3d(3vmax,-2vmax,0) rotate(7deg)}}
  100%{{transform:translate3d(-2vmax,2.5vmax,0) rotate(-5deg)}} }}
[data-testid="stAppViewContainer"], [data-testid="stSidebar"], [data-testid="stHeader"] {{ position:relative; z-index:1; }}
[data-testid="stHeader"] {{ background:transparent; }}
.block-container {{ padding-top:2.2rem; max-width:1320px; }}
.block-container > div {{ animation:rise .24s var(--ease) both; }}
@keyframes rise {{ from{{opacity:0; transform:translateY(6px)}} to{{opacity:1; transform:none}} }}
@media (prefers-reduced-motion: reduce) {{ .stApp::before, .block-container > div, .hero .glow {{ animation:none !important; }} }}

/* 데이터 카드 — 흐림(backdrop-filter)은 히어로·사이드바에만. 카드 뒤 배경은 거의 단색이라 흐림이 보이지 않고 렌더 비용만 든다.
   클릭되지 않는 카드는 hover에 반응하지 않는다(떠오르면 눌러도 되는 것처럼 착각한다). */
div[data-testid="stVerticalBlockBorderWrapper"] {{ background:var(--surface) !important; border:1px solid var(--border) !important;
  border-radius:var(--r) !important; box-shadow:inset 0 1px 0 rgba(255,255,255,.04); }}
div[data-testid="stVerticalBlockBorderWrapper"] h4 {{ color:var(--ink); font-weight:650; letter-spacing:-.2px; margin:.1rem 0 .35rem; }}
div[data-testid="stMetric"] {{ position:relative; overflow:hidden; background:var(--surface); padding:16px 18px; border-radius:var(--r);
  border:1px solid var(--border); }}
div[data-testid="stMetric"]::before {{ content:""; position:absolute; left:0; right:0; top:0; height:1px;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,.14), transparent); }}
div[data-testid="stMetricLabel"] {{ color:var(--muted) !important; }}
div[data-testid="stMetricValue"] {{ color:var(--ink) !important; font-weight:750; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }}
div[data-baseweb="tab-list"] {{ gap:4px; border-bottom:1px solid var(--border); }}
button[data-baseweb="tab"] {{ background:transparent !important; color:var(--muted) !important; border-radius:10px 10px 0 0 !important;
  padding:10px 16px !important; transition:color .15s; }}
button[data-baseweb="tab"]:hover {{ color:var(--ink) !important; }}
button[data-baseweb="tab"][aria-selected="true"] {{ color:var(--accent) !important; background:rgba(122,162,255,.08) !important; }}
div[data-baseweb="tab-highlight"] {{ background:var(--accent) !important; height:2px !important; box-shadow:0 0 12px rgba(122,162,255,.7); }}
section[data-testid="stSidebar"] {{ background:rgba(10,15,28,.82); backdrop-filter:blur(16px); border-right:1px solid var(--border); }}
/* 링크는 글 색 그대로 — 목록 전체가 파란 밑줄로 덮이지 않게. 가리킬 때만 강조색+밑줄 */
.stApp a, .stApp a:visited {{ color:var(--ink) !important; text-decoration:none !important; transition:color .15s; }}
.stApp a:hover {{ color:var(--accent) !important; text-decoration:underline !important; text-underline-offset:3px; }}
*:focus-visible {{ outline:2px solid var(--accent) !important; outline-offset:2px; }}
::-webkit-scrollbar {{ width:10px; height:10px; }} ::-webkit-scrollbar-thumb {{ background:rgba(148,163,184,.25); border-radius:99px; }}

/* 히어로 */
.hero {{ position:relative; overflow:hidden; border-radius:24px; padding:36px 40px 30px; margin-bottom:8px;
  border:1px solid var(--border); background:linear-gradient(135deg, rgba(17,26,46,.75), rgba(10,15,28,.55)); backdrop-filter:blur(18px); }}
.hero .glow {{ position:absolute; width:420px; height:420px; right:-120px; top:-200px; border-radius:50%;
  background:radial-gradient(circle, rgba(122,162,255,.38), transparent 65%); filter:blur(10px); animation:breathe 8s ease-in-out infinite; }}
@keyframes breathe {{ 0%,100%{{opacity:.75; transform:scale(1)}} 50%{{opacity:1; transform:scale(1.08)}} }}
.hero .eyebrow {{ font-size:12px; letter-spacing:.18em; font-weight:700; color:var(--accent); text-transform:uppercase; }}
.hero h1 {{ margin:6px 0 6px; font-size:clamp(28px,3.4vw,44px); line-height:1.15; letter-spacing:-.03em; font-weight:800;
  background:linear-gradient(92deg,#F8FAFC 0%,#C7D7FF 45%,{ACCENT} 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }}
.hero p {{ margin:0; color:var(--muted); font-size:15.5px; max-width:720px; line-height:1.7; }}
.hero .stats {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-top:24px; }}
.hero .stat {{ padding:14px 16px; border-radius:14px; background:rgba(255,255,255,.03); border:1px solid var(--border); }}
.hero .stat b {{ display:block; font-size:clamp(20px,2vw,28px); font-weight:800; letter-spacing:-.02em; font-variant-numeric:tabular-nums; color:#F8FAFC; }}
.hero .stat span {{ font-size:12.5px; color:var(--muted); }}
.live {{ display:inline-flex; align-items:center; gap:8px; margin-top:14px; font-size:12.5px; color:var(--muted);
  padding:4px 10px; border-radius:99px; border:1px solid var(--border); background:rgba(255,255,255,.02); }}
/* 주 1회 갱신 데이터 — 깜빡이는 '실시간' 점은 사실과 다른 신호라 정지 */
.live i {{ width:8px; height:8px; border-radius:50%; background:var(--good); }}
@media (max-width: 760px) {{ .hero {{ padding:26px 20px 22px; }} .hero .stats {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}

/* 섹션 머리 */
.sec {{ margin:28px 0 12px; }} .sec .k {{ font-size:11.5px; letter-spacing:.18em; font-weight:700; color:var(--accent); }}
.sec h3 {{ margin:2px 0 4px; font-size:21px; letter-spacing:-.02em; color:var(--ink); }}
.sec p {{ margin:0; font-size:14px; color:var(--muted); }}
.sec .line {{ height:1px; margin-top:12px; background:linear-gradient(90deg, rgba(122,162,255,.55), rgba(122,162,255,.12) 40%, transparent); }}
.chip {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.78rem; font-weight:650; margin:0 6px 4px 0;
  font-variant-numeric:tabular-nums; border:1px solid; }}
.chip.soft {{ border-color:transparent; background:rgba(34,211,238,.10); color:var(--data); }}
/* 조회·댓글 수치 — 이미 숫자가 뜻을 말하므로 색 없이 중립 */
.chip.stat {{ border-color:transparent; background:rgba(148,163,184,.12); color:#CBD5E1; }}
.chip.warn {{ border-color:transparent; background:rgba(251,191,36,.12); color:#FCD34D; }}
.rank {{ display:flex; gap:12px; align-items:baseline; padding:8px 0; border-bottom:1px solid var(--border); }}
.rank:last-child {{ border-bottom:0; }} .rank .n {{ color:var(--muted); font-weight:800; width:18px; font-variant-numeric:tabular-nums; }}
.rank .t {{ flex:1; color:var(--ink); font-size:14.5px; }} .rank .v {{ color:var(--muted); font-size:13px; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.verdict {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }}
.verdict div {{ padding:12px 14px; border-radius:14px; border:1px solid var(--border); background:var(--surface); }}
.verdict b {{ display:block; font-size:22px; font-variant-numeric:tabular-nums; }} .verdict span {{ font-size:12.5px; color:var(--muted); }}
</style>""", unsafe_allow_html=True)


# ── 데이터 ───────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=["채널", "게시일", "제목", "주요내용", "링크", "썸네일URL", "id"])
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig", dtype=str).fillna("")
    df["게시일"] = pd.to_datetime(df["게시일"], errors="coerce")
    df["연"] = df["게시일"].dt.year
    df["월"] = df["게시일"].dt.month
    df["연월"] = df["게시일"].dt.to_period("M").astype(str)
    df["조회수_n"] = pd.to_numeric(df.get("조회수", pd.Series(dtype=str)), errors="coerce")
    df["댓글수_n"] = pd.to_numeric(df.get("댓글수", pd.Series(dtype=str)), errors="coerce")
    return df


@st.cache_data(ttl=60)
def load_perf() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(보도자료별, 매체별, meta). 파일이 없으면 빈 값 — 탭이 안내 화면을 띄운다."""
    if not PERF_PATH.exists():
        return pd.DataFrame(), pd.DataFrame(), {}
    perf = pd.read_csv(PERF_PATH, encoding="utf-8-sig", dtype={"id": str})
    perf["배포일"] = pd.to_datetime(perf["배포일"], errors="coerce")
    # dtype으로 고르면 pandas 버전마다 문자열 dtype이 달라(object/str) 빈 칸이 float NaN으로 남는다 — 이름으로 지정
    num_cols = {"기사 수", "매체 수", "검토대기 기사"}
    for c in perf.columns:
        if c not in num_cols and c != "배포일":
            perf[c] = perf[c].fillna("").astype(str)
    media = pd.read_csv(PERF_MEDIA_PATH, encoding="utf-8-sig") if PERF_MEDIA_PATH.exists() else pd.DataFrame()
    meta = json.loads(PERF_META_PATH.read_text(encoding="utf-8")) if PERF_META_PATH.exists() else {}
    return perf, media, meta


@st.cache_data(ttl=60)
def load_report_index() -> list[dict]:
    p = REPORT_DIR / "index.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def raw(markup: str) -> None:
    """사용자 HTML/CSS. st.html은 내용을 격리해 렌더링해서 전역 CSS·클래스 스타일이 앱에 닿지 않는다(1.57 실측) — markdown으로 넣는다."""
    st.markdown(markup, unsafe_allow_html=True)


def esc(x: object) -> str:
    return html.escape(str(x))


def style_fig(fig, height: int = 320):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="Pretendard, sans-serif", size=13), height=height,
        margin=dict(t=10, b=10, l=10, r=10), legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=-0.18, title_text=""),
        hoverlabel=dict(bgcolor="#0F172A", bordercolor="rgba(148,163,184,0.35)", font=dict(color=TEXT)),
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.10)", zerolinecolor="rgba(148,163,184,0.16)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.10)", zerolinecolor="rgba(148,163,184,0.16)")
    return fig


def section(k: str, title: str, desc: str = "") -> None:
    raw(f"<div class='sec'><div class='k'>{esc(k)}</div><h3>{esc(title)}</h3>"
            f"{f'<p>{esc(desc)}</p>' if desc else ''}<div class='line'></div></div>")


def fmt_n(v: float) -> str:
    if v >= 10_000:
        return f"{v / 10_000:.1f}만".replace(".0만", "만")
    return f"{v:,.0f}"


df = load_data()
perf, perf_media, perf_meta = load_perf()
PERF_BY_ID = perf.set_index("id").to_dict("index") if not perf.empty else {}
reports = load_report_index()


# ── 사이드바 ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("필터")
    if st.button("🔄 새로고침", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    query = st.text_input("🔍 전역 검색어 (모든 탭 공통)", placeholder="예: 전고체, AI, 패키징",
                          help="대시보드·보도성과·채널별 리스트에 적용됩니다. 통합검색 탭에는 검색창이 따로 있습니다.")
    if not df.empty and not df["게시일"].isna().all():
        min_d, max_d = df["게시일"].min().date(), df["게시일"].max().date()
        date_range = st.date_input("📅 기간", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    else:
        date_range = None
    st.divider()
    latest = {ch: df.loc[df["채널"] == ch, "게시일"].max() for ch in CHANNELS} if not df.empty else {}
    st.caption("**채널별 최신 게시물**\n" + "\n".join(f"- {ch}: {d:%Y-%m-%d}" for ch, d in latest.items() if pd.notna(d)))
    if perf_meta:
        st.caption(f"**보도성과 기준일** {perf_meta.get('기준일', '-')} (매주 월요일 자동 갱신)")


def apply_filters(src: pd.DataFrame, channels: list[str] | None = None, extra_query: str | None = None) -> pd.DataFrame:
    out = src
    if channels:
        out = out[out["채널"].isin(channels)]
    for q in (query, extra_query):
        if q:
            out = out[out["제목"].str.contains(q, case=False, regex=False) | out["주요내용"].str.contains(q, case=False, regex=False)]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        d = out["게시일"].dt.date
        out = out[(d >= date_range[0]) & (d <= date_range[1])]
    return out


def filter_perf(src: pd.DataFrame) -> pd.DataFrame:
    out = src
    if query:
        out = out[out["제목"].str.contains(query, case=False, regex=False) | out["매체명"].str.contains(query, case=False, regex=False)]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        d = out["배포일"].dt.date
        out = out[(d >= date_range[0]) & (d <= date_range[1])]
    return out


# ── 히어로 ───────────────────────────────────────────────────────
now = pd.Timestamp.now()
this_month = df[df["연월"] == now.strftime("%Y-%m")] if not df.empty else df
yt_views = df.loc[df["채널"] == "유튜브", "조회수_n"].sum() if not df.empty else 0
home_views = df.loc[df["채널"].isin(["보도자료", "포토뉴스"]), "조회수_n"].sum() if not df.empty else 0
articles = int(perf["기사 수"].sum()) if not perf.empty else 0
raw(f"""<div class="hero"><div class="glow"></div>
<div class="eyebrow">KITECH PR Intelligence</div>
<h1>KITECH 홍보 허브</h1>
<p>보도자료·포토뉴스·유튜브·블로그 {len(df):,}건을 한곳에서 찾고, 보도자료가 언론에 얼마나 실렸는지와 콘텐츠 반응을 함께 봅니다.</p>
<div class="stats">
 <div class="stat"><b>{len(df):,}</b><span>누적 콘텐츠</span></div>
 <div class="stat"><b>{len(this_month):,}</b><span>{now.month}월 발행</span></div>
 <div class="stat"><b>{articles:,}</b><span>보도 기사 (2020~)</span></div>
 <div class="stat"><b>{fmt_n(home_views + yt_views)}</b><span>누적 조회 (홈페이지+유튜브)</span></div>
</div>
<div class="live"><i></i>주간 갱신 · 기준일 {esc(perf_meta.get('기준일', '-'))}</div>
</div>""")


# ── 카드 하나(검색·채널 탭 공용) ──────────────────────────────────
def chips(row: pd.Series) -> str:
    out = []
    v, c = row.get("조회수_n"), row.get("댓글수_n")
    if pd.notna(v):
        out.append(f"<span class='chip stat'>조회 {fmt_n(v)}</span>")
    if row["채널"] == "블로그" and pd.notna(c) and c > 0:
        out.append(f"<span class='chip stat'>댓글 {int(c)}</span>")
    if row["채널"] == "보도자료" and (p := PERF_BY_ID.get(str(row["id"]))):
        out.append(f"<span class='chip soft'>보도 매체 {int(p['매체 수'])}곳 · 기사 {int(p['기사 수'])}건</span>")
        if str(p["집계 상태"]).startswith("집계 중"):
            out.append("<span class='chip warn'>집계 중</span>")
    return "".join(out)


def render_card(row: pd.Series, show_channel: bool) -> None:
    d = row["게시일"]
    date_str = d.strftime("%Y.%m.%d") if pd.notna(d) else "-"
    thumb = row.get("썸네일URL") or ""
    with st.container(border=True):
        cols = st.columns([1.5, 8.5]) if (thumb and row["채널"] != "보도자료") else st.columns([0.001, 10])
        if thumb and row["채널"] != "보도자료":
            with cols[0]:
                st.image(thumb, width="stretch")
        with cols[1]:
            color = CHANNEL_COLORS.get(row["채널"], MUTED)
            head = (f"<span class='chip' style='color:{color};border-color:{color}'>{esc(row['채널'])}</span>" if show_channel else "")
            raw(f"<div style='color:{MUTED};font-size:.85rem;margin-bottom:2px'>{head}{date_str}</div>")
            st.markdown(f"#### {row['제목']}")
            if c := chips(row):
                raw(f"<div>{c}</div>")
            if row.get("주요내용"):
                st.caption(row["주요내용"])
            if row.get("링크"):
                st.markdown(f"[원문 보기 →]({row['링크']})")


# ── 탭 ───────────────────────────────────────────────────────────
tab_dash, tab_perf, tab_report, tab_search, *channel_tabs = st.tabs(
    ["📊 대시보드", "📈 보도성과", "🗓 월간 보고서", "🔍 통합검색"] + [f"{c} ({(df['채널'] == c).sum():,})" for c in CHANNELS]
)

# ── 📊 대시보드 ─────────────────────────────────────────────────
with tab_dash:
    fdf = apply_filters(df)
    if fdf.empty:
        st.warning("필터 조건에 맞는 데이터가 없습니다. 사이드바 검색어·기간을 넓혀 보세요.")
    else:
        ks = st.columns(5)
        ks[0].metric("전체", f"{len(fdf):,}건")
        for col, ch in zip(ks[1:], CHANNELS, strict=True):
            col.metric(ch, f"{(fdf['채널'] == ch).sum():,}건")

        section("REACH", "콘텐츠 반응", "공개된 지표만 모았습니다 — 홈페이지 게시판·유튜브는 누적 조회수, 네이버 블로그는 조회수가 비공개라 댓글 수.")
        basis = fdf["지표기준일"].replace("", pd.NA).dropna().max() if "지표기준일" in fdf else None
        r1 = st.columns(4)
        r1[0].metric("홈페이지 조회 (보도자료)", fmt_n(fdf.loc[fdf["채널"] == "보도자료", "조회수_n"].sum()) + "회")
        r1[1].metric("홈페이지 조회 (포토뉴스)", fmt_n(fdf.loc[fdf["채널"] == "포토뉴스", "조회수_n"].sum()) + "회")
        r1[2].metric("유튜브 조회", fmt_n(fdf.loc[fdf["채널"] == "유튜브", "조회수_n"].sum()) + "회")
        r1[3].metric("블로그 댓글", f"{int(fdf.loc[fdf['채널'] == '블로그', '댓글수_n'].sum()):,}개")
        cut = now - pd.Timedelta(days=90)
        rc = st.columns(3)
        for col, ch in zip(rc, ("보도자료", "포토뉴스", "유튜브"), strict=True):
            recent_ch = fdf[(fdf["채널"] == ch) & (fdf["게시일"] >= cut)]
            sub = recent_ch[recent_ch["조회수_n"].notna()].nlargest(5, "조회수_n")
            # 빈 이유를 구분한다 — 게시물이 없는 것과 조회수를 아직 못 읽은 것은 다르다
            empty_msg = ("최근 90일 게시물이 없습니다." if recent_ch.empty
                         else f"최근 90일 게시물 {len(recent_ch)}건 — 조회수는 다음 자동 갱신 때 채워집니다.")
            rows = "".join(
                f"<div class='rank'><span class='n'>{i}</span><span class='t'><a href='{esc(r['링크'])}'>{esc(r['제목'])}</a></span>"
                f"<span class='v'>{fmt_n(r['조회수_n'])}회</span></div>" for i, (_, r) in enumerate(sub.iterrows(), 1))
            with col, st.container(border=True):
                st.markdown(f"**{ch} · 최근 90일 조회 상위**")
                raw(rows or f"<p style='color:{MUTED}'>{empty_msg}</p>")
        if basis:
            st.caption(f"조회수 기준일 {basis} · 누적값이라 오래된 글일수록 큽니다(같은 기간 글끼리 비교).")

        section("VOLUME", "발행 흐름")
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("##### 채널 비중")
            ch_count = fdf["채널"].value_counts().rename_axis("채널").reset_index(name="건수")
            fig = px.pie(ch_count, names="채널", values="건수", hole=0.64, color="채널", color_discrete_map=CHANNEL_COLORS)
            fig.update_traces(textposition="inside", textinfo="percent+label", marker=dict(line=dict(color=BG, width=2)))
            st.plotly_chart(style_fig(fig).update_layout(showlegend=False))
        with c2:
            st.markdown("##### 연도별 발행량")
            yearly = fdf.dropna(subset=["연"]).groupby(["연", "채널"]).size().reset_index(name="건수")
            yearly["연"] = yearly["연"].astype(int).astype(str)
            # 문자열 축은 '처음 나온 순서'로 그려진다(실측: 2015→2026→2003) — 연도 순서를 못 박는다
            fig = px.bar(yearly, x="연", y="건수", color="채널", color_discrete_map=CHANNEL_COLORS,
                         category_orders={"채널": CHANNELS, "연": sorted(yearly["연"].unique())})
            st.plotly_chart(style_fig(fig).update_layout(xaxis_title=None, yaxis_title=None, bargap=0.28))

        c3, c4 = st.columns(2)
        with c3:
            st.markdown("##### 월별 히트맵 (연 × 월)")
            heat = fdf.dropna(subset=["연", "월"]).groupby(["연", "월"]).size().reset_index(name="건수")
            if not heat.empty:
                pivot = heat.astype({"연": int, "월": int}).pivot(index="연", columns="월", values="건수").fillna(0).sort_index(ascending=False)
                fig = px.imshow(pivot, aspect="auto", labels=dict(x="월", y="", color="건수"),
                                color_continuous_scale=[[0, "#0B1220"], [0.4, "#0E7490"], [0.7, DATA], [1, "#A5F3FC"]])
                st.plotly_chart(style_fig(fig).update_xaxes(dtick=1))
        with c4:
            st.markdown("##### 최근 12개월 추이")
            recent = fdf.dropna(subset=["연월"])
            months = sorted(recent["연월"].unique())[-12:]
            trend = recent[recent["연월"].isin(months)].groupby(["연월", "채널"]).size().reset_index(name="건수")
            fig = px.line(trend, x="연월", y="건수", color="채널", color_discrete_map=CHANNEL_COLORS, markers=True,
                          category_orders={"채널": CHANNELS}, line_shape="spline")
            st.plotly_chart(style_fig(fig).update_traces(line=dict(width=2.4)).update_layout(xaxis_title=None, yaxis_title=None))

        st.markdown("##### 제목 키워드 Top 20")
        tokens = [t for title in fdf["제목"] for t in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", title)
                  if t.lower() not in STOPWORDS and t not in STOPWORDS]
        if top := Counter(tokens).most_common(20):
            kw = pd.DataFrame(top, columns=["키워드", "빈도"]).iloc[::-1]
            fig = px.bar(kw, x="빈도", y="키워드", orientation="h", color="빈도",
                         color_continuous_scale=[[0, "#0E7490"], [0.5, DATA], [1, "#67E8F9"]])
            st.plotly_chart(style_fig(fig, 480).update_layout(coloraxis_showscale=False, bargap=0.25, yaxis_title=None))


# ── 📈 보도성과 ─────────────────────────────────────────────────
def dim_stats(src: pd.DataFrame, col: str) -> pd.DataFrame:
    """집계가 끝난 보도자료만으로 항목별 평균 매체 수(필터 반영). 분류 대기는 뺀다."""
    s = src[(src["집계 상태"] == "확정") & (src[col] != PENDING)]
    if s.empty:
        return pd.DataFrame()
    g = s.groupby(col).agg(n=("id", "count"), mean=("매체 수", "mean"), median=("매체 수", "median"),
                           articles=("기사 수", "sum")).reset_index()
    return g.sort_values("mean", ascending=True)


with tab_perf:
    if perf.empty:
        st.info("보도성과 데이터가 아직 없습니다. 매주 월요일 자동 갱신 뒤에 표시됩니다.")
    else:
        pf = filter_perf(perf)
        st.caption(f"기준일 {perf_meta.get('기준일', '-')} · 보도자료 {len(perf):,}건 중 필터 결과 {len(pf):,}건 "
                   "· 보도자료 1건이 네이버 뉴스에서 몇 개 매체에 실렸는지 자동 대조한 결과")
        if pf.empty:
            st.warning("필터 조건에 맞는 보도자료가 없습니다. 사이드바 검색어·기간을 넓혀 보세요.")
        else:
            settled = pf[pf["집계 상태"] == "확정"]
            k = st.columns(4)
            k[0].metric("보도자료", f"{len(pf):,}건")
            k[1].metric("보도 기사", f"{int(pf['기사 수'].sum()):,}건")
            k[2].metric("건당 매체 수 (중앙값)", f"{settled['매체 수'].median():.0f}곳" if not settled.empty else "-",
                        help="집계가 끝난(배포 60일 경과) 보도자료만 셉니다.")
            k[3].metric("확인 대기 기사", f"{int(pf['검토대기 기사'].sum()):,}건",
                        help="자동 대조 점수가 애매해 사람이 확인해야 하는 기사. 확인 전에는 숫자에 넣지 않습니다(하한값).")

            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown("##### 보도자료별 보도 매체 수 (연도별 중앙값)")
                yr = settled.dropna(subset=["배포일"]).assign(연=lambda d: d["배포일"].dt.year.astype(str))
                if not yr.empty:
                    by_year = yr.groupby("연")["매체 수"].median().reset_index()
                    fig = px.bar(by_year, x="연", y="매체 수", text="매체 수", color_discrete_sequence=[DATA])
                    fig.update_traces(texttemplate="%{text:.0f}곳", textposition="outside", cliponaxis=False,
                                      marker=dict(line=dict(width=0)))
                    st.plotly_chart(style_fig(fig, 300).update_layout(xaxis_title=None, yaxis_title=None, bargap=0.4))
            with c2:
                st.markdown("##### 자주 보도한 매체 Top 15")
                names = [n for cell in pf["매체명"] for n in cell.split(", ") if n]
                if top := Counter(names).most_common(15):
                    tdf = pd.DataFrame(top, columns=["매체", "보도한 보도자료 수"]).iloc[::-1]
                    fig = px.bar(tdf, x="보도한 보도자료 수", y="매체", orientation="h", text="보도한 보도자료 수",
                                 color_discrete_sequence=[DATA])
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    st.plotly_chart(style_fig(fig, 300 + 8 * len(top)).update_layout(xaxis_title=None, yaxis_title=None))

            # ── 분야·R&R별 경향 (사용자 요청: 매체 수 차트 바로 아래)
            section("WHAT GETS COVERED", "어떤 보도자료가 많이 실렸나",
                    "분류별 평균 보도 매체 수 — 집계가 끝난 보도자료 기준, 사이드바 필터 반영. 함께 나타난 경향이며 원인을 뜻하지는 않습니다.")
            if "R&R 연계" in pf:
                rr = settled[settled["R&R 연계"] != PENDING]
                direct = rr[rr["R&R 연계"] == "직접 연계"]
                notech = rr[rr["R&R 연계"] == "기술 보도 아님"]
                r = st.columns(3)
                # 비율을 delta로 넣으면 ↑ 화살표가 붙어 '늘었다'로 읽힌다 — 값 안에 둔다
                r[0].metric(f"R&R 직접 연계 보도 ({len(direct)}/{len(rr)}건)", f"{len(direct) / len(rr):.0%}" if len(rr) else "-",
                            help="우리원 R&R을 「미래비전 2035」 제조혁신·지역혁신 로드맵 요소기술로 보고, 근접도 높음·중간으로 대응한 보도.")
                r[1].metric("직접 연계 보도 평균 매체", f"{direct['매체 수'].mean():.1f}곳" if len(direct) else "-")
                r[2].metric("기술 보도 아님(인사·행사) 평균", f"{notech['매체 수'].mean():.1f}곳" if len(notech) else "-")

                axis_label = st.segmented_control("분류 기준", list(DIM_AXES), default="연구분야", key="dim_axis")
                col = DIM_AXES.get(axis_label or "연구분야", "연구분야")
                stats = dim_stats(pf, col)
                if stats.empty:
                    st.caption("이 분류로 집계가 끝난 보도자료가 없습니다.")
                else:
                    overall = settled["매체 수"].mean()
                    colors = [(POS if m >= overall else NEG) for m in stats["mean"]]
                    opac = [1.0 if n >= SMALL_N else 0.45 for n in stats["n"]]
                    fig = go.Figure(go.Bar(
                        x=stats["mean"], y=stats[col], orientation="h", marker=dict(color=colors, opacity=opac),
                        text=[f"{m:.1f}곳 · {n}건" for m, n in zip(stats["mean"], stats["n"], strict=True)],
                        textposition="outside", cliponaxis=False,
                        hovertemplate="%{y}<br>평균 %{x:.1f}곳<extra></extra>"))
                    fig.add_vline(x=overall, line=dict(color=MUTED, dash="dot", width=1.5))
                    # 라벨은 그림 영역 밖 위쪽에 둔다 — 안쪽에 두면 1위 막대와 겹친다(캡처로 두 번 확인)
                    fig.add_annotation(x=overall, y=1, xref="x", yref="paper", yanchor="bottom", showarrow=False,
                                       text=f"전체 평균 {overall:.1f}곳", font=dict(color="#C4B5FD", size=12))
                    style_fig(fig, 150 + 34 * len(stats)).update_layout(xaxis_title=None, yaxis_title=None,
                                                                        margin=dict(t=32, b=10, l=10, r=110))
                    st.plotly_chart(fig)
                    src = perf_meta.get("분류 출처", {}).get(col, "")
                    st.caption(f"분류 방법: {src} · 흐린 막대 = 표본 {SMALL_N}건 미만")

                st.markdown("##### 많이 기사화된 연구분야 — 기사 수 합계")
                st.caption("면적 = 기사 수 합계, 색 = 보도자료당 평균 매체 수. 인사·행사 등 기술 내용이 없는 보도는 뺐습니다.")
                tm = pf[~pf["연구분야"].isin([PENDING, "해당 없음"])].groupby("연구분야").agg(
                    기사=("기사 수", "sum"), 보도자료=("id", "count"), 평균매체=("매체 수", "mean")).reset_index()
                if not tm.empty:
                    fig = px.treemap(tm, path=["연구분야"], values="기사", color="평균매체",
                                     color_continuous_scale=[[0, "#1E293B"], [0.5, "#0E7490"], [1, DATA]],
                                     custom_data=["보도자료", "평균매체"])
                    fig.update_traces(texttemplate="<b>%{label}</b><br>기사 %{value}건", marker=dict(cornerradius=8),
                                      hovertemplate="%{label}<br>기사 %{value}건 · 보도자료 %{customdata[0]}건"
                                                    "<br>평균 매체 %{customdata[1]:.1f}곳<extra></extra>")
                    st.plotly_chart(style_fig(fig, 360).update_layout(coloraxis_colorbar=dict(title="평균 매체")))

            section("RELEASES", "보도자료별 성과")
            only_open = st.toggle("집계 중인 보도자료만 (배포 60일 이내)", value=False)
            table = (pf[pf["집계 상태"].str.startswith("집계 중")] if only_open else pf).sort_values("배포일", ascending=False)
            show_cols = ["배포일", "제목", "매체 수", "기사 수", "집계 상태", "연구분야", "R&R 연계", "매체명", "링크"]
            show = table[[c for c in show_cols if c in table]].copy()
            show["배포일"] = show["배포일"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                show, hide_index=True, height=min(640, 38 + 35 * max(len(show), 1)),
                column_config={
                    "매체 수": st.column_config.ProgressColumn("매체 수", format="%d곳", min_value=0,
                                                              max_value=int(perf["매체 수"].max() or 1)),
                    "기사 수": st.column_config.NumberColumn("기사 수", format="%d건"),
                    "매체명": st.column_config.TextColumn("보도 매체", width="large"),
                    "링크": st.column_config.LinkColumn("원문", display_text="보도자료 →"),
                },
            )
        with st.expander("집계 기준 · 한계"):
            st.write(perf_meta.get("집계 기준", ""))
            for k_, v_ in perf_meta.get("분류 출처", {}).items():
                st.markdown(f"- **{k_}**: {v_}")
            if not perf_media.empty:
                st.markdown("전체 기간 매체별 집계")
                st.dataframe(perf_media, hide_index=True, height=320)


# ── 🗓 월간 보고서 ──────────────────────────────────────────────
with tab_report:
    if not reports:
        st.info("월간 보고서가 아직 없습니다. 매주 월요일 자동 갱신 때 2026년 10월분부터 만들어집니다.")
    else:
        section("MONTHLY", "월간 홍보 보고서", "통계 · Good · Bad · 시사점 · 개선점 — 숫자에서 규칙으로 뽑은 자동 작성본입니다. 대외 사용 전 담당자 검토.")
        items = sorted(reports, key=lambda r: r["month"], reverse=True)
        labels = {f"{r['month'][:4]}년 {int(r['month'][5:])}월" + (" · 진행 중" if r["in_progress"] else ""): r for r in items}
        choice = st.selectbox("보고서 월", list(labels), index=0)
        rep = labels[choice]
        path = REPORT_DIR / rep["file"]
        if not path.exists():
            st.error("보고서 파일을 찾지 못했습니다. 다음 자동 갱신 때 다시 만들어집니다.")
        else:
            body = path.read_text(encoding="utf-8-sig")
            raw(f"""<div class='verdict'>
<div><b style='color:{GOOD}'>{rep['good']}</b><span>Good</span></div>
<div><b style='color:{BAD}'>{rep['bad']}</b><span>Bad</span></div>
<div><b>{esc(rep['basis'])}</b><span>데이터 기준일</span></div>
<div><b>{'진행 중' if rep['in_progress'] else '마감'}</b><span>상태</span></div></div>""")
            st.download_button("⬇ HTML 보고서 내려받기", data=path.read_bytes(), file_name=rep["file"], mime="text/html",
                               width="content", type="primary")
            components.html(body, height=2350, scrolling=True)


# ── 🔍 통합검색 ─────────────────────────────────────────────────
with tab_search:
    search_q = st.text_input("🔍 키워드 검색 (제목·주요내용)", placeholder="예: 미세먼지, 전고체, 로봇, 탄소중립", key="tab_search_q")
    csel, ssel = st.columns([4, 1.2])
    with csel:
        sel_channels = st.multiselect("채널 선택", CHANNELS, default=CHANNELS, placeholder="검색할 채널")
    with ssel:
        sort_opt = st.selectbox("정렬", ["최신순", "오래된순", "조회수순", "채널 → 최신순"])
    sub = apply_filters(df, channels=sel_channels, extra_query=search_q)
    if sort_opt == "최신순":
        sub = sub.sort_values("게시일", ascending=False, na_position="last")
    elif sort_opt == "오래된순":
        sub = sub.sort_values("게시일", ascending=True, na_position="last")
    elif sort_opt == "조회수순":
        sub = sub.sort_values("조회수_n", ascending=False, na_position="last")
    else:
        sub = sub.sort_values(["채널", "게시일"], ascending=[True, False], na_position="last")
    st.markdown(f"**검색 결과: {len(sub):,}건**")
    if sub.empty:
        st.info("조건에 맞는 항목이 없습니다. 검색어를 줄이거나 채널을 더 골라 보세요.")
    elif len(sub) > 200:
        st.caption("결과가 200건을 넘어 표로 표시합니다.")
        disp = sub[["채널", "게시일", "제목", "조회수_n", "주요내용", "링크"]].rename(columns={"조회수_n": "조회수"})
        disp["게시일"] = disp["게시일"].dt.strftime("%Y-%m-%d")
        st.dataframe(disp, height=600, hide_index=True,
                     column_config={"링크": st.column_config.LinkColumn("링크", display_text="원문 →"),
                                    "조회수": st.column_config.NumberColumn("조회수", format="%d")})
    else:
        for _, row in sub.iterrows():
            render_card(row, show_channel=True)


# ── 채널별 4탭 ──────────────────────────────────────────────────
for tab, channel in zip(channel_tabs, CHANNELS, strict=True):
    with tab:
        sub = apply_filters(df, channels=[channel]).sort_values("게시일", ascending=False, na_position="last")
        st.markdown(f"**{len(sub):,}건**")
        if sub.empty:
            st.warning("조건에 맞는 항목이 없습니다.")
            continue
        page_size = 50
        total_pages = (len(sub) - 1) // page_size + 1
        page = st.number_input(f"페이지 (1 ~ {total_pages})", min_value=1, max_value=total_pages, value=1,
                               key=f"page_{channel}") if total_pages > 1 else 1
        for _, row in sub.iloc[(page - 1) * page_size:page * page_size].iterrows():
            render_card(row, show_channel=False)
