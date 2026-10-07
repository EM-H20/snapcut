import {test} from 'node:test';
import assert from 'node:assert/strict';
import {DUCK, musicVolume} from './duck.ts';
import type {Shot} from './types';

const live: Shot = {type: 'video', src: 'a.mp4', start: 5, end: 8, in: 0, out: 3, liveAudio: true};
const quiet: Shot = {...live, liveAudio: false};

test('live 클립과 멀면 원래 볼륨', () => assert.equal(musicVolume(1, [live], 20), 1));
test('live 클립 안에서는 DUCK', () => assert.equal(musicVolume(6.5, [live], 20), DUCK));
test('경계는 부드럽게', () => {
  const v = musicVolume(4.85, [live], 20);
  assert.ok(v < 1 && v > DUCK);
});
test('live가 아닌 영상은 덕킹 없음', () => assert.equal(musicVolume(6.5, [quiet], 20), 1));
test('끝에서 페이드아웃', () => {
  assert.equal(musicVolume(20, [], 20), 0);
  assert.ok(musicVolume(19, [], 20) < 1);
});
