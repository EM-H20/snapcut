import {Config} from '@remotion/cli/config';
import {existsSync} from 'node:fs';

// 번들 chrome-headless-shell이 실행되지 않는 환경용: SNAPCUT_CHROME 또는 설치된 Google Chrome 사용
const chrome = process.env.SNAPCUT_CHROME ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
if (existsSync(chrome)) {
  Config.setBrowserExecutable(chrome);
  Config.setChromeMode('chrome-for-testing');
}
