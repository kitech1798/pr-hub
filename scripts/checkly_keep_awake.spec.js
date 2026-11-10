// Checkly 브라우저 점검용 — 홍보 허브(Streamlit Cloud) 깨우기
// 사용: Checkly → Create → Browser check → 이 파일 내용을 그대로 붙여 넣기 → 주기 3시간(또는 1시간)
// 하는 일: 실제 브라우저로 앱을 연다 → 잠들어 있으면 "Yes, get this app back up!" 클릭 → 앱 제목이 뜰 때까지 기다린다
// 실패하면(앱이 안 뜨면) Checkly가 이메일로 알려 준다 = 잠들기 방지 + 장애 감시를 겸한다.
const { test, expect } = require('@playwright/test')

const APP_URL = 'https://kitech-pr-platform.streamlit.app/'
const READY_TEXT = 'KITECH 홍보 허브'

test('KITECH 홍보 허브 깨우기', async ({ page }) => {
  test.setTimeout(150_000)
  await page.goto(APP_URL, { waitUntil: 'domcontentloaded', timeout: 60_000 })
  await page.waitForTimeout(5_000)

  // 잠든 앱이면 깨우기 버튼(최상위 문서에 뜬다)
  let wake = page.getByRole('button', { name: /get this app back up/i })
  if ((await wake.count()) === 0) wake = page.getByText(/get this app back up/i)
  if ((await wake.count()) > 0) await wake.first().click()

  // 앱 본문은 iframe 안에서 그려진다 — 모든 프레임에서 제목을 찾는다(깨우는 중이면 부팅에 1~2분)
  const deadline = Date.now() + 120_000
  let ready = false
  while (!ready && Date.now() < deadline) {
    for (const f of page.frames()) {
      if ((await f.getByText(READY_TEXT).count()) > 0) { ready = true; break }
    }
    if (!ready) await page.waitForTimeout(5_000)
  }
  expect(ready, '앱이 2분 안에 그려지지 않음').toBeTruthy()
  await page.waitForTimeout(5_000) // 세션이 잡히도록 잠시 머문다
})
