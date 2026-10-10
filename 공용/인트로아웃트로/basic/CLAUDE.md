# 인트로/아웃트로 카드 템플릿
- `pipeline/intro.py`가 `landscape.html`(유튜브)·`portrait.html`(릴스)을 렌더한다. 계약: 길이 정확히 11초(`data-duration="11"`), 변수 `text`·`sub`·`exit`(아웃트로면 "1": 8초에 글씨가 먼저 사라짐 — 화면은 Remotion이 9초부터 어둡게).
- index.html이 없으므로 lint는 템플릿을 임시 폴더에 `index.html`로 복사해서 `npx -y hyperframes@0.8.140 lint <폴더>`로 실행한다.
