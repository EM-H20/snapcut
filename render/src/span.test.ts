import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blurAmount, span, tailOpacity} from './span.ts';
import type {Shot} from './types.ts';

const shots: Shot[] = [
  {type: 'photo', src: 'media/p.jpg', start: 0, end: 2, kenBurns: 'zoom-out'},
  {type: 'video', src: 'media/v.mp4', start: 2, end: 4, in: 0, out: 2, liveAudio: false, dissolve: 0.4},
  {type: 'photo', src: 'media/q.jpg', start: 4, end: 6, kenBurns: 'zoom-in'},
];

test('디졸브: 앞 장면을 겹치는 만큼 늘리고, 뒤 장면은 그동안 서서히 나타난다', () => {
  assert.deepEqual(span(shots, 0, 30), {from: 0, frames: 60, duration: 72, fadeIn: 0, blurIn: 0, blurOut: 0});
  assert.deepEqual(span(shots, 1, 30), {from: 60, frames: 60, duration: 60, fadeIn: 12, blurIn: 0, blurOut: 0});
  assert.deepEqual(span(shots, 2, 30), {from: 120, frames: 60, duration: 60, fadeIn: 0, blurIn: 0, blurOut: 0});
});

test('끝 페이드아웃: 마지막 구간에서 1→0', () => {
  assert.equal(tailOpacity(0, 90, 30), 1);
  assert.equal(tailOpacity(59, 90, 30), 1);
  assert.ok(tailOpacity(75, 90, 30) < 1 && tailOpacity(75, 90, 30) > 0);
  assert.equal(tailOpacity(89, 90, 30), 0);
  assert.equal(tailOpacity(80, 90, 0), 1);
});

test('블러 전환: 들어오는 장면은 앞 절반만큼 선명해지고, 앞 장면은 끝 절반만큼 흐려진다', () => {
  const s: Shot[] = [
    {type: 'clip', src: 'cards/i.mp4', start: 0, end: 3},
    {type: 'video', src: 'media/v.mp4', start: 3, end: 5, in: 0, out: 2, liveAudio: false, blur: 0.6},
  ];
  assert.equal(span(s, 0, 30).blurOut, 9);
  assert.equal(span(s, 1, 30).blurIn, 9);
  assert.equal(span(s, 1, 30).blurOut, 0);
});
test('블러 양: 경계에서 최대, 멀어지면 0', () => {
  assert.equal(blurAmount(0, 60, 9, 0, 30), 30);
  assert.equal(blurAmount(9, 60, 9, 0, 30), 0);
  assert.equal(blurAmount(59, 60, 0, 9, 30), 30);
  assert.equal(blurAmount(30, 60, 9, 9, 30), 0);
});
