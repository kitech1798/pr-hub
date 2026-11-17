"""한국생산기술연구원 홍보 허브 — 4채널 아카이브 + 언론 보도성과 + 월간 보고서.

실행:
    streamlit run "C:\\Users\\admin\\Desktop\\교육\\기관-홍보-허브\\app\\streamlit_app.py"

탭(4개):
    개요       — 채널별 발행·반응(조회수·댓글) 통계
    보도성과   — 보도자료별 보도 매체·기사 수, 분야·R&R별 경향(보도자료 성과분석이 주 1회 내보냄)
    월간 보고  — 2026년 10월분부터. 통계·Good·Bad·시사점·개선점, HTML 내려받기
    아카이브   — 4채널 통합 검색·열람(채널은 알약 필터)

모양(토큰·CSS·HTML 부품)은 ui.py, 이 파일은 데이터와 화면 구성만 맡는다.
데이터는 매주 월요일 scripts/weekly_update.ps1 이 갱신한다.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui  # noqa: E402  (같은 폴더 모듈 — 위 sys.path 줄이 먼저 와야 한다)
from ui import CHANNEL_COLORS, DATA, GOOD, INK, INK_2, MUTED, NEG, esc  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
REPORT_DIR = ROOT / "reports"
DATA_PATH = DATA_DIR / "허브-데이터셋.csv"
PERF_PATH = DATA_DIR / "보도성과.csv"
PERF_MEDIA_PATH = DATA_DIR / "보도성과_매체.csv"
PERF_META_PATH = DATA_DIR / "보도성과_meta.json"
ICON_PATH = Path(__file__).resolve().parent / "favicon.png"
CHANNELS = ["보도자료", "포토뉴스", "유튜브", "블로그"]

POS = DATA  # 평균 이상
DIM_AXES = {
    "보도유형": "보도유형", "연구분야": "연구분야", "국가전략기술": "전략기술",
    "제조혁신 로드맵": "제조혁신 로드맵", "지역혁신 로드맵": "지역혁신 로드맵", "R&R 연계": "R&R 연계", "가시성": "가시성",
}
PENDING = "분류 대기"
SMALL_N = 5  # 표본이 이보다 적은 항목은 흐리게 — 평균이 한두 건에 휘둘린다
PAGE_SIZE = 50
PLOT_CONFIG = {"displayModeBar": False}

STOPWORDS = {
    "생기원", "한국생산기술연구원", "kitech", "기술", "개발", "연구원", "연구",
    "위해", "통해", "관련", "대한", "이번", "지난", "최근", "원장", "통한",
    "위한", "대해", "함께", "기반", "이를", "있는", "있다", "있어", "있도록",
    "또한", "이상", "이하", "올해", "내년", "지난해",
    # 영문 영상 제목의 기능어
    "the", "and", "for", "with", "what", "how", "from", "this", "that", "are", "you", "your", "its", "into", "who", "why",
}

st.set_page_config(page_title=ui.ORG_NAME, page_icon=str(ICON_PATH) if ICON_PATH.exists() else "📰",
                   layout="wide", initial_sidebar_state="collapsed")
st.markdown(ui.css(), unsafe_allow_html=True)


def raw(markup: str) -> None:
    """사용자 HTML/CSS. st.html은 내용을 격리해 렌더링해서 전역 CSS가 앱에 닿지 않는다(1.57 실측) — markdown으로 넣는다."""
    st.markdown(markup, unsafe_allow_html=True)


# 인트로는 세션당 1회 — 위젯을 만질 때마다 다시 뜨지 않게. (새로고침하면 새 세션이라 다시 뜬다)
# 요소 자리는 항상 하나 — Streamlit 은 요소를 '위치'로 식별한다. 첫 실행에만 요소가 있고 다음 실행엔 없으면
# 뒤따르는 st.tabs 가 새 위젯으로 취급돼 어떤 탭에서 무엇을 눌러도 첫 탭('개요')으로 튕긴다(실측).
SHOW_INTRO = not st.session_state.get("kt_intro_done", False)
raw(ui.intro_html() if SHOW_INTRO else "")
st.session_state["kt_intro_done"] = True
with st.container(key="kt_js"):  # 보조 스크립트(빛 따라가기·카운트업·건너뛰기) — 화면에는 안 보인다
    components.html(ui.ENHANCE_JS, height=0)


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


def fmt_n(v: float) -> str:
    if v >= 10_000:
        return f"{v / 10_000:.1f}만".replace(".0만", "만")
    return f"{v:,.0f}"


def style_fig(fig, height: int = 320):
    """차트 공통 — 격자는 거의 보이지 않게, 범례는 위쪽 한 줄, 글자는 본문 톤."""
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=INK_2, family="Pretendard, sans-serif", size=13), height=height,
        margin=dict(t=14, b=10, l=10, r=10),
        legend=dict(bgcolor="rgba(0,0,0,0)", orientation="h", y=1.12, x=0, title_text=""),
        hoverlabel=dict(bgcolor="#0F172A", bordercolor="rgba(148,163,184,0.35)", font=dict(color=INK)),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor="rgba(148,163,184,0.18)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.07)", zeroline=False)
    return fig


def chart(fig) -> None:
    st.plotly_chart(fig, config=PLOT_CONFIG)


df = load_data()
perf, perf_media, perf_meta = load_perf()
PERF_BY_ID = perf.set_index("id").to_dict("index") if not perf.empty else {}
reports = load_report_index()
now = pd.Timestamp.now()
perf_basis = perf_meta.get("기준일", "-")


# ── 히어로 ───────────────────────────────────────────────────────
dated = df["게시일"].dropna() if not df.empty else pd.Series(dtype="datetime64[ns]")
raw(ui.hero_html(
    total=len(df),
    y0=int(dated.min().year) if len(dated) else None, y1=int(dated.max().year) if len(dated) else None,
    counts={ch: int((df["채널"] == ch).sum()) for ch in CHANNELS},
    basis=perf_basis, intro=SHOW_INTRO,
))


# ── 전역 필터 바(사이드바 대신 — 처음 온 사람이 폼부터 만나지 않게) ───────
if not df.empty and not df["게시일"].isna().all():
    min_d, max_d = df["게시일"].min().date(), df["게시일"].max().date()
else:
    min_d = max_d = None


def reset_filters() -> None:
    st.session_state["q"] = ""
    if min_d:
        st.session_state["range"] = (min_d, max_d)


raw("<div style='height:20px'></div>")
fb_q, fb_d, fb_b = st.columns([5, 3, 1.3], vertical_alignment="bottom")
with fb_q:
    query = st.text_input("검색", key="q", placeholder="예: 전고체, AI, 패키징",
                          help="개요·보도성과·아카이브에 공통으로 적용됩니다.")
with fb_d:
    date_range = (st.date_input("기간", value=(min_d, max_d), min_value=min_d, max_value=max_d, key="range")
                  if min_d else None)
with fb_b:
    if st.button("새로고침", width="stretch", help="데이터 캐시를 비우고 다시 읽습니다."):
        st.cache_data.clear()
        st.rerun()


def apply_filters(src: pd.DataFrame, channels: list[str] | None = None) -> pd.DataFrame:
    out = src
    if channels:
        out = out[out["채널"].isin(channels)]
    if query:
        out = out[out["제목"].str.contains(query, case=False, regex=False) | out["주요내용"].str.contains(query, case=False, regex=False)]
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


def empty_with_reset(message: str, hint: str, key: str) -> None:
    """빈 결과 — 이유 한 줄 + 다음 행동 버튼."""
    raw(ui.empty_state(message, hint))
    st.button("필터 초기화", on_click=reset_filters, key=key)


# ── 탭 ───────────────────────────────────────────────────────────
raw("<div style='height:8px'></div>")
tab_dash, tab_perf, tab_report, tab_archive = st.tabs(["개요", "보도성과", "월간 보고", "아카이브"])

# ── 개요 ────────────────────────────────────────────────────────
with tab_dash:
    fdf = apply_filters(df)
    if fdf.empty:
        empty_with_reset("조건에 맞는 콘텐츠가 없습니다", "검색어를 줄이거나 기간을 넓혀 보세요.", "reset_dash")
    else:
        # 1) 지금 — 지표 카드 4장(히어로가 이미 보여 주는 '전체 건수'는 되풀이하지 않는다)
        months_idx = pd.period_range(end=now.to_period("M"), periods=12)
        mcount = fdf.dropna(subset=["연월"]).groupby("연월").size()
        series = [int(mcount.get(str(p), 0)) for p in months_idx]
        pf0 = filter_perf(perf) if not perf.empty else perf
        yt_views = fdf.loc[fdf["채널"] == "유튜브", "조회수_n"].sum()
        home_pr = fdf.loc[fdf["채널"] == "보도자료", "조회수_n"].sum()
        home_ph = fdf.loc[fdf["채널"] == "포토뉴스", "조회수_n"].sum()
        cards = [
            ui.kpi(f"{now.month}월 발행", f"{series[-1]:,}", "건", ui.delta_text(series[-1], series[-2])),
            ui.kpi("최근 12개월 발행", f"{sum(series):,}", "건", f"월 평균 {sum(series) / 12:.1f}건", spark=series),
            ui.kpi("보도 기사", f"{int(pf0['기사 수'].sum()):,}" if not pf0.empty else "-", "건",
                   f"보도자료 {len(pf0):,}건 대상 · 2020~" if not pf0.empty else "보도성과 데이터 대기"),
            ui.kpi("누적 조회", fmt_n(home_pr + home_ph + yt_views), "회", "홈페이지 + 유튜브 · 누적값"),
        ]
        raw(ui.section("지금", f"{now.month}월에 {series[-1]:,}건을 발행했습니다", "필터가 걸려 있으면 그 범위의 수치입니다.") + ui.grid(cards))

        # 2) 반응 — 제목이 결론을 말한다(가장 큰 채널을 데이터에서 계산)
        views = {"홈페이지 보도자료": home_pr, "홈페이지 포토뉴스": home_ph, "유튜브": yt_views}
        total_views = sum(views.values())
        top_name = max(views, key=views.get)
        title = (f"누적 조회는 {top_name}에서 가장 많이 나옵니다 ({views[top_name] / total_views:.0%})"
                 if total_views else "콘텐츠 반응")
        raw(ui.section("반응", title, "공개된 지표만 모았습니다 — 홈페이지 게시판·유튜브는 누적 조회수, 네이버 블로그는 조회수가 비공개라 댓글 수."))
        share = lambda v: f"전체 조회의 {v / total_views:.0%}" if total_views else ""  # noqa: E731
        raw(ui.grid([
            ui.kpi("홈페이지 조회 · 보도자료", fmt_n(home_pr), "회", share(home_pr)),
            ui.kpi("홈페이지 조회 · 포토뉴스", fmt_n(home_ph), "회", share(home_ph)),
            ui.kpi("유튜브 조회", fmt_n(yt_views), "회", share(yt_views)),
            ui.kpi("블로그 댓글", f"{int(fdf.loc[fdf['채널'] == '블로그', '댓글수_n'].sum()):,}", "개", "조회수 비공개 — 댓글 수 기준"),
        ]))
        cut = now - pd.Timedelta(days=90)
        panels = []
        for ch in ("보도자료", "포토뉴스", "유튜브"):
            recent_ch = fdf[(fdf["채널"] == ch) & (fdf["게시일"] >= cut)]
            sub = recent_ch[recent_ch["조회수_n"].notna()].nlargest(5, "조회수_n")
            # 빈 이유를 구분한다 — 게시물이 없는 것과 조회수를 아직 못 읽은 것은 다르다
            empty_msg = ("최근 90일 게시물이 없습니다." if recent_ch.empty
                         else f"최근 90일 게시물 {len(recent_ch)}건 — 조회수는 다음 자동 갱신 때 채워집니다.")
            panels.append(ui.rank_panel(f"{ch} · 최근 90일 조회 상위",
                                        [(r["링크"], r["제목"], f"{fmt_n(r['조회수_n'])}회") for _, r in sub.iterrows()], empty_msg))
        raw(ui.grid(panels, cols3=True))
        basis = fdf["지표기준일"].replace("", pd.NA).dropna().max() if "지표기준일" in fdf else None
        if basis:
            st.caption(f"조회수 기준일 {basis} · 누적값이라 오래된 글일수록 큽니다(같은 기간 글끼리 비교).")

        # 3) 발행 흐름
        yearly = fdf.dropna(subset=["연"]).groupby(["연", "채널"]).size().reset_index(name="건수")
        yearly["연"] = yearly["연"].astype(int).astype(str)
        ytot = yearly.groupby("연")["건수"].sum()
        peak_y = ytot.idxmax()
        raw(ui.section("발행 흐름", f"{peak_y}년에 가장 많이 발행했습니다 — {int(ytot.max()):,}건", "채널 구성과 연도·월별 흐름입니다."))
        with st.container(border=True):
            raw(ui.chart_title("채널 구성", f"{len(fdf):,}건") + ui.share_bar({ch: int((fdf["채널"] == ch).sum()) for ch in CHANNELS}))
        c1, c2 = st.columns([3, 2])
        with c1, st.container(border=True):
            raw(ui.chart_title("연도별 발행량", "막대 위 숫자는 최다 연도"))
            # 문자열 축은 '처음 나온 순서'로 그려진다(실측: 2015→2026→2003) — 연도 순서를 못 박는다
            fig = px.bar(yearly, x="연", y="건수", color="채널", color_discrete_map=CHANNEL_COLORS,
                         category_orders={"채널": CHANNELS, "연": sorted(yearly["연"].unique())})
            # 최다 연도 표시 — 범주 축에 주석(x=문자열)을 걸면 축 범위가 깨져(실측: 막대 소실) 보이지 않는 텍스트 트레이스로 단다
            fig.add_scatter(x=[peak_y], y=[int(ytot.max())], mode="text", text=[f"<b>{int(ytot.max()):,}건</b>"],
                            textposition="top center", textfont=dict(color=INK, size=13), showlegend=False, hoverinfo="skip")
            fig.update_xaxes(type="category", tickangle=0, dtick=2)
            chart(style_fig(fig, 340).update_layout(xaxis_title=None, yaxis_title=None, bargap=0.28))
        with c2, st.container(border=True):
            raw(ui.chart_title("월별 히트맵", "연 × 월 발행 건수"))
            heat = fdf.dropna(subset=["연", "월"]).groupby(["연", "월"]).size().reset_index(name="건수")
            if not heat.empty:
                pivot = heat.astype({"연": int, "월": int}).pivot(index="연", columns="월", values="건수").fillna(0).sort_index(ascending=False)
                fig = px.imshow(pivot, aspect="auto", labels=dict(x="월", y="", color="건수"),
                                color_continuous_scale=[[0, "#0C1220"], [0.4, "#0E7490"], [0.7, DATA], [1, "#A5F3FC"]])
                fig.update_traces(xgap=3, ygap=3)
                chart(style_fig(fig, 340).update_xaxes(dtick=1).update_layout(coloraxis_showscale=False))
        with st.container(border=True):
            raw(ui.chart_title("최근 12개월 추이", "선 끝 이름 = 채널"))
            # 12개월을 빈 달 0으로 채운다 — 채널마다 빠진 달이 있으면 범주 순서가 뒤섞여 선이 꼬인다(실측)
            month_keys = [str(m) for m in months_idx]
            grid = pd.MultiIndex.from_product([month_keys, CHANNELS], names=["연월", "채널"])
            trend = (fdf.groupby(["연월", "채널"]).size().reindex(grid, fill_value=0).rename("건수").reset_index())
            fig = px.line(trend, x="연월", y="건수", color="채널", color_discrete_map=CHANNEL_COLORS,
                          category_orders={"채널": CHANNELS, "연월": month_keys}, line_shape="linear")  # 건수에 spline 은 0 아래로 꺼져 거짓 곡선이 된다
            fig.update_xaxes(type="category")
            # 선 끝 이름 — 같은 값끼리 겹치지 않게 아래에서 위로 15px 간격을 보장
            ends = sorted(((float(tr.y[-1]), tr) for tr in fig.data), key=lambda t: t[0])
            px_per = 220 / (max(e[0] for e in ends) or 1)
            prev = None
            for yv, tr in ends:
                pos = yv * px_per
                if prev is not None and pos - prev < 15:
                    pos = prev + 15
                prev = pos
                fig.add_annotation(x=tr.x[-1], y=yv, text=tr.name, showarrow=False, xanchor="left", xshift=8,
                                   yshift=pos - yv * px_per, font=dict(color=tr.line.color, size=12))
            style_fig(fig, 300).update_traces(line=dict(width=2.2)).update_layout(
                xaxis_title=None, yaxis_title=None, showlegend=False, margin=dict(t=14, b=10, l=10, r=80))
            chart(fig)

        # 4) 키워드
        tokens = [t for title_ in fdf["제목"] for t in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", title_)
                  if t.lower() not in STOPWORDS and t not in STOPWORDS]
        if top := Counter(tokens).most_common(20):
            raw(ui.section("키워드", f"제목에 가장 자주 쓰인 말은 ‘{top[0][0]}’입니다", "기관명·일반 연결어는 뺀 제목 단어 빈도 상위 20개."))
            raw(ui.word_ranking(top))


# ── 보도성과 ────────────────────────────────────────────────────
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
        raw(ui.empty_state("보도성과 데이터가 아직 없습니다", "매주 월요일 자동 갱신 뒤에 표시됩니다."))
    else:
        pf = filter_perf(perf)
        if pf.empty:
            empty_with_reset("조건에 맞는 보도자료가 없습니다", "검색어를 줄이거나 기간을 넓혀 보세요.", "reset_perf")
        else:
            settled = pf[pf["집계 상태"] == "확정"]
            med = settled["매체 수"].median() if not settled.empty else None
            raw(ui.section(
                "보도성과", f"보도자료 1건은 중앙값 {med:.0f}곳의 매체에 보도됩니다" if med is not None else "보도자료 성과",
                f"기준일 {perf_basis} · 보도자료 {len(perf):,}건 중 필터 결과 {len(pf):,}건 · 네이버 뉴스에서 몇 개 매체에 실렸는지 자동 대조한 결과"))
            pend = int(pf["검토대기 기사"].sum())
            raw(ui.grid([
                ui.kpi("보도자료 1건당 보도 매체 (중앙값)", f"{med:.0f}" if med is not None else "-", "곳",
                       f"집계가 끝난(배포 60일 경과) {len(settled):,}건 기준 · 확인 대기 기사 {pend:,}건은 빠진 하한값입니다",
                       hint="자동 대조 점수가 애매해 사람이 확인해야 하는 기사는 확인 전에는 숫자에 넣지 않습니다.", feature=True),
                ui.kpi("보도 기사", f"{int(pf['기사 수'].sum()):,}", "건"),
                ui.kpi("보도자료", f"{len(pf):,}", "건"),
            ]))

            c1, c2 = st.columns([3, 2])
            with c1, st.container(border=True):
                raw(ui.chart_title("연도별 보도 매체 수", "집계가 끝난 보도자료의 중앙값"))
                yr = settled.dropna(subset=["배포일"]).assign(연=lambda d: d["배포일"].dt.year.astype(str))
                if not yr.empty:
                    by_year = yr.groupby("연")["매체 수"].median().reset_index()
                    fig = px.bar(by_year, x="연", y="매체 수", text="매체 수", color_discrete_sequence=[DATA])
                    fig.update_traces(texttemplate="%{text:.0f}곳", textposition="outside", cliponaxis=False,
                                      marker=dict(line=dict(width=0)))
                    chart(style_fig(fig, 320).update_layout(xaxis_title=None, yaxis_title=None, bargap=0.4).update_yaxes(visible=False))
            with c2, st.container(border=True):
                raw(ui.chart_title("자주 보도한 매체 Top 15"))
                names = [n for cell in pf["매체명"] for n in cell.split(", ") if n]
                if top := Counter(names).most_common(15):
                    tdf = pd.DataFrame(top, columns=["매체", "보도한 보도자료 수"]).iloc[::-1]
                    fig = px.bar(tdf, x="보도한 보도자료 수", y="매체", orientation="h", text="보도한 보도자료 수",
                                 color_discrete_sequence=[DATA])
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    chart(style_fig(fig, 320 + 8 * len(top)).update_layout(xaxis_title=None, yaxis_title=None).update_xaxes(visible=False))

            # ── 분야·R&R별 경향
            sec_title, sec_desc = "어떤 보도자료가 많이 실렸나", ("분류별 평균 보도 매체 수 — 집계가 끝난 보도자료 기준, 위 필터 반영. "
                                                          "함께 나타난 경향이며 원인을 뜻하지는 않습니다.")
            if "R&R 연계" in pf:
                rr = settled[settled["R&R 연계"] != PENDING]
                direct = rr[rr["R&R 연계"] == "직접 연계"]
                notech = rr[rr["R&R 연계"] == "기술 보도 아님"]
                if len(rr):
                    sec_title = f"집계된 보도자료의 {len(direct) / len(rr):.0%}가 우리원 R&R과 직접 연계됩니다"
                raw(ui.section("분야 · R&R", sec_title, sec_desc))
                raw(ui.grid([
                    # 비율을 증감 화살표로 쓰면 '늘었다'로 읽힌다 — 값 안에 둔다
                    ui.kpi(f"R&R 직접 연계 보도 ({len(direct)}/{len(rr)}건)", f"{len(direct) / len(rr):.0%}" if len(rr) else "-",
                           hint="우리원 R&R을 「미래비전 2035」 제조혁신·지역혁신 로드맵 요소기술로 보고, 근접도 높음·중간으로 대응한 보도."),
                    ui.kpi("직접 연계 보도 평균 매체", f"{direct['매체 수'].mean():.1f}" if len(direct) else "-", "곳"),
                    ui.kpi("기술 보도 아님(인사·행사) 평균", f"{notech['매체 수'].mean():.1f}" if len(notech) else "-", "곳"),
                ], cols3=True))

                axis_label = st.segmented_control("분류 기준", list(DIM_AXES), default="연구분야", key="dim_axis")
                col = DIM_AXES.get(axis_label or "연구분야", "연구분야")
                stats = dim_stats(pf, col)
                with st.container(border=True):
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
                                           text=f"전체 평균 {overall:.1f}곳", font=dict(color=INK, size=12))
                        style_fig(fig, 150 + 34 * len(stats)).update_layout(xaxis_title=None, yaxis_title=None,
                                                                            margin=dict(t=32, b=10, l=10, r=110)).update_xaxes(visible=False)
                        chart(fig)
                        src = perf_meta.get("분류 출처", {}).get(col, "")
                        st.caption(f"분류 방법: {src} · 흐린 막대 = 표본 {SMALL_N}건 미만")

                with st.container(border=True):
                    raw(ui.chart_title("많이 기사화된 연구분야", "면적 = 기사 수 합계, 색 = 보도자료당 평균 매체 수. 인사·행사 등 기술 내용이 없는 보도는 뺐습니다."))
                    tm = pf[~pf["연구분야"].isin([PENDING, "해당 없음"])].groupby("연구분야").agg(
                        기사=("기사 수", "sum"), 보도자료=("id", "count"), 평균매체=("매체 수", "mean")).reset_index()
                    if not tm.empty:
                        fig = px.treemap(tm, path=["연구분야"], values="기사", color="평균매체",
                                         color_continuous_scale=[[0, "#16233B"], [0.5, "#0E7490"], [1, DATA]],
                                         custom_data=["보도자료", "평균매체"])
                        fig.update_traces(texttemplate="<b>%{label}</b><br>기사 %{value}건", marker=dict(cornerradius=8),
                                          hovertemplate="%{label}<br>기사 %{value}건 · 보도자료 %{customdata[0]}건"
                                                        "<br>평균 매체 %{customdata[1]:.1f}곳<extra></extra>")
                        chart(style_fig(fig, 360).update_layout(coloraxis_colorbar=dict(title="평균 매체")))
            else:
                raw(ui.section("분야 · R&R", sec_title, sec_desc))

            raw(ui.section("보도자료별", "보도자료별 성과"))
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


# ── 월간 보고 ───────────────────────────────────────────────────
with tab_report:
    if not reports:
        raw(ui.empty_state("월간 보고서가 아직 없습니다", "매주 월요일 자동 갱신 때 2026년 10월분부터 만들어집니다."))
    else:
        raw(ui.section("월간 보고", "월간 홍보 보고서", "통계 · Good · Bad · 시사점 · 개선점 — 숫자에서 규칙으로 뽑은 자동 작성본입니다. 대외 사용 전 담당자 검토."))
        items = sorted(reports, key=lambda r: r["month"], reverse=True)
        labels = {f"{r['month'][:4]}년 {int(r['month'][5:])}월" + (" · 진행 중" if r["in_progress"] else ""): r for r in items}
        choice = st.selectbox("보고서 월", list(labels), index=0)
        rep = labels[choice]
        path = REPORT_DIR / rep["file"]
        if not path.exists():
            raw(ui.empty_state("보고서 파일을 찾지 못했습니다", "다음 자동 갱신 때 다시 만들어집니다."))
        else:
            body = path.read_text(encoding="utf-8-sig")
            raw(ui.grid([
                ui.kpi("Good", str(rep["good"]), "건"), ui.kpi("Bad", str(rep["bad"]), "건"),
                ui.kpi("데이터 기준일", str(rep["basis"])), ui.kpi("상태", "진행 중" if rep["in_progress"] else "마감"),
            ]))
            st.download_button("HTML 보고서 내려받기", data=path.read_bytes(), file_name=rep["file"], mime="text/html",
                               width="content", type="primary")
            with st.container(key="report_sheet"):
                components.html(body, height=2350, scrolling=True)


# ── 아카이브 ────────────────────────────────────────────────────
def _more() -> None:
    st.session_state["arch_n"] = st.session_state.get("arch_n", PAGE_SIZE) + PAGE_SIZE


with tab_archive:
    raw(ui.section("아카이브", "발행한 모든 콘텐츠", "위 검색·기간 필터가 그대로 적용됩니다. 제목을 누르면 원문이 새 창으로 열립니다."))
    a1, a2 = st.columns([5, 2], vertical_alignment="bottom")
    with a1:
        picked = st.pills("채널", CHANNELS, selection_mode="multi", default=CHANNELS, key="arch_ch")
    with a2:
        sort_opt = st.selectbox("정렬", ["최신순", "오래된순", "조회수순", "채널 → 최신순"], key="arch_sort")
    channels = list(picked) or CHANNELS  # 아무것도 안 고르면 전체 — 빈 화면을 만들지 않는다
    sub = apply_filters(df, channels=channels)
    if sort_opt == "최신순":
        sub = sub.sort_values("게시일", ascending=False, na_position="last")
    elif sort_opt == "오래된순":
        sub = sub.sort_values("게시일", ascending=True, na_position="last")
    elif sort_opt == "조회수순":
        sub = sub.sort_values("조회수_n", ascending=False, na_position="last")
    else:
        sub = sub.sort_values(["채널", "게시일"], ascending=[True, False], na_position="last")

    if sub.empty:
        empty_with_reset("조건에 맞는 항목이 없습니다", "검색어를 줄이거나 채널·기간을 넓혀 보세요.", "reset_arch")
    else:
        per = sub["채널"].value_counts()
        st.caption(f"{len(sub):,}건 · " + " · ".join(f"{ch} {int(per.get(ch, 0)):,}" for ch in CHANNELS if per.get(ch, 0)))
        sig = (tuple(channels), sort_opt, query, str(date_range))
        if st.session_state.get("arch_sig") != sig:  # 조건이 바뀌면 처음부터
            st.session_state["arch_sig"] = sig
            st.session_state["arch_n"] = PAGE_SIZE
        n = st.session_state.get("arch_n", PAGE_SIZE)
        view = sub.iloc[:n]
        tiles = len(channels) == 1 and channels[0] in ("포토뉴스", "유튜브")
        parts = []
        for _, row in view.iterrows():
            d = row["게시일"]
            date_str = d.strftime("%Y.%m.%d") if pd.notna(d) else "-"
            thumb = (row.get("썸네일URL") or "") if row["채널"] != "보도자료" else ""
            if tiles:
                parts.append(ui.tile_html(date=date_str, title=row["제목"], link=row.get("링크") or "", thumb=thumb, chips_html=chips(row)))
            else:
                parts.append(ui.row_html(date=date_str, title=row["제목"], link=row.get("링크") or "", summary=row.get("주요내용") or "",
                                         chips_html=chips(row), channel=row["채널"] if len(channels) > 1 else None, thumb=thumb))
        raw(f"<div class='{'kt-tiles' if tiles else 'kt-list'}'>{''.join(parts)}</div>")
        if n < len(sub):
            st.button(f"더 보기 ({len(sub) - n:,}건 남음)", on_click=_more, key="arch_more")


# ── 푸터 · 보조 스크립트 ─────────────────────────────────────────
latest = {ch: f"{d:%Y-%m-%d}" for ch in CHANNELS if not df.empty and pd.notna(d := df.loc[df["채널"] == ch, "게시일"].max())}
raw(ui.footer_html(latest, perf_basis))
