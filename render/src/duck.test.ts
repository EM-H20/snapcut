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
test('duck: false면 현장 소리와 음악을 둘 다 그대로', () => assert.equal(musicVolume(6.5, [{...live, duck: false}], 20), 1));
test('duck: 0.6이면 그 장면은 음악을 60%까지만 줄임', () => assert.equal(musicVolume(6.5, [{...live, duck: 0.6}], 20), 0.6));
test('duckFade가 길면 서서히 줄었다 커진다', () => {
  const slow = {...live, duckFade: 2};
  assert.equal(musicVolume(5, [slow], 20), DUCK);
  const mid = musicVolume(4, [slow], 20);
  assert.ok(mid > DUCK && mid < 1);  // 1초 전엔 반쯤 줄어 있다 (기본 페이드면 아직 원래 볼륨)
  assert.ok(musicVolume(3.5, [slow], 20) < 1 && musicVolume(3.5, [live], 20) === 1);  // 0.3초 페이드보다 훨씬 앞에서 줄기 시작
  assert.ok(musicVolume(9.5, [slow], 20) < 1);  // 끝난 뒤에도 천천히 돌아온다
});
test('페이드 끝 시각 뒤(크레딧)에는 음악 0', () => {
  assert.equal(musicVolume(25, [], 20), 0);
  assert.ok(musicVolume(19, [], 20) > 0);
});
