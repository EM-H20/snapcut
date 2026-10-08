import {test} from 'node:test';
import assert from 'node:assert/strict';
import {shotLabel} from './shotLabel.ts';
import type {CollageShotT} from './types.ts';

test('영상은 파일 이름 + 원본 기준 초', () => {
  const shot = {type: 'video', src: 'media/_talkv_abc_mp4.mp4', start: 0, end: 3, in: 24.3, out: 27.3, liveAudio: false} as const;
  assert.equal(shotLabel(shot, 1.25), '_talkv_abc_mp4 25.6초');
});
test('분할은 칸 이름을 모두', () => {
  const shot: CollageShotT = {type: 'collage', srcs: ['media/a_jpg.jpg', 'media/b_jpg.jpg'], start: 0, end: 2, kenBurns: 'zoom-in'};
  assert.equal(shotLabel(shot, 0), 'a_jpg, b_jpg');
});
test('크레딧은 크레딧', () => {
  assert.equal(shotLabel({type: 'credits', src: 'media/v.mp4', in: 0, out: 5, lines: ['a'], start: 0, end: 5, liveAudio: true}, 0), '크레딧');
});
