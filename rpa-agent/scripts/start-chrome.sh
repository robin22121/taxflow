#!/usr/bin/env bash
# macOS용 CDP Chrome 실행 (start-chrome.ps1 macOS 대응)
#
# 이지원천 전용 프로필로 원격 디버깅 포트(기본 9222)를 열어 크롬을 띄운다.
# 위하고·홈택스·위택스 로그인은 이 프로필에서만 유지된다 (사용자 개인 크롬과 격리).
#
# 실행: bash scripts/start-chrome.sh [PORT]

set -e

PORT="${1:-9222}"
PROFILE_DIR="${EASYONE_CHROME_PROFILE:-$HOME/.easyone-agent/chrome-profile}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if [ ! -x "$CHROME" ]; then
    echo "Google Chrome이 /Applications 에 없습니다: $CHROME" >&2
    exit 1
fi

if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "이미 CDP 포트 $PORT 이 열려 있습니다. 그대로 사용합니다."
    exit 0
fi

mkdir -p "$PROFILE_DIR"

echo "크롬 실행: $CHROME (포트 $PORT, 프로필 $PROFILE_DIR)"
"$CHROME" \
    --remote-debugging-port="$PORT" \
    --user-data-dir="$PROFILE_DIR" \
    --no-first-run \
    --no-default-browser-check \
    --disable-features=BlockThirdPartyCookies,PrivacySandboxSettings4 \
    >/dev/null 2>&1 &

echo "PID $! — 이 창을 로그인·실측에 사용하세요."
