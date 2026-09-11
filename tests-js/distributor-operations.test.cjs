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
  contractPanelState,
  pendingAllocationEligibility,
  pendingAllocationRequest,
  normalizeAllocationRetries,
  allocationRetryForDecision,
  dispatchEligibilityText,
  allocationReviewOutcome,
  pendingAllocationActionState,
  shouldRetainPendingAllocationRetry,
  fulfillmentBenchmark,
  activeAlertStages,
  flowStageFacts,
  createVoiceController,
  projectionSourceState,
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

test('configured source failure stays distinct from a disabled operation', () => {
  assert.equal(projectionSourceState({
    available: false,
    case_id: 'SYN-OPS-SOURCE-FAILURE',
    stage: 'SOURCE_UNAVAILABLE',
    alerts: [{ code: 'SOURCE_UNAVAILABLE', status: 'OPEN' }],
  }), 'SOURCE_UNAVAILABLE');
  assert.equal(projectionSourceState({ available: false, case_id: '', stage: 'DISABLED' }), 'DISABLED');
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

test('a zero additional current plan keeps an earlier selection as historical evidence', () => {
  const completePlan = { ...contractPlan, new_quantity: 0, rows: [{ ...contractPlan.rows[0], new_quantity: 0 }] };
  assert.equal(contractPanelState(completePlan, {
    status: 'SELECTED', plan_id: 'cap-earlier', state_revision: 'rev-earlier', event_id: 'evt-earlier',
  }), 'COMPLETE');
});

test('pending allocation review uses only the pending decision event and an idempotency ID', () => {
  const projection = {
    case_id: 'CASE-ALLOCATION-1',
    allocation_decision: { status: 'PENDING', event_id: 'pending-source-event-12', pending_event_id: 'wrong-field' },
    events: [{ event_id: 'unrelated-event-1' }],
  };
  assert.deepEqual(pendingAllocationEligibility(projection), {
    status: 'PENDING', pending_event_id: 'pending-source-event-12', eligible: true, reason: '',
  });
  assert.deepEqual(pendingAllocationRequest(projection, 'retry-uuid-1'), {
    retry_id: 'retry-uuid-1', pending_event_id: 'pending-source-event-12',
  });
  assert.equal(pendingAllocationRequest({ allocation_decision: { status: 'PENDING', pending_event_id: 'wrong-field' }, events: [{ event_id: 'event-1' }] }, 'retry-uuid-2'), null);
  assert.equal(pendingAllocationRequest({ allocation_decision: { status: 'SELECTED', event_id: 'selected-event' }, events: [{ event_id: 'event-2' }] }, 'retry-uuid-3'), null);
});

test('allocation retry readback stays separate and matches the decision source', () => {
  const projection = {
    allocation_decision: { status: 'PENDING', event_id: 'pending-event-12' },
    events: [{ event_id: 'pending-event-12', status: 'BLOCKED' }],
    allocation_retries: [
      { retry_id: 'retry-1', pending_event_id: 'other-event', status: 'FAILED' },
      { retry_id: 'retry-2', pending_event_id: 'pending-event-12', status: 'PENDING', operations: [{ status: 'BLOCKED' }] },
    ],
  };
  assert.equal(allocationRetryForDecision(projection).retry_id, 'retry-2');
  assert.equal(allocationRetryForDecision(projection).status, 'PENDING');
  assert.equal(normalizeAllocationRetries(projection.allocation_retries).length, 2);
  assert.equal(allocationRetryForDecision({ allocation_decision: { status: 'PENDING', event_id: 'pending-event-12' }, events: [{ event_id: 'pending-event-12' }] }), null);
});

test('pending allocation action disables only the matching in-flight review', () => {
  const projection = {
    available: true,
    case_id: 'CASE-ALLOCATION-1',
    feasible_allocation_plan: contractPlan,
    allocation_decision: { status: 'PENDING', event_id: 'pending-event-12' },
  };
  const inFlight = pendingAllocationActionState(projection, {
    caseId: 'CASE-ALLOCATION-1', pendingEventId: 'pending-event-12', inFlight: true,
  });
  assert.equal(inFlight.eligible, true);
  assert.equal(inFlight.in_flight, true);
  assert.equal(inFlight.disabled, true);
  assert.match(inFlight.label, /Reviewing/);

  const ready = pendingAllocationActionState(projection, {
    caseId: 'CASE-ALLOCATION-1', pendingEventId: 'pending-event-12', inFlight: false,
  });
  assert.equal(ready.eligible, true);
  assert.equal(ready.in_flight, false);
  assert.equal(ready.disabled, false);
  assert.equal(ready.label, 'Review pending allocation');

  const otherCase = pendingAllocationActionState(projection, {
    caseId: 'CASE-OTHER', pendingEventId: 'pending-event-12', inFlight: true,
  });
  assert.equal(otherCase.disabled, false);
  assert.equal(otherCase.in_flight, false);
});

test('allocation retry feedback uses the submitted row and keeps dispatch separate', () => {
  const base = {
    available: true,
    case_id: 'CASE-ALLOCATION-1',
    feasible_allocation_plan: contractPlan,
    allocation_decision: { status: 'SELECTED', event_id: 'pending-event-12' },
  };
  const applied = allocationReviewOutcome({
    ...base,
    allocation_retries: [{
      retry_id: 'retry-applied', pending_event_id: 'pending-event-12', status: 'APPLIED',
      operations: [{ kind: 'prepare_pick', status: 'APPLIED' }],
    }],
  }, 'retry-applied');
  assert.equal(applied.status, 'APPLIED');
  assert.equal(applied.tone, 'success');
  assert.match(applied.message, /verified pick preparation/);
  assert.match(applied.message, /Dispatch remains a separate step/);
  assert.doesNotMatch(applied.message, /No pick/);

  const blocked = allocationReviewOutcome({
    ...base,
    allocation_retries: [{
      retry_id: 'retry-blocked', pending_event_id: 'pending-event-12', status: 'BLOCKED',
      operations: [{ kind: 'prepare_pick', status: 'BLOCKED' }],
    }],
  }, 'retry-blocked');
  assert.equal(blocked.tone, 'error');
  assert.doesNotMatch(blocked.message, /verified pick preparation/);

  const unknown = allocationReviewOutcome({
    ...base,
    allocation_retries: [{
      retry_id: 'retry-unknown', pending_event_id: 'pending-event-12', status: 'UNKNOWN_OUTCOME',
    }],
  }, 'retry-unknown');
  assert.equal(unknown.tone, 'error');
  assert.doesNotMatch(unknown.message, /verified pick preparation/);

  const pending = allocationReviewOutcome({
    ...base,
    allocation_retries: [{ retry_id: 'retry-pending', pending_event_id: 'pending-event-12', status: 'PENDING' }],
  }, 'retry-pending');
  assert.equal(pending.tone, 'error');
  assert.match(pending.message, /not confirmed/);

  const unavailable = allocationReviewOutcome({
    ...base,
    allocation_retries: [{ retry_id: 'retry-unavailable', pending_event_id: 'pending-event-12', status: 'UNAVAILABLE' }],
  }, 'retry-unavailable');
  assert.equal(unavailable.tone, 'error');
  assert.doesNotMatch(unavailable.message, /verified pick preparation/);

  const missingSubmittedRow = allocationReviewOutcome({
    ...base,
    allocation_retries: [{ retry_id: 'older', pending_event_id: 'pending-event-12', status: 'APPLIED' }],
  }, 'retry-that-was-submitted');
  assert.equal(missingSubmittedRow.status, 'UNKNOWN_OUTCOME');
  assert.equal(missingSubmittedRow.tone, 'error');
});

test('allocation retry fallback uses the latest matching action and known outcomes release its ID', () => {
  const projection = {
    allocation_decision: { status: 'PENDING', event_id: 'pending-event-12' },
    allocation_retries: [
      { retry_id: 'retry-old', pending_event_id: 'pending-event-12', status: 'BLOCKED' },
      { retry_id: 'retry-latest', pending_event_id: 'pending-event-12', status: 'PENDING' },
    ],
  };
  assert.equal(allocationRetryForDecision(projection).retry_id, 'retry-latest');
  assert.equal(shouldRetainPendingAllocationRetry(null, 'UNKNOWN_OUTCOME'), true);
  for (const status of ['APPLIED', 'PENDING', 'UNAVAILABLE', 'BLOCKED']) {
    assert.equal(shouldRetainPendingAllocationRetry(null, status), false, status);
  }
  assert.equal(shouldRetainPendingAllocationRetry({ status: 503 }, ''), true);
  assert.equal(shouldRetainPendingAllocationRetry({ status: 409 }, ''), false);
});

test('dispatch eligibility is rendered as an explicit source-backed term', () => {
  assert.equal(dispatchEligibilityText('NO_DISPATCH_REMAINING'), 'No dispatch remains for this order');
  assert.equal(dispatchEligibilityText('FINAL_REMAINDER_ALLOWED'), 'Eligible for an allowed final remainder');
  assert.equal(dispatchEligibilityText('MEETS_MINIMUM'), 'Meets the minimum dispatch quantity');
  const [row] = contractPlanRows({
    ...contractPlan,
    rows: [{ ...contractPlan.rows[0], dispatch_eligibility: 'NO_DISPATCH_REMAINING' }],
  });
  assert.equal(row.dispatch_eligibility, 'NO_DISPATCH_REMAINING');
});

test('current-case benchmark compares only source-backed commitments and recorded completion', () => {
  const benchmark = fulfillmentBenchmark({
    available: true,
    synthetic_input: true,
    quantities: { uom: 'Nos', dispatched: 40, delivery_confirmed: 40 },
    allocations: [{ customer_order: 'SO-A', requested: 25 }, { customer_order: 'SO-B', requested: 15 }],
  });
  assert.deepEqual(benchmark, {
    status: 'CURRENT', target: 40, dispatched: 40, confirmed: 40, unit: 'Nos', order_count: 2, synthetic: true,
  });
  assert.equal(fulfillmentBenchmark({ available: true, quantities: { dispatched: 0, delivery_confirmed: 0 }, allocations: [] }).status, 'UNAVAILABLE');
  assert.equal(fulfillmentBenchmark({
    available: true, quantities: { dispatched: 25, delivery_confirmed: 25 },
    allocations: [{ customer_order: 'SO-A', requested: 25 }, { customer_order: 'SO-B' }],
  }).status, 'UNAVAILABLE');
});

test('flow distinguishes current zero stock from cumulative completed work and only flags open alerts', () => {
  const projection = {
    available: true,
    synthetic_input: true,
    quantities: { uom: 'Nos', ordered: 40, usable: 0, held: 0, allocated: 0, dispatched: 40, delivery_confirmed: 40 },
    allocations: [{ customer_order: 'SO-A', requested: 25, picked: 25 }, { customer_order: 'SO-B', requested: 15, picked: 15 }],
    alerts: [{ code: 'QUALITY_CHECK', status: 'RESOLVED' }, { code: 'PARTS_SHORTAGE', status: 'OPEN' }],
    events: [], lots: [],
  };
  assert.match(flowStageFacts(projection, { key: 'inspection', metric: 'usable', detail: 'Quality evidence' }).current, /No current hold/);
  assert.match(flowStageFacts(projection, { key: 'allocation', metric: 'allocated', detail: 'Customer demand' }).current, /No stock awaiting allocation/);
  assert.deepEqual(activeAlertStages(projection), { arrival: { index: 1, code: 'PARTS_SHORTAGE' } });
});

test('voice controller dictates English into the input without sending and reads only on request', () => {
  const input = { value: 'Which order', focused: false, focus() { this.focused = true; } };
  const statuses = [];
  const dictateButton = { disabled: false, attributes: {}, setAttribute(key, value) { this.attributes[key] = value; } };
  const readButton = { disabled: false };
  const stopButton = { hidden: true };
  let recognition;
  class FakeRecognition {
    start() { this.started = true; }
    stop() { this.stopped = true; this.onend(); }
  }
  const synthesis = { spoken: [], cancelled: 0, speak(value) { this.spoken.push(value); }, cancel() { this.cancelled += 1; } };
  const voice = createVoiceController({
    recognitionFactory: () => { recognition = new FakeRecognition(); return recognition; },
    speechSynthesisApi: synthesis,
    utteranceFactory: (value) => ({ text: value }),
    input,
    setStatus: (message) => statuses.push(message),
    dictateButton, readButton, stopButton,
  });
  assert.deepEqual(voice.support(), { dictation: true, reading: true });
  voice.toggleDictation();
  assert.equal(recognition.lang, 'en-US');
  recognition.onresult({ results: [[{ transcript: 'can ship now' }]] });
  assert.equal(input.value, 'Which order can ship now');
  assert.equal(input.focused, true);
  assert.match(statuses.at(-1), /Review it/);
  recognition.onerror({ error: 'not-allowed' });
  assert.match(statuses.at(-1), /permission was denied/);
  voice.setAnswer('The current source records 40 dispatched.');
  assert.equal(readButton.disabled, false);
  voice.readAnswer();
  assert.equal(synthesis.spoken[0].lang, 'en-US');
  assert.equal(stopButton.hidden, false);
  voice.setAnswer('A replacement answer from the current source.');
  assert.equal(synthesis.cancelled, 1);
  assert.equal(stopButton.hidden, true);
  voice.readAnswer();
  voice.setAnswer('A replacement answer from the current source.');
  assert.equal(synthesis.cancelled, 1);
  voice.setAnswer('');
  assert.equal(synthesis.cancelled, 2);
  voice.stopReading();
  assert.equal(synthesis.cancelled, 3);
});

test('voice controller leaves typed interaction usable when browser speech is unsupported', () => {
  const statuses = [];
  const voice = createVoiceController({
    recognitionFactory: () => { throw new Error('unsupported'); },
    input: { value: '' }, setStatus: (message) => statuses.push(message),
  });
  assert.deepEqual(voice.support(), { dictation: false, reading: false });
  assert.equal(voice.toggleDictation(), false);
  assert.match(statuses.at(-1), /Typing remains available/);
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
  assert.match(html, /Completion against customer commitments/);
  assert.match(html, /Historical, industry, and savings baselines are unavailable/);
  assert.match(html, /Dictate in English/);
  assert.match(html, /Dictation only fills the question/);
  assert.match(html, /ops-resolved-alerts/);
  assert.ok(html.indexOf('id="ops-chat-panel"') < html.indexOf('id="ops-evidence-panel"'));
  assert.match(html, /href="#ops-chat-panel"/);
  assert.match(html, /distributor-operations\.js/);
  assert.match(html, /ops-quantity-allocated-label/);
  const javascript = fs.readFileSync(path.join(__dirname, '../workspace/distributor-operations.js'), 'utf8');
  assert.match(javascript, /reselect-pending-allocation/);
  assert.match(javascript, /Review pending allocation/);
});
