/* Distributor operations is a small source-driven view. It never invents a
 * quantity, event, delivery, or conversation answer when the API is silent. */
(() => {
  "use strict";

  const API_PATH = "/api/v1/distributor-operations";
  const EVENT_TYPES = new Set(["arrival", "inspection", "picked", "carrier_pickup", "delivery"]);
  const NUMBER_FIELDS = new Set([
    "cartons", "expected_pack_quantity", "observed_stock_quantity", "sample_quantity", "quantity", "measured",
  ]);
  const FIELD_DEFS = {
    arrival: [
      { key: "cartons", label: "Cartons observed", type: "number", min: "0", step: "1" },
      { key: "expected_pack_quantity", label: "Expected parts per carton", type: "number", min: "0", step: "any" },
      { key: "observed_stock_quantity", label: "Parts counted", type: "number", min: "0", step: "any" },
      { key: "item_code", label: "Item code", type: "text" },
      { key: "lot", label: "Lot / batch", type: "text" },
    ],
    inspection: [
      { key: "lot", label: "Lot / batch", type: "text" },
      { key: "result", label: "Result", type: "select", options: ["PASS", "FAIL"] },
      { key: "scope", label: "Inspection scope", type: "select", options: ["SAMPLE", "WHOLE_LOT"] },
      { key: "metric", label: "Metric", type: "text", placeholder: "e.g. diameter" },
      { key: "measured", label: "Measured value", type: "number", min: "0", step: "any" },
      { key: "inspection_report_ref", label: "Inspection report ID", type: "text", placeholder: "e.g. QI-2026-004" },
      { key: "sample_quantity", label: "Sample quantity", type: "number", min: "0", step: "any" },
    ],
    picked: [
      { key: "customer_order", label: "Customer order", type: "text" },
      { key: "lot", label: "Lot / batch", type: "text" },
      { key: "quantity", label: "Picked quantity", type: "number", min: "0", step: "any" },
      { key: "pick_evidence_ref", label: "Pick evidence ID", type: "text" },
    ],
    carrier_pickup: [
      { key: "shipment_id", label: "Shipment", type: "text" },
    ],
    delivery: [
      { key: "shipment_id", label: "Shipment", type: "text" },
    ],
  };
  const STAGES = [
    { key: "arrival", label: "Received", icon: "ph-package", metric: "received", detail: "Source receipt" },
    { key: "inspection", label: "Inspection", icon: "ph-seal-check", metric: "usable", detail: "Quality evidence" },
    { key: "allocation", label: "Allocated", icon: "ph-users-three", metric: "allocated", detail: "Customer demand" },
    { key: "picked", label: "Picked", icon: "ph-hand-grabbing", metric: "picked", detail: "Actual picked input" },
    { key: "dispatch", label: "Dispatched", icon: "ph-truck", metric: "dispatched", detail: "Native dispatch" },
    { key: "delivery", label: "Delivery confirmed", icon: "ph-check-circle", metric: "delivery_confirmed", detail: "Explicit evidence" },
  ];

  const isRecord = (value) => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const text = (value) => typeof value === "string" ? value.trim() : "";
  const firstText = (record, keys) => {
    if (!isRecord(record)) return "";
    for (const key of keys) {
      const value = text(record[key]);
      if (value) return value;
    }
    return "";
  };
  const numberFrom = (value) => {
    if (finite(value)) return value;
    if (!isRecord(value)) return null;
    for (const key of ["value", "quantity", "count", "observed", "actual", "total"]) {
      if (finite(value[key])) return value[key];
    }
    return null;
  };
  const numberFromKeys = (record, keys) => {
    if (!isRecord(record)) return null;
    for (const key of keys) {
      const value = numberFrom(record[key]);
      if (finite(value)) return value;
    }
    return null;
  };
  const formatNumber = (value) => finite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : "Unknown";
  const formatDate = (value) => {
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed)) return "Time unavailable";
    return new Date(parsed).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const isRetainedEvidence = (value) => text(value?.status).toUpperCase() === "RETAINED_AS_OF";
  const conversationInferenceCapability = (value) => {
    const records = [];
    if (isRecord(value)) {
      records.push(value);
      if (isRecord(value.conversation)) records.push(value.conversation);
    }
    for (const record of records) {
      const candidate = record.inference_capability
        ?? record.conversation_capability
        ?? record.live_inference
        ?? record.capability;
      const state = isRecord(candidate) ? (candidate.status ?? candidate.state ?? candidate.value) : candidate;
      if (state === true || /^(AVAILABLE|LIVE|READY|ENABLED|TRUE)$/i.test(text(state))) return "live inference available";
    }
    return "";
  };
  const retainedEvidenceLabel = (value, conversation = null) => {
    if (!isRecord(value)) return "";
    const asOf = text(value.as_of);
    if (!isRetainedEvidence(value) || !asOf || !Number.isFinite(Date.parse(asOf))) return "";
    return `Retained accepted evidence · as of ${formatDate(asOf)} · ${conversationInferenceCapability(conversation) || "read-only Agent available when configured"}`;
  };
  const erpEvidenceSourceLabel = (value) => isRetainedEvidence(value)
    ? "retained accepted ERP evidence"
    : "current ERP source";
  const freshActionsAllowed = (value) => value?.actions_enabled !== false;
  const sourceAwareErpText = (value, evidenceMode) => {
    const source = erpEvidenceSourceLabel(evidenceMode);
    return text(value)
      .replace(/current ERP source/gi, source)
      .replace(/current source/gi, source);
  };
  const pretty = (value) => text(value).replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

  function canonicalType(value) {
    const key = text(value).toLowerCase().replace(/[-\s]+/g, "_");
    if (key === "carrierpickup" || key === "pickup" || key === "carrier_pick_up") return "carrier_pickup";
    if (key === "delivery_confirmation" || key === "carrier_delivery") return "delivery";
    return EVENT_TYPES.has(key) ? key : "";
  }

  function templateDefault(template, key) {
    if (!isRecord(template)) return "";
    const candidates = [template, template.defaults, template.values, template.payload];
    for (const candidate of candidates) {
      if (isRecord(candidate) && candidate[key] !== undefined && candidate[key] !== null) return candidate[key];
    }
    if (Array.isArray(template.fields)) {
      const field = template.fields.find((item) => isRecord(item) && text(item.name || item.key) === key);
      if (field && field.value !== undefined && field.value !== null) return field.value;
    }
    return "";
  }

  function normalizeTemplate(template, index = 0) {
    if (typeof template === "string") {
      const type = canonicalType(template);
      return type ? { type, label: pretty(type), description: "Declared synthetic evidence", source: "Simulated operator input", _index: index } : null;
    }
    if (!isRecord(template)) return null;
    const type = canonicalType(template.type || template.event_type || template.kind || template.name);
    if (!type) return null;
    return {
      ...template,
      type,
      label: firstText(template, ["label", "title", "name"]) || pretty(type),
      description: firstText(template, ["description", "summary", "help"]) || "Declared synthetic evidence",
      source: firstText(template, ["source", "source_label", "provider"]) || "Simulated operator input",
      _index: index,
    };
  }

  function normalizeTemplates(value) {
    if (!Array.isArray(value)) return [];
    return value.map((template, index) => normalizeTemplate(template, index)).filter(Boolean);
  }

  function shouldPreserveTemplateFields({ currentType, nextType, fieldsRendered = false, resetFields = false } = {}) {
    return Boolean(!resetFields && currentType && nextType && currentType === nextType && fieldsRendered);
  }

  function normalizeProjection(value) {
    const source = isRecord(value) ? value : {};
    const provided = {
      quantities: isRecord(source.quantities),
      lots: Array.isArray(source.lots),
      allocations: Array.isArray(source.allocations),
      alerts: Array.isArray(source.alerts),
      events: Array.isArray(source.events),
      documents: Array.isArray(source.documents),
      handoffs: Array.isArray(source.handoffs),
      financials: isRecord(source.financials),
      available_event_templates: Array.isArray(source.available_event_templates),
    };
    return {
      ...source,
      available: source.available === true,
      case_id: text(source.case_id),
      case_label: text(source.case_label),
      stage: text(source.stage) || "UNKNOWN",
      quantities: isRecord(source.quantities) ? { ...source.quantities } : {},
      lots: Array.isArray(source.lots) ? source.lots : [],
      allocations: Array.isArray(source.allocations) ? source.allocations : [],
      alerts: Array.isArray(source.alerts) ? source.alerts : [],
      events: Array.isArray(source.events) ? source.events : [],
      documents: Array.isArray(source.documents) ? source.documents : [],
      handoffs: Array.isArray(source.handoffs) ? source.handoffs : [],
      financials: isRecord(source.financials) ? normalizeFinancials(source.financials) : {},
      available_event_templates: normalizeTemplates(source.available_event_templates),
      conversation: Array.isArray(source.conversation)
        ? source.conversation
        : isRecord(source.conversation) ? { ...source.conversation } : {},
      _provided: provided,
    };
  }

  function handoffFailureText(value) {
    if (typeof value === "string") return text(value);
    if (!isRecord(value)) return "";
    const detail = firstText(value, ["message", "detail", "reason", "error", "code"]);
    if (detail) return detail;
    const kind = firstText(value, ["kind"]);
    const phase = firstText(value, ["phase"]);
    return [kind, phase ? `phase ${phase}` : ""].filter(Boolean).join(" · ");
  }

  function handoffProvider(record, evidence) {
    const raw = firstText(evidence, ["provider"]) || firstText(record, ["provider", "route"]);
    const value = raw.toLowerCase();
    if (value.includes("airtable")) return "Airtable";
    if (value.includes("jira")) return "Jira";
    if (value.includes("slack")) return "Slack via Celigo";
    if (value.includes("celigo")) return "Celigo";
    return raw ? pretty(raw) : "External record";
  }

  function normalizeHandoffs(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(isRecord).map((record, index) => {
      const evidence = isRecord(record.evidence) ? record.evidence : {};
      const url = firstText(evidence, ["url", "href"]);
      return {
        provider: handoffProvider(record, evidence),
        status: firstText(record, ["status", "state"]) || "Status unavailable",
        updated_at: firstText(record, ["updated_at", "updatedAt", "readback_at"]),
        record_id: firstText(evidence, ["record_id", "id", "key", "name"]),
        url,
        safe_url: safeHref(url),
        last_failure: handoffFailureText(record.last_failure),
        _index: index,
      };
    });
  }

  function groupHandoffs(value) {
    const groups = new Map();
    for (const handoff of normalizeHandoffs(value)) {
      const key = handoff.provider.toLowerCase();
      if (!groups.has(key)) groups.set(key, { provider: handoff.provider, records: [] });
      groups.get(key).records.push(handoff);
    }
    return [...groups.values()].map((group) => {
      const records = [...group.records].sort((left, right) => {
        const leftTime = Date.parse(left.updated_at);
        const rightTime = Date.parse(right.updated_at);
        if (Number.isFinite(leftTime) && Number.isFinite(rightTime) && leftTime !== rightTime) return rightTime - leftTime;
        return right._index - left._index;
      });
      return {
        provider: group.provider,
        latest: records[0],
        last_verified: records.find((record) => record.status.toUpperCase() === "VERIFIED") || null,
        records,
      };
    });
  }

  function normalizeInvoiceGroup(value) {
    const source = isRecord(value) ? value : {};
    const rawStatus = text(source.status).toUpperCase();
    const status = ["CURRENT", "MISSING", "UNAVAILABLE"].includes(rawStatus) ? rawStatus : "UNAVAILABLE";
    return {
      ...source,
      status,
      records: Array.isArray(source.records) ? source.records.filter(isRecord) : [],
    };
  }

  function normalizeFinancials(value) {
    const source = isRecord(value) ? value : {};
    return {
      ...source,
      status: ["CURRENT", "UNAVAILABLE"].includes(text(source.status).toUpperCase())
        ? text(source.status).toUpperCase()
        : "UNAVAILABLE",
      purchase_order: isRecord(source.purchase_order) ? { ...source.purchase_order } : null,
      sales_orders: Array.isArray(source.sales_orders) ? source.sales_orders.filter(isRecord) : [],
      purchase_invoices: normalizeInvoiceGroup(source.purchase_invoices),
      sales_invoices: Array.isArray(source.sales_invoices)
        ? source.sales_invoices.filter(isRecord).map((row) => ({
          ...row,
          customer_order: firstText(row, ["customer_order", "sales_order"]),
          ...normalizeInvoiceGroup(row),
        }))
        : [],
    };
  }

  function financialStatusMessage(status, kind = "", evidenceMode = null) {
    const label = kind ? `${kind} invoice` : "Invoice";
    const source = erpEvidenceSourceLabel(evidenceMode);
    const normalized = text(status).toUpperCase();
    if (normalized === "CURRENT") return `${source[0].toUpperCase()}${source.slice(1)} returned invoice records.`;
    if (normalized === "MISSING") return `No ${label.toLowerCase()} linked in the ${source}.`;
    return `${label} data is unavailable from the ${source}.`;
  }

  function formatMoney(value, currency) {
    const amount = numberFrom(value);
    const unit = text(currency);
    if (!finite(amount)) return "Amount unavailable";
    return unit ? `${unit} ${formatNumber(amount)}` : `Amount known; currency unavailable (${formatNumber(amount)})`;
  }

  function financialOrderSummary(order, unit = "units") {
    const line = isRecord(order?.line) ? order.line : {};
    const currency = text(order?.currency);
    const amount = formatMoney(line.net_amount, currency);
    const rate = formatMoney(line.rate, currency);
    const quantity = numberFrom(line.quantity);
    const quantityText = finite(quantity) ? `${formatNumber(quantity)} ${unit}` : "Quantity unavailable";
    return `Line amount: ${amount} · Rate: ${rate} × ${quantityText}`;
  }

  function invoiceRecordSummary(record) {
    if (!isRecord(record)) return "Invoice record unavailable.";
    const documentRecord = isRecord(record.document) ? record.document : {};
    const docstatus = finite(numberFrom(record.docstatus)) ? `Docstatus ${formatNumber(numberFrom(record.docstatus))}` : "Docstatus unavailable";
    const status = firstText(documentRecord, ["status"]) || "Status unavailable";
    const currency = text(record.currency) || "Currency unavailable";
    return `${docstatus} · Status ${status} · Currency ${currency} · Invoice-level grand total ${formatMoney(record.grand_total, record.currency)} · Invoice-level outstanding amount ${formatMoney(record.outstanding_amount, record.currency)}`;
  }

  function normalizeContractPlan(value) {
    if (!isRecord(value) || text(value.version) !== "v1" || !text(value.plan_id) || !text(value.state_revision) || !Array.isArray(value.rows) || !value.rows.length) return null;
    if (value.rows.some((row) => !isRecord(row) || !firstText(row, ["customer_order"]))) return null;
    return {
      ...value,
      version: "v1",
      plan_id: text(value.plan_id),
      state_revision: text(value.state_revision),
      rows: value.rows,
    };
  }

  function contractPlanRows(plan) {
    const normalized = normalizeContractPlan(plan);
    if (!normalized) return [];
    return normalized.rows.map((row) => {
      const dispatchEligibility = firstText(row, ["dispatch_eligibility"]);
      return {
        customer_order: firstText(row, ["customer_order"]),
        promised_delivery_at: firstText(row, ["promised_delivery_at"]),
        customer_priority: numberFrom(row.customer_priority),
        partial_dispatch: typeof row.partial_dispatch === "boolean" ? row.partial_dispatch : null,
        minimum_dispatch_quantity: numberFrom(row.minimum_dispatch_quantity),
        allow_final_remainder: typeof row.allow_final_remainder === "boolean" ? row.allow_final_remainder : null,
        prepared_commitment: numberFrom(row.prepared_commitment),
        new_quantity: numberFrom(row.new_quantity),
        quantity: numberFrom(row.quantity),
        remaining_after_dispatch: numberFrom(row.remaining_after_dispatch),
        ...(dispatchEligibility ? { dispatch_eligibility: dispatchEligibility } : {}),
      };
    });
  }

  function contractDecisionState(plan, decision) {
    const normalized = normalizeContractPlan(plan);
    if (!normalized || !isRecord(decision)) return "UNAVAILABLE";
    const status = text(decision.status).toUpperCase();
    if (status === "PENDING") return "PENDING";
    if (status !== "SELECTED") return "UNAVAILABLE";
    return text(decision.plan_id) === normalized.plan_id && text(decision.state_revision) === normalized.state_revision
      ? "SELECTED"
      : "PENDING";
  }

  function contractPanelState(plan, decision) {
    const normalized = normalizeContractPlan(plan);
    if (!normalized) return "UNAVAILABLE";
    if (numberFrom(normalized.new_quantity) === 0) return "COMPLETE";
    return contractDecisionState(normalized, decision);
  }

  function pendingAllocationEligibility(projectionValue) {
    const decision = isRecord(projectionValue?.allocation_decision) ? projectionValue.allocation_decision : {};
    const status = text(decision.status).toUpperCase();
    if (status !== "PENDING") {
      return {
        status,
        pending_event_id: "",
        eligible: false,
        reason: status ? "Only a pending allocation decision can be reviewed." : "No pending allocation decision is recorded.",
      };
    }
    const pendingEventId = text(decision.event_id);
    return {
      status,
      pending_event_id: pendingEventId,
      eligible: Boolean(pendingEventId),
      reason: pendingEventId ? "" : "Pending allocation review is unavailable because the source event ID is missing.",
    };
  }

  function pendingAllocationRequest(projectionValue, retryId) {
    const eligibility = pendingAllocationEligibility(projectionValue);
    const id = text(retryId);
    if (!eligibility.eligible || !id) return null;
    return { retry_id: id, pending_event_id: eligibility.pending_event_id };
  }

  function normalizeAllocationRetries(value) {
    if (!Array.isArray(value)) return [];
    return value.filter(isRecord).map((retry, index) => ({
      ...retry,
      retry_id: text(retry.retry_id),
      pending_event_id: text(retry.pending_event_id),
      status: text(retry.status) || "Status unavailable",
      plan_id: text(retry.plan_id),
      state_revision: text(retry.state_revision),
      operations: Array.isArray(retry.operations) ? retry.operations : [],
      _index: index,
    })).filter((retry) => retry.retry_id || retry.pending_event_id);
  }

  function allocationRetryForDecision(projectionValue, submittedRetryId = "") {
    if (!isRecord(projectionValue) || !isRecord(projectionValue.allocation_decision)) return null;
    const decision = projectionValue.allocation_decision;
    const retries = normalizeAllocationRetries(projectionValue.allocation_retries);
    const requestedRetryId = text(submittedRetryId);
    if (requestedRetryId) return retries.find((retry) => retry.retry_id === requestedRetryId) || null;
    const decisionRetryId = text(decision.retry_id);
    if (decisionRetryId) return retries.find((retry) => retry.retry_id === decisionRetryId) || null;
    const pendingEventId = text(decision.event_id);
    return [...retries].reverse().find((retry) => pendingEventId && retry.pending_event_id === pendingEventId) || null;
  }

  function dispatchEligibilityText(value) {
    const source = text(value).toUpperCase();
    const labels = {
      FINAL_REMAINDER_ALLOWED: "Eligible for an allowed final remainder",
      MEETS_MINIMUM: "Meets the minimum dispatch quantity",
      NO_DISPATCH_REMAINING: "No dispatch remains for this order",
      NOT_EXECUTABLE: "Not executable from the current stock",
    };
    return labels[source] || (source ? `Source status: ${pretty(source)}` : "");
  }

  function allocationReviewOutcome(projectionValue, submittedRetryId) {
    const retry = allocationRetryForDecision(projectionValue, submittedRetryId);
    if (!retry) {
      return {
        status: "UNKNOWN_OUTCOME",
        tone: "error",
        message: "Pending allocation review outcome is unavailable. No pick or dispatch claim can be made.",
      };
    }
    const status = text(retry.status).toUpperCase();
    const decisionStatus = text(projectionValue?.allocation_decision?.status).toUpperCase();
    const operationStatuses = retry.operations
      .filter(isRecord)
      .map((operation) => text(operation.status).toUpperCase());
    if (status === "UNKNOWN_OUTCOME" || operationStatuses.includes("UNKNOWN_OUTCOME")) {
      return {
        status,
        tone: "error",
        message: "Pending allocation review has an unknown native outcome. No pick or dispatch claim can be made; review the source before retrying.",
      };
    }
    if (status === "BLOCKED" || operationStatuses.includes("BLOCKED")) {
      return {
        status,
        tone: "error",
        message: "Pending allocation review was blocked before completion. Dispatch remains separate; review the source before continuing.",
      };
    }
    if (status === "APPLIED") {
      return {
        status,
        tone: "success",
        message: decisionStatus === "SELECTED"
          ? "Pending allocation review selected the plan and verified pick preparation. Dispatch remains a separate step."
          : "Pending allocation review verified pick preparation. Dispatch remains a separate step.",
      };
    }
    if (status === "PENDING") {
      return {
        status,
        tone: "error",
        message: "Pending allocation review remains pending. Pick preparation is not confirmed.",
      };
    }
    return {
      status: status || "UNKNOWN_OUTCOME",
      tone: "error",
      message: `Pending allocation review returned ${pretty(status || "an unknown status")}. No pick or dispatch claim can be made.`,
    };
  }

  function pendingAllocationActionState(projectionValue, action, { sourceReady = true, panelVisible = true } = {}) {
    const eligibility = pendingAllocationEligibility(projectionValue);
    const contractState = contractPanelState(projectionValue?.feasible_allocation_plan, projectionValue?.allocation_decision);
    const eligible = Boolean(projectionValue?.available === true && freshActionsAllowed(projectionValue) && contractState === "PENDING"
      && eligibility.eligible && sourceReady && panelVisible);
    const matches = Boolean(isRecord(action)
      && text(action.caseId) === text(projectionValue?.case_id)
      && text(action.pendingEventId) === eligibility.pending_event_id);
    const inFlight = Boolean(eligible && matches && action.inFlight === true);
    return {
      eligible,
      in_flight: inFlight,
      disabled: !eligible || inFlight,
      label: inFlight ? "Reviewing pending allocation…" : "Review pending allocation",
    };
  }

  function shouldRetainPendingAllocationRetry(requestError, outcomeStatus = "") {
    if (requestError) {
      const status = Number(requestError.status);
      return !(Number.isFinite(status) && status >= 400 && status < 500);
    }
    return text(outcomeStatus).toUpperCase() === "UNKNOWN_OUTCOME";
  }

  function allocationQuantity(allocation, keys) {
    return numberFromKeys(allocation, keys);
  }

  function fulfillmentBenchmark(next) {
    if (!isRecord(next) || next.available !== true || !isRecord(next.quantities) || !Array.isArray(next.allocations)) {
      return { status: "UNAVAILABLE", reason: "The current source does not provide comparable fulfillment facts." };
    }
    const targets = next.allocations.map((allocation) =>
      allocationQuantity(allocation, ["ordered", "requested", "requested_quantity", "demand", "quantity"])
    );
    if (!targets.length || targets.some((value) => !finite(value) || value < 0)) {
      return { status: "UNAVAILABLE", reason: "Customer commitment quantities are unavailable from the current source." };
    }
    const target = targets.reduce((total, value) => total + value, 0);
    const dispatched = quantity(next, "dispatched");
    const confirmed = quantity(next, "delivery_confirmed");
    if (!finite(dispatched) || !finite(confirmed) || target <= 0) {
      return { status: "UNAVAILABLE", reason: "Current dispatch or delivery-confirmation quantities are unavailable." };
    }
    return {
      status: "CURRENT",
      target,
      dispatched,
      confirmed,
      unit: text(next.quantities.uom) || "units",
      order_count: targets.length,
      synthetic: next.synthetic_input === true,
    };
  }

  function alertStatus(alert) {
    return firstText(alert, ["status", "state"]).toUpperCase();
  }
  function isResolvedAlert(alert) {
    return /RESOLVED|CLOSED|DONE/.test(alertStatus(alert));
  }
  function alertStage(alert) {
    const code = firstText(alert, ["code", "kind", "message", "detail"]).toUpperCase();
    if (/QUALITY|INSPECTION|HOLD|SPEC/.test(code)) return "inspection";
    if (/SHORT|MISSING|RECEIV|ARRIV|LOT|BATCH/.test(code)) return "arrival";
    if (/ALLOC|RESERV|CUSTOMER|CONTRACT/.test(code)) return "allocation";
    if (/PICK/.test(code)) return "picked";
    if (/DISPATCH|SHIP|CARRIER/.test(code)) return "dispatch";
    if (/DELIVERY|POD/.test(code)) return "delivery";
    return "";
  }
  function activeAlertStages(next) {
    if (!Array.isArray(next?.alerts)) return {};
    return next.alerts.reduce((stages, alert, index) => {
      if (!isRecord(alert) || isResolvedAlert(alert)) return stages;
      const stage = alertStage(alert);
      if (stage && !stages[stage]) stages[stage] = { index, code: firstText(alert, ["code", "kind"]) || "Active alert" };
      return stages;
    }, {});
  }

  function flowStageFacts(next, stage) {
    const unit = text(next?.quantities?.uom) || "units";
    const current = quantity(next, stage.metric);
    const dispatched = quantity(next, "dispatched");
    const ordered = quantity(next, "ordered");
    if (stage.key === "inspection") {
      const held = quantity(next, "held");
      if (finite(held) && held > 0) return { current: `${formatNumber(held)} held now`, cumulative: "Review inspection evidence", complete: false };
      if (finite(dispatched) && dispatched > 0) return { current: "No current hold", cumulative: `${formatNumber(dispatched)} released to fulfillment`, complete: true };
      return { current: finite(current) ? `${formatNumber(current)} usable now` : "Inspection status unknown", cumulative: "Quality evidence", complete: stageProof(next, stage) };
    }
    if (stage.key === "allocation") {
      const pending = pendingAllocationEligibility(next);
      if (pending.status === "PENDING") {
        return {
          current: finite(current) ? `${formatNumber(current)} proposed` : "Proposed allocation quantity unknown",
          cumulative: "Decision pending · no allocation prepared",
          complete: false,
        };
      }
      const target = fulfillmentBenchmark(next);
      if (target.status === "CURRENT" && target.dispatched >= target.target) return { current: "No stock awaiting allocation", cumulative: `${formatNumber(target.target)} / ${formatNumber(target.target)} committed`, complete: true };
      return { current: finite(current) ? `${formatNumber(current)} allocated now` : "Allocation status unknown", cumulative: stage.detail, complete: stageProof(next, stage) };
    }
    if (stage.key === "picked") {
      const picked = (Array.isArray(next?.allocations) ? next.allocations : []).reduce((total, allocation) => {
        const value = allocationQuantity(allocation, ["picked", "picked_quantity", "picked_qty"]);
        return finite(value) ? total + value : total;
      }, 0);
      return { current: picked > 0 ? `${formatNumber(picked)} picked cumulatively` : "Picked evidence pending", cumulative: picked > 0 ? `Recorded in current case · ${unit}` : stage.detail, complete: picked > 0 || pickedEvidenceRecorded(next) };
    }
    if (stage.key === "delivery") {
      const label = finite(current) ? `${formatNumber(current)} recorded ${next.synthetic_input === true ? "synthetic " : ""}confirmations` : "Delivery confirmation unknown";
      return { current: label, cumulative: finite(ordered) ? `${formatNumber(current)} / ${formatNumber(ordered)} ${unit}` : stage.detail, complete: finite(current) && current > 0 };
    }
    if (stage.key === "dispatch") {
      return { current: finite(dispatched) ? `${formatNumber(dispatched)} dispatched cumulatively` : "Dispatch status unknown", cumulative: finite(ordered) ? `${formatNumber(dispatched)} / ${formatNumber(ordered)} ${unit}` : stage.detail, complete: finite(dispatched) && dispatched > 0 };
    }
    return { current: finite(current) ? `${formatNumber(current)} ${unit}` : `${stage.detail} unknown`, cumulative: stage.detail, complete: stageProof(next, stage) };
  }

  function createVoiceController({ recognitionFactory, speechSynthesisApi, utteranceFactory, input, setStatus, dictateButton, readButton, stopButton } = {}) {
    const updateStatus = (value) => { if (typeof setStatus === "function") setStatus(value); };
    let recognition = null;
    try { recognition = typeof recognitionFactory === "function" ? recognitionFactory() : null; } catch (_) { recognition = null; }
    const synthesis = speechSynthesisApi && typeof speechSynthesisApi.speak === "function" ? speechSynthesisApi : null;
    let listening = false;
    let reading = false;
    let answer = "";
    const setButtons = () => {
      if (dictateButton) { dictateButton.disabled = !recognition; dictateButton.setAttribute?.("aria-pressed", String(listening)); }
      if (readButton) readButton.disabled = !synthesis || !answer || reading;
      if (stopButton) stopButton.hidden = !reading;
    };
    if (recognition) {
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;
      recognition.onresult = (event) => {
        const result = event?.results?.[event.results.length - 1];
        const transcript = text(result?.[0]?.transcript);
        if (transcript && input) input.value = [text(input.value), transcript].filter(Boolean).join(text(input.value) ? " " : "");
        input?.focus?.();
        updateStatus(transcript ? "Dictation added. Review it, then press Ask to send." : "No English dictation was captured. You can type your question.");
      };
      recognition.onerror = (event) => {
        listening = false;
        setButtons();
        updateStatus(event?.error === "not-allowed" || event?.error === "service-not-allowed"
          ? "Microphone permission was denied. Typing remains available."
          : "Dictation is unavailable. Typing remains available.");
      };
      recognition.onend = () => { listening = false; setButtons(); };
    }
    const controller = {
      support() { return { dictation: Boolean(recognition), reading: Boolean(synthesis) }; },
      toggleDictation() {
        if (!recognition) { updateStatus("English dictation is not supported in this browser. Typing remains available."); return false; }
        if (listening) { recognition.stop?.(); listening = false; updateStatus("Dictation stopped. Review the question before sending."); }
        else { listening = true; recognition.start?.(); updateStatus("Listening for English dictation. It will not send automatically."); }
        setButtons(); return true;
      },
      setAnswer(value) {
        const nextAnswer = cleanAnswer(value);
        if (nextAnswer !== answer && reading) {
          synthesis?.cancel?.();
          reading = false;
        }
        answer = nextAnswer;
        setButtons();
      },
      readAnswer() {
        if (!synthesis || !answer || typeof utteranceFactory !== "function") { updateStatus("Answer reading is unavailable in this browser."); return false; }
        try {
          const utterance = utteranceFactory(answer); utterance.lang = "en-US";
          utterance.onend = () => { reading = false; setButtons(); updateStatus("Answer reading finished."); };
          utterance.onerror = () => { reading = false; setButtons(); updateStatus("Answer reading stopped. You can read the text above."); };
          reading = true; synthesis.speak(utterance); setButtons(); updateStatus("Reading the answer in English."); return true;
        } catch (_) { reading = false; setButtons(); updateStatus("Answer reading is unavailable in this browser."); return false; }
      },
      stopReading() { if (!synthesis) return false; synthesis.cancel?.(); reading = false; setButtons(); updateStatus("Answer reading stopped."); return true; },
    };
    setButtons();
    return controller;
  }

  function unwrapProjection(value) {
    if (!isRecord(value)) return null;
    for (const key of ["distributor_operations", "projection", "operation", "result"]) {
      if (isRecord(value[key]) && ("quantities" in value[key] || "available" in value[key] || "stage" in value[key])) return value[key];
    }
    return ("quantities" in value || "available" in value || "stage" in value) ? value : null;
  }

  function projectionSourceState(next) {
    if (!isRecord(next) || next.available === true) return "CURRENT";
    return text(next.stage).toUpperCase() === "DISABLED" || !text(next.case_id)
      ? "DISABLED"
      : "SOURCE_UNAVAILABLE";
  }

  function cleanAnswer(value) {
    return text(value)
      .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
      .replace(/<analysis>[\s\S]*?<\/analysis>/gi, "")
      .replace(/<reasoning>[\s\S]*?<\/reasoning>/gi, "")
      .trim();
  }

  function statusTone(value) {
    const status = text(value).toUpperCase();
    if (/HOLD|FAIL|ERROR|UNKNOWN|UNAVAILABLE|MISSING|CONFLICT|REJECT/.test(status)) return "coral";
    if (/PASS|COMPLETE|CONFIRMED|DELIVERED|READY|RELEASE|USABLE/.test(status)) return "lime";
    if (/DISABLED|PENDING|WAIT|REVIEW|PROCESS/.test(status)) return "amber";
    return "neutral";
  }

  function recommendedAction(code) {
    const value = text(code).toUpperCase();
    if (/SHORT|MISSING|QUANTITY|COUNT/.test(value)) return "Verify the inner count and open a supplier or carrier discrepancy task.";
    if (/QUALITY|INSPECTION|MEASURE|SPEC/.test(value)) return "Hold the lot and review the inspection evidence against its acceptance spec.";
    if (/LOT|BATCH|TRACE|IDENTITY|COUNTER/.test(value)) return "Quarantine the affected lot and verify its traceability with the source or manufacturer.";
    if (/DELIVERY|POD|SHIPMENT/.test(value)) return "Review the shipment evidence; delivery needs an explicit confirmation event.";
    return "Review the evidence and affected customer orders before changing the operation.";
  }

  function buildEventPayload({ type, values = {}, evidenceRef, now, eventId, synthetic = true }) {
    const eventType = canonicalType(type);
    if (!eventType) throw new Error("Choose a supported evidence template.");
    const commonEvidence = text(evidenceRef);
    if (!commonEvidence) throw new Error("Enter an evidence ID before processing the event.");
    const payload = {
      event_id: text(eventId) || `demo-event-${Date.now()}`,
      type: eventType,
      occurred_at: text(now) || new Date().toISOString(),
      evidence_ref: commonEvidence,
      synthetic: synthetic === true,
    };
    const fields = {};
    for (const definition of FIELD_DEFS[eventType]) {
      const raw = values[definition.key];
      if (NUMBER_FIELDS.has(definition.key)) {
        if (raw === undefined || raw === null || text(String(raw)) === "") throw new Error(`${definition.label} is required.`);
        const number = Number(raw);
        if (!Number.isFinite(number) || number < 0) throw new Error(`${definition.label} must be a non-negative number.`);
        fields[definition.key] = number;
      } else {
        const value = text(raw);
        if (!value) throw new Error(`${definition.label} is required.`);
        fields[definition.key] = value;
      }
    }
    Object.assign(payload, fields);
    return payload;
  }

  function deliveryCompletionLabel(next) {
    if (!isRecord(next) || next.available !== true || !isRecord(next.quantities)) return "";
    const sourceStatus = text(next.source_status).toUpperCase();
    // The public projection elides source_status after deriving `available`; when it is present,
    // it must still explicitly confirm the current source.
    if (sourceStatus && sourceStatus !== "CURRENT") return "";
    const quantities = next.quantities;
    const ordered = numberFrom(quantities.ordered);
    if (!finite(ordered) || ordered <= 0) return "";
    if (!["received", "dispatched", "delivery_confirmed"].every((key) => numberFrom(quantities[key]) === ordered)) return "";
    if (!["held", "missing", "usable", "allocated"].every((key) => numberFrom(quantities[key]) === 0)) return "";
    const openAlerts = Array.isArray(next.alerts)
      ? next.alerts.filter((alert) => isRecord(alert) && firstText(alert, ["status", "state"]).toUpperCase() === "OPEN").length
      : 0;
    return `Delivery confirmed · ${openAlerts} alert${openAlerts === 1 ? "" : "s"} to review`;
  }

  const exported = {
    buildEventPayload,
    cleanAnswer,
    conversationAnswer,
    providerLabel,
    retainConversationProjection,
    shouldPreserveTemplateFields,
    formatNumber,
    isRetainedEvidence,
    conversationInferenceCapability,
    retainedEvidenceLabel,
    erpEvidenceSourceLabel,
    sourceAwareErpText,
    freshActionsAllowed,
    normalizeProjection,
    normalizeHandoffs,
    groupHandoffs,
    normalizeFinancials,
    financialStatusMessage,
    financialOrderSummary,
    invoiceRecordSummary,
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
    normalizeTemplate,
    normalizeTemplates,
    recommendedAction,
    statusTone,
    deliverySummary,
    arrivalQuantitySummary,
    deliveryCompletionLabel,
    unwrapProjection,
    projectionSourceState,
    proposalActionDetail,
    approvalReadback,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  if (typeof window !== "undefined") window.Missing20DistributorOperations = exported;
  if (typeof document === "undefined") return;

  const $ = (id) => document.getElementById(id);
  const content = $("ops-content");
  const disabled = $("ops-disabled");
  const sourceState = $("ops-source-state");
  const templateSelect = $("ops-template-select");
  let projection = null;
  let selectedTemplate = null;
  let loading = false;
  let refreshQueued = false;
  let processingEvent = false;
  let asking = false;
  let pollTimer = null;
  let lastProjectionAt = "";
  let retainedConversation = null;
  let voiceController = null;
  let pendingAllocationAction = null;
  let allocationFeedback = null;
  let preparedProposal = null;
  let selectedPhoto = null;
  let photoPreviewUrl = "";

  function setText(id, value) {
    const node = $(id);
    if (node) node.textContent = value == null ? "" : String(value);
    return node;
  }
  function setConnection(label, tone = "cyan") {
    setText("ops-connection-label", label);
    const dot = $("ops-connection-dot");
    if (dot) dot.className = `status-dot status-dot-${tone}`;
  }
  function renderRefreshState({ retryPending = false } = {}) {
    const retainedLabel = retainedEvidenceLabel(projection?.evidence_mode, projection);
    if (retainedLabel) {
      setText("ops-refresh-state", retainedLabel);
      return;
    }
    const prefix = retryPending ? "Source retry pending · " : "Last successful source refresh · ";
    const value = lastProjectionAt ? formatDate(lastProjectionAt) : "none yet";
    setText("ops-refresh-state", `${prefix}${value}`);
  }
  function showSourceError(error, { configuredSourceFailure = false } = {}) {
    sourceState.hidden = false;
    setText("ops-source-title", "Current operation source unavailable");
    setText("ops-source-detail", error?.message || "The source did not return a usable projection. Quantities are unknown.");
    setConnection("Unavailable", "danger");
    renderRefreshState({ retryPending: Boolean(lastProjectionAt) });
    if (!projection || configuredSourceFailure) {
      content.hidden = true;
      disabled.hidden = false;
      disabled.querySelector("h2").textContent = configuredSourceFailure ? "Current operation source unavailable" : "Operation source unavailable";
      disabled.querySelector("p").textContent = "No quantities, allocation, benchmark, or delivery state are inferred until the source responds.";
    }
    updateEventButton();
    syncFreshEventControls(projection);
    updateAskButton();
  }
  function clearSourceError() {
    sourceState.hidden = true;
    const retained = Boolean(retainedEvidenceLabel(projection?.evidence_mode, projection));
    setConnection(retained ? "Retained evidence" : "Live source", retained ? "cyan" : "lime");
    renderRefreshState();
    updateEventButton();
    syncFreshEventControls(projection);
    updateAskButton();
  }
  function displayQuantity(value) { return finite(value) ? formatNumber(value) : "Unknown"; }
  function quantity(projectionValue, key) {
    return numberFrom(projectionValue?.quantities?.[key]);
  }
  function setQuantityCard(key, value, unit) {
    const card = document.querySelector(`[data-quantity-card="${key}"]`);
    const valueNode = $(`ops-quantity-${key}`);
    if (!valueNode) return;
    const known = finite(value);
    valueNode.textContent = displayQuantity(value);
    card?.classList.toggle("is-unknown", !known);
    const unitNode = $(`ops-quantity-${key}-unit`);
    if (unitNode && unit) unitNode.textContent = unit;
  }
  function cartonsSummary(value) {
    if (finite(value)) return `${formatNumber(value)} observed`;
    if (!isRecord(value)) return "Unknown";
    const observed = numberFromKeys(value, ["observed", "received", "actual", "count"]);
    const expected = numberFromKeys(value, ["expected", "ordered", "planned"]);
    if (finite(observed) && finite(expected)) return `${formatNumber(observed)} observed · ${formatNumber(expected)} expected`;
    if (finite(observed)) return `${formatNumber(observed)} observed`;
    if (finite(expected)) return `${formatNumber(expected)} expected`;
    return "Unknown";
  }
  function renderQuantities(next) {
    const q = next.quantities || {};
    const unit = text(q.uom) || "Unit not confirmed";
    const allocationPending = pendingAllocationEligibility(next).status === "PENDING";
    const cartons = cartonsSummary(q.cartons);
    const cartonsNode = $("ops-quantity-cartons");
    const cartonsCard = document.querySelector('[data-quantity-card="cartons"]');
    if (cartonsNode) cartonsNode.textContent = cartons;
    cartonsCard?.classList.toggle("is-unknown", cartons === "Unknown");
    for (const key of ["ordered", "received", "usable", "held", "missing", "allocated", "dispatched", "delivery_confirmed"]) {
      setQuantityCard(key, quantity(next, key), key === "delivery_confirmed" ? "explicit event" : key === "allocated" && allocationPending ? "proposed plan" : unit);
    }
    const allocatedLabel = $("ops-quantity-allocated-label");
    if (allocatedLabel) allocatedLabel.textContent = allocationPending ? "Proposed allocation" : "Allocated";
    setText("ops-uom-note", text(q.uom)
      ? `Parts are shown in stock UOM ${q.uom}; cartons remain a separate outer-package observation.`
      : "Stock UOM is not confirmed; cartons and part quantities remain separate observations.");
  }
  function renderBenchmark(next) {
    const benchmark = fulfillmentBenchmark(next);
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    const grid = $("ops-benchmark-grid");
    const badge = $("ops-benchmark-state");
    if (!grid || !badge) return;
    if (benchmark.status !== "CURRENT") {
      badge.className = "state-badge state-neutral"; badge.textContent = "Comparison unavailable";
      setText("ops-benchmark-note", `${sourceAwareErpText(benchmark.reason, next?.evidence_mode)} Historical, industry, and savings baselines are unavailable.`);
      grid.replaceChildren(emptyList("No comparable current-case benchmark is available.")); return;
    }
    badge.className = "state-badge state-cyan"; badge.textContent = "Current case only";
    const card = (label, actual, descriptor) => {
      const node = document.createElement("article"); node.className = "ops-benchmark-card";
      const title = document.createElement("span"); title.textContent = label;
      const value = document.createElement("strong"); value.textContent = `${formatNumber(actual)} / ${formatNumber(benchmark.target)}`;
      const note = document.createElement("small"); note.textContent = `${descriptor} · ${benchmark.unit}`;
      const progress = document.createElement("progress"); progress.max = benchmark.target; progress.value = Math.min(actual, benchmark.target); progress.setAttribute("aria-label", `${label}: ${formatNumber(actual)} of ${formatNumber(benchmark.target)} ${benchmark.unit}`);
      node.append(title, value, note, progress); return node;
    };
    grid.replaceChildren(
      card("Customer commitment", benchmark.target, `${benchmark.order_count} current order${benchmark.order_count === 1 ? "" : "s"}`),
      card("Native dispatch", benchmark.dispatched, "Recorded dispatch"),
      card("Recorded delivery confirmation", benchmark.confirmed, benchmark.synthetic ? "Synthetic recorded event; not independently verified receipt" : "Recorded event"),
    );
    setText("ops-benchmark-note", `Source: ${sourceLabel} · Sample: one configured operation · Historical, industry, and savings baselines are unavailable.`);
  }

  function allocationPicked(next) {
    return next.allocations.some((allocation) => finite(numberFromKeys(allocation, ["picked", "picked_quantity", "picked_qty"])) && numberFromKeys(allocation, ["picked", "picked_quantity", "picked_qty"]) > 0);
  }
  function pickedEvidenceRecorded(next, order = "") {
    return next.events.some((event) => {
      if (canonicalType(event.type || event.event_type || event.kind) !== "picked") return false;
      const eventOrder = firstText(event, ["customer_order", "sales_order"]);
      if (order && eventOrder !== order) return false;
      return /APPLIED|COMPLETE|SUCCESS|RECORDED/i.test(firstText(event, ["status", "state"]));
    });
  }
  function stageMatches(stage, key) {
    const value = text(stage).toUpperCase();
    const patterns = {
      arrival: /RECEIV|ARRIV|INBOUND/,
      inspection: /INSPECT|QUALITY|HOLD|REVIEW|RELEASE/,
      allocation: /ALLOC|RESERV|ORDER/,
      picked: /PICK/,
      dispatch: /DISPATCH|SHIP|DELIVER/,
      delivery: /DELIVERY_CONFIRMED|DELIVERED|POD|COMPLETE/,
    };
    return patterns[key]?.test(value) || false;
  }
  function stageProof(next, stage) {
    const value = quantity(next, stage.metric);
    if (stage.key === "arrival") return finite(value) && value > 0;
    if (stage.key === "picked") {
      return allocationPicked(next) || pickedEvidenceRecorded(next);
    }
    if (stage.key === "inspection") {
      return finite(value) && value > 0 || next.lots.some((lot) => /PASS|FAIL|HOLD|REJECT|RELEASE|INSPECT/i.test(firstText(lot, ["inspection_result", "quality_result", "result", "inspection_status"])));
    }
    if (stage.key === "delivery") return finite(value) && value > 0;
    return finite(value) && value > 0 || stageMatches(next.stage, stage.key);
  }
  function stageHeld(next, stage) {
    return stage.key === "inspection" && quantity(next, "held") !== null && quantity(next, "held") > 0;
  }
  function renderStages(next) {
    const list = $("ops-stage-list");
    const alertStages = activeAlertStages(next);
    list.replaceChildren(...STAGES.map((stage) => {
      const item = document.createElement("li");
      item.className = "ops-stage";
      const facts = flowStageFacts(next, stage);
      const isComplete = facts.complete;
      const alert = alertStages[stage.key];
      if (isComplete) item.classList.add("is-complete");
      if (stageHeld(next, stage)) item.classList.add("is-held");
      if (alert) item.classList.add("is-alert");
      if (!isComplete && stageMatches(next.stage, stage.key)) item.classList.add("is-current");
      const marker = document.createElement("span");
      marker.className = "ops-stage-marker";
      marker.innerHTML = `<i class="ph ${isComplete ? "ph-check" : stage.icon}" aria-hidden="true"></i>`;
      const title = document.createElement("strong"); title.textContent = stage.label;
      const detail = document.createElement("small");
      detail.textContent = facts.current;
      const cumulative = document.createElement("small"); cumulative.className = "ops-stage-cumulative"; cumulative.textContent = facts.cumulative;
      item.append(marker, title, detail, cumulative);
      if (alert) {
        const evidence = document.createElement("a");
        evidence.className = "ops-stage-alert-link";
        evidence.href = `#ops-alert-${alert.index}`;
        evidence.textContent = `${alert.code} · View evidence`;
        item.append(evidence);
      }
      return item;
    }));
  }

  function requestedOpsView() {
    const requested = text(new URLSearchParams(window.location.search).get("view")).toLowerCase();
    if (["dashboard", "agent", "operations"].includes(requested)) return requested;
    const hash = text(window.location.hash).toLowerCase();
    if (hash === "#ops-chat-panel" || hash === "#ops-evidence-panel") return "agent";
    if (["#ops-flow-panel", "#ops-alerts-panel", "#ops-details", "#ops-documents-panel", "#ops-handoffs-panel"].includes(hash)) return "operations";
    return "dashboard";
  }

  function setOpsView(view, { scrollTarget = "" } = {}) {
    const normalized = ["dashboard", "agent", "operations"].includes(view) ? view : "dashboard";
    document.body.dataset.opsView = normalized;
    document.querySelectorAll("[data-ops-view-link]").forEach((link) => {
      const selected = link.dataset.opsViewLink === normalized;
      link.classList.toggle("is-selected", selected);
      if (selected) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    if (scrollTarget) {
      window.requestAnimationFrame(() => $(scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }
  }

  function viewForOpsTarget(target) {
    return target === "ops-chat-panel" || target === "ops-evidence-panel" ? "agent" : "operations";
  }

  function focusOpsTarget(target) {
    const node = $(target);
    if (!node) return;
    setOpsView(viewForOpsTarget(target), { scrollTarget: target });
  }

  function networkNode({ key, icon, label, detail, target, alert = false, className = "" }) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `ops-network-node ${className}`.trim();
    button.dataset.networkKey = key;
    if (alert) button.classList.add("is-alert");
    const iconNode = document.createElement("i");
    iconNode.className = `ph ${icon}`;
    iconNode.setAttribute("aria-hidden", "true");
    const copy = document.createElement("span");
    const title = document.createElement("strong"); title.textContent = label;
    const meta = document.createElement("span"); meta.textContent = detail;
    copy.append(title, meta);
    button.append(iconNode, copy);
    if (target) button.addEventListener("click", () => focusOpsTarget(target));
    return button;
  }

  function renderOverview(next) {
    const graph = $("ops-overview-graph");
    if (!graph) return;
    const activeAlerts = next.alerts.filter((alert) => !isResolvedAlert(alert));
    const incidentAlerts = next.alerts.filter(isRecord);
    const handoffGroups = groupHandoffs(next.handoffs);
    const groupFor = (needle) => handoffGroups.find((group) => group.provider.toLowerCase().includes(needle));
    const statusFor = (needle) => {
      const group = groupFor(needle);
      return group?.latest?.status ? pretty(group.latest.status) : "No readback";
    };
    const sources = [
      { key: "erp", icon: "ph-buildings", label: "ERPNext", detail: `${next.documents.length} record${next.documents.length === 1 ? "" : "s"}`, target: "ops-documents-panel", alert: Boolean(incidentAlerts.length && next.documents.length) },
      { key: "airtable", icon: "ph-table", label: "Airtable", detail: statusFor("airtable"), target: "ops-handoffs-panel" },
      { key: "jira", icon: "ph-kanban", label: "Jira", detail: statusFor("jira"), target: "ops-handoffs-panel", alert: Boolean(incidentAlerts.length && groupFor("jira")) },
      { key: "celigo", icon: "ph-arrows-left-right", label: "Celigo", detail: statusFor("celigo"), target: "ops-handoffs-panel" },
      { key: "slack", icon: "ph-chat-circle-text", label: "Slack", detail: statusFor("slack"), target: "ops-handoffs-panel" },
    ];
    const network = document.createElement("div"); network.className = "ops-network";
    const sourceColumn = document.createElement("div"); sourceColumn.className = "ops-network-column";
    const sourceKicker = document.createElement("span"); sourceKicker.className = "ops-network-kicker"; sourceKicker.textContent = "Source systems";
    const sourceStack = document.createElement("div"); sourceStack.className = "ops-network-source-stack";
    sources.forEach((source) => sourceStack.append(networkNode({ ...source, className: "ops-network-source" })));
    sourceColumn.append(sourceKicker, sourceStack);

    const agentColumn = document.createElement("div"); agentColumn.className = "ops-network-column ops-network-agent-wrap";
    const agentKicker = document.createElement("span"); agentKicker.className = "ops-network-kicker"; agentKicker.textContent = "Reasoning layer";
    const agentProvider = firstProvider(next, ["conversation_provider", "provider", "model"])
      || firstProvider(next.conversation, ["provider_label", "provider", "model"])
      || "Native bridge —";
    const agent = networkNode({ key: "agent", icon: "ph-sparkle", label: "Agent board", detail: agentProvider, target: "ops-chat-panel", className: "ops-network-agent" });
    agentColumn.append(agentKicker, agent);
    if (incidentAlerts.length) {
      const incident = document.createElement("div"); incident.className = "ops-network-incident";
      const incidentIcon = document.createElement("i"); incidentIcon.className = "ph ph-warning"; incidentIcon.setAttribute("aria-hidden", "true");
      const incidentAlert = activeAlerts[0] || incidentAlerts.find((alert) => /LOT|BATCH|SHORT|MISMATCH|QUALITY|INSPECTION/i.test(firstText(alert, ["code", "kind", "message", "detail"]))) || incidentAlerts[0];
      const incidentCode = firstText(incidentAlert, ["code", "kind"]) || "Incident evidence";
      incident.append(incidentIcon, document.createTextNode(`${incidentCode} · ${activeAlerts.length ? "open · evidence highlighted" : "resolved · evidence aligned"}`));
      agentColumn.append(incident);
    }

    const managerColumn = document.createElement("div"); managerColumn.className = "ops-network-column ops-network-manager-wrap";
    const managerKicker = document.createElement("span"); managerKicker.className = "ops-network-kicker"; managerKicker.textContent = "Control";
    const proposalStatus = firstText(next.prepared_proposal, ["status"]);
    const managerDetail = proposalStatus ? proposalActionDetail(next.prepared_proposal, next.evidence_mode) : isRetainedEvidence(next.evidence_mode) ? "Recorded completion · manager confirmation" : "Bounded action · manager approval";
    const manager = networkNode({ key: "manager", icon: "ph-shield-check", label: "Manager gate", detail: managerDetail, target: "ops-evidence-panel", className: "ops-network-manager" });
    managerColumn.append(managerKicker, manager);
    network.append(sourceColumn, agentColumn, managerColumn);
    graph.replaceChildren(network);
    setText("ops-overview-case", `${next.case_id || "Case unavailable"} · ${next.purchase_order || "PO unavailable"}`);
    setText("ops-alert-focus-link", next._provided.alerts && activeAlerts.length === 0 ? "Review resolved incident" : "Focus active alert");
    setText("ops-overview-copy", activeAlerts.length ? "Open incident evidence is highlighted." : incidentAlerts.length ? "Resolved incident evidence is retained." : "Source records flow into read-only reasoning and manager control.");
  }

  function renderSignalSources(next) {
    const list = $("ops-signal-source-list");
    if (!list) return;
    const groups = groupHandoffs(next.handoffs);
    const groupFor = (needle) => groups.find((group) => group.provider.toLowerCase().includes(needle));
    const documentRecord = next.documents.find((record) => isRecord(record)) || null;
    const entries = [
      {
        label: "ERPNext",
        detail: documentRecord ? firstText(documentRecord, ["name", "record_id", "id"]) || "PO20 document" : "No linked document",
        status: documentRecord ? "VERIFIED" : "NO READBACK",
      },
      ...[["Airtable", "airtable"], ["Jira", "jira"], ["Celigo", "celigo"], ["Slack", "slack"]].map(([label, needle]) => {
        const group = groupFor(needle);
        return {
          label,
          detail: group?.latest?.record_id || group?.latest?.status ? group.latest.record_id || "Readback recorded" : "No readback",
          status: group?.latest?.status ? pretty(group.latest.status) : "NO READBACK",
        };
      }),
    ];
    const linked = entries.filter((entry) => entry.status !== "NO READBACK").length;
    setText("ops-signal-source-count", `${linked} linked · ${entries.length} systems`);
    list.replaceChildren(...entries.map((entry) => {
      const row = document.createElement("div"); row.className = "ops-signal-source";
      const identity = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = entry.label;
      const detail = document.createElement("small"); detail.textContent = entry.detail;
      identity.append(title, detail);
      const status = document.createElement("span"); status.className = `ops-signal-source-status${entry.status === "NO READBACK" ? " is-muted" : ""}`; status.textContent = entry.status;
      row.append(identity, status);
      return row;
    }));
  }

  function renderAgentTools(next) {
    const list = $("ops-agent-tools");
    if (!list) return;
    const groups = groupHandoffs(next.handoffs);
    const recordsAvailable = next.documents.length > 0;
    const collaborationAvailable = groups.length > 0;
    const tools = [
      ["read_control_context", next.available ? "READ" : "UNAVAILABLE"],
      ["read_erp_evidence", recordsAvailable ? "READ" : "MISSING"],
      ["read_collaboration_evidence", collaborationAvailable ? "READ" : "NOT NEEDED"],
      ["manager_gate", isRetainedEvidence(next.evidence_mode) ? "CONFIRM" : "REVIEW"],
    ];
    list.replaceChildren(...tools.map(([label, status]) => {
      const row = document.createElement("div"); row.className = "ops-agent-tool";
      const name = document.createElement("span"); name.textContent = label;
      const state = document.createElement("small"); state.textContent = status;
      row.append(name, state);
      return row;
    }));
    const activity = $("ops-agent-activity-copy");
    if (!activity) return;
    const latestEvent = [...next.events].reverse().find((event) => isRecord(event));
    const latestCopy = latestEvent ? eventSummary(latestEvent, next) : "No source events recorded";
    activity.textContent = `${next.events.length} source event${next.events.length === 1 ? "" : "s"} · ${latestCopy}`;
  }

  function metricBlock(label, value, className = "") {
    const wrapper = document.createElement("div");
    if (className) wrapper.className = `ops-list-value ${className}`;
    else wrapper.className = "ops-list-value";
    const strong = document.createElement("strong"); strong.textContent = value;
    const small = document.createElement("small"); small.textContent = label;
    wrapper.append(strong, small);
    return wrapper;
  }
  function emptyList(message) {
    const node = document.createElement("p"); node.className = "ops-empty"; node.textContent = message; return node;
  }
  function renderLots(next) {
    const list = $("ops-lots-list");
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    setText("ops-lots-count", next._provided.lots ? `${next.lots.length} lot${next.lots.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.lots) { list.replaceChildren(emptyList(`Lot and inspection data is unavailable from the ${sourceLabel}.`)); return; }
    if (!next.lots.length) { list.replaceChildren(emptyList("No lot records in the current operation.")); return; }
    list.replaceChildren(...next.lots.map((lot) => {
      const row = document.createElement("div"); row.className = "ops-list-row";
      const id = firstText(lot, ["lot", "lot_id", "batch", "batch_no", "name"]) || "Lot not identified";
      const status = firstText(lot, ["status", "inspection_result", "quality_result", "result"]) || "Status unavailable";
      const received = numberFromKeys(lot, ["received", "quantity", "observed_quantity", "count"]);
      const usable = numberFromKeys(lot, ["usable", "accepted", "accepted_quantity"]);
      const held = numberFromKeys(lot, ["held", "rejected", "rejected_quantity", "quarantine"]);
      const inspection = isRecord(lot.inspection) ? lot.inspection : lot.quality;
      const test = isRecord(inspection)
        ? [firstText(inspection, ["result", "status"]), firstText(inspection, ["metric"]), text(inspection.measured) ? `measured ${inspection.measured}` : ""].filter(Boolean).join(" · ")
        : status;
      const first = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = id;
      const note = document.createElement("small"); note.textContent = status;
      first.append(title, note);
      row.append(first, metricBlock("Received", displayQuantity(received)), metricBlock("Usable", displayQuantity(usable), usable === null ? "" : "is-positive"), metricBlock("Held / inspection", held === null ? test : `${displayQuantity(held)} · ${test}`, held > 0 ? "is-alert" : ""));
      return row;
    }));
  }

  function allocationLabel(allocation) {
    const source = firstText(allocation, ["source", "kind", "allocation_type", "reservation_status", "reservation"]);
    if (allocation.planned === true || allocation.is_plan === true || /PLAN/i.test(source)) return "Planned allocation";
    if (allocation.native_reservation === true || /RESERV/i.test(source)) return "Native reservation";
    return "Allocation record";
  }
  function deliverySummary(delivery, requested) {
    if (!finite(delivery)) return "Delivery confirmed unknown";
    return finite(requested)
      ? `Delivery confirmed ${displayQuantity(delivery)} / ${displayQuantity(requested)}`
      : `Delivery confirmed ${displayQuantity(delivery)}`;
  }
  function contractFlag(value, affirmative, negative) {
    return value === true ? affirmative : value === false ? negative : "Unknown";
  }
  function appendContractDetail(parent, label, value) {
    if (!value) return;
    const row = document.createElement("div");
    const labelNode = document.createElement("strong"); labelNode.textContent = label;
    row.append(labelNode, document.createTextNode(value));
    parent.append(row);
  }
  function renderContractAllocation(next) {
    const panel = $("ops-contract-panel");
    if (!panel) return;
    const plan = normalizeContractPlan(next.feasible_allocation_plan);
    const rows = contractPlanRows(plan);
    if (!plan || !rows.length) {
      panel.hidden = true;
      $("ops-contract-rows")?.replaceChildren();
      $("ops-contract-decision")?.replaceChildren();
      return;
    }
    panel.hidden = false;
    const state = contractPanelState(plan, next.allocation_decision);
    const decision = isRecord(next.allocation_decision) ? next.allocation_decision : {};
    const rawStatus = text(decision.status).toUpperCase();
    const pending = pendingAllocationEligibility(next);
    const retry = allocationRetryForDecision(next);
    const badge = $("ops-contract-state");
    if (badge) {
      badge.className = `state-badge state-${state === "SELECTED" ? "cyan" : state === "COMPLETE" ? "lime" : "amber"}`;
      badge.textContent = state === "SELECTED" ? "Plan selected" : state === "COMPLETE" ? "Current plan complete" : state === "PENDING" ? "Decision pending" : "Decision unavailable";
    }
    const candidateRule = "Minimum dispatch quantities apply only to positive new candidates; an order with no dispatch remaining does not block other candidates.";
    setText("ops-contract-note", state === "COMPLETE"
      ? "No additional allocation is currently needed. Any retained selection below is historical evidence; pick and dispatch facts remain in the fulfillment rows."
      : state === "SELECTED"
      ? `Date first; customer priority breaks ties. The server calculated this feasible plan from the contract terms. Selection is a decision record; it does not itself create a pick or dispatch. ${candidateRule}`
      : `Date first; customer priority breaks ties. The server calculated this feasible plan from the contract terms. Actual pick and dispatch evidence remains in the fulfillment rows below. ${candidateRule}`);
    const meta = $("ops-contract-meta");
    if (meta) {
      const unit = text(next.quantities?.uom) || "unit";
      meta.textContent = `Contract policy v1 · Planned additional quantity ${displayQuantity(numberFrom(plan.new_quantity))} ${unit}`;
    }
    const list = $("ops-contract-rows");
    if (list) {
      list.replaceChildren(...rows.map((row) => {
        const item = document.createElement("div"); item.className = "ops-contract-row";
        const identity = document.createElement("div");
        const order = document.createElement("strong"); order.textContent = row.customer_order || "Order unavailable";
        const promise = document.createElement("small"); promise.textContent = `Promised ${row.promised_delivery_at || "Date unavailable"} · Customer priority ${displayQuantity(row.customer_priority)}`;
        identity.append(order, promise);
        const terms = [
          `Minimum ${displayQuantity(row.minimum_dispatch_quantity)}`,
          `Partial ${contractFlag(row.partial_dispatch, "Yes", "No")}`,
          `Final remainder ${contractFlag(row.allow_final_remainder, "allowed", "not allowed")}`,
          row.dispatch_eligibility ? `Dispatch ${dispatchEligibilityText(row.dispatch_eligibility)}` : "",
        ].filter(Boolean).join(" · ");
        const planned = `Total ${displayQuantity(row.quantity)} · Prepared commitment ${displayQuantity(row.prepared_commitment)} · New to prepare ${displayQuantity(row.new_quantity)}`;
        item.append(identity, metricBlock("Contract terms", terms), metricBlock("Plan quantities", planned), metricBlock("Remaining after dispatch", displayQuantity(row.remaining_after_dispatch)));
        return item;
      }));
    }
    const decisionNode = $("ops-contract-decision");
    if (!decisionNode) return;
    decisionNode.className = `ops-contract-decision${state === "SELECTED" || state === "COMPLETE" ? " is-selected" : ""}`;
    decisionNode.replaceChildren();
    const heading = document.createElement("strong");
    heading.textContent = state === "SELECTED" ? "Agent decision: plan selected" : state === "COMPLETE" ? "Retained historical selection" : state === "PENDING" ? "Agent decision: pending" : "Agent decision: unavailable";
    const copy = document.createElement("p");
    copy.textContent = state === "COMPLETE"
      ? rawStatus === "SELECTED" ? "This is an earlier selection; the current feasible plan has no additional quantity to prepare." : "The current feasible plan has no additional quantity to prepare."
      : state === "SELECTED"
      ? "This plan selection does not itself create an ERP pick or dispatch."
      : state === "PENDING"
      ? "The source has a feasible proposal, but no allocation decision was selected or prepared. Review the pending decision before any pick or dispatch."
      : rawStatus === "SELECTED"
        ? "The recorded selection does not match this current plan, so it is not treated as selected."
        : "No selected decision is recorded for this plan.";
    const details = document.createElement("div"); details.className = "ops-contract-decision-details";
    if (state === "PENDING") {
      appendContractDetail(details, "Eligibility", pending.eligible ? "Review required · source event is available" : pending.reason);
    }
    appendContractDetail(details, "Rationale", firstText(decision, ["rationale"]));
    const refs = Array.isArray(decision.contract_refs) ? decision.contract_refs.map((ref) => text(ref)).filter(Boolean).join(", ") : "";
    appendContractDetail(details, "Contract refs", refs);
    appendContractDetail(details, "Decision event", firstText(decision, ["event_id"]));
    appendContractDetail(details, "Agent source", providerLabel(decision.provider));
    if (retry) appendContractDetail(details, "Review status", pretty(retry.status));
    decisionNode.append(heading, copy);
    if (details.childNodes.length) decisionNode.append(details);

    const action = document.createElement("div");
    action.id = "ops-pending-allocation-action";
    action.className = "ops-pending-allocation-action";
    const actionButton = document.createElement("button");
    actionButton.id = "ops-reselect-pending-allocation";
    actionButton.className = "button button-primary";
    actionButton.type = "button";
    actionButton.innerHTML = '<i class="ph ph-arrow-counter-clockwise" aria-hidden="true"></i><span data-allocation-action-label>Review pending allocation</span>';
    actionButton.addEventListener("click", () => { void reviewPendingAllocation(); });
    action.append(actionButton);
    decisionNode.append(action);
    const feedback = document.createElement("p");
    feedback.id = "ops-allocation-feedback";
    feedback.className = "ops-feedback";
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    decisionNode.append(feedback);
    updatePendingAllocationAction(next);
  }
  function renderAllocations(next) {
    const list = $("ops-orders-list");
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    renderContractAllocation(next);
    const allocationPending = pendingAllocationEligibility(next).status === "PENDING";
    setText("ops-orders-count", next._provided.allocations ? `${next.allocations.length} order${next.allocations.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.allocations) { list.replaceChildren(emptyList(`Customer allocation data is unavailable from the ${sourceLabel}.`)); return; }
    if (!next.allocations.length) { list.replaceChildren(emptyList("No customer allocation evidence in the current operation.")); return; }
    list.replaceChildren(...next.allocations.map((allocation) => {
      const row = document.createElement("div"); row.className = "ops-list-row";
      const order = firstText(allocation, ["customer_order", "sales_order", "order_name", "order", "name"]) || "Order not identified";
      const customer = firstText(allocation, ["customer", "customer_name", "customer_id"]);
      const requested = numberFromKeys(allocation, ["ordered", "requested", "requested_quantity", "demand", "quantity"]);
      const allocated = numberFromKeys(allocation, ["allocated", "reserved", "reservation_quantity"]);
      const explicitBackorder = numberFromKeys(allocation, ["backorder", "backordered", "remaining", "unfulfilled"]);
      const backorder = finite(explicitBackorder) ? explicitBackorder : finite(requested) && finite(allocated) ? Math.max(0, requested - allocated) : null;
      const picked = numberFromKeys(allocation, ["picked", "picked_quantity", "picked_qty"]);
      const dispatched = numberFromKeys(allocation, ["dispatched", "dispatched_quantity"]);
      const delivery = numberFromKeys(allocation, ["delivery_confirmed", "delivery_quantity"]);
      const status = firstText(allocation, ["status", "phase"]) || "Status unavailable";
      const first = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = order;
      const note = document.createElement("small"); note.textContent = `${customer ? `${customer} · ` : ""}${allocationPending ? "Proposed allocation" : allocationLabel(allocation)} · ${status}`;
      first.append(title, note);
      const outbound = [
        finite(picked) ? `Picked ${displayQuantity(picked)}` : pickedEvidenceRecorded(next, order) ? "Picked recorded" : "Picked unknown",
        finite(dispatched) ? `Dispatched ${displayQuantity(dispatched)}` : "Dispatched unknown",
        deliverySummary(delivery, requested),
      ].join(" · ");
      row.append(first, metricBlock(allocationPending ? "Proposed" : "Allocated", displayQuantity(allocated), allocated > 0 ? "is-positive" : ""), metricBlock("Backorder", displayQuantity(backorder), backorder > 0 ? "is-alert" : ""), metricBlock("Outbound evidence", outbound));
      return row;
    }));
  }

  function renderAlerts(next) {
    const list = $("ops-alerts-list");
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    const alerts = next.alerts.filter((alert) => !isResolvedAlert(alert));
    const resolved = next.alerts.filter((alert) => isResolvedAlert(alert));
    const history = $("ops-resolved-alerts");
    const historyList = $("ops-resolved-alerts-list");
    setText("ops-alerts-count", next._provided.alerts ? `${alerts.length} active alert${alerts.length === 1 ? "" : "s"}` : "Unknown");
    if (history) history.hidden = !resolved.length;
    if (historyList) {
      setText("ops-resolved-alerts-summary", `Resolved evidence history · ${resolved.length}`);
      historyList.replaceChildren(...resolved.map((alert) => {
        const row = document.createElement("div"); row.className = "ops-resolved-alert-row";
        const code = document.createElement("strong"); code.textContent = firstText(alert, ["code", "kind"]) || "Resolved alert";
        const detail = document.createElement("span"); detail.textContent = firstText(alert, ["message", "detail"]) || "Resolved source alert.";
        row.append(code, detail); return row;
      }));
    }
    if (!next._provided.alerts) { list.replaceChildren(emptyList(`Manager alert data is unavailable from the ${sourceLabel}.`)); return; }
    if (!alerts.length) { list.replaceChildren(emptyList("No active manager alerts in the current projection.")); return; }
    list.replaceChildren(...alerts.map((alert) => {
      const card = document.createElement("article"); card.className = "ops-alert-card";
      card.id = `ops-alert-${next.alerts.indexOf(alert)}`;
      const head = document.createElement("div"); head.className = "ops-alert-head";
      const code = document.createElement("strong"); code.className = "ops-alert-code"; code.textContent = firstText(alert, ["code", "kind"]) || "Alert";
      const badge = document.createElement("span"); badge.className = `state-badge state-${statusTone(firstText(alert, ["code", "kind"]))}`; badge.textContent = alert.synthetic === true ? "Synthetic evidence" : alert.derived === true ? "Derived date check" : "Source alert";
      head.append(code, badge);
      const message = document.createElement("p"); message.textContent = firstText(alert, ["message", "detail"]) || "Alert detail unavailable.";
      const meta = document.createElement("div"); meta.className = "ops-alert-meta";
      const action = firstText(alert, ["action", "recommended_action"]) || recommendedAction(firstText(alert, ["code", "kind"]));
      const orders = Array.isArray(alert.orders) ? alert.orders.map((order) => text(order)).filter(Boolean).join(", ") : firstText(alert, ["orders", "affected_orders"]);
      const evidence = firstText(alert, ["evidence_ref", "evidence_id"]);
      const appendMeta = (label, value, link = false) => {
        if (!value) return;
        const row = document.createElement("div");
        const labelNode = document.createElement("strong"); labelNode.textContent = label;
        row.append(labelNode, document.createTextNode(" "));
        if (link && safeHref(value)) { const anchor = document.createElement("a"); anchor.href = safeHref(value); anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.textContent = value; row.append(anchor); }
        else { row.append(document.createTextNode(value)); }
        meta.append(row);
      };
      appendMeta("Action", action);
      appendMeta("Affected orders", orders || "No linked orders");
      appendMeta("Lot / quantity", [firstText(alert, ["lot", "batch"]), finite(numberFrom(alert.quantity)) ? displayQuantity(numberFrom(alert.quantity)) : ""].filter(Boolean).join(" · "));
      appendMeta("Evidence", evidence || "Evidence reference unavailable", Boolean(evidence && /^https?:\/\//i.test(evidence)));
      card.append(head, message, meta);
      return card;
    }));
  }

  function safeHref(value) {
    const href = text(value);
    if (/^https?:\/\//i.test(href) || /^\/(?!\/)/.test(href) || /^#/.test(href)) return href;
    return "";
  }
  function appendHandoffLink(parent, label, handoff) {
    const row = document.createElement("div");
    const href = handoff.safe_url;
    if (href) {
      const anchor = document.createElement("a");
      anchor.href = href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
      anchor.textContent = `${label}${handoff.record_id ? ` · ${handoff.record_id}` : ""}`;
      row.append(anchor);
    } else {
      row.textContent = `${label}: link unavailable`;
    }
    parent.append(row);
  }
  function renderHandoffs(next) {
    const list = $("ops-handoffs-list");
    if (!list) return;
    const groups = groupHandoffs(next.handoffs);
    setText("ops-handoffs-count", groups.length ? `${groups.length} system${groups.length === 1 ? "" : "s"}` : "No verified links");
    if (!groups.length) {
      list.replaceChildren(emptyList("No linked external case record verified yet."));
      return;
    }
    list.replaceChildren(...groups.map((group) => {
      const latest = group.latest;
      const card = document.createElement("article"); card.className = "ops-handoff-card";
      const head = document.createElement("div"); head.className = "ops-handoff-head";
      const provider = document.createElement("strong"); provider.textContent = group.provider;
      const badge = document.createElement("span"); badge.className = `state-badge state-${statusTone(latest.status)}`; badge.textContent = pretty(latest.status);
      head.append(provider, badge);
      const latestVerified = latest.status.toUpperCase() === "VERIFIED";
      const timestamp = document.createElement("small"); timestamp.className = "ops-handoff-meta";
      timestamp.textContent = latest.updated_at
        ? `${latestVerified ? "Retained verification timestamp" : "Last recorded attempt"} ${formatDate(latest.updated_at)}`
        : `${latestVerified ? "Retained verification timestamp" : "Last recorded attempt"} unavailable`;
      const record = document.createElement("small"); record.className = "ops-handoff-record";
      record.textContent = latest.record_id ? `Latest record ${latest.record_id}` : "Latest record ID unavailable";
      const links = document.createElement("div"); links.className = "ops-handoff-links";
      appendHandoffLink(links, latestVerified ? "Verified evidence" : "Latest attempt evidence", latest);
      if (group.last_verified && group.last_verified !== latest) {
        const history = document.createElement("p"); history.className = "ops-handoff-history";
        history.textContent = `Last verified link is historical; latest status is ${pretty(latest.status)}.`;
        appendHandoffLink(links, "Last verified evidence", group.last_verified);
        card.append(head, timestamp, record, links, history);
      } else {
        card.append(head, timestamp, record, links);
      }
      if (latest.last_failure) {
        const failure = document.createElement("p"); failure.className = "ops-handoff-failure";
        failure.textContent = `Last failure: ${latest.last_failure}`;
        card.append(failure);
      }
      return card;
    }));
  }
  function renderDocuments(next) {
    const list = $("ops-documents-list");
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    setText("ops-documents-count", next._provided.documents ? `${next.documents.length} record${next.documents.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.documents) { list.replaceChildren(emptyList(`Native ERP document data is unavailable from the ${sourceLabel}.`)); return; }
    if (!next.documents.length) { list.replaceChildren(emptyList(`No linked ERP documents in the ${sourceLabel}.`)); return; }
    list.replaceChildren(...next.documents.map((documentRecord) => {
      const row = document.createElement("div"); row.className = "ops-document";
      const body = document.createElement("div");
      const name = firstText(documentRecord, ["name", "record_id", "id"]) || "ERP document";
      const kind = firstText(documentRecord, ["kind", "doctype", "type"]) || "Native record";
      const title = document.createElement("strong"); title.textContent = name;
      const note = document.createElement("small"); note.textContent = kind;
      body.append(title, note);
      const href = safeHref(documentRecord.url || documentRecord.href);
      const documentStatus = firstText(documentRecord, ["status"]) || "Status unavailable";
      if (href) { const anchor = document.createElement("a"); anchor.className = "ops-document-status"; anchor.href = href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; anchor.textContent = `${documentStatus} · Open record`; row.append(body, anchor); }
      else { const status = document.createElement("span"); status.className = "ops-document-status"; status.textContent = documentStatus; row.append(body, status); }
      return row;
    }));
  }

  function appendFinancialDocument(parent, documentRecord) {
    const name = firstText(documentRecord, ["name", "record_id", "id"]) || "ERP document";
    const href = safeHref(documentRecord.url || documentRecord.href);
    if (href) {
      const anchor = document.createElement("a");
      anchor.href = href; anchor.target = "_blank"; anchor.rel = "noopener noreferrer";
      anchor.textContent = name; parent.append(anchor);
    } else {
      const label = document.createElement("span");
      label.textContent = `${name} · link unavailable`; parent.append(label);
    }
  }

  function financialOrderCard(order, label, unit) {
    const card = document.createElement("article"); card.className = "ops-financial-card";
    const documentRecord = isRecord(order.document) ? order.document : {};
    const heading = document.createElement("div"); heading.className = "ops-financial-heading";
    const identity = document.createElement("div");
    const kind = document.createElement("small"); kind.textContent = firstText(documentRecord, ["kind", "doctype", "type"]) || label;
    const name = document.createElement("strong"); name.textContent = label;
    const link = document.createElement("span"); link.className = "ops-financial-document";
    appendFinancialDocument(link, documentRecord);
    identity.append(kind, name, link);
    const status = document.createElement("span"); status.className = "ops-financial-status";
    status.textContent = `Status: ${firstText(documentRecord, ["status"]) || "Status unavailable"}`;
    heading.append(identity, status);
    const party = firstText(order, ["supplier", "customer"]);
    const partyNode = document.createElement("p"); partyNode.className = "ops-financial-party";
    partyNode.textContent = `${label.startsWith("Sales") ? "Customer" : "Supplier"}: ${party || "Party unavailable"}`;
    const detail = document.createElement("p"); detail.className = "ops-financial-detail";
    detail.textContent = financialOrderSummary(order, unit);
    const currency = document.createElement("small"); currency.className = "ops-financial-meta";
    currency.textContent = `Currency: ${text(order.currency) || "Currency unavailable"}`;
    card.append(heading, partyNode, detail, currency);
    return card;
  }

  function financialInvoiceCard(record) {
    const card = document.createElement("article"); card.className = "ops-financial-card ops-financial-invoice";
    const documentRecord = isRecord(record.document) ? record.document : {};
    const heading = document.createElement("div"); heading.className = "ops-financial-heading";
    const identity = document.createElement("div");
    const kind = document.createElement("small"); kind.textContent = firstText(documentRecord, ["kind", "doctype", "type"]) || "Invoice";
    const name = document.createElement("strong"); name.textContent = firstText(documentRecord, ["name", "record_id", "id"]) || "Invoice record";
    const link = document.createElement("span"); link.className = "ops-financial-document";
    appendFinancialDocument(link, documentRecord);
    identity.append(kind, name, link);
    const status = document.createElement("span"); status.className = "ops-financial-status";
    status.textContent = firstText(documentRecord, ["status"]) || "Status unavailable";
    heading.append(identity, status);
    const detail = document.createElement("p"); detail.className = "ops-financial-detail";
    detail.textContent = invoiceRecordSummary(record);
    card.append(heading, detail);
    return card;
  }

  function renderInvoiceGroup(parent, title, group, unit, evidenceMode = null) {
    const section = document.createElement("section"); section.className = "ops-financial-group";
    const heading = document.createElement("div"); heading.className = "ops-financial-group-heading";
    const titleNode = document.createElement("strong"); titleNode.textContent = title;
    const badge = document.createElement("span");
    badge.className = `state-badge state-${group.status === "CURRENT" ? "lime" : group.status === "MISSING" ? "amber" : "coral"}`;
    badge.textContent = pretty(group.status);
    heading.append(titleNode, badge);
    const note = document.createElement("p"); note.className = "ops-financial-note";
    const sourceLabel = erpEvidenceSourceLabel(evidenceMode);
    const sourceSentence = `${sourceLabel[0].toUpperCase()}${sourceLabel.slice(1)}`;
    note.textContent = group.status === "CURRENT" && group.records.length
      ? `Invoice records read from the ${sourceLabel}.`
      : group.status === "CURRENT"
        ? `${sourceSentence} returned no invoice records.`
        : financialStatusMessage(group.status, title.startsWith("Sales") ? "Sales" : "Purchase", evidenceMode);
    section.append(heading, note);
    if (group.status === "CURRENT" && group.records.length) {
      const records = document.createElement("div"); records.className = "ops-financial-records";
      records.append(...group.records.map((record) => financialInvoiceCard(record, unit)));
      section.append(records);
    }
    parent.append(section);
  }

  function renderFinancials(next) {
    const panel = $("ops-financials-panel");
    if (!panel) return;
    if (!next._provided.financials) {
      panel.hidden = true;
      return;
    }
    const financials = normalizeFinancials(next.financials);
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    panel.hidden = false;
    const status = $("ops-financials-status");
    if (status) {
      status.className = `state-badge state-${financials.status === "CURRENT" ? "lime" : "coral"}`;
      status.textContent = pretty(financials.status);
    }
    setText("ops-financials-note", financials.status === "CURRENT"
      ? `Commercial records are read from the ${sourceLabel}. Sales order line amounts are order values; they are not revenue. Invoice totals and outstanding amounts are invoice-level amounts.`
      : `Commercial evidence is unavailable from the ${sourceLabel}. No amounts are inferred.`);
    const orders = $("ops-financial-orders");
    const invoices = $("ops-financial-invoices");
    orders.replaceChildren(); invoices.replaceChildren();
    if (financials.status !== "CURRENT") {
      orders.append(emptyList(`Source order lines are unavailable from the ${sourceLabel}.`));
      invoices.append(emptyList(`Invoice records are unavailable from the ${sourceLabel}.`));
      return;
    }
    const unit = text(next.quantities?.uom) || "units";
    if (financials.purchase_order) {
      orders.append(financialOrderCard(financials.purchase_order, "Purchase order", unit));
    }
    for (const order of financials.sales_orders) {
      const name = firstText(order.document, ["name", "record_id", "id"]) || "Sales order";
      orders.append(financialOrderCard(order, `Sales order · ${name}`, unit));
    }
    if (!orders.childNodes.length) orders.append(emptyList(`No source order lines returned from the ${sourceLabel}.`));
    renderInvoiceGroup(invoices, "Purchase invoices", financials.purchase_invoices, unit, next.evidence_mode);
    if (financials.sales_invoices.length) {
      for (const row of financials.sales_invoices) {
        renderInvoiceGroup(invoices, `Sales invoices · ${row.customer_order || "Order unavailable"}`, normalizeInvoiceGroup(row), unit, next.evidence_mode);
      }
    } else {
      invoices.append(emptyList(`No sales invoice groups returned from the ${sourceLabel}.`));
    }
  }

  function arrivalQuantitySummary(event, next) {
    const observed = numberFrom(event.observed_stock_quantity);
    if (!finite(observed)) return "Quantity count unknown";
    const unit = text(next?.quantities?.stock_uom) || text(next?.quantities?.uom) || text(event.stock_uom) || text(event.uom);
    return `${formatNumber(observed)}${unit ? ` ${unit}` : ""} counted`;
  }
  function eventSummary(event, next) {
    const type = canonicalType(event.type || event.event_type || event.kind);
    if (type === "arrival") return [finite(numberFrom(event.cartons)) ? `${formatNumber(numberFrom(event.cartons))} cartons` : "Cartons unknown", arrivalQuantitySummary(event, next), firstText(event, ["lot", "batch"])].filter(Boolean).join(" · ");
    if (type === "inspection") return [firstText(event, ["result", "status"]) || "Inspection result unknown", firstText(event, ["scope"]), firstText(event, ["metric"]), event.measured !== undefined ? `measured ${event.measured}` : ""].filter(Boolean).join(" · ");
    if (type === "picked") return [firstText(event, ["customer_order", "sales_order"]) || "Order unknown", finite(numberFrom(event.quantity)) ? `${formatNumber(numberFrom(event.quantity))} picked` : "Picked quantity unknown", firstText(event, ["lot", "batch"])].filter(Boolean).join(" · ");
    if (type === "carrier_pickup") return `${firstText(event, ["shipment_id", "shipment"]) || "Shipment unknown"} · pickup evidence`;
    if (type === "delivery") return `${firstText(event, ["shipment_id", "shipment"]) || "Shipment unknown"} · explicit delivery evidence`;
    return firstText(event, ["message", "evidence_ref"]) || "Event details unavailable";
  }
  function renderEvents(next) {
    const list = $("ops-events-list");
    setText("ops-events-count", next._provided.events ? `${next.events.length} event${next.events.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.events) { list.replaceChildren(emptyList("Source activity is unavailable from the current projection.")); return; }
    if (!next.events.length) { list.replaceChildren(emptyList("No source events recorded yet.")); return; }
    const events = next.events.map((event, index) => ({ event, index })).sort((a, b) => {
      const aSequence = numberFrom(a.event?.sequence); const bSequence = numberFrom(b.event?.sequence);
      if (finite(aSequence) && finite(bSequence)) return aSequence - bSequence;
      const aTime = Date.parse(a.event?.occurred_at || ""); const bTime = Date.parse(b.event?.occurred_at || "");
      if (Number.isFinite(aTime) && Number.isFinite(bTime) && aTime !== bTime) return aTime - bTime;
      return a.index - b.index;
    });
    list.replaceChildren(...events.map(({ event }) => {
      const item = document.createElement("li"); item.className = "ops-activity-item";
      const time = document.createElement("time"); time.className = "ops-activity-time"; time.textContent = formatDate(event.occurred_at);
      const copy = document.createElement("div"); copy.className = "ops-activity-copy";
      const title = document.createElement("strong"); title.textContent = pretty(canonicalType(event.type || event.event_type || event.kind) || event.type || event.kind || "Source event");
      const detail = document.createElement("p"); detail.textContent = eventSummary(event, next);
      const meta = document.createElement("small"); meta.textContent = `${event.synthetic === true ? "Simulated evidence" : "Source event"}${firstText(event, ["evidence_ref", "evidence_id"]) ? ` · ${firstText(event, ["evidence_ref", "evidence_id"])}` : ""}`;
      copy.append(title, detail, meta); item.append(time, copy); return item;
    }));
  }

  function conversationAnswer(conversation) {
    if (isRecord(conversation)) {
      for (const key of ["answer", "latest_answer", "text", "response", "message"]) {
        const answer = cleanAnswer(conversation[key]);
        if (answer) return answer;
      }
    }
    const messages = Array.isArray(conversation)
      ? conversation
      : isRecord(conversation) && Array.isArray(conversation.messages) ? conversation.messages : [];
    for (const message of [...messages].reverse()) {
        if (!isRecord(message)) continue;
        const role = text(message.role || message.author).toLowerCase();
        if (role && !/assistant|agent|system/.test(role)) continue;
        const answer = cleanAnswer(message.answer || message.content || message.text || message.message);
        if (answer) return answer;
    }
    return "";
  }
  function providerLabel(value) {
    if (typeof value === "string") return text(value);
    if (!isRecord(value)) return "";
    const provider = text(value.provider) || text(value.mode) || text(value.transport);
    const model = text(value.model) || text(value.model_id);
    return [provider, model].filter(Boolean).join(" · ");
  }
  function firstProvider(record, keys) {
    if (!isRecord(record)) return "";
    for (const key of keys) {
      const value = providerLabel(record[key]);
      if (value) return value;
    }
    return "";
  }
  function conversationProjectionState(next) {
    const conversation = next?.conversation;
    const rawStatus = (firstText(conversation, ["status", "state"]) || firstText(next, ["conversation_status"])).toUpperCase();
    const message = cleanAnswer(firstText(conversation, ["error", "detail", "message"]) || firstText(next, ["conversation_message"]));
    const status = rawStatus || (message ? "UNAVAILABLE" : "");
    const answer = conversationAnswer(conversation) || cleanAnswer(next?.answer || next?.answer_text);
    return { status, message, answer, hasState: Boolean(answer || /UNAVAILABLE|ERROR|FAILED|DISABLED/.test(status)) };
  }
  function retainConversationProjection(next, previous = null) {
    const caseId = text(next?.case_id);
    const prior = isRecord(previous) && text(previous.caseId) === caseId ? previous : null;
    const state = conversationProjectionState(next);
    if (caseId && state.hasState) {
      let conversation = Array.isArray(next.conversation)
        ? [...next.conversation]
        : isRecord(next.conversation) ? { ...next.conversation } : {};
      if (state.answer && !conversationAnswer(conversation)) {
        conversation = Array.isArray(conversation)
          ? [...conversation, { role: "assistant", answer: state.answer }]
          : { ...conversation, answer: state.answer };
      }
      return {
        projection: next,
        memory: {
          caseId,
          conversation,
          conversation_status: text(next.conversation_status) || state.status,
          conversation_message: text(next.conversation_message) || state.message,
          conversation_provider: text(next.conversation_provider),
          conversation_context: text(next.conversation_context),
        },
      };
    }
    if (!prior) return { projection: next, memory: null };
    const merged = {
      ...next,
      conversation: Array.isArray(prior.conversation)
        ? [...prior.conversation]
        : isRecord(prior.conversation) ? { ...prior.conversation } : {},
    };
    for (const key of ["conversation_status", "conversation_message", "conversation_provider", "conversation_context"]) {
      if (prior[key]) merged[key] = prior[key];
    }
    return { projection: merged, memory: prior };
  }
  function renderConversation(next) {
    const conversation = next.conversation || {};
    const status = (firstText(conversation, ["status", "state"]) || firstText(next, ["conversation_status"])).toUpperCase();
    const provider = firstProvider(conversation, ["provider_label", "provider", "model"])
      || firstProvider(next, ["conversation_provider", "provider", "model"])
      || (/UNAVAILABLE|ERROR|FAILED|DISABLED/.test(status) ? "Unavailable" : "Native bridge —");
    const sourceLabel = erpEvidenceSourceLabel(next?.evidence_mode);
    const context = firstText(conversation, ["context_label", "context", "source_summary"]) || firstText(next, ["conversation_context"]) || sourceLabel;
    setText("ops-chat-provider", provider);
    setText("ops-chat-context", context);
    const answerNode = $("ops-chat-answer"); answerNode.classList.remove("is-error");
    if (/UNAVAILABLE|ERROR|FAILED|DISABLED/.test(status)) {
      voiceController?.setAnswer("");
      answerNode.classList.add("is-error");
      const message = cleanAnswer(firstText(conversation, ["error", "detail", "message"]) || firstText(next, ["conversation_message"])) || "Read-only conversation is unavailable from the current bridge.";
      const paragraph = document.createElement("p"); paragraph.textContent = message; answerNode.replaceChildren(paragraph); return;
    }
    const answer = conversationAnswer(conversation);
    if (answer) { voiceController?.setAnswer(answer); answerNode.replaceChildren(Object.assign(document.createElement("p"), { textContent: answer })); return; }
    voiceController?.setAnswer("");
    const paragraph = document.createElement("p"); paragraph.className = "ops-empty"; paragraph.textContent = "Ask a read-only question about quantities, lots, customers, or delivery evidence."; answerNode.replaceChildren(paragraph);
  }

  function selectedTemplateFromProjection(next) {
    if (!selectedTemplate) return null;
    return next.available_event_templates.find((template) => template.type === selectedTemplate.type) || null;
  }
  function renderTemplateSummary(template) {
    const summary = $("ops-template-summary");
    if (!summary) return;
    if (!template) {
      summary.replaceChildren(Object.assign(document.createElement("span"), { textContent: "No event is selected." }));
      return;
    }
    const heading = document.createElement("strong"); heading.textContent = template.label;
    const detail = document.createElement("span"); detail.textContent = `${template.description} · Source: ${template.source}`;
    summary.replaceChildren(heading, detail);
  }
  function renderTemplateFields(template) {
    selectedTemplate = template;
    const fieldsNode = $("ops-template-fields"); fieldsNode.replaceChildren();
    renderTemplateSummary(template);
    if (!template) {
      const emptyEvidence = $("ops-evidence-ref");
      if (emptyEvidence) emptyEvidence.value = "";
      updateEventButton();
      return;
    }
    for (const definition of FIELD_DEFS[template.type]) {
      const label = document.createElement("label"); label.className = "ops-field"; label.htmlFor = `ops-field-${definition.key}`; label.textContent = definition.label;
      let input;
      if (definition.type === "select") {
        input = document.createElement("select");
        definition.options.forEach((option) => { const node = document.createElement("option"); node.value = option; node.textContent = option; input.append(node); });
      } else {
        input = document.createElement("input"); input.type = definition.type; if (definition.min) input.min = definition.min; if (definition.step) input.step = definition.step; if (definition.placeholder) input.placeholder = definition.placeholder;
      }
      input.id = `ops-field-${definition.key}`; input.dataset.fieldKey = definition.key; input.required = true;
      const value = templateDefault(template, definition.key);
      if (value !== "") input.value = String(value);
      input.addEventListener("input", updateEventButton);
      input.addEventListener("change", updateEventButton);
      label.append(input); fieldsNode.append(label);
    }
    const evidenceDefault = templateDefault(template, "evidence_ref");
    const evidenceNode = $("ops-evidence-ref");
    if (evidenceNode) evidenceNode.value = evidenceDefault;
    updateEventButton();
  }
  function renderTemplates(next, { resetFields = false } = {}) {
    const existing = selectedTemplate?.type || templateSelect.value;
    const currentType = selectedTemplate?.type;
    const fieldsRendered = Boolean($("ops-template-fields")?.querySelector("[data-field-key]"));
    templateSelect.replaceChildren();
    const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = next._provided.available_event_templates ? "Choose an approved event…" : "No event templates available"; templateSelect.append(placeholder);
    for (const template of next.available_event_templates) {
      const option = document.createElement("option"); option.value = template.type; option.textContent = template.label; templateSelect.append(option);
    }
    const match = next.available_event_templates.find((template) => template.type === existing) || null;
    templateSelect.value = match ? match.type : "";
    if (match && shouldPreserveTemplateFields({ currentType, nextType: match.type, fieldsRendered, resetFields })) {
      selectedTemplate = match;
      renderTemplateSummary(match);
    } else if (match) renderTemplateFields(match); else renderTemplateFields(null);
    templateSelect.disabled = !next.available_event_templates.length || !next.available || !freshActionsAllowed(next);
    syncFreshEventControls(next);
    updateEventButton();
  }
  function readTemplateValues() {
    return Object.fromEntries([...document.querySelectorAll("#ops-template-fields [data-field-key]")].map((node) => [node.dataset.fieldKey, node.value]));
  }
  function updateEventButton() {
    const button = $("ops-process-event");
    if (button) button.disabled = processingEvent || !projection?.available || !freshActionsAllowed(projection) || !selectedTemplate || !sourceState?.hidden;
  }
  function syncFreshEventControls(next = projection) {
    const form = $("ops-event-form");
    if (!form) return;
    const enabled = Boolean(next?.available === true && freshActionsAllowed(next) && sourceState?.hidden);
    form.querySelectorAll("input, select, button").forEach((control) => { control.disabled = !enabled; });
    const select = $("ops-template-select");
    if (select) select.disabled = !enabled || !Array.isArray(next?.available_event_templates) || !next.available_event_templates.length;
  }

  function proposalSourceLabel(source) {
    return text(source) === "RETAINED_ALLOCATION_RECOMMENDATION"
      ? "Retained allocation recommendation; it does not write."
      : "Operator-declared event; the agent did not create it.";
  }

  function proposalActionDetail(proposal, evidenceMode = null) {
    if (!isRecord(proposal)) return "No pending proposal";
    const status = text(proposal.status).toUpperCase();
    const retained = isRetainedEvidence(evidenceMode || proposal.evidence_mode);
    if (status === "APPLIED") return retained ? "Recorded completion confirmed" : "Approved operation applied";
    if (status === "PENDING_MANAGER_APPROVAL") return retained ? "Recorded completion awaiting confirmation" : "Proposal awaiting manager review";
    return status ? `Proposal status: ${pretty(status)}` : "Proposal status unavailable";
  }

  function approvalReadback(next) {
    const direct = isRecord(next?.approval_evidence) ? next.approval_evidence : null;
    if (direct) return direct;
    const proposal = isRecord(next?.prepared_proposal) ? next.prepared_proposal : null;
    const approval = isRecord(proposal?.approval) ? proposal.approval : null;
    if (!approval || text(proposal?.status).toUpperCase() !== "APPLIED") return null;
    return { ...approval, event_id: firstText(proposal.event, ["event_id"]) };
  }

  function renderPreparedProposal(next) {
    const incoming = isRecord(next?.prepared_proposal) ? next.prepared_proposal : null;
    if (incoming && text(incoming.proposal_id)) preparedProposal = incoming;
    const panel = $("ops-proposal-panel");
    const button = $("ops-approve-proposal");
    if (!panel || !button) return;
    const proposal = preparedProposal;
    const retained = isRetainedEvidence(next?.evidence_mode);
    setText("ops-manager-gate-label", retained ? "Recorded completion" : "Manager gate");
    setText("ops-evidence-title", retained ? "Confirm recorded completion" : "Process evidence");
    setText("ops-evidence-copy", retained
      ? "Review the recorded completion and confirm the exact retained case revision."
      : "Prepare one bounded action from operator-declared evidence, then confirm the exact case revision.");
    setText("ops-gate-note", retained
      ? "Manager confirmation recovers a recorded completed event; it does not create a fresh native operation."
      : "Manager approval stays bounded to the prepared case revision.");
    setText("ops-proposal-label", retained ? "Recorded completion" : "Manager approval");
    setText("ops-proposal-title", retained ? "Confirm recorded completion" : "Prepared same-case operation");
    setText("ops-approve-label", retained ? "Confirm recorded completion" : "Approve and execute");
    const readback = $("ops-approval-readback");
    const approval = approvalReadback(next);
    if (readback) {
      readback.hidden = !approval;
      readback.textContent = approval
        ? retained
          ? `Recorded completion confirmed by ${text(approval.manager_id) || "manager unavailable"} at ${formatDate(approval.approved_at)} · ${text(approval.event_id) || "event unavailable"}${approval.recovered === true ? " · recovered from retained event result" : ""}.`
          : `Approved by ${text(approval.manager_id) || "manager unavailable"} at ${formatDate(approval.approved_at)} · ${text(approval.event_id) || "event unavailable"}${approval.recovered === true ? " · recovered from retained event result" : ""}.`
        : "";
    }
    panel.hidden = !proposal || text(proposal.status) === "APPLIED" || text(proposal.case_id) && text(proposal.case_id) !== text(next?.case_id);
    if (panel.hidden) return;
    const event = isRecord(proposal.event) ? proposal.event : {};
    const fields = Object.entries(event)
      .filter(([key]) => !["event_id", "type", "occurred_at", "synthetic"].includes(key))
      .map(([key, value]) => `${pretty(key)}: ${Array.isArray(value) ? value.join(", ") : String(value)}`);
    const actionCopy = retained
      ? "This confirms a recorded completed event; no new native execution is attempted."
      : "Approval checks this exact current-case revision before one native execution.";
    setText("ops-proposal-summary", `${text(proposal.case_id) || text(next?.case_id)} · PO ${text(proposal.purchase_order) || text(next?.purchase_order) || "unavailable"} · ${pretty(event.type || "operation")}. ${fields.join(" · ")}. ${proposalSourceLabel(proposal.source)} ${actionCopy}`);
    button.disabled = processingEvent || !next?.available || !sourceState?.hidden || !text($("ops-manager-id")?.value) || (!retained && !freshActionsAllowed(next));
  }

  function photoAttachmentList(next) {
    return Array.isArray(next?.photo_attachments) ? next.photo_attachments.filter(isRecord) : [];
  }

  function renderPhotos(next) {
    const list = $("ops-photos-list");
    if (!list) return;
    const photos = photoAttachmentList(next);
    setText("ops-photos-count", photos.length ? `${photos.length} photo${photos.length === 1 ? "" : "s"}` : "No photos");
    if (!photos.length) { list.replaceChildren(emptyList("No same-case photos have been attached.")); return; }
    list.replaceChildren(...photos.map((photo) => {
      const card = document.createElement("article"); card.className = "ops-photo-card";
      const preview = document.createElement("button"); preview.type = "button"; preview.className = "ops-photo-open";
      const image = document.createElement("img");
      image.src = `${API_PATH}/photo?id=${encodeURIComponent(text(photo.attachment_id))}`;
      image.alt = "Operator-attached operational evidence; not analyzed";
      image.loading = "lazy"; preview.append(image);
      preview.setAttribute("aria-label", "Expand attached photo");
      preview.addEventListener("click", () => {
        const expanded = card.classList.toggle("is-expanded");
        preview.setAttribute("aria-label", expanded ? "Collapse attached photo" : "Expand attached photo");
      });
      const copy = document.createElement("div");
      const title = document.createElement("strong"); title.textContent = text(photo.event_id) ? `Associated with ${text(photo.event_id)}` : text(photo.proposal_id) ? "Prepared for manager approval" : "Unassociated operator attachment";
      const detail = document.createElement("small"); detail.textContent = `Manual photo · ${text(photo.interpretation) === "NOT_ANALYZED" ? "not analyzed" : "status unavailable"} · ${formatDate(photo.recorded_at)}`;
      copy.append(title, detail); card.append(preview, copy); return card;
    }));
  }

  function resetSelectedPhoto() {
    selectedPhoto = null;
    if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
    photoPreviewUrl = "";
    const input = $("ops-photo-file"); if (input) input.value = "";
    const preview = $("ops-photo-preview"); if (preview) { preview.hidden = true; preview.replaceChildren(); }
  }

  function attachmentId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    throw new Error("This browser cannot create an attachment ID.");
  }

  async function uploadSelectedPhoto() {
    if (!freshActionsAllowed(projection)) throw new Error("Fresh event controls are disabled for this retained operation.");
    if (!selectedPhoto) return "";
    const file = selectedPhoto;
    if (!/image\/(jpeg|png)/.test(file.type)) throw new Error("Choose a JPEG or PNG photo.");
    if (file.size <= 0 || file.size > 5_000_000) throw new Error("Choose a photo smaller than 5 MB.");
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    const encoded = btoa(binary);
    const id = attachmentId();
    const response = await requestJSON(`${API_PATH}/photo`, {
      method: "POST", body: JSON.stringify({ attachment_id: id, image: encoded, media_type: file.type }),
    });
    const next = unwrapProjection(response); if (next) renderProjection(next);
    return id;
  }
  function updateAskButton() {
    const button = $("ops-ask-submit");
    if (button) button.disabled = asking || !projection?.available || !sourceState?.hidden;
  }
  function setFeedback(message, tone = "") {
    const node = $("ops-event-feedback"); node.className = `ops-feedback${tone ? ` is-${tone}` : ""}`; node.textContent = message;
  }

  function createPendingAllocationRetryId() {
    const cryptoApi = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (cryptoApi && typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
    throw new Error("Pending allocation review is unavailable because this browser cannot create a request ID.");
  }

  function setAllocationFeedback(message, tone = "", context = {}) {
    allocationFeedback = {
      caseId: text(context.caseId) || text(projection?.case_id),
      pendingEventId: text(context.pendingEventId) || pendingAllocationEligibility(projection).pending_event_id,
      message: text(message),
      tone,
    };
    updatePendingAllocationAction(projection);
  }

  function updatePendingAllocationAction(next = projection) {
    const shell = $("ops-pending-allocation-action");
    const button = $("ops-reselect-pending-allocation");
    const feedback = $("ops-allocation-feedback");
    if (!shell || !button) return;
    const panel = $("ops-contract-panel");
    const actionState = pendingAllocationActionState(next, pendingAllocationAction, {
      sourceReady: Boolean(sourceState?.hidden),
      panelVisible: Boolean(panel && !panel.hidden),
    });
    shell.hidden = !actionState.eligible;
    button.disabled = actionState.disabled;
    const label = button.querySelector("[data-allocation-action-label]");
    if (label) label.textContent = actionState.label;
    if (feedback) {
      const showFeedback = Boolean(allocationFeedback && allocationFeedback.caseId === text(next?.case_id));
      feedback.hidden = !showFeedback;
      feedback.className = `ops-feedback ops-allocation-feedback${showFeedback && allocationFeedback.tone ? ` is-${allocationFeedback.tone}` : ""}`;
      feedback.textContent = showFeedback ? allocationFeedback.message : "";
    }
  }

  function syncPendingAllocationState(next, caseChanged = false) {
    const eligibility = pendingAllocationEligibility(next);
    if (caseChanged) {
      pendingAllocationAction = null;
      allocationFeedback = null;
      return;
    }
    if (pendingAllocationAction && pendingAllocationAction.caseId !== text(next?.case_id)) pendingAllocationAction = null;
    if (pendingAllocationAction && eligibility.status === "PENDING" && eligibility.pending_event_id
      && pendingAllocationAction.pendingEventId !== eligibility.pending_event_id) pendingAllocationAction = null;
    if (pendingAllocationAction && !pendingAllocationAction.inFlight && eligibility.status !== "PENDING") pendingAllocationAction = null;
    if (allocationFeedback && allocationFeedback.caseId !== text(next?.case_id)) allocationFeedback = null;
    if (allocationFeedback && eligibility.status === "PENDING" && eligibility.pending_event_id
      && allocationFeedback.pendingEventId && allocationFeedback.pendingEventId !== eligibility.pending_event_id) allocationFeedback = null;
  }

  async function reviewPendingAllocation() {
    const source = projection;
    const eligibility = pendingAllocationEligibility(source);
    if (!source?.available || !freshActionsAllowed(source) || !sourceState?.hidden || !eligibility.eligible
      || contractPanelState(source.feasible_allocation_plan, source.allocation_decision) !== "PENDING") return;
    let action = pendingAllocationAction;
    const sameAction = action
      && action.caseId === text(source.case_id)
      && action.pendingEventId === eligibility.pending_event_id;
    if (!sameAction) {
      try {
        action = {
          caseId: text(source.case_id),
          pendingEventId: eligibility.pending_event_id,
          retryId: createPendingAllocationRetryId(),
          inFlight: false,
        };
        pendingAllocationAction = action;
      } catch (error) {
        setAllocationFeedback(error.message || "Pending allocation review is unavailable.", "error", {
          caseId: text(source.case_id), pendingEventId: eligibility.pending_event_id,
        });
        return;
      }
    }
    if (action.inFlight) return;
    const request = pendingAllocationRequest(source, action.retryId);
    if (!request) {
      setAllocationFeedback(`Pending allocation review is unavailable from the ${erpEvidenceSourceLabel(source?.evidence_mode)}.`, "error", {
        caseId: action.caseId, pendingEventId: action.pendingEventId,
      });
      return;
    }
    action.inFlight = true;
    updatePendingAllocationAction(source);
    let requestError = null;
    try {
      const response = await requestJSON(`${API_PATH}/reselect-pending-allocation`, {
        method: "POST",
        body: JSON.stringify(request),
      });
      const responseProjection = unwrapProjection(response);
      if (responseProjection) renderProjection(responseProjection);
    } catch (error) {
      requestError = error;
    }
    const sourceRefresh = await refresh({ silent: true });
    if (requestError) {
      const detail = requestError.status
        ? `Pending allocation review was rejected: ${requestError.message || "the source rejected the request"}.`
        : "Pending allocation review could not be confirmed. The same request ID will be reused if you retry.";
      setAllocationFeedback(
        sourceRefresh === false ? `${detail} Source refresh also failed.` : detail,
        "error",
        { caseId: action.caseId, pendingEventId: action.pendingEventId },
      );
    } else {
      const outcome = allocationReviewOutcome(projection, action.retryId);
      setAllocationFeedback(
        sourceRefresh === false ? `${outcome.message} Source refresh failed; retry the source connection before continuing.` : outcome.message,
        outcome.tone,
        { caseId: action.caseId, pendingEventId: action.pendingEventId },
      );
    }
    if (pendingAllocationAction === action) {
      action.inFlight = false;
      const outcomeStatus = requestError ? "" : allocationReviewOutcome(projection, action.retryId).status;
      if (!shouldRetainPendingAllocationRetry(requestError, outcomeStatus)) pendingAllocationAction = null;
    }
    updatePendingAllocationAction(projection);
  }

  function renderProjection(value, { skipConversation = asking, resetEventFields = false } = {}) {
    const normalized = normalizeProjection(value);
    const retained = retainConversationProjection(normalized, retainedConversation);
    const next = retained.projection;
    retainedConversation = retained.memory;
    const previousCaseId = projection?.case_id;
    const caseChanged = Boolean(previousCaseId && next.case_id && previousCaseId !== next.case_id);
    syncPendingAllocationState(next, caseChanged);
    projection = next;
    if (next.available) {
      lastProjectionAt = new Date().toISOString();
      renderRefreshState();
    }
    document.body.dataset.operationsState = next.available ? "ready" : "disabled";
    setText("ops-case-label", next.case_label || (next.available ? "Current operation" : "No configured operation"));
    setText("ops-case-id", next.case_id || "Case identifier unavailable");
    const purchaseOrder = next.documents.find((record) => /^purchase order$/i.test(firstText(record, ["kind", "doctype", "type"])));
    setText("ops-case-po", purchaseOrder ? `PO ${firstText(purchaseOrder, ["name", "record_id", "id"]) || "identifier unavailable"}` : "Purchase order unavailable");
    const stageLabel = deliveryCompletionLabel(next) || pretty(next.stage);
    setText("ops-stage-badge", stageLabel);
    const stageBadge = $("ops-stage-badge"); stageBadge.className = `state-badge state-${statusTone(stageLabel)}`; stageBadge.textContent = stageLabel;
    setText("ops-flow-message", firstText(next, ["message", "summary"]) || "Current quantities and evidence from the source projection.");
    setText("ops-synthetic-badge", next.synthetic_input === true ? "Declared synthetic inputs" : "Native source events");
    const sourceStateKind = projectionSourceState(next);
    if (!next.available) {
      voiceController?.setAnswer("");
      if (caseChanged || resetEventFields) renderTemplateFields(null);
      content.hidden = true;
      disabled.hidden = false;
      if (sourceStateKind === "SOURCE_UNAVAILABLE") {
        const sourceAlert = next.alerts.find((alert) => firstText(alert, ["code", "kind"]).toUpperCase() === "SOURCE_UNAVAILABLE");
        showSourceError(
          new Error(firstText(sourceAlert, ["message", "detail"]) || "The configured operation source did not return current facts."),
          { configuredSourceFailure: true },
        );
      } else {
        disabled.querySelector("h2").textContent = "Distributor operations are not configured";
        disabled.querySelector("p").textContent = "This workspace is waiting for its explicit case configuration. No quantities or delivery state are inferred.";
        setConnection("Disabled", "amber");
      }
      updateEventButton();
      syncFreshEventControls(next);
      updateAskButton();
      return;
    }
    disabled.hidden = true;
    content.hidden = false;
    clearSourceError();
    renderQuantities(next);
    renderStages(next);
    renderOverview(next);
    renderSignalSources(next);
    renderAgentTools(next);
    renderBenchmark(next);
    renderTemplates(next, { resetFields: resetEventFields || caseChanged });
    renderLots(next);
    renderAllocations(next);
    renderAlerts(next);
    renderHandoffs(next);
    renderDocuments(next);
    renderFinancials(next);
    renderEvents(next);
    renderPhotos(next);
    renderPreparedProposal(next);
    if (!skipConversation) renderConversation(next);
    updateEventButton();
  }

  async function requestJSON(path, options = {}) {
    const response = await fetch(path, { headers: { Accept: "application/json", "Content-Type": "application/json" }, ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = firstText(payload, ["detail", "message", "error"]) || `Request failed (${response.status})`;
      const error = new Error(detail); error.status = response.status; throw error;
    }
    return payload;
  }
  async function refresh({ silent = false, periodic = false } = {}) {
    if (loading) { if (!periodic) refreshQueued = true; return null; }
    loading = true;
    if (!silent && !projection) setConnection("Connecting", "cyan");
    try {
      const payload = await requestJSON(API_PATH);
      const next = unwrapProjection(payload);
      if (!next) throw new Error("The source returned no distributor operation projection.");
      renderProjection(next);
      return true;
    } catch (error) {
      showSourceError(error);
      return false;
    } finally {
      loading = false;
      if (refreshQueued) { refreshQueued = false; void refresh({ silent: true }); }
    }
  }

  templateSelect.addEventListener("change", () => {
    if (!freshActionsAllowed(projection)) {
      templateSelect.value = "";
      renderTemplateFields(null);
      return;
    }
    const template = projection?.available_event_templates.find((item) => item.type === templateSelect.value) || null;
    renderTemplateFields(template);
  });
  $("ops-event-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (processingEvent || !selectedTemplate || !freshActionsAllowed(projection)) {
      if (!freshActionsAllowed(projection)) setFeedback("Fresh event controls are disabled for this retained operation.", "error");
      return;
    }
    processingEvent = true; updateEventButton(); setFeedback("Preparing the operator-declared event for manager approval…");
    try {
      const payload = buildEventPayload({
        type: selectedTemplate.type,
        values: readTemplateValues(),
        evidenceRef: $("ops-evidence-ref").value,
        now: new Date().toISOString(),
        eventId: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : undefined,
        synthetic: projection?.synthetic_input === true,
      });
      const photoAttachmentId = await uploadSelectedPhoto();
      const response = await requestJSON(`${API_PATH}/prepare-proposal`, {
        method: "POST",
        body: JSON.stringify({
          proposal_id: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : attachmentId(),
          case_id: projection.case_id,
          event: payload,
          source: "OPERATOR_DECLARED",
          ...(photoAttachmentId ? { photo_attachment_id: photoAttachmentId } : {}),
        }),
      });
      const next = unwrapProjection(response);
      if (next) renderProjection(next);
      else if (selectedTemplate) renderTemplateFields(selectedTemplate);
      const approvalFeedback = $("ops-proposal-feedback");
      if (approvalFeedback) {
        approvalFeedback.className = "ops-feedback";
        approvalFeedback.textContent = "";
      }
      setFeedback("Proposal prepared. A manager must approve this exact case revision before it can execute.", "success");
    } catch (error) {
      setFeedback(error.message || "Evidence proposal could not be prepared.", "error");
    } finally {
      processingEvent = false; updateEventButton(); renderPreparedProposal(projection);
    }
  });
  $("ops-photo-file")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0] || null;
    resetSelectedPhoto();
    if (!file) return;
    if (!freshActionsAllowed(projection)) {
      setFeedback("Fresh event controls are disabled for this retained operation.", "error");
      return;
    }
    if (!/image\/(jpeg|png)/.test(file.type) || file.size <= 0 || file.size > 5_000_000) {
      setFeedback("Choose a JPEG or PNG photo smaller than 5 MB.", "error"); return;
    }
    selectedPhoto = file; photoPreviewUrl = URL.createObjectURL(file);
    const preview = $("ops-photo-preview"); const image = document.createElement("img");
    image.src = photoPreviewUrl; image.alt = "Selected manual evidence photo; not analyzed";
    preview.replaceChildren(image, Object.assign(document.createElement("span"), { textContent: "Manual attachment; not analyzed." })); preview.hidden = false;
  });
  $("ops-manager-id")?.addEventListener("input", () => renderPreparedProposal(projection));
  $("ops-approve-proposal")?.addEventListener("click", async () => {
    const proposal = preparedProposal;
    const managerId = text($("ops-manager-id")?.value);
    const retained = isRetainedEvidence(projection?.evidence_mode);
    if (!proposal || !managerId || processingEvent || (!retained && !freshActionsAllowed(projection))) return;
    processingEvent = true; renderPreparedProposal(projection);
    const feedback = $("ops-proposal-feedback"); feedback.className = "ops-feedback";
    feedback.textContent = retained
      ? "Checking retained evidence and confirming the recorded completed event…"
      : "Checking the current case and executing one approved operation…";
    try {
      const response = await requestJSON(`${API_PATH}/approve-proposal`, {
        method: "POST",
        body: JSON.stringify({ proposal_id: proposal.proposal_id, case_id: projection.case_id, state_revision: proposal.state_revision, manager_id: managerId }),
      });
      const next = unwrapProjection(response);
      preparedProposal = null;
      if (next) renderProjection(next, { resetEventFields: true });
      resetSelectedPhoto();
      feedback.className = "ops-feedback is-success";
      feedback.textContent = retained
        ? "Recorded completed event confirmed. Retained evidence and same-case readback are shown below."
        : "Manager approval recorded. Native operation result and same-case readback are shown below.";
      void refresh({ silent: true });
    } catch (error) {
      feedback.className = "ops-feedback is-error";
      feedback.textContent = retained
        ? "Recorded completion confirmation could not be recorded; retained evidence remains unchanged."
        : error.message || "Approved operation could not execute.";
    } finally {
      processingEvent = false; renderPreparedProposal(projection);
    }
  });
  $("ops-retry").addEventListener("click", () => { void refresh(); });
  document.querySelectorAll("[data-ops-view-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const view = text(link.dataset.opsViewLink) || "dashboard";
      const url = new URL(link.href, window.location.href);
      window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
      setOpsView(view, { scrollTarget: text(url.hash).replace(/^#/, "") });
    });
  });
  document.querySelectorAll(".ops-overview-links a").forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const target = text(link.getAttribute("href")).replace(/^#/, "");
      if (!target) return;
      const url = new URL(window.location.href);
      url.searchParams.set("view", viewForOpsTarget(target));
      url.hash = target;
      window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
      focusOpsTarget(target);
    });
  });
  window.addEventListener("popstate", () => setOpsView(requestedOpsView()));
  window.addEventListener("hashchange", () => setOpsView(requestedOpsView()));
  setOpsView(requestedOpsView());
  function initializeVoiceControls() {
    const recognitionConstructor = window.SpeechRecognition || window.webkitSpeechRecognition;
    voiceController = createVoiceController({
      recognitionFactory: recognitionConstructor ? () => new recognitionConstructor() : null,
      speechSynthesisApi: window.speechSynthesis,
      utteranceFactory: typeof window.SpeechSynthesisUtterance === "function" ? (answer) => new window.SpeechSynthesisUtterance(answer) : null,
      input: $("ops-question"),
      setStatus: (message) => setText("ops-voice-status", message),
      dictateButton: $("ops-dictate"),
      readButton: $("ops-read-answer"),
      stopButton: $("ops-stop-reading"),
    });
    const support = voiceController.support();
    setText("ops-voice-status", support.dictation || support.reading
      ? "Optional English voice controls are ready. Dictation never sends automatically."
      : "English voice controls are unavailable in this browser. Typing remains available.");
    $("ops-dictate")?.addEventListener("click", () => voiceController.toggleDictation());
    $("ops-read-answer")?.addEventListener("click", () => voiceController.readAnswer());
    $("ops-stop-reading")?.addEventListener("click", () => voiceController.stopReading());
  }
  initializeVoiceControls();
  $("ops-ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = text($("ops-question").value);
    if (!question || asking || !projection?.available) return;
    asking = true; $("ops-ask-submit").disabled = true; $("ops-ask-submit").textContent = "Asking…";
    const answerNode = $("ops-chat-answer"); answerNode.classList.remove("is-error");
    const waiting = document.createElement("p"); waiting.textContent = isRetainedEvidence(projection?.evidence_mode)
      ? "Reading retained accepted evidence…"
      : "Reading the current operation source…"; answerNode.replaceChildren(waiting);
    try {
      const response = await requestJSON(`${API_PATH}/ask`, { method: "POST", body: JSON.stringify({ question }) });
      const next = unwrapProjection(response);
      if (next) renderProjection(next);
      const responseProjection = next || response;
      const responseConversation = Array.isArray(responseProjection.conversation)
        ? responseProjection.conversation
        : isRecord(responseProjection.conversation) ? responseProjection.conversation : {};
      const answer = cleanAnswer(responseProjection.answer || responseProjection.answer_text || conversationAnswer(responseConversation));
      if (projection) {
        if (Array.isArray(responseConversation) && responseConversation.length) {
          projection.conversation = responseConversation;
        } else if (isRecord(responseConversation) && Object.keys(responseConversation).length) {
          projection.conversation = {
            ...(isRecord(projection.conversation) ? projection.conversation : {}),
            ...responseConversation,
            ...(answer ? { answer } : {}),
          };
        }
        if (answer && conversationAnswer(projection.conversation) !== answer) {
          projection.conversation = Array.isArray(projection.conversation)
            ? [...projection.conversation, { role: "assistant", answer }]
            : { ...(isRecord(projection.conversation) ? projection.conversation : {}), answer };
        }
        for (const key of ["conversation_status", "conversation_message", "conversation_provider", "conversation_context"]) {
          if (responseProjection[key] !== undefined) projection[key] = responseProjection[key];
        }
        const retained = retainConversationProjection(projection, retainedConversation);
        projection = retained.projection;
        retainedConversation = retained.memory;
        renderConversation(projection);
      }
      $("ops-question").value = "";
    } catch (error) {
      answerNode.classList.add("is-error");
      const message = error.message || "Read-only conversation is unavailable.";
      const paragraph = document.createElement("p"); paragraph.textContent = message; answerNode.replaceChildren(paragraph);
      if (projection?.case_id) {
        const unavailable = {
          ...projection,
          conversation: { status: "UNAVAILABLE", message },
          conversation_status: "UNAVAILABLE",
          conversation_message: message,
        };
        const retained = retainConversationProjection(unavailable, retainedConversation);
        projection = retained.projection;
        retainedConversation = retained.memory;
      }
    } finally {
      asking = false; updateAskButton(); $("ops-ask-submit").innerHTML = '<i class="ph ph-chat-circle-dots" aria-hidden="true"></i>Ask';
    }
  });

  function startPolling() {
    if (pollTimer !== null) window.clearInterval(pollTimer);
    pollTimer = document.visibilityState === "visible" ? window.setInterval(() => void refresh({ silent: true, periodic: true }), 30000) : null;
  }
  document.addEventListener("visibilitychange", () => {
    startPolling();
    if (document.visibilityState === "visible") void refresh({ silent: true, periodic: true });
  });
  window.addEventListener("pagehide", () => { if (pollTimer !== null) window.clearInterval(pollTimer); pollTimer = null; });
  updateEventButton();
  updateAskButton();
  void refresh();
  startPolling();

  if (typeof window !== "undefined") window.Missing20DistributorOperationsState = { get projection() { return projection; }, get lastProjectionAt() { return lastProjectionAt; }, refresh };
})();
