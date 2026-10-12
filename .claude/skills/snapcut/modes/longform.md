# 롱폼 모드 (longform)

렌더 후 마스터링·점검과 완성 보고는 SKILL.md §3을 따른다.

영상소스에 영상이 하나뿐이고 10분 이상이면(게임 방송·플레이 녹화 등) 뮤비 대신 롱폼으로 진행한다고 말하고 시작한다. 1~7단계(뮤비) 대신 아래 순서.
1. **전사** — `.venv/bin/python -m pipeline transcribe <영상명>`을 `run_in_background`로. 처음이면 모델(약 3GB)을 받는다고 사용자에게 먼저 말한다. 출력의 `오디오 트랙:`에 트랙이 여러 개면, 트랙 이름을 보여 주며 사람별 트랙이 어느 것인지 묻고 `--track 2,3`처럼 다시 실행한다(1번 = OBS 전체 믹스). 출력의 `마이크1=2번(…)`을 사용자에게 전하고, 마이크별 이름을 알려 주면 `speakers`에 적는다(모르면 마이크1 그대로 두고 나중에).
2. **고르기** — `.cache/transcript.json`(문장별 원본 초)을 처음부터 끝까지 읽고(길면 나눠서), 출력의 `큰 소리 순간`과 함께 후보 구간을 정한다. 후보마다 `ffmpeg -ss <초-5> -t 15 -i <원본> -vf fps=1,scale=320:-1,tile=5x3 -frames:v 1 .cache/lf_<초>.jpg`로 화면을 본다. 구간은 시간순, 겹치지 않게, 하나에 20초~2분. 게임 용어 오인식은 `fixes`에 적는다.
3. **longform.json 작성** — 프로젝트 루트(`projects/<영상명>/longform.json`):
   ```json
   {"clips": [{"in": 1834.2, "out": 1901.0, "title": "바론 스틸"}], "fixes": {"바로 스틸": "바론 스틸"},
    "captionStyle": "동글파랑", "speakers": {"마이크1": "송하영", "마이크2": {"name": "정해인", "side": "right"}}}
   ```
   `in/out`은 원본 기준 초. 문장 중간에 걸친 경계는 plan이 문장 밖으로 민다. 시점 주인(`pov`, 기본 마이크1)은 아래 자막바, 나머지는 고정된 쪽 말풍선(기본 왼쪽·오른쪽 교대, `side`로 지정). 트랙 하나짜리 영상의 이름표는 `"speaker": "이름"`. 스타일은 `공용/자막/`(`둥글배그` 기본, `흰바`, `동글파랑`, `빨강정보`).
   `"shorts": false`면 그 구간은 쇼츠를 만들지 않는다. 쇼츠는 1분 안팎 구간이 좋다.
4. **plan** — `.venv/bin/python -m pipeline plan <영상명>`. `주의:` 줄은 그대로 전한다.
5. **확인** — `studio`를 백그라운드로 띄우고 http://localhost:3002 를 알려준다(롱폼 기본, 쇼츠는 `--format shorts` — 첫 클립). 수정은 longform.json을 고치고 plan → studio 다시 실행 → 새로고침.
6. **렌더** — `.venv/bin/python -m pipeline render <영상명>` → `output/<영상명>_longform.mp4` + `.srt`, 쇼츠는 `output/shorts/`.

