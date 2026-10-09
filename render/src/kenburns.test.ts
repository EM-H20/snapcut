import {test} from 'node:test';
import assert from 'node:assert/strict';
import {kenBurns} from './kenburns.ts';

test('zoom-in은 1.0→1.1', () => {
  assert.deepEqual(kenBurns('zoom-in', 0), {scale: 1, x: 0});
  assert.equal(kenBurns('zoom-in', 1).scale.toFixed(2), '1.10');
});
test('pan은 반대 방향', () => {
  assert.equal(kenBurns('pan-left', 0).x, 2);
  assert.equal(kenBurns('pan-right', 1).x, 2);
});
test('범위 밖 진행률은 잘라냄', () => assert.deepEqual(kenBurns('zoom-out', 5), kenBurns('zoom-out', 1)));
test('scroll-down은 확대한 채 맨 위에서 맨 아래로', () => {
  const top = kenBurns('scroll-down', 0), bottom = kenBurns('scroll-down', 1);
  assert.equal(top.scale, 2.5);
  assert.equal(top.y, 30); // (2.5-1)/(2*2.5) = 사진 윗변이 화면 윗변에 닿음
  assert.equal(bottom.y, -30);
  assert.equal(kenBurns('scroll-down', 0.5).y, 0);
});
test('still은 움직이지 않음', () => {
  assert.deepEqual(kenBurns('still', 0), {scale: 1, x: 0});
  assert.deepEqual(kenBurns('still', 1), {scale: 1, x: 0});
});
