const {test} = require('node:test');
const assert = require('node:assert/strict');
const {questionsFor, comparableSegments, retainedChartState} = require('../workspace/conversation-views.js');
const history = require('../workspace/operations-history.js');
test('initial questions are read-only prompts, latest useful follow-ups replace them', () => {
  assert.equal(questionsFor([]).length, 3);
  assert.match(questionsFor([])[1], /trend/);
  assert.deepEqual(questionsFor([{follow_up_questions: ['Which receipts?', 'Compare quality?']}]), ['Which receipts?', 'Compare quality?']);
  assert.deepEqual(questionsFor([{follow_up_questions: [null, '', 'Read ERP']}]), ['Read ERP']);
});
test('an outage at the end does not erase the last comparable historical cohort', () => {
  const point = (value, uom = 'Box', currency = 'USD') => ({case_id: 'a', uom, currency,
    observed_at: '2026-09-08T12:00:00Z', metrics: {received: value}});
  const points = [point(10), point(20), point(null, null, null)];
  assert.deepEqual(comparableSegments(points, 'received', history).map(s => s.map(p => p.value)), [[10, 20]]);
  assert.equal(retainedChartState(points, 'received', history).unit, 'Box');
  assert.equal(retainedChartState(points, 'received', history).emptyMessage, '');
});
test('missing, nonfinite or unitless retained values do not masquerade as a trend', () => {
  const point = (value, uom = 'Box') => ({case_id: 'a', uom,
    observed_at: '2026-09-08T12:00:00Z', metrics: {received: value}});
  for (const value of [undefined, null, NaN, Infinity, '10']) {
    const result = retainedChartState([point(value)], 'received', history);
    assert.equal(result.emptyMessage, 'No retained values for this metric.');
    assert.deepEqual(result.segments, []);
  }
  assert.equal(retainedChartState([point(10, null)], 'received', history).emptyMessage,
    'Unit not confirmed; comparison unavailable.');
  const dollars = { ...point(40, null), currency: 'USD', metrics: {net_billed_sales: 40} };
  assert.equal(retainedChartState([dollars], 'net_billed_sales', history).unit, 'USD');
});
test('chat trends retain outage and case boundaries before selecting a cohort', () => {
  const point = (case_id, value, uom = 'Nos') => ({case_id, uom, observed_at: '2026-09-08T12:00:00Z', metrics: {received: value}});
  const segments = comparableSegments([point('a', 10), point('a', null, null), point('a', 20), point('b', 80), point('a', 30)], 'received', history);
  assert.deepEqual(segments.map(s => s.map(p => p.value)), [[10], [20], [30]]);
});
