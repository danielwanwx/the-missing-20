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
  normalizeHandoffs,
  groupHandoffs,
  normalizeContractPlan,
  contractPlanRows,
  contractDecisionState,
  retainConversationProjection,
  shouldPreserveTemplateFields,
  deliverySummary,
  arrivalQuantitySummary,
  unwrapProjection,
  recommendedAction,
  statusTone,
  deliveryCompletionLabel,
  normalizeFinancials,
  financialStatusMessage,
  financialOrderSummary,
  invoiceRecordSummary,
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

test('external handoffs group by provider and retain a verified evidence link', () => {
  const groups = groupHandoffs([
    {
      route: 'airtable-distributor', status: 'VERIFIED', updated_at: '2026-09-10T10:00:00Z',
      evidence: { provider: 'Airtable', record_id: 'rec-1', url: 'https://airtable.test/rec-1' },
    },
    {
      route: 'jira:create', status: 'VERIFIED', updated_at: '2026-09-10T10:01:00Z',
      evidence: { provider: 'Jira', record_id: 'M20-1', url: 'https://jira.test/M20-1' },
    },
  ]);
  assert.deepEqual(groups.map((group) => group.provider), ['Airtable', 'Jira']);
  assert.equal(groups[0].latest.status, 'VERIFIED');
  assert.equal(groups[0].last_verified.safe_url, 'https://airtable.test/rec-1');
});

test('pending latest handoff keeps the prior verified link explicitly historical', () => {
  const [group] = groupHandoffs([
    {
      route: 'jira:create', status: 'VERIFIED', updated_at: '2026-09-10T10:00:00Z',
      evidence: { provider: 'Jira', record_id: 'M20-1', url: 'https://jira.test/M20-1' },
    },
    {
      route: 'jira:comment', status: 'PENDING', updated_at: '2026-09-10T10:02:00Z',
      last_failure: { message: 'readback pending' }, evidence: { provider: 'Jira', record_id: 'M20-1' },
    },
  ]);
  assert.equal(group.latest.status, 'PENDING');
  assert.equal(group.last_verified.record_id, 'M20-1');
  assert.equal(group.last_verified.safe_url, 'https://jira.test/M20-1');
  assert.equal(group.latest.last_failure, 'readback pending');
});

test('journal-shaped handoff failures expose phase and kind safely', () => {
  const [handoff] = normalizeHandoffs([{
    route: 'jira', status: 'ERROR', updated_at: '2026-09-10T10:02:00Z',
    last_failure: { phase: 'readback', kind: 'provider_unavailable' }, evidence: { provider: 'Jira' },
  }]);
  assert.equal(handoff.last_failure, 'provider_unavailable · phase readback');
});

test('missing, unknown, and failed handoffs stay without a verified success link', () => {
  assert.deepEqual(groupHandoffs(undefined), []);
  const groups = groupHandoffs([
    { route: 'airtable', status: 'UNKNOWN', evidence: {} },
    { route: 'slack', status: 'ERROR', last_failure: 'provider unavailable', evidence: {} },
  ]);
  assert.deepEqual(groups.map((group) => group.latest.status).sort(), ['ERROR', 'UNKNOWN']);
  assert.equal(groups.every((group) => group.last_verified === null), true);
});

test('unsafe external evidence URLs are rejected before link rendering', () => {
  const [handoff] = normalizeHandoffs([{
    route: 'celigo', status: 'VERIFIED', evidence: { provider: 'Celigo', url: 'javascript:alert(1)' },
  }]);
  assert.equal(handoff.safe_url, '');
});

const contractPlan = {
  version: 'v1',
  plan_id: 'cap-demo-1',
  state_revision: 'rev-demo-1',
  new_quantity: 20,
  rows: [{
    customer_order: 'SO-7',
    promised_delivery_at: '2026-09-11T09:00:00+00:00',
    customer_priority: 2,
    partial_dispatch: true,
    minimum_dispatch_quantity: 10,
    allow_final_remainder: true,
    prepared_commitment: 0,
    new_quantity: 20,
    quantity: 20,
    remaining_after_dispatch: 4,
  }],
};

test('contract projection exposes exact terms and a matching selected decision', () => {
  const plan = normalizeContractPlan(contractPlan);
  assert.ok(plan);
  assert.deepEqual(contractPlanRows(plan), [{
    customer_order: 'SO-7',
    promised_delivery_at: '2026-09-11T09:00:00+00:00',
    customer_priority: 2,
    partial_dispatch: true,
    minimum_dispatch_quantity: 10,
    allow_final_remainder: true,
    prepared_commitment: 0,
    new_quantity: 20,
    quantity: 20,
    remaining_after_dispatch: 4,
  }]);
  assert.equal(contractDecisionState(plan, {
    status: 'SELECTED', plan_id: 'cap-demo-1', state_revision: 'rev-demo-1', event_id: 'evt-1',
  }), 'SELECTED');
});

test('pending or stale contract decisions never render as selected', () => {
  const plan = normalizeContractPlan(contractPlan);
  assert.equal(contractDecisionState(plan, { status: 'PENDING', plan_id: 'cap-demo-1', state_revision: 'rev-demo-1' }), 'PENDING');
  assert.equal(contractDecisionState(plan, { status: 'SELECTED', plan_id: 'cap-other', state_revision: 'rev-demo-1' }), 'PENDING');
  assert.equal(contractDecisionState(plan, { status: 'UNAVAILABLE' }), 'UNAVAILABLE');
  assert.equal(contractDecisionState(plan, null), 'UNAVAILABLE');
});

test('legacy projections have no contract panel data', () => {
  assert.equal(normalizeContractPlan({ version: 'v1', rows: [] }), null);
  assert.equal(normalizeContractPlan({ allocations: [{ customer_order: 'SO-legacy' }] }), null);
  assert.deepEqual(contractPlanRows(undefined), []);
});

test('contract values remain literal text for safe DOM rendering', () => {
  const hostileOrder = '<img src=x onerror=alert(1)>';
  const plan = normalizeContractPlan({
    ...contractPlan,
    rows: [{ ...contractPlan.rows[0], customer_order: hostileOrder }],
  });
  assert.equal(contractPlanRows(plan)[0].customer_order, hostileOrder);
  const source = fs.readFileSync(path.join(__dirname, '../workspace/distributor-operations.js'), 'utf8');
  assert.match(source, /order\.textContent = row\.customer_order/);
  assert.doesNotMatch(source, /order\.innerHTML/);
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

test('commercial projection preserves order line values and invoice-level amounts', () => {
  const financials = normalizeFinancials({
    status: 'CURRENT',
    purchase_order: {
      currency: 'USD',
      supplier: 'M20 Supplier',
      document: { name: 'PO-18', status: 'Submitted', url: '/app/purchase-order/PO-18' },
      line: { quantity: 40, rate: 4, net_amount: 160 },
    },
    sales_orders: [{
      currency: 'USD',
      customer: 'Demo Customer',
      document: { name: 'SO-11', status: 'To Deliver', url: '/app/sales-order/SO-11' },
      line: { quantity: 25, rate: 6, net_amount: 150 },
    }],
    purchase_invoices: { status: 'MISSING', records: [] },
    sales_invoices: [{ customer_order: 'SO-11', status: 'CURRENT', records: [{
      docstatus: 1,
      currency: 'USD',
      grand_total: 150,
      outstanding_amount: 150,
      document: { name: 'SI-11', status: 'Submitted', url: '/app/sales-invoice/SI-11' },
    }] }],
  });
  assert.equal(financials.status, 'CURRENT');
  assert.match(financialOrderSummary(financials.purchase_order, 'Box'), /Line amount: USD 160/);
  assert.match(financialOrderSummary(financials.sales_orders[0], 'Nos'), /Line amount: USD 150/);
  assert.match(invoiceRecordSummary(financials.sales_invoices[0].records[0]), /Docstatus 1/);
  assert.match(invoiceRecordSummary(financials.sales_invoices[0].records[0]), /Invoice-level grand total USD 150/);
  assert.match(invoiceRecordSummary(financials.sales_invoices[0].records[0]), /Invoice-level outstanding amount USD 150/);
});

test('missing and unavailable invoice states stay distinct and never say unpaid', () => {
  const missing = financialStatusMessage('MISSING', 'Purchase');
  const unavailable = financialStatusMessage('UNAVAILABLE', 'Sales');
  assert.match(missing, /No purchase invoice linked/i);
  assert.match(unavailable, /data is unavailable/i);
  assert.doesNotMatch(`${missing} ${unavailable}`, /unpaid/i);
  assert.equal(normalizeFinancials({ status: 'UNAVAILABLE' }).purchase_invoices.status, 'UNAVAILABLE');
  assert.deepEqual(normalizeFinancials({ status: 'UNAVAILABLE' }).purchase_invoices.records, []);
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
  assert.match(html, /Cross-system readback/);
  assert.match(html, /Commercial evidence/);
  assert.match(html, /Sales order line amounts are order values; they are not revenue/);
  assert.match(html, /ops-financials-panel/);
  assert.match(html, /distributor-operations\.js/);
});
