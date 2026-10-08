# snapcut

여행·행사 후 쌓인 사진/영상을 음악 비트에 맞춘 추억 뮤비로 자동 편집. Claude Code에서 `/snapcut <영상명>`.

## 설치
터미널에서 한 줄:
```bash
npx github:EM-H20/snapcut
```
`~/snapcut`에 내려받고 설치까지 끝낸다. 다른 위치는 `npx github:EM-H20/snapcut ~/원하는/폴더`. 같은 명령을 다시 실행하면 최신 버전으로 업데이트된다.

이미 클론했다면 `./install.sh`. 설치 스크립트가 한 번에 처리한다(여러 번 실행해도 안전).
- ffmpeg·Node 22+·Python 3.13+ 확인 — 없으면 Homebrew로 설치
- Python 가상환경(`.venv`)과 패키지, Remotion(`render/`), HyperFrames 내려받기
- Finder 우클릭 변환 버튼 설치, `공용/음악/`·`projects/` 폴더 생성

필요: macOS, [Homebrew](https://brew.sh)(도구가 없을 때만), [Google Chrome](https://www.google.com/chrome/) 권장, [Claude Code](https://claude.com/claude-code).

렌더링은 설치된 Google Chrome을 사용한다(`render/remotion.config.ts`) — Remotion 번들 브라우저가 일부 Mac에서 실행되지 않기 때문. 다른 Chrome 경로는 `SNAPCUT_CHROME` 환경변수로 지정.

## 사용법

### 1. 재료 넣기
```
snapcut/
├── 공용/음악/                 ← 곡 (mp3/m4a/wav/aac/flac) — 모든 영상이 공유
└── projects/제주여행/
    └── 영상소스/              ← 사진·영상 (jpg/png/heic/mp4/mov, 하위 폴더 가능)
```
- 폴더 이름(`제주여행`)이 영상 이름이 된다. 원본은 절대 수정되지 않는다.
- 아이폰 사진은 사진 앱에서 "수정되지 않은 원본 내보내기"를 쓰면 촬영 시각이 살아 있어 순서가 정확하다. 카톡으로 받은 사진은 촬영 시각이 없어 파일 날짜로 정렬된다.

### 2. Claude Code에서 실행
저장소 폴더에서 Claude Code를 열고:
```
/snapcut 제주여행
```
"제주여행 뮤비 만들어줘"처럼 말로 해도 된다. Claude가 순서대로 진행한다.

1. **준비** — 형식 변환, 흔들린 사진·연사 중복·라이브 포토 영상 제외, 영상 하이라이트 탐색, 썸네일 시트 생성 (사진 수백 장이면 몇 분)
2. **고르기** — Claude가 썸네일 시트를 보고 베스트 컷을 고른다
3. **질문** — 곡, 형식(릴스 / 유튜브 / 둘 다), 타이틀·엔딩 문구를 확인한다
4. **타임라인** — 컷을 비트에 맞춰 배치한다 (`projects/제주여행/selection.json`에 고른 내용이 저장됨)
5. **미리보기** — 브라우저에 Remotion Studio(http://localhost:3000)가 열린다. 렌더 없이 바로 재생된다
6. **렌더** — "둘 다 뽑아줘"라고 하면 완성 영상을 만든다

완성본: `projects/제주여행/output/제주여행_reels.mp4`, `제주여행_youtube.mp4`

### 3. 대화로 고치기
미리보기를 보면서 말로 요청하고, 반영되면 **브라우저를 새로고침**한다.
- "3번 사진 빼줘", "12번이랑 13번 순서 바꿔"
- "후반부 더 빠르게" / "전체적으로 잔잔하게"
- "타이틀을 '우리의 제주'로 바꿔", "엔딩 문구 바꿔"
- "17번 영상은 웃음소리 살려줘" (그 구간만 음악이 줄고 현장 소리가 나온다)
- "다른 곡으로 바꿔줘"

### 4. 확인 없이 한 번에
```
/snapcut 제주여행 --바로
```
릴스·유튜브 둘 다, 지정한 곡(없으면 Claude 추천 곡), Claude가 쓴 문구로 미리보기 없이 렌더까지 간다.

### 5. 형식
| | 릴스 | 유튜브 |
|---|---|---|
| 화면 | 9:16 (1080×1920) | 16:9 (1920×1080) |
| 길이 | 곡의 하이라이트 구간 최대 45초 | 곡 전체 |
| 템포 | 사진당 2박 | 사진당 4박 |

비율이 안 맞는 사진은 흐린 배경 위에 잘리지 않게 놓고, 영상은 검은 여백으로 둔다. 사진이 곡보다 모자라면 음악이 마지막 장면에서 끝난다.

### 변환만 미리 하기
사진을 넣자마자 변환해 두면 나중에 `/snapcut`이 빨라진다. Finder에서 `영상소스`(또는 프로젝트) 폴더 우클릭 → 빠른 동작 → **"snapcut 영상소스 변환"**. 끝나면 알림이 뜨고, 기록은 `~/Library/Logs/snapcut-convert.log`. 변환이 끝나기 전에 `/snapcut`을 같이 돌리지 않는다.

### 명령어로 직접 쓰기
Claude 없이도 각 단계를 실행할 수 있다(저장소 루트에서).
```bash
.venv/bin/python -m pipeline prepare 제주여행
```
| 명령 | 하는 일 |
|---|---|
| `convert <영상명>` | 형식 변환만 |
| `prepare <영상명>` | 변환 + 선별 + 하이라이트 + 썸네일 시트(`.cache/sheets/`) |
| `music` | `공용/음악/` 곡 목록 |
| `plan <영상명>` | `selection.json` → 타임라인(`.cache/storyboard.json`) + 인트로/아웃트로 카드 |
| `studio <영상명>` | 미리보기 열기 |
| `render <영상명> --formats reels,youtube` | 완성 영상 렌더 |

`selection.json`의 `items[].id`는 썸네일 시트의 `#번호`다. **사진을 추가하고 `prepare`를 다시 돌리면 번호가 바뀌므로** 고르기를 다시 해야 한다.

### 문제가 생기면
- **"HDR 영상 N개" 경고** — 아이폰 HDR 영상은 색이 바래 보일 수 있다. 렌더본을 확인하고 이상하면 알려주기.
- **렌더가 실패하고 Chrome 관련 오류** — Google Chrome이 설치돼 있는지 확인. 다른 위치라면 `SNAPCUT_CHROME=/경로/Google Chrome`.
- **빠른 동작 메뉴가 안 보임** — 시스템 설정 → 키보드 → 키보드 단축키 → 서비스(또는 확장 프로그램 → Finder)에서 켜기. 또는 `.venv/bin/python tools/install_quick_action.py` 재실행.
- **곡을 바꿨는데 박자가 이상함** — `projects/<영상명>/.cache/music/`을 지우고 `plan` 다시 실행.

### 빠른 동작 수동 설치 (스크립트가 안 될 때)
Automator → 새 문서 → 빠른 동작 → "작업 흐름이 받는 항목: 폴더 / Finder" → "셸 스크립트 실행"(입력 전달: 인수로) → `tools/install_quick_action.py`의 `SCRIPT` 내용을 붙여넣고 `{ROOT}`·`{LOG}`를 실제 경로로 → 저장 이름 "snapcut 영상소스 변환".

## 라이선스
snapcut 코드는 [MIT](LICENSE).

설치 시 내려받는 도구는 각자의 라이선스를 따른다(이 저장소에 포함되지 않음).
- [Remotion](https://www.remotion.dev/license) — 개인·소규모 팀 무료, 일정 규모 이상 회사는 유료 라이선스 필요
- [HyperFrames](https://github.com/heygen-com/hyperframes) — Apache 2.0
- [GSAP](https://gsap.com/licensing/) — 인트로 카드 애니메이션, CDN에서 로드

넣는 사진·영상·음악의 권리는 사용자에게 있다.

선택: Remotion 공식 Claude 스킬 `npx skills add remotion-dev/skills`.
