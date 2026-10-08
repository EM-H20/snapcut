import {test} from 'node:test';
import assert from 'node:assert/strict';
import {collageGrid} from './collage.ts';

test('2·3장은 긴 쪽으로 나란히', () => {
  assert.deepEqual(collageGrid(2, true), {cols: 2, rows: 1});
  assert.deepEqual(collageGrid(3, false), {cols: 1, rows: 3});
});
test('4장은 2x2', () => assert.deepEqual(collageGrid(4, false), {cols: 2, rows: 2}));
