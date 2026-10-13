#!/usr/bin/env bash
# snapcut 설치: 필수 도구 → Python 가상환경 → HyperFrames·키트 → Finder 빠른 동작. 여러 번 실행해도 안전하다.
set -euo pipefail
cd "$(dirname "$0")"

say() { printf '\n▶ %s\n' "$1"; }
die() { printf '\n✗ %s\n' "$1" >&2; exit 1; }

[ "$(uname)" = Darwin ] || die "snapcut은 macOS 전용입니다."

WITH_SAM2=0
for arg in "$@"; do
  case "$arg" in
    --with-sam2) WITH_SAM2=1 ;;  # Barty-Bart object-separation (SAM 2): torch 등 수 GB — 기본 설치에는 없다
    *) die "알 수 없는 옵션: $arg (가능: --with-sam2)" ;;
  esac
done

need() {  # $1 명령, $2 brew 패키지 — 없으면 Homebrew로 설치
  command -v "$1" >/dev/null && return
  command -v brew >/dev/null || die "$1이(가) 없습니다. Homebrew(https://brew.sh)를 설치한 뒤 다시 실행하세요."
  say "$2 설치 (brew)"
  brew install "$2"
}

say "필수 도구 확인"
need ffmpeg ffmpeg
need node node
need whisper-cli whisper-cpp  # 롱폼 자막 전사 — 모델(약 3GB)은 첫 전사 때 공용/모델/에 받는다
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

say "Python 패키지 설치 (.venv, $("$PY" --version))"
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e '.[dev,promo]'
.venv/bin/python -m playwright install chromium  # pipeline capture (키트 seek 페이지 → mp4)

say "HyperFrames 내려받기 + 작업 스킬 설치"
npx -y hyperframes@0.8.149 --version >/dev/null
npx -y hyperframes@0.8.149 skills update music-to-video talking-head-recut embedded-captions faceless-explainer motion-graphics product-launch-video general-video

say "외부 모션 키트 받기 (kits.lock)"
.venv/bin/python -m pipeline kits
npm i --prefix kits --no-audit --no-fund --silent playwright@1.63.0  # animate 키트 도구 (kits/는 git 제외)
if [ "$WITH_SAM2" = 1 ]; then
  say "SAM 2 사물 분리 (kits/.object-separation, 키트 object-separation SKILL.md의 패키지)"
  [ -x kits/.object-separation/bin/python ] || "$PY" -m venv kits/.object-separation
  kits/.object-separation/bin/pip install -q torch transformers opencv-python-headless pillow numpy
fi

say "Finder 빠른 동작 설치"
.venv/bin/python tools/install_quick_action.py

mkdir -p "공용/음악" projects
.venv/bin/python -m pipeline --help >/dev/null

say "완료"
echo "  1) 공용/음악/ 에 곡을 넣고"
echo "  2) projects/<영상명>/영상소스/ 에 사진·영상을 넣은 뒤"
echo "  3) Claude Code에서 /snapcut <영상명>"
echo "  자세한 사용법: README.md"
