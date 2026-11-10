"""허브 앱(Streamlit Community Cloud)이 잠들지 않게 실제 브라우저로 방문한다.

왜 브라우저인가
    Community Cloud는 12시간 동안 '보는 사람'이 없으면 앱을 재운다. curl·HTTP 호출은 인증 리다이렉트에서 멈춰
    앱 세션이 생기지 않으므로 타이머가 리셋되지 않는다 — Chromium이 페이지를 끝까지 열어야 한다.

왜 이 PC의 작업 스케줄러인가
    같은 일을 하던 GitHub Actions 로봇(naonjip·export-safety-belt 저장소)은 2026-08부터 계정 결제 문제로
    작업이 시작조차 안 되고 있었다(실행 3초 실패, "recent account payments have failed"). 결제가 풀리면
    Actions로 옮겨도 되지만, 그 전까지는 이 PC가 3시간마다 방문한다. PC가 꺼져 있던 동안 잠들면
    켜진 직후 첫 실행이 깨우기 버튼을 누른다(StartWhenAvailable).

    python scripts/keep_awake.py          # 결과 한 줄 → logs/keep_awake.log
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

APP_URL = "https://kitech-pr-platform.streamlit.app/"
LOG = Path(__file__).resolve().parents[1] / "logs" / "keep_awake.log"
WAKE_TEXT = "get this app back up"   # 잠든 앱 화면의 버튼: "Yes, get this app back up!"
READY_TEXT = "KITECH 홍보 허브"        # 앱이 실제로 그려졌다는 증거(히어로 제목)


def visit(url: str = APP_URL) -> str:
    """'awake'(이미 깨어 있음) / 'woken'(깨움) / 'fail:<이유>'."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(6_000)
            state = "awake"
            # 잠든 앱 화면은 앱 iframe 바깥(최상위 문서)에 버튼이 뜬다
            btn = page.get_by_role("button", name=WAKE_TEXT, exact=False)
            if btn.count() == 0:  # 잠든 화면 마크업이 바뀌어 버튼 역할이 빠져도 문구로 찾는다(잠든 상태를 직접 시험할 수 없어 이중화)
                btn = page.get_by_text(WAKE_TEXT, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=10_000)
                state = "woken"
            # 앱 본문은 iframe 안에서 그려진다 — 모든 프레임에서 제목을 찾는다
            deadline = 180_000 if state == "woken" else 60_000  # 깨우면 컨테이너 부팅에 1~3분
            step = 5_000
            for _ in range(deadline // step):
                if any(f.get_by_text(READY_TEXT).count() > 0 for f in page.frames):
                    page.wait_for_timeout(5_000)  # 세션이 잡히도록 잠시 머문다
                    return state
                page.wait_for_timeout(step)
            return f"fail:{state} 후 {deadline // 1000}초 안에 앱이 그려지지 않음"
        except PWTimeout as e:
            return f"fail:시간 초과 {e.message[:80]}"
        finally:
            browser.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = visit()
    except Exception as e:  # 브라우저 실행 실패 등 — 로그에 남기고 실패 코드로
        result = f"fail:{type(e).__name__} {e}"[:200]
    line = f"{datetime.now():%Y-%m-%d %H:%M} | {result}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    # 로그가 끝없이 자라지 않게 최근 500줄만
    lines = LOG.read_text(encoding="utf-8").splitlines()
    if len(lines) > 500:
        LOG.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    print(line)
    return 1 if result.startswith("fail") else 0


if __name__ == "__main__":
    sys.exit(main())
