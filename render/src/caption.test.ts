import {test} from 'node:test';
import assert from 'node:assert/strict';
import {activeCaption} from './caption.ts';

const caps = [
  {start: 0.3, end: 2.3, text: '첫 문장'},
  {start: 2.3, end: 3.0, text: '바로 이어짐'},
  {start: 5.0, end: 6.0, text: '떨어진 문장'},
];

test('지금 시각의 자막: 시작 포함, 끝 미포함, 빈 구간은 null', () => {
  assert.equal(activeCaption(caps, 0.0), null);
  assert.equal(activeCaption(caps, 0.3), '첫 문장');
  assert.equal(activeCaption(caps, 2.3), '바로 이어짐');
  assert.equal(activeCaption(caps, 4.0), null);
  assert.equal(activeCaption(caps, 6.0), null);
});
