"""KITECH 홍보 허브 — 디자인 시스템(토큰 · CSS · HTML 부품).

화면 로직(streamlit_app.py)과 분리한 이유: 숫자·문장은 데이터에서 오고, 모양은 여기서만 정한다.
부품은 전부 '문자열을 돌려주는 순수 함수'라 Streamlit 없이 단위 테스트할 수 있다(tests/test_ui.py).

주의 — st.markdown(unsafe_allow_html=True)에 넣는 HTML은 ① 한 줄 문자열이어야 하고(빈 줄·4칸 들여쓰기는
마크다운이 코드블록으로 바꾼다) ② 동적 텍스트는 반드시 esc()를 거쳐야 한다.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path
from collections.abc import Iterable, Sequence

# ── 토큰 ─────────────────────────────────────────────────────────
BG = "#070B14"            # 기존 검은 톤 유지
SURFACE_1 = "#0C1220"     # 면 = 그림자가 아니라 명도 단계(바탕 → +3% → 호버 +6%)
SURFACE_2 = "#111A2C"
INK, INK_2, MUTED = "#F1F5FB", "#C3CEDE", "#8E9BB0"   # MUTED 는 BG 위 약 6.5:1
ACCENT = "#7AA2FF"        # UI 전용(탭·포커스·소제목)
DATA = "#22D3EE"          # 데이터 전용(단일 계열 막대·평균 이상)
GOOD, BAD, WARN = "#34D399", "#F87171", "#FCD34D"
NEG = "#64748B"           # 평균 이하
# 채널색 — OKLCH L=.76 C=.12 로 명도·채도를 맞추고 색상(hue)만 벌렸다. 데이터에서만 쓴다.
CHANNEL_COLORS = {"보도자료": "#EC9C63", "포토뉴스": "#BD9FF2", "유튜브": "#F290A2", "블로그": "#79C685"}
ORG_NAME = "한국생산기술연구원 홍보 허브"

_NOISE = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'>"
          "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/>"
          "</filter><rect width='100%' height='100%' filter='url(%23n)' opacity='.55'/></svg>")

_CSS = """
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
:root{--bg:__BG__;--s1:__S1__;--s2:__S2__;--line:rgba(148,163,184,.14);--line2:rgba(148,163,184,.28);
  --ink:__INK__;--ink2:__INK2__;--mute:__MUTED__;--accent:__ACCENT__;--data:__DATA__;--good:__GOOD__;--bad:__BAD__;--warn:__WARN__;
  --r:12px;--ease:cubic-bezier(.2,.7,.2,1);}
/* 폰트 — 와일드카드가 Streamlit 아이콘 글리프(Material Symbols)까지 덮어 글자로 깨뜨리지 않게 아이콘은 제외 */
.stApp *:not([data-testid="stIconMaterial"]):not([class*="material"]):not([class*="Material"]){
  font-family:'Pretendard','Pretendard Variable',-apple-system,BlinkMacSystemFont,system-ui,'Malgun Gothic',sans-serif !important;}
html,body,.stApp{background-color:var(--bg) !important;color:var(--ink);word-break:keep-all;}
/* 배경 빛은 정적 한 겹 — 움직이는 빛은 히어로 안에만 둔다(전체 화면 blur 레이어는 스크롤 비용이 크다) */
.stApp{background-image:radial-gradient(70vw 46vh at 14% -10%,rgba(122,162,255,.10),transparent 70%);background-repeat:no-repeat;}
.stApp::after{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;opacity:.035;background-image:url("__NOISE__");}
[data-testid="stAppViewContainer"],[data-testid="stHeader"]{position:relative;z-index:1;}
[data-testid="stHeader"]{background:transparent;}
.block-container{max-width:1240px;padding-top:1.4rem;padding-bottom:3rem;}
.st-key-kt_js{position:absolute;height:0;overflow:hidden;margin:0;}

/* ── 탭 ── */
div[data-baseweb="tab-list"]{gap:8px;border-bottom:1px solid var(--line);}
button[data-baseweb="tab"]{background:transparent !important;color:var(--mute) !important;padding:12px 18px !important;border-radius:0 !important;transition:color .15s;}
button[data-baseweb="tab"] p{font-size:16px !important;font-weight:600 !important;}
button[data-baseweb="tab"]:hover{color:var(--ink) !important;}
button[data-baseweb="tab"][aria-selected="true"]{color:var(--ink) !important;}
div[data-baseweb="tab-highlight"]{background:var(--accent) !important;height:2px !important;}
div[data-baseweb="tab-border"]{display:none;}
@media(max-width:640px){button[data-baseweb="tab"]{padding:12px 10px !important;}div[data-baseweb="tab-list"]{gap:0;}}

/* ── 입력·알약·표 ── */
div[data-baseweb="input"],div[data-baseweb="select"]>div,div[data-baseweb="base-input"]{background:var(--s1) !important;border-color:var(--line) !important;border-radius:10px !important;}
div[data-baseweb="input"]:focus-within,div[data-baseweb="select"]>div:focus-within{border-color:var(--accent) !important;}
[data-testid="stWidgetLabel"] p{font-size:13px;color:var(--mute);font-weight:600;}
button[data-testid^="stBaseButton-pills"],button[data-testid^="stBaseButton-segmented"]{border-radius:999px !important;border:1px solid var(--line) !important;background:transparent !important;color:var(--ink2) !important;min-height:40px;padding:0 16px;transition:border-color .15s,background .15s,color .15s;}
button[data-testid^="stBaseButton-pills"]:hover,button[data-testid^="stBaseButton-segmented"]:hover{border-color:var(--line2) !important;background:var(--s1) !important;}
button[data-testid="stBaseButton-pillsActive"],button[data-testid="stBaseButton-segmented_controlActive"]{border-color:var(--accent) !important;background:rgba(122,162,255,.12) !important;color:var(--ink) !important;}
button[data-testid="stBaseButton-secondary"]{border-radius:10px;border-color:var(--line);background:transparent;min-height:40px;}
button[data-testid="stBaseButton-secondary"]:hover{border-color:var(--accent);color:var(--ink);}
div[data-testid="stVerticalBlockBorderWrapper"]{background:var(--s1) !important;border:1px solid var(--line) !important;border-radius:var(--r) !important;}
details{border-color:var(--line) !important;border-radius:var(--r) !important;}
.stApp a,.stApp a:visited{color:var(--ink) !important;text-decoration:none !important;transition:color .15s;}
.stApp a:hover{color:var(--accent) !important;}
*:focus-visible{outline:2px solid var(--accent) !important;outline-offset:2px;}
::-webkit-scrollbar{width:10px;height:10px;}::-webkit-scrollbar-thumb{background:rgba(148,163,184,.25);border-radius:99px;}

/* ── 인트로(세션당 1회) — 로딩 중 레이아웃 흔들림을 가리는 마스크를 겸한다 ── */
.kt-intro{--em:clamp(130px,27vmin,230px);position:fixed;inset:0;z-index:99999;display:grid;place-items:center;background:var(--bg);
  animation:kt-out .75s cubic-bezier(.7,0,.2,1) 3.5s forwards;cursor:pointer;}
.kt-intro.kt-skip{animation:kt-out .35s cubic-bezier(.7,0,.2,1) 0s forwards;}
.kt-intro .box{position:relative;display:flex;flex-direction:column;align-items:center;padding:0 20px;}
/* 일출: 엠블럼이 가로선(지평선) 아래에서 올라온다 — 선 위쪽만 보이게 .sun 이 잘라 낸다 */
.kt-intro .halo{position:absolute;left:50%;top:var(--em);width:min(640px,96vw);height:calc(var(--em) * .95);transform:translate(-50%,-100%);
  background:radial-gradient(ellipse 50% 100% at 50% 100%,rgba(122,162,255,.30),rgba(122,162,255,.08) 55%,transparent 75%);opacity:0;animation:kt-fade 1.5s ease .8s forwards;}
/* 아래쪽만 자르고 좌우·위는 열어 둔다 — overflow:hidden 은 엠블럼 그림자를 네모로 잘라 상자가 비친다 */
.kt-intro .sun{position:relative;width:var(--em);height:var(--em);clip-path:inset(-90px -90px 0 -90px);}
.kt-intro .emb{position:absolute;inset:0;background:var(--logo) center/contain no-repeat;
  filter:drop-shadow(0 0 26px rgba(122,162,255,.22));animation:kt-sunrise 1.35s cubic-bezier(.45,.05,.25,1) .8s both;}
/* 금속 하이라이트는 한 번만 스친다 — 엠블럼 모양으로 잘라(mask) 선 밖으로 번지지 않게 */
.kt-intro .emb::after{content:"";position:absolute;inset:0;background:linear-gradient(105deg,transparent 40%,rgba(255,255,255,.55) 50%,transparent 60%) 160% 0/260% 100% no-repeat;
  -webkit-mask:var(--logo) center/contain no-repeat;mask:var(--logo) center/contain no-repeat;animation:kt-sheen 1s ease-in-out 2.1s forwards;}
.kt-intro .rule{position:relative;height:1px;width:0;background:linear-gradient(90deg,transparent,rgba(160,184,255,.9) 22%,rgba(160,184,255,.9) 78%,transparent);animation:kt-rule 1s var(--ease) .25s forwards;}
.kt-intro .rule::after{content:"";position:absolute;left:0;right:0;top:5px;height:6px;opacity:.7;
  background:repeating-linear-gradient(90deg,rgba(142,155,176,.55) 0 1px,transparent 1px 26px);
  -webkit-mask:linear-gradient(90deg,transparent,#000 25%,#000 75%,transparent);mask:linear-gradient(90deg,transparent,#000 25%,#000 75%,transparent);}
.kt-intro .name{margin-top:30px;font-size:clamp(16px,2vw,22px);letter-spacing:.04em;color:var(--ink2);opacity:0;transform:translateY(10px);animation:kt-name .8s var(--ease) 2.3s forwards;}
.kt-intro .skip{position:absolute;right:28px;bottom:24px;font-size:13px;color:var(--mute);opacity:0;animation:kt-name .5s ease .9s forwards;}
@keyframes kt-rule{to{width:min(560px,76vw)}}
/* 시작 값을 명시한다 — 생략하면 브라우저가 시작 시점의 요소 높이로 %를 계산해(CSS 로딩 순서에 따라 ≈0) 떠오르지 않고 제자리에 나타난다 */
@keyframes kt-sunrise{from{transform:translateY(calc(var(--em) * 1.05))}to{transform:none}}
@keyframes kt-sheen{to{background-position:-60% 0}}
@keyframes kt-name{to{opacity:1;transform:none}}
@keyframes kt-fade{to{opacity:1}}
@keyframes kt-out{to{clip-path:inset(0 0 100% 0);visibility:hidden}}

/* ── 히어로 ── */
.kt-hero{position:relative;overflow:hidden;isolation:isolate;border-radius:20px;border:1px solid var(--line);
  padding:clamp(28px,4.4vw,60px) clamp(22px,4.4vw,60px);background:linear-gradient(160deg,#0D1527 0%,#080D18 72%);}
.kt-hero .aurora{position:absolute;inset:-30%;z-index:-2;animation:kt-drift 40s ease-in-out infinite alternate;
  background:radial-gradient(40% 50% at 78% 20%,rgba(122,162,255,.34),transparent 70%),radial-gradient(35% 45% at 96% 82%,rgba(79,70,229,.26),transparent 70%),radial-gradient(30% 40% at 18% 104%,rgba(34,211,238,.12),transparent 70%);}
.kt-hero .aurora.paused{animation-play-state:paused;}
.kt-hero::after{content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(420px circle at var(--mx,-999px) var(--my,-999px),rgba(255,255,255,.07),transparent 60%);}
@keyframes kt-drift{0%{transform:translate3d(0,0,0) rotate(0)}100%{transform:translate3d(-4%,3%,0) rotate(6deg)}}
.kt-eyebrow{font-size:12px;letter-spacing:.2em;font-weight:700;color:var(--accent);text-transform:uppercase;}
.kt-hero h1{margin:14px 0 0 !important;padding:0 !important;font-size:clamp(22px,2.6vw,31px) !important;line-height:1.25 !important;letter-spacing:-.02em !important;font-weight:700 !important;color:var(--ink) !important;}
.kt-hero .big{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;margin-top:clamp(8px,2vw,20px);}
.kt-hero .num{font-size:clamp(64px,11vw,120px);line-height:1;font-weight:800;letter-spacing:-.04em;font-variant-numeric:tabular-nums;color:#fff;}
.kt-hero .unit{font-size:clamp(18px,2.2vw,28px);font-weight:400;color:var(--ink2);}
.kt-hero p.lead{margin:18px 0 0 !important;max-width:640px;font-size:16px;line-height:1.75;color:var(--mute);}
.kt-share{margin-top:34px;}
.kt-share .bar{display:flex;height:8px;gap:3px;}
.kt-share .bar i{display:block;height:100%;border-radius:99px;transform-origin:left;animation:kt-grow .9s var(--ease) both;animation-delay:calc(var(--i)*90ms);}
.kt-hero.intro .kt-share .bar i{animation-delay:calc(2.2s + var(--i)*90ms);}
@keyframes kt-grow{from{transform:scaleX(0)}to{transform:none}}
.kt-share .legend{display:flex;flex-wrap:wrap;gap:8px 26px;margin-top:14px;font-size:14px;color:var(--ink2);}
.kt-share .legend span{display:inline-flex;align-items:center;gap:8px;}
.kt-share .legend i{width:8px;height:8px;border-radius:50%;}
.kt-share .legend b{font-variant-numeric:tabular-nums;color:var(--ink);font-weight:700;}
.kt-live{display:inline-flex;align-items:center;gap:8px;margin-top:22px;font-size:13px;color:var(--mute);padding:5px 12px;border-radius:99px;border:1px solid var(--line);}
.kt-live i{width:7px;height:7px;border-radius:50%;background:var(--good);}

/* ── 섹션 · 카드 ── */
.kt-sec{margin:56px 0 16px;}
.kt-sec .k{font-size:12px;letter-spacing:.16em;font-weight:700;color:var(--accent);text-transform:uppercase;}
.kt-sec h2{margin:6px 0 6px !important;padding:0 !important;font-size:clamp(22px,2.4vw,28px) !important;line-height:1.3 !important;letter-spacing:-.02em !important;font-weight:700 !important;color:var(--ink) !important;}
.kt-sec p{margin:0 !important;font-size:14.5px;line-height:1.7;color:var(--mute);max-width:760px;}
.kt-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:12px;margin:8px 0 4px;}
.kt-grid.c3{grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));}
.kt-card{position:relative;background:var(--s1);border:1px solid var(--line);border-radius:var(--r);padding:20px 22px;}
.kt-card::before{content:"";position:absolute;inset:-1px;border-radius:inherit;padding:1px;pointer-events:none;opacity:0;transition:opacity .2s;
  background:radial-gradient(240px circle at var(--mx,-999px) var(--my,-999px),rgba(122,162,255,.6),transparent 62%);
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;}
.kt-card:hover::before{opacity:1;}
.kt-card .l{font-size:13px;font-weight:600;color:var(--mute);}
.kt-card .v{display:flex;align-items:baseline;gap:6px;margin-top:10px;}
.kt-card .v b{font-size:clamp(32px,3.2vw,44px);line-height:1.05;font-weight:750;letter-spacing:-.03em;font-variant-numeric:tabular-nums;color:var(--ink);}
.kt-card .v u{text-decoration:none;font-size:16px;font-weight:500;color:var(--mute);}
.kt-card .s{margin-top:8px;font-size:13px;line-height:1.55;color:var(--mute);}
.kt-card .s .up,.kt-card .s .dn{font-variant-numeric:tabular-nums;font-weight:650;color:var(--ink2);}
.kt-card .spark{position:absolute;right:18px;bottom:16px;width:120px;height:32px;}
.kt-card.feature{grid-column:span 2;background:linear-gradient(150deg,#0F1A31 0%,var(--s1) 70%);}
.kt-card.feature .v b{font-size:clamp(56px,7vw,84px);}
.kt-card.feature .v u{font-size:22px;}
@media(max-width:640px){.kt-card.feature{grid-column:span 1;}.kt-card .spark{position:static;margin-top:10px;}}
.kt-card.panel h4{margin:0 0 6px !important;padding:0 !important;font-size:15px !important;font-weight:650 !important;color:var(--ink) !important;}
.kt-rank{display:flex;gap:12px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line);}
.kt-rank:last-child{border-bottom:0;}
.kt-rank .n{width:18px;color:var(--mute);font-weight:800;font-variant-numeric:tabular-nums;}
.kt-rank .t{flex:1;font-size:14.5px;line-height:1.5;}
.kt-rank .t a{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.kt-rank .v{font-size:13px;color:var(--mute);white-space:nowrap;font-variant-numeric:tabular-nums;}
.kt-words{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));column-gap:48px;}
.kt-words ol{margin:0;padding:0;list-style:none;}
.kt-words li{break-inside:avoid;display:grid;grid-template-columns:22px 1fr 44px;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid var(--line);font-size:14.5px;}
.kt-words .n{color:var(--mute);font-weight:800;font-variant-numeric:tabular-nums;}
.kt-words .b{position:relative;height:6px;border-radius:99px;background:rgba(148,163,184,.10);}
.kt-words .b i{position:absolute;left:0;top:0;bottom:0;border-radius:99px;background:var(--data);}
.kt-words .t{grid-column:2;}
.kt-words .v{grid-column:3;grid-row:1 / span 2;text-align:right;color:var(--mute);font-variant-numeric:tabular-nums;font-size:13px;}
.kt-ct{margin:2px 0 6px;font-size:15px;font-weight:650;color:var(--ink);}
.kt-ct small{display:block;margin-top:2px;font-size:12.5px;font-weight:400;color:var(--mute);}
.kt-ct + .kt-share{margin-top:14px;}
.st-key-report_sheet iframe{border:1px solid var(--line);border-radius:var(--r);background:var(--bg);}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12.5px;font-weight:650;margin:0 6px 4px 0;font-variant-numeric:tabular-nums;}
.chip.soft{background:rgba(34,211,238,.10);color:var(--data);}
.chip.stat{background:rgba(148,163,184,.12);color:#CBD5E1;}
.chip.warn{background:rgba(252,211,77,.12);color:var(--warn);}

/* ── 아카이브 ── */
.kt-list{margin-top:8px;}
.kt-row{display:grid;grid-template-columns:116px 1fr auto;gap:8px 24px;align-items:start;padding:22px 0;border-bottom:1px solid var(--line);}
.kt-row .meta{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--mute);font-variant-numeric:tabular-nums;}
.kt-row .ch{display:inline-flex;align-items:center;gap:6px;color:var(--ink2);font-weight:600;}
.kt-row .ch i{width:7px;height:7px;border-radius:50%;}
.kt-row .t{font-size:18px;line-height:1.5;font-weight:600;letter-spacing:-.01em;display:inline;}
.kt-row .t::after{content:" ↗";color:var(--mute);font-weight:400;transition:color .15s;}
.kt-row .t:hover::after{color:var(--accent);}
.kt-row .sum{margin:8px 0 8px !important;font-size:14.5px;line-height:1.7;color:var(--mute);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.kt-row img{width:132px;height:84px;object-fit:cover;border-radius:8px;background:var(--s2);}
@media(max-width:700px){.kt-row{grid-template-columns:1fr;}.kt-row .meta{flex-direction:row;gap:12px;}.kt-row img{width:100%;height:auto;aspect-ratio:16/9;}}
.kt-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,260px),1fr));gap:16px;margin-top:8px;}
.kt-tile{display:block;border:1px solid var(--line);border-radius:var(--r);overflow:hidden;background:var(--s1);transition:border-color .2s,background .2s;}
.kt-tile:hover{border-color:var(--line2);background:var(--s2);}
.kt-tile .img{aspect-ratio:16/10;overflow:hidden;background:var(--s2);}
.kt-tile img{width:100%;height:100%;object-fit:cover;display:block;transition:transform .24s var(--ease);}
.kt-tile:hover img{transform:scale(1.03);}
.kt-tile .b{padding:14px 16px 16px;}
.kt-tile time{font-size:12.5px;color:var(--mute);font-variant-numeric:tabular-nums;}
.kt-tile .tt{margin-top:6px;font-size:15.5px;line-height:1.5;font-weight:600;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}
.kt-empty{padding:48px 20px;text-align:center;border:1px dashed var(--line2);border-radius:var(--r);}
.kt-empty b{display:block;font-size:17px;color:var(--ink);}
.kt-empty span{display:block;margin-top:6px;font-size:14px;color:var(--mute);}
.kt-foot{margin-top:72px;padding-top:24px;border-top:1px solid var(--line);display:flex;flex-wrap:wrap;gap:8px 32px;justify-content:space-between;font-size:13px;line-height:1.7;color:var(--mute);}
.kt-foot b{color:var(--ink2);font-weight:650;}

/* ── 스크롤 진입(지원 브라우저만) — 모션은 한 번, transform·opacity 만 ── */
@supports (animation-timeline: view()){
  .kt-sec,.kt-card,div[data-testid="stPlotlyChart"]{animation:kt-rise linear both;animation-timeline:view();animation-range:entry 0% entry 35%;}
}
@keyframes kt-rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){
  .kt-intro{display:none !important;}
  .kt-hero .aurora,.kt-share .bar i,.kt-sec,.kt-card,div[data-testid="stPlotlyChart"]{animation:none !important;}
}
"""

# 마우스 따라 도는 빛 · 숫자 카운트업 · 인트로 건너뛰기 — components.html(iframe)은 같은 출처라 부모 문서에 닿는다.
# 실패해도(차단·구형 브라우저) 화면은 정적으로 정상이다. 이벤트 리스너는 부모에 한 번만 건다.
ENHANCE_JS = """<script>(function(){var P,D;try{P=window.parent;D=P.document;}catch(e){return;}
if(!P.__ktBound){P.__ktBound=true;
D.addEventListener('mousemove',function(e){var t=e.target&&e.target.closest&&e.target.closest('.kt-card,.kt-hero');if(!t)return;
var r=t.getBoundingClientRect();t.style.setProperty('--mx',(e.clientX-r.left)+'px');t.style.setProperty('--my',(e.clientY-r.top)+'px');},{passive:true});
D.addEventListener('keydown',function(e){if(e.key==='Escape'||e.key==='Enter'||e.key===' '){var i=D.querySelector('.kt-intro');if(i)i.classList.add('kt-skip');}});
D.addEventListener('click',function(e){var i=e.target&&e.target.closest&&e.target.closest('.kt-intro');if(i)i.classList.add('kt-skip');});}
var reduce=P.matchMedia&&P.matchMedia('(prefers-reduced-motion: reduce)').matches;
function fmt(n){return Math.round(n).toLocaleString('en-US');}
function count(el){var to=+el.getAttribute('data-count');el.setAttribute('data-done','1');if(reduce||!to)return;
 var t0=P.performance.now(),dur=1100;(function s(t){var k=Math.min(1,(t-t0)/dur);k=1-Math.pow(1-k,3);el.textContent=fmt(to*k);
 if(k<1)P.requestAnimationFrame(s);else el.textContent=fmt(to);})(t0);}
function arm(el){var to=+el.getAttribute('data-count');el.setAttribute('data-done','1');if(reduce||!to)return;
 var i=D.querySelector('.kt-intro'),over=!i||P.getComputedStyle(i).visibility==='hidden';
 el.textContent=fmt(0);
 if(over){P.setTimeout(function(){count(el);},150);}
 else{i.addEventListener('animationend',function h(e){if(e.animationName==='kt-out'){i.removeEventListener('animationend',h);count(el);}});}
 P.setTimeout(function(){el.textContent=fmt(to);},9000);}
/* iframe 은 데이터 로딩보다 먼저 뜰 수 있다 — 히어로가 생길 때까지 부모 타이머로 기다린다(iframe 이 다시 만들어져도 살아남게) */
var n=0,iv=P.setInterval(function(){var h=D.querySelector('.kt-hero');n++;
 if(h){D.querySelectorAll('[data-count]:not([data-done])').forEach(arm);
  var au=h.querySelector('.aurora');if(au&&P.IntersectionObserver&&!au.__ktIO){au.__ktIO=1;
   new P.IntersectionObserver(function(en){au.classList.toggle('paused',!en[0].isIntersecting);}).observe(h);}
  P.clearInterval(iv);}
 else if(n>150){P.clearInterval(iv);}},100);
})();</script>"""


def css() -> str:
    """<style> 블록 한 덩이. 토큰은 이 모듈 상수에서만 주입한다(두 곳에서 어긋나지 않게)."""
    body = (_CSS.replace("__BG__", BG).replace("__S1__", SURFACE_1).replace("__S2__", SURFACE_2)
            .replace("__INK__", INK).replace("__INK2__", INK_2).replace("__MUTED__", MUTED)
            .replace("__ACCENT__", ACCENT).replace("__DATA__", DATA).replace("__GOOD__", GOOD)
            .replace("__BAD__", BAD).replace("__WARN__", WARN).replace("__NOISE__", _NOISE))
    return f"<style>{body}</style>"


def esc(x: object) -> str:
    return html.escape(str(x))


# ── HTML 부품 ────────────────────────────────────────────────────
def _emblem_data_uri() -> str:
    """app/emblem.webp(배경 투명 처리본, scripts/make_emblem.py)를 CSS 변수로 심는다. 파일이 없으면 빈 문자열 → 엠블럼 없이 선·이름만 보인다."""
    try:
        return "data:image/webp;base64," + base64.b64encode((Path(__file__).parent / "emblem.webp").read_bytes()).decode("ascii")
    except OSError:
        return ""


def intro_html() -> str:
    logo = _emblem_data_uri()
    style = f" style='--logo:url(\"{logo}\")'" if logo else ""
    return (f"<div class='kt-intro' role='presentation'{style}><div class='box'><div class='halo'></div>"
            "<div class='sun'><div class='emb'></div></div><div class='rule'></div>"
            f"<div class='name'>{esc(ORG_NAME)}</div></div><div class='skip'>건너뛰기 ›</div></div>")


def share_bar(counts: dict[str, int]) -> str:
    """채널 구성비 100% 누적 막대 + 범례. 히어로·개요가 같은 부품을 쓴다."""
    total = sum(counts.values()) or 1
    segs = "".join(
        f"<i style='flex:{max(v, 0)} 1 0;background:{CHANNEL_COLORS.get(k, MUTED)};--i:{i}' title='{esc(k)} {v / total:.0%}'></i>"
        for i, (k, v) in enumerate(counts.items()) if v > 0)
    legend = "".join(
        f"<span><i style='background:{CHANNEL_COLORS.get(k, MUTED)}'></i>{esc(k)} <b>{v:,}</b></span>" for k, v in counts.items())
    return f"<div class='kt-share'><div class='bar'>{segs}</div><div class='legend'>{legend}</div></div>"


def hero_html(total: int, y0: int | None, y1: int | None, counts: dict[str, int], basis: str, intro: bool) -> str:
    span = f" · {y0}–{y1}" if y0 and y1 else ""
    return (f"<section class='kt-hero{' intro' if intro else ''}'><div class='aurora'></div>"
            f"<div class='kt-eyebrow'>KITECH PR ARCHIVE{esc(span)}</div>"
            f"<h1>{esc(ORG_NAME)}</h1>"
            f"<div class='big'><span class='num' data-count='{int(total)}'>{int(total):,}</span><span class='unit'>건의 홍보 기록</span></div>"
            "<p class='lead'>발행한 모든 홍보 콘텐츠와, 그것이 언론에 실린 기록을 한곳에서 봅니다.</p>"
            f"{share_bar(counts)}"
            f"<div class='kt-live'><i></i>주간 갱신 · 기준일 {esc(basis)}</div></section>")


def spark_svg(values: Sequence[float]) -> str:
    """12개월 같은 짧은 계열의 스파크라인. 값이 모두 같거나 비어 있어도 깨지지 않는다."""
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    w, h, pad = 120.0, 32.0, 3.0
    pts = [(pad + i * (w - 2 * pad) / (len(vals) - 1), h - pad - (v - lo) / span * (h - 2 * pad)) for i, v in enumerate(vals)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pts[0][0]:.1f},{h} {line} {pts[-1][0]:.1f},{h}"
    lx, ly = pts[-1]
    return (f"<svg class='spark' viewBox='0 0 {w:.0f} {h:.0f}' aria-hidden='true'>"
            f"<polygon points='{area}' fill='{ACCENT}' opacity='.14'/>"
            f"<polyline points='{line}' fill='none' stroke='{ACCENT}' stroke-width='1.6' stroke-linejoin='round' stroke-linecap='round'/>"
            f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.4' fill='{ACCENT}'/></svg>")


def delta_text(cur: float, prev: float, unit: str = "건", basis: str = "전월 대비") -> str:
    """증감을 색이 아니라 기호+숫자+글자로 — 색만으로 구분하지 않는다."""
    d = cur - prev
    if d == 0:
        return f"<span class='dn'>■ 변동 없음</span> · {esc(basis)}"
    arrow, cls = ("▲", "up") if d > 0 else ("▼", "dn")
    return f"<span class='{cls}'>{arrow} {abs(d):,.0f}{esc(unit)}</span> · {esc(basis)}"


def kpi(label: str, value: str, unit: str = "", sub_html: str = "", spark: Sequence[float] | None = None,
        hint: str = "", feature: bool = False) -> str:
    """지표 카드. value·unit·label 은 이스케이프하고, sub_html 은 호출 쪽이 esc/delta_text 로 만든 것만 받는다."""
    title = f" title='{esc(hint)}'" if hint else ""
    u = f"<u>{esc(unit)}</u>" if unit else ""
    s = f"<div class='s'>{sub_html}</div>" if sub_html else ""
    sp = spark_svg(spark) if spark else ""
    return (f"<div class='kt-card{' feature' if feature else ''}'{title}><div class='l'>{esc(label)}</div>"
            f"<div class='v'><b>{esc(value)}</b>{u}</div>{s}{sp}</div>")


def grid(cards: Iterable[str], cols3: bool = False) -> str:
    return f"<div class='kt-grid{' c3' if cols3 else ''}'>{''.join(cards)}</div>"


def section(kicker: str, title: str, desc: str = "") -> str:
    d = f"<p>{esc(desc)}</p>" if desc else ""
    return f"<div class='kt-sec'><div class='k'>{esc(kicker)}</div><h2>{esc(title)}</h2>{d}</div>"


def chart_title(title: str, sub: str = "") -> str:
    s = f"<small>{esc(sub)}</small>" if sub else ""
    return f"<div class='kt-ct'>{esc(title)}{s}</div>"


def rank_panel(title: str, rows: Sequence[tuple[str, str, str]], empty: str) -> str:
    """rows = (링크, 제목, 값). 제목·링크는 esc 한다."""
    body = "".join(
        f"<div class='kt-rank'><span class='n'>{i}</span><span class='t'><a href='{esc(href)}' target='_blank' rel='noopener'>{esc(t)}</a></span>"
        f"<span class='v'>{esc(v)}</span></div>" for i, (href, t, v) in enumerate(rows, 1))
    body = body or f"<p style='color:{MUTED};margin:8px 0 0'>{esc(empty)}</p>"
    return f"<div class='kt-card panel'><h4>{esc(title)}</h4>{body}</div>"


def word_ranking(items: Sequence[tuple[str, int]]) -> str:
    """상위 단어 막대 목록 — 앞 절반과 뒤 절반을 두 목록으로 나눠 그리드에 얹는다(CSS 다단은 마크다운 안에서 폭이 줄어든다)."""
    if not items:
        return ""
    top = max(v for _, v in items) or 1

    def one(chunk: Sequence[tuple[str, int]], start: int) -> str:
        lis = "".join(
            f"<li><span class='n'>{i}</span><span class='t'>{esc(w)}</span><span class='v'>{v}</span>"
            f"<span class='b' style='grid-column:2'><i style='width:{v / top * 100:.0f}%'></i></span></li>"
            for i, (w, v) in enumerate(chunk, start))
        return f"<ol>{lis}</ol>"

    half = (len(items) + 1) // 2
    return f"<div class='kt-words'>{one(items[:half], 1)}{one(items[half:], half + 1)}</div>"


def row_html(*, date: str, title: str, link: str, summary: str, chips_html: str, channel: str | None, thumb: str) -> str:
    ch = (f"<span class='ch'><i style='background:{CHANNEL_COLORS.get(channel, MUTED)}'></i>{esc(channel)}</span>" if channel else "")
    img = (f"<img src='{esc(thumb)}' alt='' loading='lazy' referrerpolicy='no-referrer'>" if thumb else "<span></span>")
    t = (f"<a class='t' href='{esc(link)}' target='_blank' rel='noopener'>{esc(title)}</a>" if link
         else f"<span class='t'>{esc(title)}</span>")
    sm = f"<p class='sum'>{esc(summary)}</p>" if summary else ""
    return (f"<article class='kt-row'><div class='meta'><time>{esc(date)}</time>{ch}</div>"
            f"<div class='main'>{t}{sm}<div>{chips_html}</div></div>{img}</article>")


def tile_html(*, date: str, title: str, link: str, thumb: str, chips_html: str) -> str:
    img = (f"<img src='{esc(thumb)}' alt='' loading='lazy' referrerpolicy='no-referrer'>" if thumb else "")
    return (f"<a class='kt-tile' href='{esc(link)}' target='_blank' rel='noopener'><div class='img'>{img}</div>"
            f"<div class='b'><time>{esc(date)}</time><div class='tt'>{esc(title)}</div><div>{chips_html}</div></div></a>")


def empty_state(message: str, hint: str = "") -> str:
    h = f"<span>{esc(hint)}</span>" if hint else ""
    return f"<div class='kt-empty'><b>{esc(message)}</b>{h}</div>"


def footer_html(latest: dict[str, str], perf_basis: str) -> str:
    dates = " · ".join(f"{esc(k)} {esc(v)}" for k, v in latest.items())
    return ("<footer class='kt-foot'><div><b>한국생산기술연구원 전략홍보실</b><br>"
            "홈페이지·유튜브·네이버 블로그에 공개된 콘텐츠의 메타 정보와, 네이버 뉴스 검색을 대조한 보도 집계입니다.</div>"
            f"<div>채널별 최신 게시물 — {dates}<br>보도성과 기준일 {esc(perf_basis)} · 매주 월요일 자동 갱신</div></footer>")
