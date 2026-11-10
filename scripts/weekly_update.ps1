# KITECH 홍보 허브 — 주간 자동 갱신 (작업 스케줄러: 매주 월요일 08:30)
#
#  1. 보도자료 성과분석  : 새 보도자료 수집 + 집계 중(배포 67일 이내) 재검색 → 엑셀·주간 메모·허브용 CSV
#  2. 허브 4채널 증분 수집: 보도자료·포토뉴스·블로그(새 글만) + 유튜브(목록 전체, 30초) + 반응 지표(조회수·댓글)
#  3. 안전장치          : 보도성과 검사·복사 → 월간 보고서(2026-10~) → 테스트 → 채널 건수 급감 검사
#  4. 커밋·푸시          : 3이 모두 통과할 때만. 푸시하면 Streamlit Cloud가 1~2분 뒤 자동 반영
#
# 수동 실행:  powershell -ExecutionPolicy Bypass -File scripts\weekly_update.ps1 [-NoPush]
# 로그:      logs\weekly_YYYYMMDD_HHmm.log  ·  마지막 결과 한 줄: logs\last_status.txt
#
# ⚠ PowerShell 5.1은 파이썬이 stderr로 쓴 로그를 '오류'로 바꿔 스크립트를 멈춘다(2026-11-10 실측).
#   그래서 모든 단계를 cmd /c 로 실행하고 출력은 cmd가 파일로 돌린다.
param([switch]$NoPush)

$ErrorActionPreference = 'Continue'
$hub = Split-Path $PSScriptRoot -Parent
$prc = Join-Path (Split-Path $hub -Parent) '보도자료 성과분석'
$logDir = Join-Path $hub 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd_HHmm'
$log = Join-Path $logDir "weekly_$stamp.log"
$utf8 = New-Object System.Text.UTF8Encoding($false)

$env:PYTHONIOENCODING = 'utf-8'
$env:TQDM_DISABLE = '1'   # 진행 막대가 로그를 수천 줄로 불리는 것 방지

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe' }
$prcPy = Join-Path $prc '.venv\Scripts\python.exe'

function Note([string]$msg) {
    [IO.File]::AppendAllText($log, "`r`n[$(Get-Date -Format 'HH:mm:ss')] $msg`r`n", $utf8)
}

function Step([string]$name, [string]$workdir, [string]$cmdline) {
    Note "▶ $name"
    cmd /c "cd /d `"$workdir`" && $cmdline >> `"$log`" 2>&1"
    $code = $LASTEXITCODE
    Note "◀ $name — exit $code"
    return $code
}

$warn = @()
$block = @()

# 1. 보도자료 성과분석 (exit 2 = 네이버 한도 등으로 검색만 중단, 산출물은 저장됨)
$env:PYTHONPATH = 'src'
$c = Step '보도자료 성과분석 weekly' $prc "`"$prcPy`" -m prc.cli weekly"
Remove-Item Env:PYTHONPATH
if ($c -eq 2) { $warn += '성과분석 검색 중단(한도·키) — 주간 메모 확인' }
elseif ($c -ne 0) { $warn += "성과분석 실패(exit $c) — 보도성과는 지난주 값 유지" }

# 2. 허브 채널 수집 — 한 채널이 실패해도 나머지는 진행(급감 검사가 지워진 데이터를 막는다)
$collect = [ordered]@{
    '보도자료' = 'scripts\collect_kitech.py --board press --incremental'
    '포토뉴스' = 'scripts\collect_kitech.py --board photo --incremental'
    '블로그'   = 'scripts\collect_naver_blog.py --incremental'
    '유튜브 목록' = 'scripts\collect_youtube.py --fetch'
    '유튜브 병합' = 'scripts\collect_youtube.py --merge'
    '반응 지표' = 'scripts\collect_metrics.py'   # 최근 400일 홈페이지 조회수 + 블로그 댓글 + 이력(유튜브 조회수는 병합 단계에서)
}
foreach ($k in $collect.Keys) {
    $c = Step "수집: $k" $hub "`"$py`" $($collect[$k])"
    if ($c -ne 0) { $warn += "수집 실패: $k" }
}

# 3. 안전장치
if ((Step '보도성과 가져오기' $hub "`"$py`" scripts\hub_guard.py import-perf") -ne 0) { $warn += '보도성과 가져오기 막힘 — 지난주 값 유지' }
if ((Step '월간 보고서' $hub "`"$py`" scripts\monthly_report.py") -ne 0) { $warn += '월간 보고서 생성 실패 — 지난주 판 유지' }
if ((Step '테스트' $hub "`"$py`" -m pytest -q tests") -ne 0) { $block += '테스트 실패' }
if ((Step '데이터 급감 검사' $hub "`"$py`" scripts\hub_guard.py check") -ne 0) { $block += '데이터 급감' }

# 4. 커밋·푸시
$result = ''
if ($block.Count -gt 0) {
    $result = "막음: $($block -join ', ') — 커밋·푸시 안 함"
} else {
    git -C $hub add -- 'data/허브-데이터셋.csv' 'data/보도성과.csv' 'data/보도성과_매체.csv' 'data/보도성과_meta.json' `
        'data/보도성과_분야.csv' 'data/지표_이력.csv' 'reports' 2>$null
    git -C $hub diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        $result = '변경 없음'
    } else {
        $msg = "data: 주간 자동 갱신 $(Get-Date -Format 'yyyy-MM-dd')"
        if ($warn.Count -gt 0) { $msg += " (경고: $($warn -join '; '))" }
        $c = Step '커밋' $hub "git commit -q -m `"$msg`""
        if ($c -ne 0) { $result = '커밋 실패' }
        elseif ($NoPush) { $result = '커밋함(푸시 생략 -NoPush)' }
        else {
            $c = Step '푸시' $hub 'git push -q origin main'
            $result = if ($c -eq 0) { '푸시함 — Streamlit Cloud 1~2분 뒤 반영' } else { '푸시 실패 — 다음 실행 때 같이 올라감' }
        }
    }
}

$status = "$(Get-Date -Format 'yyyy-MM-dd HH:mm') | $result"
if ($warn.Count -gt 0) { $status += " | 경고: $($warn -join '; ')" }
Note $status
[IO.File]::WriteAllText((Join-Path $logDir 'last_status.txt'), $status + "`r`n", $utf8)
# 오래된 로그는 12주치만 남긴다
Get-ChildItem $logDir -Filter 'weekly_*.log' | Sort-Object Name -Descending | Select-Object -Skip 12 | Remove-Item -Force
Write-Output $status
if ($block.Count -gt 0) { exit 1 }
exit 0
