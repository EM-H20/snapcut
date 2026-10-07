# snapcut

여행·행사 후 쌓인 사진/영상을 음악 비트에 맞춘 추억 뮤비로 자동 편집. Claude Code에서 `/snapcut <영상명>`.

## 설치
```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd render && npm install && cd ..
.venv/bin/python tools/install_quick_action.py   # Finder 우클릭 변환 버튼
```
필요: macOS, ffmpeg(`brew install ffmpeg`), Node 22+.

렌더링은 설치된 Google Chrome을 사용한다(render/remotion.config.ts) — 번들 브라우저가 이 Mac에서 실행되지 않음. 다른 Chrome 경로는 SNAPCUT_CHROME 환경변수로 지정.

## 사용
1. `projects/<영상명>/영상소스/`에 사진·영상을 넣는다 (jpg/png/heic/mp4/mov).
2. `공용/음악/`에 곡을 넣는다.
3. Claude Code에서 `/snapcut <영상명>`.

변환만 미리: Finder에서 `영상소스` 폴더 우클릭 → 빠른 동작 → "snapcut 영상소스 변환".

### 빠른 동작 수동 설치 (스크립트가 안 될 때)
Automator → 새 문서 → 빠른 동작 → "작업 흐름이 받는 항목: 폴더 / Finder" → "셸 스크립트 실행"(입력 전달: 인수로) → `tools/install_quick_action.py`의 `SCRIPT` 내용을 붙여넣고 `{ROOT}`·`{LOG}`를 실제 경로로 → 저장 이름 "snapcut 영상소스 변환".

## 라이선스 메모
렌더링에 [Remotion](https://www.remotion.dev/license)을 사용한다 — 개인 무료, 일정 규모 이상 회사는 유료 라이선스. HyperFrames는 Apache 2.0.

선택: Remotion 공식 Claude 스킬 `npx skills add remotion-dev/skills`.
