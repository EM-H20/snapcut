import {test} from 'node:test';
import assert from 'node:assert/strict';
import {activeByPlace} from './caption.ts';
import type {Caption} from './types.ts';

const caps: Caption[] = [
  {start: 0.3, end: 2.3, text: '첫 문장', name: '나', place: 'bar'},
  {start: 1.0, end: 3.0, text: '친구 말', name: '친구', place: 'left'},
  {start: 1.5, end: 2.0, text: '또 친구', name: '셋째', place: 'left'},
  {start: 5.0, end: 6.0, text: '예전 자막'},
];

test('자리별 지금 자막: 시작 포함·끝 미포함, 같은 자리는 쌓이고 place가 없으면 자막바', () => {
  assert.deepEqual(activeByPlace(caps, 0.0), {bar: [], left: [], right: []});
  assert.deepEqual(activeByPlace(caps, 1.6).left.map((c) => c.text), ['친구 말', '또 친구']);
  assert.deepEqual(activeByPlace(caps, 1.6).bar.map((c) => c.text), ['첫 문장']);
  assert.deepEqual(activeByPlace(caps, 2.3).bar, []);
  assert.deepEqual(activeByPlace(caps, 5.5).bar.map((c) => c.text), ['예전 자막']);
});
