---
name: snapcut
description: 여행·행사 사진/영상 폴더를 음악 비트에 맞춘 추억 뮤비(릴스 9:16 / 유튜브 16:9)로 편집한다. "/snapcut <영상명>", "<영상명> 뮤비 만들어줘", "<영상명> 편집해줘", 스토리보드 수정·렌더 요청에 사용.
---

# snapcut 워크플로

인자: `<영상명>` (= `projects/<영상명>/`), 선택 `--바로`(확인 없이 렌더까지).
모든 명령은 저장소 루트에서 `.venv/bin/python -m pipeline ...`로 실행한다.

## 1. 준비
`.venv/bin/python -m pipeline prepare <영상명>` — 변환·선별·하이라이트·썸네일 시트. 출력의 제외 목록, HDR 경고, 시각 정보 없는 항목 수를 사용자에게 한 줄씩 전한다.

## 2. 고르기
- `.cache/sheets/sheet_*.jpg`를 **전부** Read로 본다. 칸의 `#번호` = `candidates.json`의 인덱스 = selection의 `id`. `V3s`는 영상(길이).
- `.cache/candidates.json`에서 시각(`taken_at`)·종류를 확인한다.
- 고르는 기준: 사람 표정이 좋은 컷, 장소가 드러나는 풍경, 음식·소품 같은 디테일을 섞는다. 비슷한 구도가 연달아 나오면 하나만. 눈 감은 사진, 초점 나간 사진, 의미 없는 바닥·하늘은 뺀다.
- 넉넉히 골라도 된다 — 자리가 모자라면 plan이 처음·끝을 살리고 균등하게 줄인다.
- 순서는 시간순 유지. 바꿀 이유가 있으면 사용자에게 말한다.

## 3. 음악·문구·형식
- 음악이 정해지지 않았으면 `.venv/bin/python -m pipeline music`으로 `공용/음악/` 목록을 보여주고 분위기에 맞는 곡을 추천한 뒤 사용자에게 고르게 한다. 저작권 판단·경고는 하지 않는다(사용자 몫).
- 형식(릴스/유튜브/둘 다)을 사용자가 말하지 않았으면 묻는다.
- 타이틀·부제·엔딩 문구를 제안한다(예: "제주, 2026 가을" / "2026.09.12–15" / "함께해서 즐거웠어").

## 4. selection.json 작성
`projects/<영상명>/selection.json`:
```json
{
  "title": "제주, 2026 가을",
  "subtitle": "2026.09.12–15",
  "ending": "함께해서 즐거웠어",
  "music": "song.mp3",
  "formats": ["reels", "youtube"],
  "intro": "basic",
  "items": [{"id": 0}, {"id": 7, "in": 2.0, "out": 5.5, "liveAudio": true}]
}
```
영상 항목의 `in/out/liveAudio`는 생략하면 하이라이트 제안값을 쓴다. 웃음·함성처럼 현장 소리를 살릴 장면만 `liveAudio: true`.

## 5. 타임라인 계산
`.venv/bin/python -m pipeline plan <영상명>` — 형식별 길이·장면 수·뺀 항목 수를 사용자에게 전한다.

## 6. 확인 (`--바로`면 건너뜀)
`.venv/bin/python -m pipeline studio <영상명>`을 **백그라운드로** 실행하고 http://localhost:3000 을 알려준다. 수정 요청("3번째 사진 빼", "후반 빠르게", "타이틀 바꿔")은 selection.json을 고치고 5단계를 다시 실행한 뒤 "브라우저 새로고침"을 안내한다. Studio는 계속 띄워 둔다.
- "빠르게/느리게"는 장면 수를 늘리거나 줄여서 반영한다(사진당 비트 수는 형식별 고정: 릴스 2, 유튜브 4).

## 7. 렌더
사용자가 렌더를 요청하면 `.venv/bin/python -m pipeline render <영상명> --formats reels,youtube`(요청한 형식만). 완성 경로를 알려준다.

## 규칙
- `영상소스/` 안에는 절대 쓰지 않는다.
- 오류 메시지는 그대로 전하고, 원인이 selection.json이면 고친 뒤 다시 실행한다.
