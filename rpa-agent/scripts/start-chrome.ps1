# 에이전트 전용 크롬 실행 (CDP)
#
# 노트북에 이미 설치된 크롬을 원격 디버깅 포트(9222)와 전용 프로필로 띄운다.
# 이 크롬에만 에이전트(Playwright `connect_over_cdp`)가 붙는다.
#
# 실행:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start-chrome.ps1
#
# 사용자 크롬(북마크·확장 등)과 섞이지 않게 별도 --user-data-dir을 쓰고,
# 이 프로필 안에서만 위하고·홈택스·위택스 로그인 상태를 유지한다.

param(
    [int]    $Port         = 9222,
    [string] $ProfileDir   = "$env:USERPROFILE\.easyone-agent\chrome-profile",
    [string] $ChromePath   = ""
)

$ErrorActionPreference = "Stop"

if (-not $ChromePath) {
    $candidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { $ChromePath = $p; break }
    }
}
if (-not $ChromePath -or -not (Test-Path $ChromePath)) {
    throw "chrome.exe를 찾지 못했습니다. -ChromePath 로 경로를 지정하세요."
}

# 포트가 이미 열려 있으면 (이미 실행 중이면) 재기동하지 않는다.
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listening) {
    Write-Host "이미 CDP 포트 $Port 이 열려 있습니다. 그대로 사용합니다."
    exit 0
}

New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null

# --disable-features: 자동화 감지 완화·크래시 리포트 팝업 억제
# --no-first-run·--no-default-browser-check: 무인 실행 방해 요소 제거
# --start-maximized: 실측 시 화면 확보
$args = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDir",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-features=BlockThirdPartyCookies,PrivacySandboxSettings4",
    "--start-maximized"
)

Write-Host "크롬 실행: $ChromePath (포트 $Port, 프로필 $ProfileDir)"
Start-Process -FilePath $ChromePath -ArgumentList $args
