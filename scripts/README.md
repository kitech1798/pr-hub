# KITECH 홍보 허브 — 수집 스크립트

보도자료(`/pages/61`)와 포토뉴스(`/pages/60`) 게시판에서 메타데이터를 모아 `data/허브-데이터셋.csv`에 누적합니다.

## 0. 사전 준비 (최초 1회)

PowerShell에서 프로젝트 폴더로 이동 후 패키지 설치.

```powershell
cd C:\Users\admin\Desktop\교육\기관-홍보-허브
python -m pip install -r scripts\requirements.txt
```

## 1. 구조 점검 — 항목 3개만 콘솔에 찍어보기

스크래핑이 제대로 동작하는지 가장 먼저 확인.

```powershell
python scripts\collect_kitech.py --board press --inspect
python scripts\collect_kitech.py --board photo --inspect
```

출력에서 **id / title / url / thumbnail / date** 가 모두 채워져 보이면 정상.
일부가 비어 있으면 KITECH 페이지 마크업 변동 → 수집 로직 보정 필요(연락 주세요).

## 2. 1페이지만 시험 수집

전체 돌리기 전에 한 페이지만 돌려서 CSV 생성·내용 확인.

```powershell
python scripts\collect_kitech.py --board press --pages 1
```

`data\허브-데이터셋.csv`가 생기고, 약 9행이 채워집니다. 엑셀로 열어 컬럼이 맞는지 확인.

## 3. 전체 수집

```powershell
python scripts\collect_kitech.py --board press      # 약 250건 — 약 5~7분
python scripts\collect_kitech.py --board photo      # 약 1,085건 — 약 15~20분
```

서버 부담 완화를 위해 요청 사이 0.5초 대기. 둘 다 같은 CSV에 채널 컬럼으로 구분되어 누적됩니다.

### 보도자료 카테고리 구조

KITECH 보도자료는 categoryId로 분리되어 있습니다.
- `categoryId=50` — 보도자료 (2026년~)
- `categoryId=49` — 과거 (2016~2025, 약 220건)
- `categoryId=51` — 아카이브

기본적으로 [50, 49, 51] 모두 순회하며 id 중복은 자동 dedup. 일부만 받고 싶다면:

```powershell
python scripts\collect_kitech.py --board press --categories 50,49
```

## 4. 주간 자동 갱신 (매주 월요일 08:30)

작업 스케줄러 `KITECH_홍보_주간갱신`이 `scripts\weekly_update.ps1`을 실행합니다.

1. `..\보도자료 성과분석` 주간 갱신 → 보도성과 CSV 내보내기
2. 4채널 증분 수집 (`--incremental`: 이미 가진 글만 나오는 페이지에서 멈추고 새 글만 상세 수집)
3. `hub_guard.py import-perf`(보도성과 검사·복사) → `pytest tests`(앱 렌더 포함) → `hub_guard.py check`(채널 건수 5% 넘게 줄면 막음)
4. 모두 통과하면 `data/` 커밋·푸시 → Streamlit Cloud 자동 반영

```powershell
powershell -ExecutionPolicy Bypass -File scripts\weekly_update.ps1 -NoPush   # 푸시 없이 시험
Get-Content logs\last_status.txt                                            # 마지막 결과 한 줄
Start-ScheduledTask -TaskName KITECH_홍보_주간갱신                            # 지금 한 번 돌리기
```

## 5. 반응 지표 · 월간 보고서

| 채널 | 공개 지표 | 수집 |
|---|---|---|
| 보도자료·포토뉴스 | 홈페이지 게시판 '조회수'(누적) | `collect_metrics.py` (매주 최근 400일, `--all` 전체 약 15분) |
| 유튜브 | view_count | `collect_youtube.py --merge` |
| 블로그 | 조회수 비공개 → 댓글 수만 | `collect_metrics.py` |

- 이력은 `data/지표_이력.csv`에 쌓인다(2026-11-10부터). 한 달 이상 쌓이면 '그달 늘어난 조회수'를 계산할 수 있다.
- 월간 보고서: `python scripts\monthly_report.py` → `reports\monthly_report_YYYY-MM.html`(2026-10부터). Good·Bad·시사점·개선점은 숫자 규칙으로 뽑는다(판정 기준은 보고서 맨 아래).
- 데이터셋 열 정의는 `common.py`의 `CSV_FIELDS` 한 곳에만 있다. 수집기마다 따로 두면 저장할 때 다른 수집기의 열을 지운다.

## 산출 컬럼

| 컬럼 | 설명 | v1 화면 노출 |
|---|---|---|
| 채널 | 보도자료 / 포토뉴스 (앞으로 유튜브·블로그 추가) | 탭 분류 키 |
| 게시일 | YYYY-MM-DD | ✅ |
| 제목 | 게시글 제목 | ✅ |
| 주요내용 | 본문 첫 200자(자동 발췌, 추후 AI 요약으로 교체) | ✅ |
| 링크 | 원문 URL | ✅ |
| id | 게시글 고유 ID | (내부 키) |
| 썸네일URL | 이미지 URL (v2에서 활용) | (v2) |
| 분야태그 | 추후 AI 분류 + 본인 검수 | (v2) |
| 비고 | 수기 메모 | - |

## 트러블슈팅

- `ModuleNotFoundError: No module named 'lxml'` → 0번 단계 다시
- `requests.exceptions.SSLError` → 회선/방화벽 문제. 사내망에서 안 되면 외부망에서 시도
- 항목 일부가 비어 나옴 → `--inspect` 결과 공유 부탁드립니다
