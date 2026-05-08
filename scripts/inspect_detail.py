"""상세 페이지 본문 컨테이너 진단 — 어떤 selector를 쓰면 본문이 잡히는지 찾기"""
import sys
from common import make_session, fetch

URLS = [
    "https://www.kitech.re.kr/pages/61?id=14318&menuMode=READ&q=",
    "https://www.kitech.re.kr/pages/60?id=14321&menuMode=READ&q=",
]

session = make_session()
for url in URLS:
    print(f"\n{'='*80}\n{url}\n{'='*80}")
    soup = fetch(session, url, sleep=0.5)

    print("\n--- '등록일' 위치 ---")
    for s in soup.find_all(string=lambda x: x and "등록일" in x):
        p = s.parent
        cls = ".".join(p.get("class") or [])
        print(f"  <{p.name} id={p.get('id')} class={cls}>: '{str(s).strip()[:60]}'")
        if p.parent:
            pp = p.parent
            ppcls = ".".join(pp.get("class") or [])
            print(f"    parent: <{pp.name} id={pp.get('id')} class={ppcls}>")
        break

    print("\n--- id/class에 'view', 'content', 'board', 'article' 포함된 요소 ---")
    for el in soup.find_all(True):
        cls = " ".join(el.get("class") or [])
        idv = el.get("id") or ""
        marker = (cls + " " + idv).lower()
        if any(k in marker for k in ["view", "content", "board", "article", "detail"]):
            text = el.get_text(" ", strip=True)
            if 100 < len(text) < 30000:
                tag = el.name
                cls_short = ".".join(el.get("class") or [])
                print(f"  <{tag} id={idv} class={cls_short}> len={len(text)}")
                print(f"    preview: {text[:120]}...")

    print("\n--- 의미있는 <p> 5개 ---")
    pcount = 0
    for p in soup.find_all("p"):
        t = p.get_text(strip=True)
        if 30 < len(t) < 1000:
            parent = p.parent
            pcls = ".".join(parent.get("class") or [])
            print(f"  <p in {parent.name}.{pcls}>: {t[:100]}")
            pcount += 1
            if pcount >= 5:
                break
