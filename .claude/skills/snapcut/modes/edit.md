# 편집 모드 (edit)

렌더 후 마스터링·점검과 완성 보고는 SKILL.md §3을 따른다.

말하는 영상 하나를 처음부터 끝까지 살리며 쉼·실수를 자르고, 그 위에 오버레이(제목·강조·B롤)를 얹는다. 키트는 `kits/hyperframes-student-kit`(HyperFrames **0.7.109** 고정 — 이 모드의 구성은 0.8 스킬로 쓰지 않는다). 작업 폴더는 `projects/<이름>/work/edit/`(키트의 `video-projects/<slug>/`와 같은 모양).

1. **자르기 준비** — `.venv/bin/python -m pipeline edit <이름> [--file 파일] [--track N]`을 `run_in_background`로. 처음이면 Whisper 모델(약 3GB)을 받는다고 먼저 말한다. 하는 일: 원본을 영상 1·목소리 트랙 1로 정리(HDR은 SDR로) → 단어 단위 전사(`assets/raw.json`, 키트 형식) → 키트 무음 컷(`assets/silenced.mp4`) → 실수 후보(`assets/candidates.json`). 출력의 길이 변화를 사용자에게 전한다.
2. **실수 고르기** — `assets/candidates.json`(키트 후보 + 한국어 말더듬 `k…`)과 `assets/raw.silence-transcript.json`의 문장을 처음부터 읽는다. 키트의 다시 말하기·말 끊김 검출은 영어만 읽으므로 **한국어 다시 말하기는 문장을 읽고 직접 찾는다**(같은 말을 다시 시작한 앞쪽 시도를 자름). 판단 기준은 `kits/hyperframes-student-kit/.claude/skills/cut-mistakes/SKILL.md`. 결과를 `assets/approved-cuts.json`에 `{"cuts": [{"start": 초, "end": 초, "reason": "…"}]}`로 쓴다. 시간은 **silenced.mp4 기준**(silence-transcript의 `start/end`). 자를 게 없으면 `{"cuts": []}`. 애매한 후보는 자르지 않는다.
3. **적용** — `.venv/bin/python -m pipeline edit <이름> --cuts` → `assets/clean.mp4`, `assets/transcript.json`(clean 기준 단어 시각), `assets/clean.srt`, 그리고 없을 때만 시작 구성 `index.html`(영상 + 소리만). 다시 실행해도 `index.html`은 덮어쓰지 않는다.
4. **B롤 (선택, Barty-Bart motion-broll)** — 사용자가 B롤·설명 그래픽을 원할 때. `kits/motion-graphics/skills/motion-broll/SKILL.md`를 읽고 그대로 따르되:
   - 작업 폴더(cwd)는 `projects/<이름>/work/edit/` (`./motion/`이 그 안에 생김), 영상은 `assets/clean.mp4`, 자막은 `assets/clean.srt`.
   - 인터뷰의 영상·자막 질문은 위 파일로 대신하고, 밀도·룩만 사용자에게 추천과 함께 정한다.
   - 클립 fps는 clean.mp4의 fps. 투명 패널(`bg:null`)은 `.mov`.
   - 끝나면 키트의 `composite.py`가 만든 `motion/out/preview.mp4`(원본 소리 포함)를 `index.html`의 `<video id="clean">`·`<audio id="clean-audio">` src로 바꾼다(B롤이 박힌 바탕 위에 오버레이를 얹는 순서).
5. **오버레이** — `kits/hyperframes-student-kit/.claude/skills/`의 `hyperframes-video-beats`, `video-storytelling`, `style-library`를 읽고 `index.html`에 쓴다. 시간은 `assets/transcript.json` 단어 시각에 맞춘다. 키트 규칙 중 ElevenLabs·Kie.ai(유료)는 쓰지 않는다. 문법 검사: `npx -y hyperframes@0.7.109 lint projects/<이름>/work/edit`.
6. **확인** — `.venv/bin/python -m pipeline studio <이름>`을 백그라운드로 띄우고 http://localhost:3002 를 알려준다. 수정은 `index.html`(오버레이) 또는 approved-cuts → `--cuts`.
7. **렌더** — `.venv/bin/python -m pipeline render <이름>` → `output/<이름>_edit.mp4` + `.srt`. 계획 파일이 없는 모드라 점검은 처음·끝 2초 검정만 의도한 것으로 본다.

숏폼(9:16)은 요청할 때만: `kits/hyperframes-student-kit/.claude/skills/short-form-edit/SKILL.md`를 따른다(아직 `pipeline` 명령으로 묶지 않음 — 렌더는 `npx -y hyperframes@0.7.109 render <폴더> -o output/...` 후 `pipeline master`·`pipeline check`).
