# snapcut

영상 만들기 전부의 입구(추억 뮤비·롱폼·편집·홍보·애니메이션·웹). 사용은 `/snapcut <이름> <요청>`.

## 구조
- `pipeline/` (Python): 변환·선별·분석·타임라인. `python -m pipeline <convert|prepare|plan|edit|words|capture|studio|render|music>`
- `pipeline/edit.py`: edit 모드 — whisper 단어 전사 → student-kit 컷 스크립트(kits/) → `work/edit/` 구성 (hyperframes@0.7.109)
- `pipeline/capture.py`: `window.seek` 페이지 → mp4 (Playwright, `.[promo]`)
- `pipeline/hf/`: storyboard → HyperFrames 구성 HTML(뮤비·롱폼·쇼츠)과 렌더·미리보기 실행 (hyperframes@0.8.149)
- `공용/음악/` 곡 라이브러리(git 제외), `공용/인트로아웃트로/<템플릿>/` HyperFrames 카드
- `projects/<이름>/영상소스/` 원본(읽기 전용), `selection.json`(Claude 작성), `.cache/`, `output/` — 전부 git 제외

## 명령
- 테스트: `.venv/bin/python -m pytest` (빠름), `.venv/bin/python -m pytest -m slow` (렌더 E2E)
- 품질 점검: `.venv/bin/python -m pipeline check <이름> [mp4]` (render가 끝나면 자동), 음량·색(태그 없는 영상은 bt709로 다시 인코딩): `pipeline master <mp4>`
- 외부 키트: `.venv/bin/python -m pipeline kits` (kits.lock 커밋으로 kits/에 받기)

## 규칙
- `영상소스/`에 쓰지 않는다.
- 음악 저작권 판단·경고를 넣지 않는다.
- 타이밍 계산은 `pipeline/plan.py`(결정적), Claude는 무엇을 넣을지와 문구만.
