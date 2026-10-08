#!/usr/bin/env bash
# snapcut 설치: 필수 도구 → Python 가상환경 → Remotion → Finder 빠른 동작. 여러 번 실행해도 안전하다.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n▶ %s\n' "$1"; }
die() { printf '\n✗ %s\n' "$1" >&2; exit 1; }

[ "$(uname)" = Darwin ] || die "snapcut은 macOS 전용입니다."

need() {  # $1 명령, $2 brew 패키지 — 없으면 Homebrew로 설치
  command -v "$1" >/dev/null && return
  command -v brew >/dev/null || die "$1이(가) 없습니다. Homebrew(https://brew.sh)를 설치한 뒤 다시 실행하세요."
  say "$2 설치 (brew)"
  brew install "$2"
}

say "필수 도구 확인"
need ffmpeg ffmpeg
need node node
node_major=$(node -p 'process.versions.node.split(".")[0]')
[ "$node_major" -ge 22 ] || die "Node 22 이상이 필요합니다 (현재 $(node -v)). 'brew upgrade node' 후 다시 실행하세요."

PY=""
for c in python3.14 python3.13 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 13))'; then
    PY=$c
    break
  fi
done
if [ -z "$PY" ]; then
  command -v brew >/dev/null || die "Python 3.13 이상이 필요합니다."
  say "Python 3.13 설치 (brew)"
  brew install python@3.13
  PY=python3.13
fi

CHROME="${SNAPCUT_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -x "$CHROME" ] || echo "  참고: Google Chrome이 없습니다. 렌더는 Remotion 번들 브라우저로 시도하며 일부 Mac에서는 실패합니다 — Chrome 설치를 권장합니다."

say "Python 패키지 설치 (.venv, $("$PY" --version))"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e '.[dev]'

say "Remotion 설치 (render/)"
(cd render && npm install --no-audit --no-fund --loglevel=error)

say "HyperFrames 내려받기 (인트로/아웃트로 카드용)"
npx -y hyperframes@0.8.140 --version >/dev/null

say "Finder 빠른 동작 설치"
.venv/bin/python tools/install_quick_action.py

mkdir -p "공용/음악" projects
.venv/bin/python -m pipeline --help >/dev/null

say "완료"
echo "  1) 공용/음악/ 에 곡을 넣고"
echo "  2) projects/<영상명>/영상소스/ 에 사진·영상을 넣은 뒤"
echo "  3) Claude Code에서 /snapcut <영상명>"
echo "  자세한 사용법: README.md"
