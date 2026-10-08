#!/usr/bin/env node
// npx github:EM-H20/snapcut [설치폴더] — 저장소를 받아(이미 있으면 업데이트) install.sh를 실행한다.
import {execFileSync} from 'node:child_process';
import {existsSync} from 'node:fs';
import {homedir, platform} from 'node:os';
import {join, resolve} from 'node:path';

const REPO = process.env.SNAPCUT_REPO ?? 'https://github.com/EM-H20/snapcut.git';
const target = resolve(process.argv[2] ?? join(homedir(), 'snapcut'));
const run = (cmd, args, cwd) => execFileSync(cmd, args, {cwd, stdio: 'inherit'});

if (platform() !== 'darwin') {
  console.error('✗ snapcut은 macOS 전용입니다.');
  process.exit(1);
}

try {
  if (existsSync(join(target, '.git'))) {
    console.log(`▶ 기존 설치 업데이트: ${target}`);
    run('git', ['pull', '--ff-only'], target);
  } else if (existsSync(target)) {
    console.error(`✗ ${target} 폴더가 이미 있습니다. 다른 위치를 지정하세요: npx github:EM-H20/snapcut <설치폴더>`);
    process.exit(1);
  } else {
    console.log(`▶ 내려받기: ${target}`);
    run('git', ['clone', '--depth', '1', REPO, target]);
  }
  run('./install.sh', [], target);
} catch (e) {
  console.error(`\n✗ 설치 실패 (${e.message.split('\n')[0]})`);
  process.exit(1);
}

console.log(`\n다음: cd ${target} && claude  →  /snapcut <영상명>`);
