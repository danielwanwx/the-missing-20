const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {
  buildEventPayload,
  cleanAnswer,
  conversationAnswer,
  providerLabel,
  normalizeProjection,
  retainConversationProjection,
  shouldPreserveTemplateFields,
  deliverySummary,
  arrivalQuantitySummary,
  unwrapProjection,
  recommendedAction,
  statusTone,
  deliveryCompletionLabel,
} = require('../workspace/distributor-operations.js');

test('projection keeps missing source quantities unknown instead of turning them into zero', () => {
  const projection = normalizeProjection({
    available: true,
    stage: 'RECEIVING',
    quantities: { ordered: 40, received: null, uom: 'Nos' },
    lots: [], allocations: [], alerts: [], events: [], documents: [], available_event_templates: [],
  });
  assert.equal(projection.quantities.ordered, 40);
  assert.equal(projection.quantities.received, null);
  assert.equal(projection.quantities.usable, undefined);
  assert.equal(projection._provided.quantities, true);
});

test('projection preserves native conversation turns and unavailable status metadata', () => {
  const projection = normalizeProjection({
    available: true,
    quantities: {},
    conversation: [{ question: 'Which lot is held?', answer: 'LOT-7 is held.', read_only: true }],
    conversation_status: 'UNAVAILABLE',
    conversation_message: 'The read-only bridge is not configured.',
  });
  assert.deepEqual(projection.conversation, [{ question: 'Which lot is held?', answer: 'LOT-7 is held.', read_only: true }]);
  assert.equal(projection.conversation_status, 'UNAVAILABLE');
  assert.equal(projection.conversation_message, 'The read-only bridge is not configured.');
  assert.equal(conversationAnswer(projection.conversation), 'LOT-7 is held.');
});

test('conversation memory survives empty same-case polls and clears on case change', () => {
  const completed = retainConversationProjection({
    case_id: 'CASE-1',
    conversation: [{ role: 'assistant', answer: '39 Boxes are ready.' }],
    conversation_status: 'COMPLETE',
  });
  const pendingPoll = retainConversationProjection({
    case_id: 'CASE-1',
    conversation: [],
    conversation_status: 'PENDING',
  }, completed.memory);
  assert.equal(conversationAnswer(pendingPoll.projection.conversation), '39 Boxes are ready.');
  const emptyCompletedPoll = retainConversationProjection({
    case_id: 'CASE-1',
    conversation: [],
    conversation_status: 'COMPLETE',
  }, pendingPoll.memory);
  assert.equal(conversationAnswer(emptyCompletedPoll.projection.conversation), '39 Boxes are ready.');
  const unavailable = retainConversationProjection({
    case_id: 'CASE-2',
    conversation: { status: 'UNAVAILABLE', message: 'Read-only bridge unavailable.' },
  });
  const unavailablePoll = retainConversationProjection({ case_id: 'CASE-2', conversation: [] }, unavailable.memory);
  assert.equal(unavailablePoll.projection.conversation.status, 'UNAVAILABLE');
  assert.equal(unavailablePoll.projection.conversation.message, 'Read-only bridge unavailable.');
  const changedCase = retainConversationProjection({ case_id: 'CASE-3', conversation: [] }, completed.memory);
  assert.equal(conversationAnswer(changedCase.projection.conversation), '');
  assert.equal(changedCase.memory, null);
});

test('template polling preserves a selected form until an explicit reset', () => {
  assert.equal(shouldPreserveTemplateFields({ currentType: 'carrier_pickup', nextType: 'carrier_pickup', fieldsRendered: true }), true);
  assert.equal(shouldPreserveTemplateFields({ currentType: 'carrier_pickup', nextType: 'carrier_pickup', fieldsRendered: true, resetFields: true }), false);
  assert.equal(shouldPreserveTemplateFields({ currentType: 'carrier_pickup', nextType: 'delivery', fieldsRendered: true }), false);
  assert.equal(shouldPreserveTemplateFields({ currentType: 'carrier_pickup', nextType: 'carrier_pickup', fieldsRendered: false }), false);
});

test('API wrappers preserve the inner operation projection for chat responses', () => {
  const projection = unwrapProjection({
    distributor_operations: {
      available: true,
      stage: 'RECEIVED',
      quantities: {},
      conversation: {
        question: 'What arrived?',
        answer: '39 Boxes.',
        provider: { mode: 'bedrock', model: 'us.amazon.nova-pro-v1:0', provider: 'bedrock' },
      },
    },
  });
  assert.equal(conversationAnswer(projection.conversation), '39 Boxes.');
  assert.equal(providerLabel(projection.conversation.provider), 'bedrock · us.amazon.nova-pro-v1:0');
  assert.equal(providerLabel('native-test-bridge'), 'native-test-bridge');
});

test('arrival event contains only the reviewed typed fields and is explicitly synthetic', () => {
  assert.deepEqual(buildEventPayload({
    type: 'arrival',
    eventId: 'evt-arrival-1',
    now: '2026-09-10T12:00:00Z',
    evidenceRef: 'scanner-04',
    values: {
      cartons: '4', expected_pack_quantity: '10', observed_stock_quantity: '38', item_code: 'PART-20', lot: 'L7',
    },
  }), {
    event_id: 'evt-arrival-1', type: 'arrival', occurred_at: '2026-09-10T12:00:00Z', evidence_ref: 'scanner-04', synthetic: true,
    cartons: 4, expected_pack_quantity: 10, observed_stock_quantity: 38, item_code: 'PART-20', lot: 'L7',
  });
});

test('inspection event requires a report reference and does not send a caller-supplied spec', () => {
  const payload = buildEventPayload({
    type: 'inspection', eventId: 'evt-inspect-1', now: '2026-09-10T12:01:00Z', evidenceRef: 'inspection-photo-1',
    values: {
      lot: 'L8', result: 'FAIL', scope: 'SAMPLE', metric: 'diameter', measured: '10.40', sample_quantity: '2', inspection_report_ref: 'QI-004',
    },
  });
  assert.equal(payload.inspection_report_ref, 'QI-004');
  assert.equal(payload.measured, 10.4);
  assert.equal(Object.hasOwn(payload, 'spec'), false);
  assert.throws(() => buildEventPayload({ type: 'inspection', evidenceRef: 'photo', values: { lot: 'L8', result: 'FAIL', scope: 'SAMPLE', metric: 'diameter', measured: '10.40', sample_quantity: '2' } }), /Inspection report ID is required/);
});

test('delivery is a separate event from pickup and both require shipment evidence', () => {
  const pickup = buildEventPayload({ type: 'carrier_pickup', eventId: 'evt-pickup', now: '2026-09-10T12:02:00Z', evidenceRef: 'carrier-scan', values: { shipment_id: 'SHP-1' } });
  const delivery = buildEventPayload({ type: 'delivery', eventId: 'evt-delivery', now: '2026-09-10T12:03:00Z', evidenceRef: 'pod-test-1', values: { shipment_id: 'SHP-1' } });
  assert.equal(pickup.type, 'carrier_pickup');
  assert.equal(delivery.type, 'delivery');
  assert.notEqual(pickup.type, delivery.type);
  assert.equal(delivery.evidence_ref, 'pod-test-1');
});

test('outbound delivery evidence preserves known counts and unavailable quantity', () => {
  assert.equal(deliverySummary(15, 15), 'Delivery confirmed 15 / 15');
  assert.equal(deliverySummary(20, 24), 'Delivery confirmed 20 / 24');
  assert.equal(deliverySummary(0, 24), 'Delivery confirmed 0 / 24');
  assert.equal(deliverySummary(null, 24), 'Delivery confirmed unknown');
});

test('completion badge keeps delivery confirmation visible with open alerts to review', () => {
  const completed = {
    available: true,
    source_status: 'CURRENT',
    quantities: {
      ordered: 40,
      received: 40,
      dispatched: 40,
      delivery_confirmed: 40,
      held: 0,
      missing: 0,
      usable: 0,
      allocated: 0,
    },
    alerts: [{ status: 'OPEN' }, { status: 'OPEN' }, { status: 'OPEN' }, { status: 'RESOLVED' }],
  };
  assert.equal(deliveryCompletionLabel(completed), 'Delivery confirmed · 3 alerts to review');

  for (const incomplete of [
    { ...completed, quantities: { ...completed.quantities, delivery_confirmed: undefined } },
    { ...completed, available: false },
    { ...completed, source_status: 'UNAVAILABLE' },
    { ...completed, quantities: { ...completed.quantities, delivery_confirmed: 39 } },
    { ...completed, quantities: { ...completed.quantities, held: 1 } },
  ]) {
    assert.equal(deliveryCompletionLabel(incomplete), '');
  }
});

test('arrival activity uses the source stock UOM for counted quantity', () => {
  assert.equal(arrivalQuantitySummary({ observed_stock_quantity: 20 }, { quantities: { uom: 'Box' } }), '20 Box counted');
  assert.equal(arrivalQuantitySummary({ observed_stock_quantity: 20 }, { quantities: {} }), '20 counted');
  assert.equal(arrivalQuantitySummary({}, { quantities: { uom: 'Box' } }), 'Quantity count unknown');
});

test('answers hide paired reasoning blocks and alerts retain an actionable tone', () => {
  assert.equal(cleanAnswer('Visible answer <thinking>private chain</thinking> <analysis>also private</analysis>'), 'Visible answer');
  assert.equal(statusTone('QUALITY_HOLD'), 'coral');
  assert.match(recommendedAction('INNER_QUANTITY_MISMATCH'), /inner count/i);
});

test('page exposes the guarded business loop and synthetic evidence label', () => {
  const html = fs.readFileSync(path.join(__dirname, '../workspace/distributor-operations.html'), 'utf8');
  assert.match(html, /Process evidence/);
  assert.match(html, /Simulated scanner \/ inspection \/ carrier evidence/);
  assert.match(html, /Delivery confirmed/);
  assert.match(html, /Ask about this operation/);
  assert.match(html, /distributor-operations\.js/);
});
