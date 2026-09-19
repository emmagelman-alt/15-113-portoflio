const {test} = require('node:test');
const assert = require('node:assert/strict');
const {accentProgression} = require('../static/accent-progression.js');
const phrases = ['a','b','c'].map(id => ({id}));
test('only valid scores strictly above 95 advance', () => {
  for (const score of [null, undefined, '96', NaN, Infinity, 0, 94.9, 95, 101]) {
    assert.equal(accentProgression(phrases, 'a', score, []), null);
  }
  assert.equal(accentProgression(phrases, 'a', 95.1, []).nextId, 'b');
});
test('skips completed phrases and preserves caller progress', () => {
  const completed = ['b'];
  assert.deepEqual(accentProgression(phrases, 'a', 99, completed), {completed:['b','a'],nextId:'c',roundComplete:false});
  assert.deepEqual(completed,['b']);
});
test('last phrase wraps to a different phrase and completes round', () => {
  assert.deepEqual(accentProgression(phrases, 'c', 100, ['a','b']), {completed:['a','b','c'],nextId:'a',roundComplete:true});
});
test('unknown phrase cannot advance; one phrase safely completes', () => {
  assert.equal(accentProgression(phrases, 'unknown', 99, []), null);
  assert.deepEqual(accentProgression([{id:'a'}], 'a', 99, []), {completed:['a'],nextId:null,roundComplete:true});
});
