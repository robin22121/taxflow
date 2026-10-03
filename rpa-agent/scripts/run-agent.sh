#!/usr/bin/env bash
# 에이전트 상시 실행 + 자동 업데이트 감독 스크립트 (macOS) — run-agent.ps1 의 맥 대응
#
# 이 스크립트 하나만 실행하면 된다:
#   - `easyone_agent start`가 크롬(CDP)을 확인·실행하고, 위하고·홈택스에 로그인한 뒤 작업을 기다린다.
#     이미 로그인된 크롬이면 입력 없이 통과한다.
#   - 에이전트가 "origin에 새 버전이 있다"며 멈추면(종료 코드 3) git pull · uv sync 후 다시 실행한다.
#   - 로그인 실패로 멈추면(종료 코드 2) 계정 잠금을 막기 위해 **재시작하지 않고** 멈춘다 —
#     `uv run python -m easyone_agent setup` 으로 자격 증명을 확인한 뒤 다시 실행한다.
#
# 실행: bash rpa-agent/scripts/run-agent.sh [브랜치, 기본 main]

BRANCH="${1:-main}"
RETRY_WAIT_SEC=60

cd "$(dirname "$0")/.." || exit 1

update_agent_code() {
    git fetch --quiet origin "$BRANCH" || { echo "업데이트 확인 실패 — 현재 버전으로 계속합니다"; return; }
    local_sha="$(git rev-parse HEAD)"
    remote_sha="$(git rev-parse "origin/$BRANCH")"
    if [ "$local_sha" != "$remote_sha" ]; then
        echo "새 버전 발견 (${local_sha:0:7} -> ${remote_sha:0:7}) — 업데이트합니다."
        git pull --ff-only origin "$BRANCH" && uv sync
    fi
}

while true; do
    update_agent_code

    echo "에이전트 실행 시작: uv run python -m easyone_agent start"
    uv run python -m easyone_agent start
    exit_code=$?

    if [ "$exit_code" -eq 2 ]; then
        echo "위하고/홈택스 로그인 실패로 에이전트가 멈췄습니다. 계정 잠금 방지를 위해 자동 재시작하지 않습니다." >&2
        echo "uv run python -m easyone_agent setup 으로 자격 증명을 다시 확인한 뒤 이 스크립트를 다시 실행하세요." >&2
        break
    fi
    if [ "$exit_code" -eq 3 ]; then
        echo "업데이트 반영을 위해 즉시 재시작합니다."
        continue
    fi

    echo "에이전트가 예기치 않게 종료됐습니다 (exit $exit_code). ${RETRY_WAIT_SEC}초 후 다시 시도합니다." >&2
    sleep "$RETRY_WAIT_SEC"
done
