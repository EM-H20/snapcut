import {test} from 'node:test';
import assert from 'node:assert/strict';
import {creditsRoll} from './creditsRoll.ts';

test('크레딧은 화면 아래에서 시작해 위로 다 빠져나간다', () => {
  assert.equal(creditsRoll(0, 300, 1080, 900).y, 1080);
  assert.equal(creditsRoll(300, 300, 1080, 900).y, -900);
});
test('끝 2초 동안 검게 어두워진다 (30fps)', () => {
  assert.equal(creditsRoll(0, 300, 1080, 900).dark, 0);
  assert.equal(creditsRoll(240, 300, 1080, 900).dark, 0);
  assert.equal(creditsRoll(300, 300, 1080, 900).dark, 1);
});
