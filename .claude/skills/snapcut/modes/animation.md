# 짧은 애니메이션 모드 (animation)

렌더 후 마스터링·점검과 완성 보고는 SKILL.md §3을 따른다. 영상소스가 없는 모드라 `projects/<이름>/`과 `brief.json`만 만든다. 아래 `P` = `projects/<이름>`, `W` = `P/work/animation`, `SK` = `kits/animate/plugins/animate/skills/animate`. **`.venv/bin/python -m pipeline …`은 저장소 루트에서, 키트 도구는 적힌 폴더에서 실행한다.**

## 키트 고르기 (추천 하나를 말하고 진행)
| 요청 | 키트 | 진행 |
|---|---|---|
| 기본: 설명 애니메이션, 손그림·종이·수학·아이소메트릭 화풍, 내레이션 | animate | §1 |
| 장면이 이어지는 모션그래픽, 장면 검토, 코드로 만든 효과음, 시뮬레이션·3D | claude-motion | §2 |
| Remotion 모션그래픽(릴스·가로), 키트 규칙 10개 | claude-remotion-skill | §3 |

공통:
- 키트 SKILL.md를 직접 읽고 따른다(animate `SK/SKILL.md`, claude-motion `kits/claude-motion/.claude/skills/*/SKILL.md`, claude-remotion-skill `kits/claude-remotion-skill/remotion-motion-graphics/SKILL.md`). Remotion 문법은 `kits/remotion-skills/skills/remotion-markup`·`remotion-render`를 참고로 읽는다(Studio부터 열라는 지시는 따르지 않고 렌더 + 스틸 확인).
- 유료·출처 불명은 끈다: ElevenLabs(animate 기본 음성, Remotion voiceover), remotion.media 효과음.
- 한국어 내레이션: `say -v Yuna --data-format=LEI16@48000 -o <폴더>/voice/<id>.wav "문장"`.
- 한국어 글자: 키트 글꼴엔 한글이 없어 시스템 한글 글꼴로 나온다(Remotion 컴포지션에서는 `"Apple SD Gothic Neo", system-ui, sans-serif`를 직접 지정). animate `pixel` 화풍은 한글을 못 그린다.
- 키트의 대조 시트 도구(animate `review.mjs`, claude-motion `npm run sheet`)는 ffmpeg `drawtext`가 필요한데 brew ffmpeg에는 없다. 프레임 확인은 스틸 명령과 `pipeline check`의 시트로 한다.
- 끝: 결과를 `P/output/<이름>_<키트>.mp4`로 두고 `.venv/bin/python -m pipeline master P/output/<파일>.mp4`(색 태그가 없으면 bt709 변환, 음량) → `.venv/bin/python -m pipeline check <이름> P/output/<파일>.mp4`.

## 1. animate (캔버스 + Playwright, 24fps)
처음 한 번 `kits/node_modules`에 Playwright가 있어야 한다(`.venv/bin/python -m pipeline kits`의 `node  playwright` 줄; 없으면 `npm i --prefix kits playwright@1.63.0`).
1. 화풍 데모를 피스로 복사(저장소 루트): `mkdir -p W/<피스> && cp -R SK/styles/<화풍>/demo/. W/<피스>/` (화풍: cut-paper, crosshatch, riso, sketchbook, math, pixel, isometric).
2. 음성(선택): `W/<피스>/voice/script.json` = `{"lead": 0.25, "tail": 0.4, "lines": [{"id": "l1", "text": "…", "after": 0.35}, …]}`, 줄마다 위 `say`로 `voice/<id>.wav`. 피스 폴더에서 `node <SK 절대경로>/tools/voice.mjs .` → `voice.json`(줄 시각). **한국어는 단어 시각이 비므로(키트 정규식이 한글을 지움) 줄 단위(`t0`/`t1`)로 큐를 맞춘다.** `piece.json`에 `"voice": {"file": "voice/voice.wav", "music": -12}`.
3. `src/head.html`의 `DURATION`·`ERA_LIST`·`SHOTS`·`cues`·`acts`, `src/scenes.js`, `src/bridges.js`, `src/score.js`를 음성 길이에 맞춘다.
4. 피스 폴더에서: `node <SK>/tools/build.mjs .` → `node <SK>/tools/still.mjs . 1.6,2.6,4.2,6.4 look.png --scale 0.5`(보고 고침) → `node <SK>/tools/export.mjs . --no-captions` → `renders/final.mp4` (자막 미리보기는 Menlo라 한글이 깨져 끔).
5. `cp W/<피스>/renders/final.mp4 P/output/<이름>_animate.mp4` → master → check. 어두운 화풍(math 등)의 얇은 선 화면은 점검이 검정으로 보지 않는다.

## 2. claude-motion (Remotion 4.0.529 + Python 효과음)
1. 프로젝트 사본(저장소 루트): `mkdir -p W/remotion && rsync -a --exclude media --exclude .git --exclude examples --exclude node_modules --exclude README.md --exclude .claude kits/claude-motion/ W/remotion/` → `W/remotion`에서 `npm ci --no-audit --no-fund`(약 300MB).
2. 박자 JSON 하나(`<영상>.json`: fps, duration, s1/s2/…) → `src/<영상>.tsx`(키트 `Mask`·`Grain`·`Background`·`Spark`, `lib.ts`의 easing·`prog`) → `src/Root.tsx`에 `<Composition>` 등록. **`lib.sp()`는 예시의 60fps 기준이라 다른 fps 영상에서는 스프링 시작이 어긋난다 — 그 영상 fps로 `spring()`을 감싼 helper를 쓴다.**
3. 스틸 확인(`W/remotion`에서): `npx remotion still src/index.ts <Id> out/s_<프레임>.png --frame=<프레임> --scale=0.33 --log=error`.
4. 효과음: `sfx/cues/<영상>.py`(TIMELINE = 박자 JSON, OUT = `public/<영상>.wav`, `score(mix, tl)`) → `python3 -m sfx sfx/cues/<영상>.py`.
5. 렌더 + 합치기(`W/remotion`에서): `npx remotion render src/index.ts <Id> out/<영상>-silent.mp4 --color-space=bt709 --log=error` → `ffmpeg -loglevel error -y -i out/<영상>-silent.mp4 -i public/<영상>.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 256k -movflags +faststart -shortest ../../../output/<이름>_claude-motion.mp4`.
- 시뮬레이션·3D는 `sims/`(키트 `web-sims` 스킬). 음악을 넣으면 -21 LUFS로 작게 나오니 master가 올린다.

## 3. claude-remotion-skill (같은 Remotion 사본 사용)
1. `W/remotion`에서: `cp <kits>/claude-remotion-skill/examples/scripts/gen-sfx.mjs scripts/ && node scripts/gen-sfx.mjs` → `public/sfx/{whoosh,pop,tick,bass,pad,pad19}.wav`. 테마는 `<kits>/claude-remotion-skill/remotion-motion-graphics/assets/theme.ts`를 `src/<폴더>/theme.ts`로 복사해 색·글꼴만 바꾼다.
2. 컴포지션은 키트 `references/motion-patterns.md`(배경 메시, 단어 등장, 그레이드, 그레인, 비네트, 퇴장, 숨쉬기, 효과음은 2–3프레임 먼저)대로 `src/<폴더>/`에 쓰고 Root에 등록. 길이 0인 선(`strokeLinecap="round"`)은 점으로 보이니 시작 전에는 그리지 않는다.
3. 스틸 확인은 §2-3과 같다. 렌더(소리 포함): `npx remotion render src/index.ts <Id> ../../../output/<이름>_remotion.mp4 --codec=h264 --crf=17 --color-space=bt709 --log=error`.
- Remotion 라이선스: 개인·소규모 팀 무료, 일정 규모 이상 회사는 유료(README).
