# 에이전트 상시 실행 + 자동 업데이트 감독 스크립트
#
# 매일 아침(또는 부팅 시) 이 스크립트 하나만 실행하면 된다:
#   - 노트북 전용 크롬(CDP)을 띄우고
#   - `easyone_agent run`을 돌리다가, 에이전트가 "origin에 새 버전이 있다"며
#     스스로 멈추면(종료 코드 3) git pull · uv sync 후 다시 실행한다
#   - 로그인 실패로 멈추면(종료 코드 2) 계정 잠금을 막기 위해 **재시작하지 않고** 멈춘다 —
#     `uv run python -m easyone_agent setup` 으로 자격 증명을 고친 뒤 이 스크립트를 다시 실행한다
#
# 크레덴셜(토큰·위하고/홈택스/위택스 ID·PW·공인인증서 비밀번호)은 Windows 자격 증명
# 관리자에만 있고, 이 스크립트의 git pull·uv sync는 코드만 건드린다 (§1 약관 논리상
# 실행 주체는 항상 이 노트북 — 서버가 아니다. plan/16-wehago-rpa.md §1).
#
# Windows 작업 스케줄러 등록 (관리자 PowerShell, 1회):
#   $action    = New-ScheduledTaskAction -Execute "powershell.exe" `
#                  -Argument "-ExecutionPolicy Bypass -File `"$env:USERPROFILE\taxflow\rpa-agent\scripts\run-agent.ps1`""
#   $trigger   = New-ScheduledTaskTrigger -AtLogOn
#   $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBattery -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
#   Register-ScheduledTask -TaskName "EasyoneAgent" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest

param(
    [string] $Branch       = "main",
    [int]    $RetryWaitSec = 60
)

$ErrorActionPreference = "Continue"
$repoDir = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoDir

# easyone_agent.__main__ 의 EXIT_LOGIN_FAILED(2) / EXIT_UPDATE_AVAILABLE(3) 과 짝을 이룬다.

function Update-AgentCode {
    try {
        git fetch --quiet origin $Branch
        $local  = (git rev-parse HEAD).Trim()
        $remote = (git rev-parse "origin/$Branch").Trim()
        if ($local -ne $remote) {
            $localShort = $local.Substring(0, 7)
            $remoteShort = $remote.Substring(0, 7)
            Write-Host "새 버전 발견 ($localShort -> $remoteShort) — 업데이트합니다."
            git pull --ff-only origin $Branch
            uv sync
            return $true
        }
    } catch {
        Write-Warning "업데이트 확인/적용 실패 (네트워크 또는 git 상태 문제) — 현재 버전으로 계속 실행합니다: $_"
    }
    return $false
}

powershell -ExecutionPolicy Bypass -File ".\scripts\start-chrome.ps1"

while ($true) {
    Update-AgentCode | Out-Null

    Write-Host "에이전트 실행 시작: uv run python -m easyone_agent run"
    uv run python -m easyone_agent run
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 2) {
        Write-Error "위하고/홈택스 로그인 실패로 에이전트가 멈췄습니다. 계정 잠금 방지를 위해 자동 재시작하지 않습니다."
        Write-Error "uv run python -m easyone_agent setup 으로 자격 증명을 다시 확인한 뒤 이 스크립트를 다시 실행하세요."
        break
    }
    if ($exitCode -eq 3) {
        Write-Host "업데이트 반영을 위해 즉시 재시작합니다."
        continue
    }

    Write-Warning "에이전트가 예기치 않게 종료됐습니다 (exit $exitCode). ${RetryWaitSec}초 후 다시 시도합니다."
    Start-Sleep -Seconds $RetryWaitSec
}
