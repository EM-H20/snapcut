# 인트로/아웃트로 카드 템플릿
- `pipeline/intro.py`가 `landscape.html`(유튜브)·`portrait.html`(릴스)을 렌더한다. 계약: 길이 정확히 3초(`data-duration="3"`), 변수 `text`·`sub`.
- index.html이 없으므로 lint는 템플릿을 임시 폴더에 `index.html`로 복사해서 `npx -y hyperframes@0.8.140 lint <폴더>`로 실행한다.
