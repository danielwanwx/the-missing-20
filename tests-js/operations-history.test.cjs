const { test } = require('node:test');
const assert = require('node:assert/strict');
const { finite, visiblePoints, series, stepPath } = require('../workspace/operations-history.js');
const { benchmarkSummary } = require('../workspace/operations-history.js');
const point = (time, value, rest = {}) => ({ observed_at: time, metrics: { received: value }, currency: 'USD', uom: 'Carton', source_id: 'erp', ...rest });
test('unknown values are not zero observations', () => {
  assert.equal(finite(null), false); assert.equal(finite('12'), false);
  assert.equal(finite(NaN), false); assert.equal(finite(0), true);
});
test('time windows use observed source history, not invented samples', () => {
  const rows = [point('2026-09-07T00:00:00Z', 10), point('2026-09-08T00:00:00Z', 20)];
  assert.equal(visiblePoints(rows, 24, Date.parse('2026-09-08T01:00:00Z')).length, 1);
  assert.equal(visiblePoints(rows, 0).length, 2);
});
test('outages and unit changes break paths', () => {
  const rows = [point('2026-09-08T00:00:00Z', 10), point('2026-09-08T01:00:00Z', null), point('2026-09-08T02:00:00Z', 20), point('2026-09-08T03:00:00Z', 30, {uom: 'Each'})];
  assert.deepEqual(series(rows, 'received').map((segment) => segment.length), [1, 1, 1]);
});
test('stock quantities use a step path, without interpolated arrival', () => {
  assert.equal(stepPath([{time: 1, value: 10}, {time: 2, value: 20}], (x) => x, (y) => y), 'M 1 10 H 2 V 20');
});
test('comparison is explicit, sample-bound, and not an industry improvement claim', () => {
  const payload = {baseline: {metrics: {received: {status: 'AVAILABLE', previous_mean: 0, change: 12, sample_count: 3}}}};
  assert.equal(benchmarkSummary(payload, 'received'), 'Prior avg 0 · +12 vs 3 observations');
  assert.doesNotMatch(benchmarkSummary(payload, 'received'), /%|industry|improvement/i);
  assert.equal(benchmarkSummary({baseline: {status: 'SOURCE_UNAVAILABLE'}}, 'received'), 'Source unavailable');
  assert.match(benchmarkSummary({}, 'received'), /0\/3 prior observations/);
});
