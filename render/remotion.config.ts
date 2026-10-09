import {Config} from '@remotion/cli/config';
import {existsSync} from 'node:fs';

// 번들 chrome-headless-shell이 실행되지 않는 환경용: SNAPCUT_CHROME 또는 설치된 Google Chrome 사용
const chrome = process.env.SNAPCUT_CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (existsSync(chrome)) {
  Config.setBrowserExecutable(chrome);
  Config.setChromeMode('chrome-for-testing');
}
// 색 태그 없는 풀레인지(yuvj420p) 출력은 재생기마다 색이 달라 보인다 → bt709로 태그해 렌더
Config.setColorSpace('bt709');
// 카톡 원본은 이미 압축돼 있어 세대 손실이 눈에 띈다 → 기본 18보다 낮춘다
Config.setCrf(14);
