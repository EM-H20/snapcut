# 제품 출시·소개 모드 (promo)

렌더 후 마스터링·점검과 완성 보고는 SKILL.md §3을 따른다. 영상소스가 없는 모드라 `projects/<이름>/`과 `brief.json`만 만들고, 작업은 `projects/<이름>/work/promo/`, 결과는 `projects/<이름>/output/`.

**경로:** `.venv/bin/python -m pipeline …`은 저장소 루트에서 실행하므로 `projects/<이름>/…` 전체 경로를 쓴다. 키트의 node·npx·python 스크립트는 작업 폴더(`projects/<이름>/work/promo/`)에서 실행한다(키트 경로가 cwd 기준). 아래 `W` = `projects/<이름>/work/promo`, `O` = `projects/<이름>/output`.

## 키트 고르기 (추천 하나를 말하고 진행)
| 요청 | 키트 | 진행 |
|---|---|---|
| 기본: 제품·서비스 출시 영상, 말(내레이션)로 끌고 가는 40~60초 | product-launch-motion | §1 |
| 차트, 숫자 공개, 브랜드 효과 한 가지, 애플식 필름, 릴스용 짧은 루프 | motion-graphics-skills | §2 |
| 음악에 맞춘 고급 런치 필름, 레퍼런스 영상 따라 만들기 | claude-motion-design | §3 |

공통 규칙:
- 키트 SKILL.md를 `kits/<키트>/…`에서 직접 읽고 따른다. 키트 파일은 고치지 않는다 — 고쳐 써야 하는 템플릿은 작업 폴더로 복사한다.
- 유료 키 기능은 끈다: 21st.dev, Firecrawl, ElevenLabs·Cartesia, Suno·Envato·Higgsfield, Kie.ai. 소재는 사용자가 준 것 + 키 없는 곳(Mixkit, svgl, simple-icons, picsum).
- 숫자·고객·인용은 지어내지 않는다(키트 진실 규칙). 예시 값은 화면에 "예시"로 표시한다.
- 한국어 내레이션: 사용자가 녹음을 주지 않으면 `say -v Yuna --data-format=LEI16@48000 -o W/assets/voice/<id>.wav "문장"`(macOS 기본 한국어 목소리 — `--data-format` 없이 .wav를 쓰면 실패) → 단어 시각은 `.venv/bin/python -m pipeline words W/assets/voice/<id>.wav --out W/transcripts/<id>.json`.
- 키트 자체 마스터링(product-launch `master.sh` 등)은 건너뛴다. 렌더 결과를 `O/<이름>_<결과물>.mp4`(launch, film, 스킬 이름 등)로 두고 `.venv/bin/python -m pipeline master O/<파일>.mp4` → `.venv/bin/python -m pipeline check <이름> O/<파일>.mp4`.
- 소리가 없는 결과물에 무음 트랙을 붙이지 않는다(점검은 소리가 없을 때만 음량을 건너뛴다).

## 1. product-launch-motion (HyperFrames 0.8.149)
`kits/product-launch-motion/SKILL.md`의 14단계. cwd는 `work/promo/`, 스크립트는 키트에서 바로 부른다(`node <키트>/scripts/assemble.mjs` — 모든 경로가 cwd 기준).
1. 인테이크·방향·진실 패스·대본(`BRIEF.md`, `SCRIPT.md`) — 키트 템플릿 `assets/BRIEF.md`.
2. 음성 먼저: 프레임마다 `assets/voice/<id>.wav`(위 `say`), 단어 시각 `pipeline words`(저장소 루트에서) → `transcripts/<id>.json` → 작업 폴더에서 `node <키트>/scripts/word-timings.mjs --in transcripts/ --out audio_meta.json` (`--transcript`를 쓸 때는 `--id` 필수).
3. 스토리보드 → 프레임 `compositions/frames/<id>.html`(키트 `assets/frame-skeleton.html` 복사), `film.json`, `audio/cues.json`(없으면 `{"cues":{}}`), GSAP는 `vendor/gsap.min.js`(키트 README의 curl 한 번).
4. 조립(매번 이 순서): `assemble.mjs` → `transitions.mjs` → `wire-audio.mjs` → `wire-grade.mjs`.
5. 검사: `npx -y hyperframes@0.8.149 lint .` (오류 0).
6. 렌더(작업 폴더에서): `npx -y hyperframes@0.8.149 render . -o ../../output/<이름>_launch.mp4` → master → check(저장소 루트에서).
- 키트 함정: 전환·그레인이 1920×1080 고정(다른 크기는 직접 고침), `cues.example.json`의 id는 예시 film과 안 맞음, 효과음은 mp3만.

## 2. motion-graphics-skills (seek 페이지 → `pipeline capture`)
스킬 15개(`kits/motion-graphics-skills/skills/<스킬>/SKILL.md`) 중 요청에 맞는 것 하나. brand-intake·motion-brief-writer·motion-prompt-writer·reference-to-motion은 글(브리프·프롬프트)만 만든다.
1. 스킬의 빌드 브리프대로 `W/<스킬>.html` 하나를 쓴다: `window.seek(초)`가 그 순간을 그리고, `?render`면 자동 재생하지 않음, 외부 요청 없음.
2. 렌더(저장소 루트에서): `.venv/bin/python -m pipeline capture W/<스킬>.html O/<이름>_<스킬>.mp4 --seconds <길이> --size <WxH> [--fps 30]` (vox-explainer는 24, loop-cover는 20).
3. 릴스면 `reel-export` 스킬의 ffmpeg 인코딩(1080x1920, 안전 영역 y 360–1420)을 쓰되 무음 트랙(`anullsrc`)은 빼고, 원본에 소리가 있을 때만 `-map 0:a`.
4. 소리를 코드로 만드는 스킬(vox-explainer, title-sequence-3d)은 capture가 소리를 담지 않으므로 소리를 wav로 따로 만들어 `ffmpeg -i 영상 -i 소리 -c:v copy -c:a aac -shortest`로 붙인다.

## 3. claude-motion-design (키트 Playwright 렌더러)
`kits/claude-motion-design/skill/motion-design/SKILL.md`. 키트의 `howseen-video/INDEX.md`는 저장소에 없으니 건너뛴다. Python 의존성은 snapcut venv(`.[promo]`)로 충분(`imageio-ffmpeg`만 필요하면 `.venv/bin/pip install imageio-ffmpeg`).
- 만들기: `scripts/render_template.py`·`audio_template.py`를 `work/promo/`에 `render.py`·`audio.py`로 복사해 상수(URL·FPS·T·SUB·출력 이름)를 고친다. 페이지는 `window.seek`(async 가능) + `window.ready=true`, `#stage`. `python -m http.server`로 띄운 뒤 `render.py probe … → draft → full`. 미리 보기는 30fps·SUB 1–2로(기본 60fps·SUB 8은 1초에 1분 넘게 걸림). 음악·효과음은 Mixkit(키 없음) → `audio.py` → 키트 §3의 마지막 인코딩으로 붙인다(템플릿 렌더에는 bt709 태그가 없어 점검 실패): `ffmpeg -i out/video.mp4 -i out/audio.wav -map 0:v -map 1:a -vf "scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv" -c:v libx264 -crf 16 -c:a aac -b:a 256k -shortest -movflags +faststart ../../output/<이름>_film.mp4`(작업 폴더에서). 템플릿의 `imageio_ffmpeg`는 `FF = "ffmpeg"`로 바꾸면 설치가 필요 없다.
- 따라 만들기(remake): 레퍼런스는 사용자가 준 파일을 `ref/reference.mp4`로(유튜브 받기는 사용자가 원할 때만). 작업 폴더에 `remake_analyze.py`를 복사해 `FF = "ffmpeg"`로, `cuts.json`의 fps를 원본 fps(ffprobe)로 고치고 `mkdir -p ref/sheet` 뒤 `.venv/bin/python remake_analyze.py`(2026-10-13 확인: 14초 30fps → 419프레임, 시트). 컷 검출은 프레임 차이가 튀는 **딱 끊긴 컷만** 잡는다 — 디졸브·줌 전환은 시트를 보고 직접 장면을 나눈다. 스크립트들이 원작 65초·1557프레임·24fps에 고정돼 있어 `remake_stub.py`의 그룹 경계, `remake_qa.py`의 범위, `remake_render.py`의 FPS를 레퍼런스에 맞게 고친 사본을 쓴다. 레퍼런스의 음악·목소리·사람 사진은 쓰지 않는다.
