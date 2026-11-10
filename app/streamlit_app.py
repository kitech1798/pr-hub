"""KITECH 홍보 허브 — 대시보드 + 통합검색 + 채널별 리스트.

실행:
    streamlit run "C:\\Users\\admin\\Desktop\\교육\\기관-홍보-허브\\app\\streamlit_app.py"

탭 구성:
    📊 대시보드  — 채널별·연도별·월별 통계와 차트
    📈 보도성과  — 보도자료별 보도 매체·기사 수(보도자료 성과분석이 주 1회 내보냄)
    🔍 통합검색 — 4채널 동시 검색·필터·정렬
    채널별 4탭   — 보도자료 / 포토뉴스 / 유튜브 / 블로그 리스트
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DATA_PATH = DATA_DIR / "허브-데이터셋.csv"
# 보도자료 성과분석(별도 프로젝트)이 주 1회 내보내는 집계 — scripts/hub_guard.py import-perf 가 검사 후 복사
PERF_PATH = DATA_DIR / "보도성과.csv"
PERF_MEDIA_PATH = DATA_DIR / "보도성과_매체.csv"
PERF_META_PATH = DATA_DIR / "보도성과_meta.json"
CHANNELS = ["보도자료", "포토뉴스", "유튜브", "블로그"]

# 미드나잇 + 시안 팔레트
BG = "#0B1220"
SURFACE = "#111A2E"
CARD = "#16213A"
BORDER = "#1F2A44"
TEXT = "#E6EDF7"
MUTED = "#94A3B8"
ACCENT = "#22D3EE"     # 시안 (Primary)
ACCENT2 = "#38BDF8"    # 스카이

CHANNEL_COLORS = {
    "보도자료": "#38BDF8",  # 스카이
    "포토뉴스": "#22D3EE",  # 시안
    "유튜브":   "#F472B6",  # 핑크 (구분 + 임팩트)
    "블로그":   "#4ADE80",  # 라임그린
}
PLOTLY_TEMPLATE = "plotly_dark"

# 한국어 키워드 추출에서 제외할 흔한 토큰
STOPWORDS = {
    "생기원", "한국생산기술연구원", "kitech", "기술", "개발", "연구원", "연구",
    "위해", "통해", "관련", "대한", "이번", "지난", "최근", "원장", "통한",
    "위한", "대해", "함께", "기반", "이를", "있는", "있다", "있어", "있도록",
    "또한", "이상", "이하", "올해", "내년", "지난해",
}

st.set_page_config(page_title="KITECH 홍보 허브", page_icon="📰", layout="wide")

# ── Custom CSS — 미드나잇 + 시안 톤 ─────────────────────────
st.markdown(
    f"""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');

    /* 글꼴 */
    .stApp, .stApp * {{
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont,
                     system-ui, 'Segoe UI', 'Malgun Gothic', sans-serif !important;
    }}
    /* 글로벌 배경 */
    .stApp {{
        background:
            radial-gradient(1200px 600px at 10% -10%, rgba(34,211,238,0.06), transparent 60%),
            radial-gradient(900px 500px at 100% 0%, rgba(56,189,248,0.05), transparent 60%),
            {BG};
    }}
    /* 메인 타이틀 — 시안 그라데이션 */
    h1 {{
        background: linear-gradient(90deg, {ACCENT2} 0%, {ACCENT} 60%, #A5F3FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 700;
        letter-spacing: -0.5px;
    }}
    /* 캡션·보조 텍스트 톤 */
    .stCaption, .st-emotion-cache-10trblm {{ color: {MUTED}; }}
    /* 컨테이너(카드) */
    div[data-testid="stVerticalBlockBorderWrapper"] {{
        background: {CARD} !important;
        border: 1px solid {BORDER} !important;
        border-radius: 12px !important;
        transition: all .18s ease;
    }}
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {{
        border-color: {ACCENT} !important;
        box-shadow: 0 0 0 1px rgba(34,211,238,0.25), 0 8px 24px rgba(34,211,238,0.08);
    }}
    /* 메트릭 카드 */
    div[data-testid="stMetric"] {{
        background: {SURFACE};
        padding: 14px 18px;
        border-radius: 12px;
        border: 1px solid {BORDER};
    }}
    div[data-testid="stMetricLabel"] {{ color: {MUTED} !important; font-size: 0.85rem; }}
    div[data-testid="stMetricValue"] {{
        color: {ACCENT} !important;
        font-weight: 700;
        font-variant-numeric: tabular-nums;
    }}
    /* 탭 */
    div[data-baseweb="tab-list"] {{
        gap: 4px;
        border-bottom: 1px solid {BORDER};
    }}
    button[data-baseweb="tab"] {{
        background: transparent !important;
        color: {MUTED} !important;
        border-radius: 10px 10px 0 0 !important;
        padding: 8px 16px !important;
    }}
    button[data-baseweb="tab"][aria-selected="true"] {{
        color: {ACCENT} !important;
        background: rgba(34,211,238,0.08) !important;
        border-bottom: 2px solid {ACCENT} !important;
    }}
    /* 사이드바 입력 강조 */
    section[data-testid="stSidebar"] {{
        background: {SURFACE};
        border-right: 1px solid {BORDER};
    }}
    /* 링크 */
    a, a:visited {{ color: {ACCENT2}; text-decoration: none; }}
    a:hover {{ color: {ACCENT}; text-decoration: underline; }}
    /* 카드 안 #### 헤딩 (각 항목 제목) */
    div[data-testid="stVerticalBlockBorderWrapper"] h4 {{
        color: {TEXT};
        font-weight: 600;
        letter-spacing: -0.2px;
        margin: 0.2rem 0 0.4rem 0;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


# ── 데이터 로드 ──────────────────────────────────────────────
@st.cache_data(ttl=30)
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame(columns=["채널", "게시일", "제목", "주요내용", "링크", "썸네일URL"])
    df = pd.read_csv(DATA_PATH, encoding="utf-8-sig")
    df["게시일"] = pd.to_datetime(df["게시일"], errors="coerce")
    df["연"] = df["게시일"].dt.year
    df["월"] = df["게시일"].dt.month
    df["연월"] = df["게시일"].dt.to_period("M").astype(str)
    # 문자열 컬럼은 NaN을 빈 문자열로 정규화 (st.image 등에 NaN 전달 방지)
    for c in ["채널", "제목", "주요내용", "링크", "썸네일URL", "id", "분야태그", "비고"]:
        if c in df.columns:
            df[c] = df[c].fillna("").astype(str)
    return df


@st.cache_data(ttl=30)
def load_perf() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """(보도자료별, 매체별, meta). 파일이 없으면 빈 값 — 탭이 안내 화면을 띄운다."""
    if not PERF_PATH.exists():
        return pd.DataFrame(), pd.DataFrame(), {}
    perf = pd.read_csv(PERF_PATH, encoding="utf-8-sig", dtype={"id": str})
    perf["배포일"] = pd.to_datetime(perf["배포일"], errors="coerce")
    for c in ("매체명", "등급별 매체 수", "집계 상태", "제목", "링크"):
        perf[c] = perf[c].fillna("").astype(str)
    media = pd.read_csv(PERF_MEDIA_PATH, encoding="utf-8-sig") if PERF_MEDIA_PATH.exists() else pd.DataFrame()
    meta = json.loads(PERF_META_PATH.read_text(encoding="utf-8")) if PERF_META_PATH.exists() else {}
    return perf, media, meta


def perf_badge(row_id: str) -> str:
    """보도자료 카드에 붙일 '매체 N곳 · 기사 M건' 칩(성과 데이터가 없으면 빈 문자열)."""
    p = PERF_BY_ID.get(str(row_id))
    if not p:
        return ""
    pending = " · 집계 중" if str(p["집계 상태"]).startswith("집계 중") else ""
    return (
        f"<span style='display:inline-block;padding:2px 10px;border-radius:999px;"
        f"background:rgba(34,211,238,0.10);color:{ACCENT};font-size:0.8rem;font-weight:600;"
        f"font-variant-numeric:tabular-nums;'>보도 매체 {int(p['매체 수'])}곳 · 기사 {int(p['기사 수'])}건{pending}</span>"
    )


def style_fig(fig, height: int = 320):
    """모든 plotly figure 공통 — 다크 + 투명 배경 + 시안 그리드."""
    fig.update_layout(
        template=PLOTLY_TEMPLATE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=TEXT, family="sans-serif"),
        height=height,
        margin=dict(t=10, b=10, l=10, r=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.12)", zerolinecolor="rgba(148,163,184,0.18)")
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.12)", zerolinecolor="rgba(148,163,184,0.18)")
    return fig


df = load_data()
perf, perf_media, perf_meta = load_perf()
PERF_BY_ID = perf.set_index("id").to_dict("index") if not perf.empty else {}

st.title("KITECH 홍보 허브")
st.caption(
    f"보도자료 · 포토뉴스 · 유튜브 · 블로그 통합 보기 — 총 {len(df):,}건"
)

# ── 사이드바: 전역 필터 ───────────────────────────────────────
with st.sidebar:
    st.header("필터")
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    query = st.text_input(
        "🔍 전역 검색어 (모든 탭 공통)",
        placeholder="예: 전고체, AI, 패키징",
        help="모든 탭(대시보드·채널별 리스트)에 적용됩니다. 통합검색 탭에는 별도 검색창이 따로 있습니다.",
    )

    if not df.empty and not df["게시일"].isna().all():
        min_d = df["게시일"].min().date()
        max_d = df["게시일"].max().date()
        date_range = st.date_input(
            "📅 기간",
            value=(min_d, max_d),
            min_value=min_d,
            max_value=max_d,
        )
    else:
        date_range = None

    st.divider()
    # 예전엔 '지금 시각'을 갱신일로 보여줬다 — 데이터가 언제 것인지 알 수 없어 실제 값으로 바꾼다
    latest = {
        ch: df.loc[df["채널"] == ch, "게시일"].max() for ch in CHANNELS
    } if not df.empty else {}
    lines = [f"- {ch}: {d:%Y-%m-%d}" for ch, d in latest.items() if pd.notna(d)]
    st.caption("**채널별 최신 게시물**\n" + "\n".join(lines))
    if perf_meta:
        st.caption(f"**보도성과 기준일** {perf_meta.get('기준일', '-')} (매주 월요일 자동 갱신)")


def apply_filters(
    src: pd.DataFrame,
    channels: list[str] | None = None,
    extra_query: str | None = None,
) -> pd.DataFrame:
    """전역 검색(query) + 선택적 추가 검색(extra_query, AND 결합)."""
    out = src.copy()
    if channels:
        out = out[out["채널"].isin(channels)]
    for q in (query, extra_query):
        if not q:
            continue
        m = (
            out["제목"].fillna("").str.contains(q, case=False, na=False, regex=False)
            | out["주요내용"].fillna("").str.contains(q, case=False, na=False, regex=False)
        )
        out = out[m]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        d = out["게시일"].dt.date
        out = out[(d >= start) & (d <= end)]
    return out


# ── 탭 구성 ───────────────────────────────────────────────────
tab_dash, tab_perf, tab_search, *channel_tabs = st.tabs(
    ["📊 대시보드", "📈 보도성과", "🔍 통합검색"] + [f"{c} ({len(df[df['채널'] == c]):,})" for c in CHANNELS]
)

# ── 📊 대시보드 ───────────────────────────────────────────────
with tab_dash:
    fdf = apply_filters(df)

    if fdf.empty:
        st.warning("필터 조건에 맞는 데이터가 없습니다.")
    else:
        # KPI 5개
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("전체", f"{len(fdf):,}건")
        for kcol, ch in zip([k2, k3, k4, k5], CHANNELS):
            kcol.metric(ch, f"{(fdf['채널'] == ch).sum():,}건")

        st.divider()

        # 1행: 채널별 도넛 + 연도별 stacked bar
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("##### 채널 비중")
            ch_count = fdf["채널"].value_counts().reset_index()
            ch_count.columns = ["채널", "건수"]
            fig = px.pie(
                ch_count, names="채널", values="건수", hole=0.6,
                color="채널", color_discrete_map=CHANNEL_COLORS,
            )
            fig.update_traces(
                textposition="inside", textinfo="percent+label",
                marker=dict(line=dict(color=BG, width=2)),
            )
            style_fig(fig, height=320)
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("##### 연도별 발행량 (채널 누적)")
            yearly = (
                fdf.dropna(subset=["연"])
                .groupby(["연", "채널"]).size().reset_index(name="건수")
                .sort_values("연")
            )
            yearly["연"] = yearly["연"].astype(int).astype(str)
            year_order = sorted(yearly["연"].unique())
            fig = px.bar(
                yearly, x="연", y="건수", color="채널",
                color_discrete_map=CHANNEL_COLORS,
                category_orders={"채널": CHANNELS, "연": year_order},
            )
            style_fig(fig, height=320)
            fig.update_layout(xaxis_title=None, bargap=0.25)
            fig.update_xaxes(categoryorder="category ascending")
            st.plotly_chart(fig, use_container_width=True)

        # 2행: 월별 히트맵 + 최근 12개월 추이
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("##### 월별 히트맵 (연 × 월)")
            heat = (
                fdf.dropna(subset=["연", "월"])
                .groupby(["연", "월"]).size().reset_index(name="건수")
            )
            if not heat.empty:
                heat["연"] = heat["연"].astype(int)
                heat["월"] = heat["월"].astype(int)
                pivot = heat.pivot(index="연", columns="월", values="건수").fillna(0)
                pivot = pivot.sort_index(ascending=False)
                fig = px.imshow(
                    pivot, aspect="auto",
                    color_continuous_scale=[
                        [0.0, "#0B1220"], [0.4, "#0E7490"],
                        [0.7, "#22D3EE"], [1.0, "#A5F3FC"],
                    ],
                    labels=dict(x="월", y="연", color="건수"),
                )
                style_fig(fig, height=320)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("게시일 데이터가 부족합니다.")

        with c4:
            st.markdown("##### 최근 12개월 추이")
            recent = fdf.dropna(subset=["연월"]).copy()
            if not recent.empty:
                last_months = sorted(recent["연월"].unique())[-12:]
                recent = recent[recent["연월"].isin(last_months)]
                trend = (
                    recent.groupby(["연월", "채널"]).size().reset_index(name="건수")
                )
                fig = px.line(
                    trend, x="연월", y="건수", color="채널",
                    color_discrete_map=CHANNEL_COLORS, markers=True,
                    category_orders={"채널": CHANNELS},
                )
                style_fig(fig, height=320)
                fig.update_traces(line=dict(width=2.4))
                fig.update_layout(xaxis_title=None)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("게시일 데이터가 부족합니다.")

        # 3행: 키워드 Top 20 + 채널 × 연도 히트맵
        c5, c6 = st.columns(2)
        with c5:
            st.markdown("##### 제목 키워드 Top 20")
            tokens: list[str] = []
            for t in fdf["제목"].dropna():
                # 한글 2자 이상 + 영문 3자 이상 토큰
                for tok in re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", str(t)):
                    low = tok.lower()
                    if low in STOPWORDS or tok in STOPWORDS:
                        continue
                    tokens.append(tok)
            top = Counter(tokens).most_common(20)
            if top:
                kw_df = pd.DataFrame(top, columns=["키워드", "빈도"])
                fig = px.bar(
                    kw_df.iloc[::-1], x="빈도", y="키워드", orientation="h",
                    color="빈도",
                    color_continuous_scale=[
                        [0.0, "#0E7490"], [0.5, "#22D3EE"], [1.0, "#67E8F9"],
                    ],
                )
                style_fig(fig, height=520)
                fig.update_layout(coloraxis_showscale=False, bargap=0.2)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("키워드를 추출할 만한 제목이 없습니다.")

        with c6:
            st.markdown("##### 채널 × 연도 빈도")
            if not fdf["연"].dropna().empty:
                ch_year = (
                    fdf.dropna(subset=["연"])
                    .groupby(["채널", "연"]).size().reset_index(name="건수")
                )
                ch_year["연"] = ch_year["연"].astype(int).astype(str)
                pivot2 = ch_year.pivot(index="채널", columns="연", values="건수").fillna(0)
                pivot2 = pivot2.reindex(
                    index=[c for c in CHANNELS if c in pivot2.index],
                    columns=sorted(pivot2.columns),
                )
                fig = px.imshow(
                    pivot2, aspect="auto",
                    color_continuous_scale=[
                        [0.0, "#0B1220"], [0.4, "#1E40AF"],
                        [0.7, "#38BDF8"], [1.0, "#A5F3FC"],
                    ],
                    labels=dict(x="연도", y="채널", color="건수"), text_auto=True,
                )
                style_fig(fig, height=320)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("연도 데이터가 부족합니다.")


# ── 📈 보도성과 ───────────────────────────────────────────────
def filter_perf(src: pd.DataFrame) -> pd.DataFrame:
    """사이드바 전역 검색어·기간을 보도성과에도 똑같이 적용(제목·매체명, 배포일)."""
    out = src
    if query:
        m = (out["제목"].str.contains(query, case=False, regex=False)
             | out["매체명"].str.contains(query, case=False, regex=False))
        out = out[m]
    if date_range and isinstance(date_range, tuple) and len(date_range) == 2:
        d = out["배포일"].dt.date
        out = out[(d >= date_range[0]) & (d <= date_range[1])]
    return out


with tab_perf:
    if perf.empty:
        st.info(
            "보도성과 데이터가 아직 없습니다. 매주 월요일 자동 갱신 뒤에 표시됩니다.\n\n"
            "수동으로 채우려면 `보도자료 성과분석` 폴더에서 주간 갱신을 실행한 뒤 "
            "`python scripts/hub_guard.py import-perf`를 실행하세요."
        )
    else:
        pf = filter_perf(perf)
        st.caption(
            f"기준일 {perf_meta.get('기준일', '-')} · 보도자료 {len(perf):,}건 중 필터 결과 {len(pf):,}건 "
            "· 보도자료 1건이 네이버 뉴스에서 몇 개 매체에 실렸는지 자동 대조한 결과"
        )
        if pf.empty:
            st.warning("필터 조건에 맞는 보도자료가 없습니다. 사이드바 검색어·기간을 넓혀 보세요.")
        else:
            settled = pf[pf["집계 상태"] == "확정"]
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("보도자료", f"{len(pf):,}건")
            k2.metric("보도 기사", f"{int(pf['기사 수'].sum()):,}건")
            k3.metric(
                "건당 매체 수 (중앙값)",
                f"{settled['매체 수'].median():.0f}곳" if not settled.empty else "-",
                help="집계가 끝난(배포 60일 경과) 보도자료만 셉니다. 집계 중인 건은 숫자가 아직 늘어납니다.",
            )
            k4.metric(
                "확인 대기 기사",
                f"{int(pf['검토대기 기사'].sum()):,}건",
                help="자동 대조 점수가 애매해 사람이 확인해야 하는 기사. 확인 전에는 위 숫자에 넣지 않습니다(하한값).",
            )

            c1, c2 = st.columns([3, 2])
            with c1:
                st.markdown("##### 보도자료별 보도 매체 수")
                yr = settled.dropna(subset=["배포일"]).copy()
                if not yr.empty:
                    yr["연"] = yr["배포일"].dt.year.astype(str)
                    by_year = yr.groupby("연")["매체 수"].median().reset_index()
                    fig = px.bar(by_year, x="연", y="매체 수", text="매체 수",
                                 color_discrete_sequence=[CHANNEL_COLORS["보도자료"]])
                    fig.update_traces(texttemplate="%{text:.0f}곳", textposition="outside", cliponaxis=False)
                    style_fig(fig, height=300)
                    fig.update_layout(xaxis_title=None, yaxis_title="중앙값 (곳)", bargap=0.35)
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("연도별 중앙값 — 집계가 끝난 보도자료만")
                else:
                    st.caption("집계가 끝난 보도자료가 아직 없습니다.")
            with c2:
                st.markdown("##### 자주 보도한 매체 Top 15")
                names = [n for cell in pf["매체명"] for n in cell.split(", ") if n]
                top = Counter(names).most_common(15)
                if top:
                    tdf = pd.DataFrame(top, columns=["매체", "보도한 보도자료 수"]).iloc[::-1]
                    fig = px.bar(tdf, x="보도한 보도자료 수", y="매체", orientation="h",
                                 text="보도한 보도자료 수", color_discrete_sequence=[ACCENT])
                    fig.update_traces(textposition="outside", cliponaxis=False)
                    style_fig(fig, height=300 + 8 * len(top))
                    fig.update_layout(xaxis_title=None, yaxis_title=None, bargap=0.25)
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.caption("보도 매체가 아직 없습니다.")

            st.markdown("##### 보도자료별 성과")
            only_open = st.toggle("집계 중인 보도자료만 (배포 60일 이내)", value=False)
            table = pf[pf["집계 상태"].str.startswith("집계 중")] if only_open else pf
            table = table.sort_values("배포일", ascending=False)
            show = table[["배포일", "제목", "매체 수", "기사 수", "집계 상태", "매체명", "링크"]].copy()
            show["배포일"] = show["배포일"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                show, use_container_width=True, hide_index=True, height=min(640, 38 + 35 * max(len(show), 1)),
                column_config={
                    "매체 수": st.column_config.ProgressColumn(
                        "매체 수", format="%d곳", min_value=0, max_value=int(perf["매체 수"].max() or 1)),
                    "기사 수": st.column_config.NumberColumn("기사 수", format="%d건"),
                    "매체명": st.column_config.TextColumn("보도 매체", width="large"),
                    "링크": st.column_config.LinkColumn("원문", display_text="보도자료 →"),
                },
            )
        with st.expander("집계 기준 · 한계"):
            st.write(perf_meta.get("집계 기준", ""))
            st.write(
                "매체 등급·전체 매체별 집계는 아래 표와 같습니다(기간·검색 필터와 무관한 전체 기간)."
            )
            if not perf_media.empty:
                st.dataframe(perf_media, use_container_width=True, hide_index=True, height=320)


# ── 🔍 통합검색 ───────────────────────────────────────────────
with tab_search:
    # 본문 검색창을 가장 위에 크게 — 사이드바와 별도로 작동(둘 다 입력하면 AND)
    search_q = st.text_input(
        "🔍 키워드 검색 (제목·주요내용)",
        placeholder="예: 미세먼지, 전고체, 로봇, 탄소중립",
        key="tab_search_q",
        help="공백·특수문자 그대로 매칭합니다(대소문자 무시).",
    )

    csel, fsel, ssel = st.columns([3, 2, 1.2])
    with csel:
        sel_channels = st.multiselect(
            "채널 선택",
            CHANNELS, default=CHANNELS,
            placeholder="검색할 채널 (옵션 선택)",
            help="원하는 채널만 골라서 통합 검색. 빈 칸이면 전체 미선택 상태입니다.",
        )
    with fsel:
        st.markdown("&nbsp;", unsafe_allow_html=True)  # 라벨 높이 맞추기
    with ssel:
        sort_opt = st.selectbox("정렬", ["최신순", "오래된순", "채널 → 최신순"])

    sub = apply_filters(df, channels=sel_channels, extra_query=search_q)

    if sort_opt == "최신순":
        sub = sub.sort_values("게시일", ascending=False, na_position="last")
    elif sort_opt == "오래된순":
        sub = sub.sort_values("게시일", ascending=True, na_position="last")
    else:
        sub = sub.sort_values(["채널", "게시일"], ascending=[True, False], na_position="last")

    st.markdown(f"**검색 결과: {len(sub):,}건**")

    if sub.empty:
        st.info("조건에 맞는 항목이 없습니다.")
    else:
        # 결과 미리보기 — 처음 200건만 카드, 그 이상은 표로 폴백
        if len(sub) > 200:
            st.caption("결과가 200건을 넘어 표 형식으로 표시합니다.")
            disp = sub[["채널", "게시일", "제목", "주요내용", "링크"]].copy()
            disp["게시일"] = disp["게시일"].dt.strftime("%Y-%m-%d")
            st.dataframe(
                disp, use_container_width=True, height=600,
                column_config={
                    "링크": st.column_config.LinkColumn("링크", display_text="원문 →"),
                },
            )
        else:
            for _, row in sub.iterrows():
                d = row["게시일"]
                date_str = d.strftime("%Y.%m.%d") if pd.notna(d) else "-"
                link = row.get("링크") or ""
                with st.container(border=True):
                    cols = st.columns([1.0, 1.5, 7.5])
                    with cols[0]:
                        st.markdown(f"**{date_str}**")
                    with cols[1]:
                        ch_color = CHANNEL_COLORS.get(row["채널"], ACCENT)
                        st.markdown(
                            f"<span style='display:inline-block;padding:2px 10px;"
                            f"border:1px solid {ch_color};border-radius:999px;"
                            f"color:{ch_color};font-size:0.78rem;font-weight:600;"
                            f"letter-spacing:0.3px;'>{row['채널']}</span>",
                            unsafe_allow_html=True,
                        )
                    with cols[2]:
                        st.markdown(f"#### {row['제목']}")
                        if row["채널"] == "보도자료" and (badge := perf_badge(row["id"])):
                            st.markdown(badge, unsafe_allow_html=True)
                        st.write(row.get("주요내용") or "")
                        if link:
                            st.markdown(f"[원문 보기 →]({link})")


# ── 채널별 4탭 ────────────────────────────────────────────────
for tab, channel in zip(channel_tabs, CHANNELS):
    with tab:
        sub = apply_filters(df, channels=[channel]).sort_values(
            "게시일", ascending=False, na_position="last"
        )
        st.markdown(f"**{len(sub):,}건**")

        if sub.empty:
            st.warning("조건에 맞는 항목이 없습니다.")
            continue

        # 너무 많으면 페이지네이션
        page_size = 50
        total_pages = (len(sub) - 1) // page_size + 1
        if total_pages > 1:
            page = st.number_input(
                f"페이지 (1 ~ {total_pages})", min_value=1, max_value=total_pages,
                value=1, key=f"page_{channel}",
            )
        else:
            page = 1
        start = (page - 1) * page_size
        page_sub = sub.iloc[start:start + page_size]

        for _, row in page_sub.iterrows():
            d = row["게시일"]
            date_str = d.strftime("%Y.%m.%d") if pd.notna(d) else "-"
            link = row.get("링크") or ""
            thumb = row.get("썸네일URL") or ""
            with st.container(border=True):
                if thumb and channel in ("포토뉴스", "유튜브", "블로그"):
                    cols = st.columns([1.5, 1.2, 7.3])
                    with cols[0]:
                        st.image(thumb, use_container_width=True)
                    info_cols = cols[1:]
                else:
                    info_cols = st.columns([1.2, 8.8])
                with info_cols[0]:
                    st.markdown(f"**{date_str}**")
                with info_cols[1]:
                    st.markdown(f"#### {row['제목']}")
                    if channel == "보도자료" and (badge := perf_badge(row["id"])):
                        st.markdown(badge, unsafe_allow_html=True)
                    st.write(row.get("주요내용") or "")
                    if link:
                        st.markdown(f"[원문 보기 →]({link})")
