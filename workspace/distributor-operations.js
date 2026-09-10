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
      available_event_templates: normalizeTemplates(source.available_event_templates),
      conversation: Array.isArray(source.conversation)
        ? source.conversation
        : isRecord(source.conversation) ? { ...source.conversation } : {},
      _provided: provided,
    };
  }

  function unwrapProjection(value) {
    if (!isRecord(value)) return null;
    for (const key of ["distributor_operations", "projection", "operation", "result"]) {
      if (isRecord(value[key]) && ("quantities" in value[key] || "available" in value[key] || "stage" in value[key])) return value[key];
    }
    return ("quantities" in value || "available" in value || "stage" in value) ? value : null;
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

  function buildEventPayload({ type, values = {}, evidenceRef, now, eventId }) {
    const eventType = canonicalType(type);
    if (!eventType) throw new Error("Choose a supported evidence template.");
    const commonEvidence = text(evidenceRef);
    if (!commonEvidence) throw new Error("Enter an evidence ID before processing the event.");
    const payload = {
      event_id: text(eventId) || `demo-event-${Date.now()}`,
      type: eventType,
      occurred_at: text(now) || new Date().toISOString(),
      evidence_ref: commonEvidence,
      synthetic: true,
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

  const exported = {
    buildEventPayload,
    cleanAnswer,
    conversationAnswer,
    providerLabel,
    retainConversationProjection,
    shouldPreserveTemplateFields,
    formatNumber,
    normalizeProjection,
    normalizeTemplate,
    normalizeTemplates,
    recommendedAction,
    statusTone,
    deliverySummary,
    arrivalQuantitySummary,
    unwrapProjection,
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
  function showSourceError(error) {
    sourceState.hidden = false;
    setText("ops-source-title", "Current operation source unavailable");
    setText("ops-source-detail", error?.message || "The source did not return a usable projection. Quantities are unknown.");
    setConnection("Unavailable", "danger");
    if (!projection) {
      content.hidden = true;
      disabled.hidden = false;
      disabled.querySelector("h2").textContent = "Operation source unavailable";
      disabled.querySelector("p").textContent = "No quantities or delivery state are inferred until the source responds.";
    }
    updateEventButton();
    updateAskButton();
  }
  function clearSourceError() {
    sourceState.hidden = true;
    setConnection("Live source", "lime");
    updateEventButton();
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
    const cartons = cartonsSummary(q.cartons);
    const cartonsNode = $("ops-quantity-cartons");
    const cartonsCard = document.querySelector('[data-quantity-card="cartons"]');
    if (cartonsNode) cartonsNode.textContent = cartons;
    cartonsCard?.classList.toggle("is-unknown", cartons === "Unknown");
    for (const key of ["ordered", "received", "usable", "held", "missing", "allocated", "dispatched", "delivery_confirmed"]) {
      setQuantityCard(key, quantity(next, key), key === "delivery_confirmed" ? "explicit event" : unit);
    }
    setText("ops-uom-note", text(q.uom)
      ? `Parts are shown in stock UOM ${q.uom}; cartons remain a separate outer-package observation.`
      : "Stock UOM is not confirmed; cartons and part quantities remain separate observations.");
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
    list.replaceChildren(...STAGES.map((stage) => {
      const item = document.createElement("li");
      item.className = "ops-stage";
      const isComplete = stageProof(next, stage);
      if (isComplete) item.classList.add("is-complete");
      if (stageHeld(next, stage)) item.classList.add("is-held");
      if (!isComplete && stageMatches(next.stage, stage.key)) item.classList.add("is-current");
      const marker = document.createElement("span");
      marker.className = "ops-stage-marker";
      marker.innerHTML = `<i class="ph ${isComplete ? "ph-check" : stage.icon}" aria-hidden="true"></i>`;
      const title = document.createElement("strong"); title.textContent = stage.label;
      const detail = document.createElement("small");
      const value = stage.metric === "picked"
        ? (allocationPicked(next) || pickedEvidenceRecorded(next) ? "Server recorded" : "Awaiting picked evidence")
        : finite(quantity(next, stage.metric)) ? `${formatNumber(quantity(next, stage.metric))} ${stage.metric === "delivery_confirmed" ? "confirmed" : text(next.quantities?.uom) || "units"}` : stage.detail;
      detail.textContent = value;
      item.append(marker, title, detail);
      return item;
    }));
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
    setText("ops-lots-count", next._provided.lots ? `${next.lots.length} lot${next.lots.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.lots) { list.replaceChildren(emptyList("Lot and inspection data is unavailable from the current source.")); return; }
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
  function renderAllocations(next) {
    const list = $("ops-orders-list");
    setText("ops-orders-count", next._provided.allocations ? `${next.allocations.length} order${next.allocations.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.allocations) { list.replaceChildren(emptyList("Customer allocation data is unavailable from the current source.")); return; }
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
      const note = document.createElement("small"); note.textContent = `${customer ? `${customer} · ` : ""}${allocationLabel(allocation)} · ${status}`;
      first.append(title, note);
      const outbound = [
        finite(picked) ? `Picked ${displayQuantity(picked)}` : pickedEvidenceRecorded(next, order) ? "Picked recorded" : "Picked unknown",
        finite(dispatched) ? `Dispatched ${displayQuantity(dispatched)}` : "Dispatched unknown",
        deliverySummary(delivery, requested),
      ].join(" · ");
      row.append(first, metricBlock("Allocated", displayQuantity(allocated), allocated > 0 ? "is-positive" : ""), metricBlock("Backorder", displayQuantity(backorder), backorder > 0 ? "is-alert" : ""), metricBlock("Outbound evidence", outbound));
      return row;
    }));
  }

  function renderAlerts(next) {
    const list = $("ops-alerts-list");
    const alerts = next.alerts.filter((alert) => !/RESOLVED|CLOSED|DONE/i.test(firstText(alert, ["status", "state"])));
    setText("ops-alerts-count", next._provided.alerts ? `${alerts.length} active alert${alerts.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.alerts) { list.replaceChildren(emptyList("Manager alert data is unavailable from the current source.")); return; }
    if (!alerts.length) { list.replaceChildren(emptyList("No active manager alerts in the current projection.")); return; }
    list.replaceChildren(...alerts.map((alert) => {
      const card = document.createElement("article"); card.className = "ops-alert-card";
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
  function renderDocuments(next) {
    const list = $("ops-documents-list");
    setText("ops-documents-count", next._provided.documents ? `${next.documents.length} record${next.documents.length === 1 ? "" : "s"}` : "Unknown");
    if (!next._provided.documents) { list.replaceChildren(emptyList("Native ERP document data is unavailable from the current source.")); return; }
    if (!next.documents.length) { list.replaceChildren(emptyList("No linked ERP documents in the current source.")); return; }
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
    const context = firstText(conversation, ["context_label", "context", "source_summary"]) || firstText(next, ["conversation_context"]) || "Current operation source";
    setText("ops-chat-provider", provider);
    setText("ops-chat-context", context);
    const answerNode = $("ops-chat-answer"); answerNode.classList.remove("is-error");
    if (/UNAVAILABLE|ERROR|FAILED|DISABLED/.test(status)) {
      answerNode.classList.add("is-error");
      const message = cleanAnswer(firstText(conversation, ["error", "detail", "message"]) || firstText(next, ["conversation_message"])) || "Read-only conversation is unavailable from the current bridge.";
      const paragraph = document.createElement("p"); paragraph.textContent = message; answerNode.replaceChildren(paragraph); return;
    }
    const answer = conversationAnswer(conversation);
    if (answer) { answerNode.replaceChildren(Object.assign(document.createElement("p"), { textContent: answer })); return; }
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
    templateSelect.disabled = !next.available_event_templates.length || !next.available;
    updateEventButton();
  }
  function readTemplateValues() {
    return Object.fromEntries([...document.querySelectorAll("#ops-template-fields [data-field-key]")].map((node) => [node.dataset.fieldKey, node.value]));
  }
  function updateEventButton() {
    const button = $("ops-process-event");
    if (button) button.disabled = processingEvent || !projection?.available || !selectedTemplate || !sourceState?.hidden;
  }
  function updateAskButton() {
    const button = $("ops-ask-submit");
    if (button) button.disabled = asking || !projection?.available || !sourceState?.hidden;
  }
  function setFeedback(message, tone = "") {
    const node = $("ops-event-feedback"); node.className = `ops-feedback${tone ? ` is-${tone}` : ""}`; node.textContent = message;
  }

  function renderProjection(value, { skipConversation = asking, resetEventFields = false } = {}) {
    const normalized = normalizeProjection(value);
    const retained = retainConversationProjection(normalized, retainedConversation);
    const next = retained.projection;
    retainedConversation = retained.memory;
    const previousCaseId = projection?.case_id;
    const caseChanged = Boolean(previousCaseId && next.case_id && previousCaseId !== next.case_id);
    projection = next;
    lastProjectionAt = new Date().toISOString();
    document.body.dataset.operationsState = next.available ? "ready" : "disabled";
    setText("ops-case-label", next.case_label || (next.available ? "Current operation" : "No configured operation"));
    setText("ops-case-id", next.case_id || "Case identifier unavailable");
    const purchaseOrder = next.documents.find((record) => /^purchase order$/i.test(firstText(record, ["kind", "doctype", "type"])));
    setText("ops-case-po", purchaseOrder ? `PO ${firstText(purchaseOrder, ["name", "record_id", "id"]) || "identifier unavailable"}` : "Purchase order unavailable");
    setText("ops-stage-badge", pretty(next.stage));
    const stageBadge = $("ops-stage-badge"); stageBadge.className = `state-badge state-${statusTone(next.stage)}`; stageBadge.textContent = pretty(next.stage);
    setText("ops-flow-message", firstText(next, ["message", "summary"]) || "Current quantities and evidence from the source projection.");
    setText("ops-synthetic-badge", next.synthetic_input === true ? "Declared synthetic inputs" : "Native source events");
    if (!next.available) {
      if (caseChanged || resetEventFields) renderTemplateFields(null);
      content.hidden = true;
      disabled.hidden = false;
      disabled.querySelector("h2").textContent = "Distributor operations are not configured";
      disabled.querySelector("p").textContent = "This workspace is waiting for its explicit case configuration. No quantities or delivery state are inferred.";
      setConnection("Disabled", "amber");
      updateEventButton();
      updateAskButton();
      return;
    }
    disabled.hidden = true;
    content.hidden = false;
    clearSourceError();
    renderQuantities(next);
    renderStages(next);
    renderTemplates(next, { resetFields: resetEventFields || caseChanged });
    renderLots(next);
    renderAllocations(next);
    renderAlerts(next);
    renderDocuments(next);
    renderEvents(next);
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
  async function refresh({ silent = false } = {}) {
    if (loading) { refreshQueued = true; return; }
    loading = true;
    if (!silent && !projection) setConnection("Connecting", "cyan");
    try {
      const payload = await requestJSON(API_PATH);
      const next = unwrapProjection(payload);
      if (!next) throw new Error("The source returned no distributor operation projection.");
      renderProjection(next);
    } catch (error) {
      showSourceError(error);
    } finally {
      loading = false;
      if (refreshQueued) { refreshQueued = false; void refresh({ silent: true }); }
    }
  }

  templateSelect.addEventListener("change", () => {
    const template = projection?.available_event_templates.find((item) => item.type === templateSelect.value) || null;
    renderTemplateFields(template);
  });
  $("ops-event-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (processingEvent || !selectedTemplate) return;
    processingEvent = true; updateEventButton(); setFeedback("Processing the declared synthetic event…");
    try {
      const payload = buildEventPayload({
        type: selectedTemplate.type,
        values: readTemplateValues(),
        evidenceRef: $("ops-evidence-ref").value,
        now: new Date().toISOString(),
        eventId: typeof crypto !== "undefined" && crypto.randomUUID ? crypto.randomUUID() : undefined,
      });
      const response = await requestJSON(`${API_PATH}/events`, { method: "POST", body: JSON.stringify(payload) });
      const next = unwrapProjection(response);
      if (next) renderProjection(next, { resetEventFields: true });
      else if (selectedTemplate) renderTemplateFields(selectedTemplate);
      setFeedback("Evidence processed. The projection and alerts were refreshed.", "success");
      void refresh({ silent: true });
    } catch (error) {
      setFeedback(error.message || "Evidence could not be processed.", "error");
    } finally {
      processingEvent = false; updateEventButton();
    }
  });
  $("ops-retry").addEventListener("click", () => { void refresh(); });
  $("ops-ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = text($("ops-question").value);
    if (!question || asking || !projection?.available) return;
    asking = true; $("ops-ask-submit").disabled = true; $("ops-ask-submit").textContent = "Asking…";
    const answerNode = $("ops-chat-answer"); answerNode.classList.remove("is-error");
    const waiting = document.createElement("p"); waiting.textContent = "Reading the current operation source…"; answerNode.replaceChildren(waiting);
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
    pollTimer = document.visibilityState === "visible" ? window.setInterval(() => void refresh({ silent: true }), 5000) : null;
  }
  document.addEventListener("visibilitychange", () => {
    startPolling();
    if (document.visibilityState === "visible") void refresh({ silent: true });
  });
  window.addEventListener("pagehide", () => { if (pollTimer !== null) window.clearInterval(pollTimer); pollTimer = null; });
  updateEventButton();
  updateAskButton();
  void refresh();
  startPolling();

  if (typeof window !== "undefined") window.Missing20DistributorOperationsState = { get projection() { return projection; }, get lastProjectionAt() { return lastProjectionAt; }, refresh };
})();
