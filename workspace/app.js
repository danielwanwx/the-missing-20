/* The Missing 20 live client. Business state comes from the experiment API and SSE ledger. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const query = new URLSearchParams(window.location.search);
  const smokeCapture = query.get("smoke") === "1";
  const demoMode = ["complete", "degraded", "invalid"].includes(query.get("mode") || "complete")
    ? (query.get("mode") || "complete")
    : "complete";
  const EVENT_TYPES = [
    "incident.detected",
    "investigation.started",
    "agent.started",
    "agent.completed",
    "tool.started",
    "tool.completed",
    "evidence.returned",
    "agent.handoff",
    "synthesis.started",
    "synthesis.completed",
    "evaluation.started",
    "evaluation.completed",
    "recovery.prepared",
    "approval.requested",
    "approval.recorded",
    "execution.started",
    "execution.completed",
    "verification.completed",
    "copilot.message",
    "provider.degraded",
    "workflow.blocked",
  ];
  const OPERATION_TYPES = new Set([
    "agent.started",
    "agent.completed",
    "tool.started",
    "tool.completed",
    "evidence.returned",
    "agent.handoff",
    "synthesis.started",
    "synthesis.completed",
    "evaluation.started",
    "evaluation.completed",
  ]);
  const AGENT_DEFS = [
    {
      id: "retryable_message_investigator",
      name: "Receipt retry",
      focus: "Failed message path",
    },
    {
      id: "short_shipment_investigator",
      name: "Shipment check",
      focus: "Physical quantity",
    },
    {
      id: "duplicate_posting_investigator",
      name: "Duplicate check",
      focus: "Existing postings",
    },
  ];
  const ROLE_DEFS = [
    { role: "INTEGRATION_OPERATOR", principal: "integration-operator", name: "Integration operator" },
    { role: "AP_APPROVER", principal: "ap-approver", name: "AP approver" },
  ];

  const state = {
    view: new URLSearchParams(window.location.search).get("view") === "agent" ? "agent" : "dashboard",
    incidentId: "",
    snapshot: null,
    units: new Map(),
    events: [],
    lastSequence: 0,
    connection: "connecting",
    streamError: "",
    source: null,
    reconnectTimer: null,
    loaded: false,
    startIssued: false,
    startBusy: false,
    replaying: false,
    replayTargetSequence: 0,
    selectedUnitId: "",
    selectedAgentId: "",
    movingIds: new Set(),
    activeEdges: new Set(),
    chatMessages: [],
    chatHydrated: false,
    chatPending: false,
    commandBusy: false,
    commandError: "",
    renderQueued: false,
    refreshPromise: Promise.resolve(),
  };

  function value(value) {
    return String(value == null ? "" : value);
  }

  function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function slug(raw) {
    return value(raw).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function human(raw) {
    return value(raw).replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function actionLabel(raw) {
    const labels = {
      restart_receipt_message: "Receipt Message Restart",
      release_invoice: "Invoice Release",
    };
    return labels[value(raw)] || human(raw);
  }

  function stateClass(raw) {
    const status = value(raw).toUpperCase();
    if (["HEALTHY", "COMPLETE", "COMPLETED", "PASS", "GRANTED", "APPROVED", "ERP_RECORDED", "VERIFIED"].includes(status)) {
      return "state-lime";
    }
    if (["RUNNING", "INVESTIGATING", "STARTED", "ADMITTED", "HANDED_OFF", "SCRIPTED_SYNTHETIC_PROOF"].includes(status)) {
      return "state-cyan";
    }
    if (["ANOMALY", "QUEUE_FAILED", "HELD", "FAILED", "BLOCKED", "DEGRADED", "NOT_PROVEN", "NOT PROVEN", "PENDING_APPROVAL"].includes(status)) {
      return "state-coral";
    }
    return "state-neutral";
  }

  function makeKey(prefix) {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return `${prefix}:${window.crypto.randomUUID()}`;
    }
    return `${prefix}:${Date.now().toString(36)}:${Math.random().toString(36).slice(2)}`;
  }

  function create(tag, className, content) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (content != null) node.textContent = content;
    return node;
  }

  function setBadge(node, label, rawState) {
    if (!node) return;
    node.className = `state-badge ${stateClass(rawState)}`;
    node.textContent = value(label);
  }

  function setConnection(connection, detail) {
    state.connection = connection;
    const labels = { live: "LIVE", connecting: "CONNECTING", paused: "PAUSED" };
    $("connection-label").textContent = labels[connection] || "PAUSED";
    $("connection-dot").className = `status-dot ${connection === "live" ? "status-dot-lime" : connection === "paused" ? "status-dot-danger" : "status-dot-cyan"}`;
    $("sequence-label").textContent = `seq ${state.lastSequence || "—"}`;
    $("footer-status").textContent = detail || (connection === "live" ? "Connected to the authoritative event ledger." : "Live movement is paused until the stream reconnects.");
    document.body.dataset.connection = connection;
  }

  function streamIsLive() {
    return state.connection === "live";
  }

  function incidentStatus() {
    return value(state.snapshot && state.snapshot.incident && state.snapshot.incident.status);
  }

  function hasStartedInvestigation() {
    return state.events.some((event) => eventType(event) === "investigation.started");
  }

  function hasCompletedInvestigation() {
    return state.events.some((event) => eventType(event) === "evaluation.completed");
  }

  function canOperate() {
    return streamIsLive()
      && !state.replaying
      && !state.startBusy
      && demoMode !== "degraded"
      && incidentStatus() !== "CLOSED"
      && hasCompletedInvestigation();
  }

  function showUnavailable(detail, visible) {
    $("unavailable").hidden = !visible;
    if (visible) $("unavailable-detail").textContent = value(detail || "The local experiment did not return a usable state.");
  }

  function applyDemoMode(snapshot) {
    document.body.dataset.demoMode = demoMode;
    if (demoMode !== "degraded") return snapshot;
    const advisory = snapshot && snapshot.advisory ? snapshot.advisory : {};
    return {
      ...snapshot,
      advisory: {
        ...advisory,
        status: "DEGRADED",
        provider: "scripted",
        usefulness: "NOT_PROVEN",
        authority: "ADVISORY_NOT_OPERATIONAL_DECISION",
        error_code: "DEMO_DEGRADED_MODE",
      },
    };
  }

  function applyModeVisibility() {
    const degraded = demoMode === "degraded";
    [".live-panel", ".agent-system-panel", ".copilot-panel"].forEach((selector) => {
      const panel = document.querySelector(selector);
      if (panel) panel.hidden = degraded;
    });
    ["tab-agent", "open-agent", "dashboard-to-agent"].forEach((id) => {
      const control = $(id);
      if (!control) return;
      control.disabled = degraded;
      control.setAttribute("aria-disabled", String(degraded));
    });
    ["chat-input", "chat-submit"].forEach((id) => {
      const control = $(id);
      if (!control) return;
      control.disabled = degraded;
      control.setAttribute("aria-disabled", String(degraded));
    });
    document.querySelectorAll(".suggestion").forEach((control) => {
      control.disabled = degraded;
      control.setAttribute("aria-disabled", String(degraded));
    });
  }

  async function requestJSON(path, options) {
    const init = { credentials: "same-origin", ...options };
    if (init.body && typeof init.body !== "string") {
      init.body = JSON.stringify(init.body);
    }
    const response = await fetch(path, init);
    let payload = null;
    try {
      payload = await response.json();
    } catch (_error) {
      payload = null;
    }
    if (!response.ok) {
      const detail = payload && payload.error ? payload.error.detail || payload.error.code : `request returned ${response.status}`;
      throw new Error(value(detail));
    }
    return payload;
  }

  function mergeInitialEvents(rows) {
    const ordered = (Array.isArray(rows) ? rows : [])
      .filter((item) => item && Number.isInteger(Number(item.sequence)))
      .map((item) => ({ ...item, sequence: Number(item.sequence), event_type: value(item.event_type || item.event) }))
      .sort((a, b) => a.sequence - b.sequence);
    state.events = ordered;
    state.lastSequence = ordered.length ? ordered[ordered.length - 1].sequence : 0;
  }

  function applySnapshot(snapshot, unitRows, initial) {
    if (!snapshot || !snapshot.incident_id) return;
    const previousUnits = state.units;
    const rows = Array.isArray(unitRows) ? unitRows : Array.isArray(snapshot.units) ? snapshot.units : [];
    const nextUnits = new Map();
    rows.forEach((item) => {
      if (item && item.unit_id) nextUnits.set(value(item.unit_id), item);
    });
    if (!initial && state.snapshot && number(snapshot.projection_sequence) < state.lastSequence) {
      return;
    }
    if (!initial) {
      nextUnits.forEach((item, id) => {
        const prior = previousUnits.get(id);
        if (prior && prior.status !== item.status && item.status === "ERP_RECORDED") {
          state.movingIds.add(id);
        }
      });
    }
    state.snapshot = applyDemoMode(snapshot);
    state.incidentId = value(snapshot.incident_id);
    state.units = nextUnits;
    if (initial) mergeInitialEvents(snapshot.events || snapshot.activity);
    state.loaded = state.units.size > 0;
    // Refresh the unit projection once per authoritative snapshot, rather than
    // rebuilding all 100 buttons for every unrelated SSE operation event.
    renderFlow();
    renderAll();
  }

  function queueRefresh() {
    if (!state.incidentId) return state.refreshPromise;
    state.refreshPromise = state.refreshPromise.then(async () => {
      const snapshot = await requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}`);
      // The snapshot is one authoritative read and already carries its unit
      // projection. Fetching /units concurrently can cross an execution commit
      // and pair a new VERIFIED snapshot with an old 80/20 unit list.
      applySnapshot(snapshot, snapshot.units, false);
    }).catch((error) => {
      setConnection("paused", `Snapshot refresh failed: ${error.message}`);
    });
    return state.refreshPromise;
  }

  function eventType(event) {
    return value(event && (event.event_type || event.event));
  }

  function pauseStream(reason) {
    state.streamError = reason || "The event stream is unavailable.";
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    setConnection("paused", `${state.streamError} Live movement is paused.`);
    if (state.reconnectTimer == null) {
      state.reconnectTimer = window.setTimeout(() => {
        state.reconnectTimer = null;
        reconnectStream();
      }, 1500);
    }
    renderAll();
  }

  async function reconnectStream() {
    if (!state.incidentId || state.source) return;
    try {
      // A server restart or ledger rotation can make the browser cursor newer
      // than the current stream.  Re-read the authoritative projection and use
      // its contiguous event history as the safe cursor before resubscribing.
      const [snapshot, units] = await Promise.all([
        requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}`),
        requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}/units`),
      ]);
      // Use the unit rows embedded in the same snapshot so reconnect cannot
      // combine a reset projection with a response from another case version.
      applySnapshot(snapshot, snapshot.units || units.units, true);
      if (state.replaying) {
        state.replayTargetSequence = number(snapshot.projection_sequence);
      }
      state.streamError = "";
      connectEvents();
    } catch (error) {
      pauseStream(`Stream recovery failed: ${error.message}`);
    }
  }

  function acceptEvent(event) {
    const sequence = Number(event && event.sequence);
    const type = eventType(event);
    if (!Number.isInteger(sequence) || sequence < 1 || !type) {
      pauseStream("The event stream returned an invalid event.");
      return;
    }
    if (sequence <= state.lastSequence) return;
    if (sequence !== state.lastSequence + 1) {
      pauseStream(`Event sequence gap at ${state.lastSequence + 1}.`);
      return;
    }
    state.lastSequence = sequence;
    state.events.push({ ...event, sequence, event_type: type });
    state.activeEdges.clear();
    if (type === "execution.started") state.activeEdges.add("message-queue->erp");
    $("sequence-label").textContent = `seq ${state.lastSequence}`;
    scheduleRender();
    if (["execution.completed", "verification.completed"].includes(type)) queueRefresh();
    if (
      state.replaying
      && state.replayTargetSequence > 0
      && sequence >= state.replayTargetSequence
    ) {
      finishReplay();
    }
  }

  function finishReplay() {
    state.replaying = false;
    state.replayTargetSequence = 0;
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    setConnection("live", "Replay complete; the immutable investigation ledger is shown.");
    renderAll();
  }

  function connectEvents() {
    if (!state.incidentId || state.source) return;
    setConnection(
      "connecting",
      state.replaying
        ? "Replaying the immutable investigation ledger."
        : "Opening the authoritative event stream.",
    );
    const replayQuery = state.replaying ? "&replay=1" : "";
    const url = `/api/v1/incidents/${encodeURIComponent(state.incidentId)}/events?after=${state.lastSequence}${replayQuery}`;
    const source = new EventSource(url);
    state.source = source;
    const receive = (message) => {
      try {
        acceptEvent(JSON.parse(message.data));
      } catch (_error) {
        pauseStream("The event stream returned invalid JSON.");
      }
    };
    source.addEventListener("stream.reset", () => {
      pauseStream("The event ledger reset; resubscribing from a safe cursor.");
    });
    EVENT_TYPES.forEach((type) => source.addEventListener(type, receive));
    source.onopen = () => {
      state.streamError = "";
      setConnection("live");
      renderAll();
    };
    source.onerror = () => {
      if (state.source !== source) return;
      // EventSource reports a clean EOF as an error.  A finite replay is only
      // complete after its authoritative target sequence has actually drained;
      // evaluation.completed can arrive much earlier for an open incident.
      if (
        state.replaying
        && state.replayTargetSequence > 0
        && state.lastSequence >= state.replayTargetSequence
      ) {
        finishReplay();
        return;
      }
      pauseStream("The event stream disconnected.");
    };
  }

  function setView(view) {
    state.view = demoMode === "degraded" ? "dashboard" : view === "agent" ? "agent" : "dashboard";
    document.body.dataset.view = state.view;
    const query = new URLSearchParams(window.location.search);
    query.set("view", state.view);
    window.history.replaceState(null, "", `/?${query.toString()}`);
    $("dashboard-view").hidden = state.view !== "dashboard";
    $("agent-view").hidden = state.view !== "agent";
    $("tab-dashboard").classList.toggle("is-selected", state.view === "dashboard");
    $("tab-agent").classList.toggle("is-selected", state.view === "agent");
    $("tab-dashboard").setAttribute("aria-selected", String(state.view === "dashboard"));
    $("tab-agent").setAttribute("aria-selected", String(state.view === "agent"));
    $("tab-dashboard").tabIndex = state.view === "dashboard" ? 0 : -1;
    $("tab-agent").tabIndex = state.view === "agent" ? 0 : -1;
    window.scrollTo(0, 0);
    renderAll();
  }

  function agentDefinition(id) {
    return AGENT_DEFS.find((item) => item.id === id) || { id, name: human(id), focus: "Investigation path" };
  }

  function agentState(id) {
    const events = state.events.filter((item) => item.actor === id || value(item.payload && item.payload.stage).startsWith(id));
    const started = [...events].reverse().find((item) => eventType(item) === "agent.started");
    const completed = [...events].reverse().find((item) => eventType(item) === "agent.completed");
    const latestStartedSequence = started ? started.sequence : 0;
    const latestCompletedSequence = completed ? completed.sequence : 0;
    const status = latestStartedSequence && latestCompletedSequence >= latestStartedSequence ? "COMPLETE" : latestStartedSequence ? "RUNNING" : "IDLE";
    const tools = events.filter((item) => eventType(item) === "tool.completed").length;
    const evidence = new Set(events.flatMap((item) => Array.isArray(item.payload && item.payload.evidence_ids) ? item.payload.evidence_ids : Array.isArray(item.payload && item.payload.result_evidence_ids) ? item.payload.result_evidence_ids : [])).size;
    const handoff = events.some((item) => eventType(item) === "agent.handoff");
    return { ...agentDefinition(id), status, tools, evidence, handoff };
  }

  function allAgentStates() {
    const ids = new Set(AGENT_DEFS.map((item) => item.id));
    state.events.forEach((event) => {
      if (eventType(event).startsWith("agent.") && event.actor && event.actor !== "orchestrator") ids.add(value(event.actor));
    });
    return [...ids].map(agentState);
  }

  function orchestratorStatus() {
    if (state.replaying) {
      return {
        label: "Replaying",
        raw: "RUNNING",
        detail: "Replaying the immutable investigation ledger",
      };
    }
    if (allAgentStates().some((item) => item.status === "RUNNING")) return { label: "Investigating", raw: "RUNNING", detail: "Three investigators are reading admitted evidence" };
    const lifecycleTypes = new Set([
      "investigation.started",
      "agent.started",
      "agent.completed",
      "tool.started",
      "tool.completed",
      "evidence.returned",
      "agent.handoff",
      "synthesis.started",
      "synthesis.completed",
      "evaluation.started",
      "evaluation.completed",
      "execution.started",
      "execution.completed",
      "verification.completed",
      "provider.degraded",
      "workflow.blocked",
    ]);
    const latest = [...state.events].reverse().find((item) => lifecycleTypes.has(eventType(item)));
    const latestType = eventType(latest);
    if (latestType === "verification.completed") return { label: "Verified", raw: "VERIFIED", detail: "Recovery verified by the API" };
    if (latestType === "evaluation.completed") return { label: "Ready for decision", raw: "COMPLETE", detail: "Evaluation returned; deterministic policy owns the next step" };
    if (latestType === "provider.degraded") return { label: "Advisory degraded", raw: "DEGRADED", detail: "The advisory result is visible; operational controls remain closed" };
    if (latestType === "workflow.blocked") return { label: "Stopped safely", raw: "BLOCKED", detail: "The deterministic workflow stopped without an effect" };
    if (latestType === "execution.started") return { label: "Recovering", raw: "RUNNING", detail: "Controlled execution is in progress" };
    if (["investigation.started", "agent.started", "agent.completed", "tool.started", "tool.completed", "evidence.returned", "agent.handoff", "synthesis.started", "synthesis.completed", "evaluation.started", "execution.completed"].includes(latestType)) {
      return { label: "Investigating", raw: "RUNNING", detail: "The event ledger is advancing the investigation" };
    }
    return { label: "Idle", raw: "IDLE", detail: "Start the investigation to launch the agents" };
  }

  function eventLabel(event) {
    const type = eventType(event);
    const payload = event.payload || {};
    const actor = event.actor && event.actor !== "orchestrator" ? agentDefinition(value(event.actor)).name : "Orchestrator";
    if (type === "incident.detected") return "Reconciliation gap detected";
    if (type === "investigation.started") return "Investigation started";
    if (type === "agent.started") return `${actor} started`;
    if (type === "agent.completed") return `${actor} completed`;
    if (type === "agent.handoff") return `${actor} handed evidence to synthesis`;
    if (type === "tool.started") return `${actor} called ${human(payload.tool || "read tool")}`;
    if (type === "tool.completed") return `${actor} received ${human(payload.tool || "tool result")}`;
    if (type === "evidence.returned") return `${actor} returned an evidence packet`;
    if (type === "synthesis.started") return "Synthesis started";
    if (type === "synthesis.completed") return "Synthesis selected a hypothesis";
    if (type === "evaluation.started") return "Evaluation started";
    if (type === "evaluation.completed") return `Evaluation ${human(event.status || payload.decision || "completed")}`;
    if (type === "copilot.message") return "Copilot answered from the investigation";
    if (type === "recovery.prepared") return "Recovery proposal prepared";
    if (type === "approval.requested") return "Two-role approval requested";
    if (type === "approval.recorded") return `${human(payload.role || "Role")} recorded approval`;
    if (type === "execution.started") return "Controlled recovery started";
    if (type === "execution.completed") return "Controlled recovery committed";
    if (type === "verification.completed") return "Fresh read verified the effect";
    if (type === "provider.degraded") return "Provider became degraded";
    if (type === "workflow.blocked") return "Workflow stopped safely";
    return human(type || "event");
  }

  function eventDetail(event) {
    const payload = event.payload || {};
    const type = eventType(event);
    if (type === "incident.detected") return `${number(payload.missing_quantity)} units stopped at the message queue.`;
    if (type === "tool.started") return `${number(event.sequence)} · read-only operation in progress`;
    if (type === "tool.completed") return `${(payload.result_evidence_ids || []).length} evidence IDs returned`;
    if (type === "evidence.returned") return `${(payload.evidence_ids || []).length} admitted IDs available to the workflow`;
    if (type === "agent.handoff") return `${(payload.evidence_ids || []).length} evidence IDs handed off`;
    if (type === "evaluation.completed") return value(payload.decision || event.status);
    if (type === "approval.recorded") return value(payload.principal_id || payload.role);
    if (type === "execution.completed") return "One effect recorded; executor returned a receipt.";
    if (type === "verification.completed") {
      const delta = Number.isInteger(payload.replay_effect_delta) ? payload.replay_effect_delta : "not proven";
      return `${number(payload.recorded_units)} / ${number(payload.expected_units)} units · replay delta ${delta}`;
    }
    if (type === "provider.degraded") return "The advisory path is visible; controlled actions remain deterministic.";
    return value(event.status || "recorded");
  }

  function shortTime(raw) {
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? "—" : parsed.toISOString().slice(11, 19);
  }

  function unitNodeId(unit) {
    if (value(unit.status) === "QUEUE_FAILED" || value(unit.current_stage) === "MESSAGE_QUEUE") return "message-queue";
    if (value(unit.current_stage) === "WAREHOUSE") return "warehouse";
    return "erp";
  }

  function renderUnitDetail() {
    const detailNode = $("unit-detail");
    if (!detailNode) return;
    const detail = state.units.get(state.selectedUnitId);
    detailNode.replaceChildren();
    if (!detail) {
      detailNode.append(create("span", "detail-placeholder", "Select a unit to inspect its authoritative record."));
      return;
    }
    const title = create("strong", "unit-detail-title", value(detail.unit_id));
    const fields = create("div", "unit-detail-fields");
    [["Stage", human(detail.current_stage)], ["State", human(detail.status)], ["Revision", value(detail.revision)], ["Message", detail.source_message_id || "No source message"]].forEach(([label, field]) => {
      const item = create("span", "unit-detail-field");
      item.append(create("small", null, label), create("strong", null, value(field)));
      fields.append(item);
    });
    detailNode.append(title, fields);
  }

  function renderHeader() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const incident = snapshot.incident || {};
    const counts = snapshot.unit_counts || {};
    const expected = number(incident.expected_quantity, number(counts.total));
    const recorded = number(incident.recorded_quantity, number(counts.erp_recorded));
    const missing = number(incident.missing_quantity, number(counts.queue_failed));
    const unit = incident.unit === "EA" ? "units" : value(incident.unit || "records");
    $("incident-title").textContent = missing ? `${missing} ${unit} stopped before ERP` : `All ${expected} ${unit} are accounted for`;
    $("incident-subtitle").textContent = state.replaying
      ? "Replaying the immutable investigation ledger; authoritative business state is not being changed."
      : missing
        ? "A message-queue exception is holding the invoice. Start the investigation to watch the exact records before any recovery."
        : "The controlled recovery is verified. The same incident session remains available for replay.";
    $("incident-id").textContent = `Incident ${value(snapshot.incident_id)}`;
    $("trace-id").textContent = `Trace ${value(snapshot.trace_id)}`;
    $("missing-count").textContent = String(missing);
    $("expected-count").textContent = String(expected);
    $("recorded-count").textContent = String(recorded);
    $("queue-count").textContent = String(missing);
    const heroLabel = document.querySelector(".hero-count span");
    if (heroLabel) heroLabel.textContent = missing ? "stopped at queue" : "verified in ERP";
    const mode = value(snapshot.mode);
    const execution = snapshot.execution || {};
    document.body.dataset.recovered = String(missing === 0 && execution.verified === true);
    const isScripted = mode === "SCRIPTED_SYNTHETIC";
    $("mode-label").textContent = isScripted ? "Scripted synthetic experiment" : human(mode || "Experiment");
    $("mode-detail").textContent = demoMode === "degraded"
      ? "Local API · advisory degraded; usefulness NOT_PROVEN"
      : isScripted
        ? "Local API · synthetic records only"
        : "Provider state from API";
    $("mode-dot").className = `status-dot ${isScripted ? "status-dot-lime" : "status-dot-cyan"}`;
    $("sequence-label").textContent = `seq ${state.lastSequence || number(snapshot.projection_sequence) || "—"}`;
  }

  function renderFlow() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const flow = snapshot.flow || { nodes: [], edges: [] };
    const map = $("flow-map");
    map.replaceChildren();
    const nodes = Array.isArray(flow.nodes) ? flow.nodes : [];
    const edges = Array.isArray(flow.edges) ? flow.edges : [];
    nodes.forEach((item, index) => {
      const column = create("div", "flow-column");
      const node = create("article", `flow-node ${stateClass(item.status)}`, null);
      node.dataset.nodeId = value(item.id);
      const header = create("div", "flow-node-header");
      const dot = create("span", "node-dot", null);
      dot.setAttribute("aria-hidden", "true");
      header.append(dot, create("span", "flow-node-label", value(item.label)));
      const badge = create("span", "state-badge", value(item.status));
      badge.classList.add(stateClass(item.status));
      header.append(badge);
      const count = create("strong", "flow-node-count", String(number(item.count)));
      const countLabel = create("span", "flow-node-count-label", "records");
      const cluster = create("div", "unit-cluster");
      cluster.dataset.nodeId = value(item.id);
      state.units.forEach((unit) => {
        if (unitNodeId(unit) !== value(item.id)) return;
        const entity = create("button", `unit-entity ${slug(unit.status)}${state.movingIds.has(unit.unit_id) ? " is-moving" : ""}`, value(unit.unit_id).split("-").pop());
        entity.type = "button";
        entity.dataset.unitId = value(unit.unit_id);
        entity.dataset.unitStatus = value(unit.status);
        entity.dataset.unitStage = value(unit.current_stage);
        entity.setAttribute("aria-label", `${value(unit.unit_id)}, ${human(unit.status)}, stage ${human(unit.current_stage)}`);
        entity.title = value(unit.unit_id);
        entity.addEventListener("click", () => {
          state.selectedUnitId = value(unit.unit_id);
          renderUnitDetail();
        });
        entity.addEventListener("animationend", () => {
          state.movingIds.delete(value(unit.unit_id));
          entity.classList.remove("is-moving");
        }, { once: true });
        cluster.append(entity);
      });
      node.append(header, count, countLabel, cluster);
      column.append(node);
      if (index < nodes.length - 1) {
        const next = nodes[index + 1];
        const edge = edges.find((candidate) => candidate.from === item.id && candidate.to === next.id);
        if (edge) {
          const link = create("div", `flow-link${state.activeEdges.has(`${edge.from}->${edge.to}`) ? " is-active" : ""}`);
          link.dataset.edge = `${edge.from}->${edge.to}`;
          link.append(create("span", "flow-link-line"));
          column.append(link);
        }
      }
      map.append(column);
    });
    const pathNode = nodes.find((item) => item.id === "message-queue");
    setBadge($("path-status"), pathNode ? (pathNode.status === "ANOMALY" ? "Attention needed" : pathNode.status) : "Waiting", pathNode ? pathNode.status : "IDLE");
    renderUnitDetail();
  }

  function renderAgentCard(item, compact) {
    const active = item.status === "RUNNING";
    const card = create("button", `agent-card${compact ? " agent-card-compact" : ""}${state.selectedAgentId === item.id ? " is-selected" : ""}`);
    card.type = "button";
    card.dataset.agentId = item.id;
    card.setAttribute("aria-label", `${item.name}, ${human(item.status)}`);
    const top = create("div", "agent-card-top");
    const mark = create("span", `agent-mark ${active ? "is-active" : ""}`, null);
    mark.setAttribute("aria-hidden", "true");
    top.append(mark, create("strong", "agent-card-name", item.name));
    const badge = create("span", `state-badge ${stateClass(item.status)}`, item.status === "IDLE" ? "WAITING" : item.status);
    top.append(badge);
    card.append(top, create("span", "agent-card-focus", item.focus));
    const stats = create("span", "agent-card-stats", `${item.tools} tools · ${item.evidence} evidence IDs${item.handoff ? " · handed off" : ""}`);
    card.append(stats);
    card.addEventListener("click", () => {
      state.selectedAgentId = state.selectedAgentId === item.id ? "" : item.id;
      renderAll();
    });
    return card;
  }

  function renderDashboardAgents() {
    const agents = allAgentStates();
    const dashboard = $("dashboard-agents");
    dashboard.replaceChildren();
    agents.forEach((item) => dashboard.append(renderAgentCard(item, true)));
    const active = agents.filter((item) => item.status === "RUNNING").length;
    setBadge($("active-agent-count"), `${active} active`, active ? "RUNNING" : "IDLE");
  }

  function renderAgentGraph() {
    const agents = allAgentStates();
    const container = $("agent-nodes");
    container.replaceChildren();
    agents.forEach((item) => container.append(renderAgentCard(item, false)));
    const links = $("agent-graph-links");
    links.replaceChildren();
    agents.forEach((item) => {
      const link = create("span", `agent-link${item.status === "RUNNING" ? " is-active" : ""}`);
      link.dataset.agentId = item.id;
      links.append(link);
    });
    const orchestration = orchestratorStatus();
    const pulse = document.querySelector(".node-pulse");
    if (pulse) pulse.classList.toggle("is-active", orchestration.raw === "RUNNING");
    setBadge($("orchestrator-status"), orchestration.label, orchestration.raw);
    $("orchestrator-detail").textContent = orchestration.detail;
    setBadge($("workspace-state"), orchestration.label, orchestration.raw);
    const operations = state.events.filter((item) => OPERATION_TYPES.has(eventType(item)) || ["copilot.message", "provider.degraded", "workflow.blocked"].includes(eventType(item)));
    $("operation-count").textContent = `${operations.length} records`;
    const feed = $("operation-feed");
    feed.replaceChildren();
    const filtered = state.selectedAgentId ? operations.filter((item) => item.actor === state.selectedAgentId || value(item.payload && item.payload.stage).startsWith(state.selectedAgentId)) : operations;
    filtered.slice(-18).reverse().forEach((item) => {
      const row = create("li", `operation-item operation-${slug(eventType(item))}`);
      const dot = create("span", `operation-dot ${stateClass(item.status)}`, null);
      dot.setAttribute("aria-hidden", "true");
      const copy = create("div", "operation-copy");
      copy.append(create("strong", null, eventLabel(item)), create("span", null, eventDetail(item)));
      const meta = create("span", "operation-meta", `#${value(item.sequence).padStart(2, "0")} · ${shortTime(item.occurred_at)}`);
      row.append(dot, copy, meta);
      feed.append(row);
    });
    if (!filtered.length) feed.append(create("li", "empty-state", "No agent operations yet. Start the investigation to see actual tools and handoffs."));
    renderEvidencePackets();
  }

  function renderEvidencePackets() {
    const container = $("evidence-packets");
    container.replaceChildren();
    const evidenceEvents = state.events.filter((item) => eventType(item) === "evidence.returned");
    const renderedIds = new Set();
    const durableEvidence = state.snapshot && Array.isArray(state.snapshot.evidence)
      ? state.snapshot.evidence
      : [];
    if (!evidenceEvents.length && !durableEvidence.length) return;
    const heading = create("div", "evidence-heading");
    heading.append(create("span", "panel-label", "EVIDENCE PACKETS"), create("span", "sequence-label", `${durableEvidence.length || evidenceEvents.length} returned`));
    container.append(heading);
    evidenceEvents.slice(-6).reverse().forEach((event) => {
      const ids = Array.isArray(event.payload && event.payload.evidence_ids) ? event.payload.evidence_ids : [];
      const card = create("article", "evidence-packet");
      const top = create("div", "evidence-packet-top");
      top.append(create("strong", null, agentDefinition(event.actor).name), create("span", "state-badge state-cyan", `${ids.length} IDs`));
      const list = create("div", "evidence-id-list");
      ids.slice(0, 5).forEach((id) => {
        renderedIds.add(value(id));
        const code = create("code", null, id);
        code.dataset.evidenceId = value(id);
        list.append(code);
      });
      card.append(top, list);
      container.append(card);
    });
    // Chat citations may point at a fresh-read evidence revision rather than the
    // initial investigator packet.  Keep every durable citation target rendered
    // so clicking a citation always lands on an actual DOM node.
    durableEvidence.forEach((item) => {
      const evidenceId = value(item && item.evidence_id);
      if (!evidenceId || renderedIds.has(evidenceId)) return;
      const card = create("article", "evidence-packet");
      card.dataset.evidenceId = evidenceId;
      const top = create("div", "evidence-packet-top");
      top.append(create("strong", null, human(item.source_type || "Authoritative record")), create("span", "state-badge state-cyan", "READ"));
      const list = create("div", "evidence-id-list");
      const code = create("code", null, evidenceId);
      code.dataset.evidenceId = evidenceId;
      list.append(code);
      card.append(top, list);
      container.append(card);
    });
  }

  function renderLatestEvent() {
    const latest = state.events[state.events.length - 1];
    const latestNode = $("latest-event");
    latestNode.replaceChildren();
    if (!latest) {
      latestNode.append(create("strong", null, "Waiting for the incident stream"), create("span", null, "Actual agent and tool events will appear here."));
      $("latest-event-sequence").textContent = "—";
      return;
    }
    latestNode.append(create("strong", null, eventLabel(latest)), create("span", null, eventDetail(latest)));
    $("latest-event-sequence").textContent = `#${value(latest.sequence).padStart(2, "0")}`;
  }

  function renderDashboard() {
    renderFlow();
    renderDashboardAgents();
    renderLatestEvent();
  }

  function renderInvestigationControls() {
    const complete = hasCompletedInvestigation() || state.replaying;
    const closed = incidentStatus() === "CLOSED";
    const started = state.startIssued || hasStartedInvestigation();
    const startAllowed = streamIsLive()
      && !state.startBusy
      && !state.replaying
      && demoMode !== "degraded"
      && !started
      && !complete
      && !closed;
    const startLabel = state.startBusy
      ? "Starting Investigation…"
      : started
        ? "Investigation in progress…"
        : "Start Investigation";
    const replayAllowed = complete && streamIsLive() && !state.startBusy && !state.replaying;
    ["dashboard-start-investigation", "agent-start-investigation"].forEach((id) => {
      const button = $(id);
      if (!button) return;
      button.hidden = complete || closed;
      button.textContent = startLabel;
      button.disabled = !startAllowed;
      button.setAttribute("aria-disabled", String(!startAllowed));
    });
    ["dashboard-replay-investigation", "agent-replay-investigation"].forEach((id) => {
      const button = $(id);
      if (!button) return;
      button.hidden = !complete;
      button.textContent = state.replaying ? "Replaying Investigation…" : "Replay Investigation";
      button.disabled = !replayAllowed;
      button.setAttribute("aria-disabled", String(!replayAllowed));
    });
    document.body.dataset.replaying = String(state.replaying);
  }

  async function startInvestigation() {
    const complete = hasCompletedInvestigation();
    if (
      state.startBusy
      || state.startIssued
      || !streamIsLive()
      || demoMode === "degraded"
      || state.replaying
      || complete
      || incidentStatus() === "CLOSED"
    ) return;
    state.startIssued = true;
    state.startBusy = true;
    state.commandError = "";
    renderAll();
    try {
      const response = await requestJSON(
        `/api/v1/incidents/${encodeURIComponent(state.incidentId)}/start`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: {} },
      );
      if (response && response.command === "investigation_already_complete") {
        await reconnectStream();
      }
    } catch (error) {
      state.startIssued = false;
      state.commandError = error.message;
      setConnection(state.connection, `Investigation could not start: ${error.message}`);
    } finally {
      state.startBusy = false;
      renderAll();
    }
  }

  function replayInvestigation() {
    if (!hasCompletedInvestigation() || !streamIsLive() || state.replaying) return;
    const initialEvents = state.events.filter((event) => eventType(event) === "incident.detected");
    if (!initialEvents.length) return;
    // The snapshot can lag the live ledger while the investigation is still
    // streaming.  The contiguous client cursor is authoritative for the trace
    // that is actually visible, so replay must drain through that cursor.
    const replayTargetSequence = Math.max(
      state.lastSequence,
      number(state.snapshot && state.snapshot.projection_sequence),
    );
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    state.events = initialEvents;
    state.lastSequence = Math.max(...initialEvents.map((event) => number(event.sequence)));
    state.replaying = true;
    state.replayTargetSequence = replayTargetSequence;
    state.startIssued = false;
    state.startBusy = false;
    state.chatMessages = [];
    state.chatHydrated = false;
    state.activeEdges.clear();
    state.movingIds.clear();
    setConnection("connecting", "Replaying the immutable investigation ledger.");
    renderAll();
    connectEvents();
  }

  function renderDecision() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const approval = snapshot.approval || {};
    const approvals = Array.isArray(snapshot.approvals) ? snapshot.approvals : [];
    const execution = snapshot.execution || {};
    const intent = value(approval.intent_id);
    const activeTool = value(approval.tool);
    const prepared = Boolean(intent && activeTool);
    const decisions = Array.isArray(snapshot.decisions) ? snapshot.decisions : [];
    const currentDecision = decisions.find((item) => item && item.eligibility === "PENDING_APPROVAL") || decisions[0] || null;
    const currentAction = value(currentDecision && currentDecision.allowed_action);
    const history = Array.isArray(approval.history) ? approval.history : [];
    const completedIntent = history
      .filter((item) => value(item.status) === "CONSUMED")
      .sort((a, b) => number(a.case_version) - number(b.case_version))
      .pop();
    const noAction = value(currentDecision && currentDecision.eligibility) === "NO_ACTION"
      || value(approval.decision_eligibility) === "NO_ACTION";
    const requiredRoles = Array.isArray(approval.required_roles) && approval.required_roles.length
      ? approval.required_roles.map((role) => value(role))
      : ROLE_DEFS.map((definition) => definition.role);
    const approvedRoles = new Set(
      approvals
        .filter((item) => value(item.intent_id) === intent && value(item.status) === "APPROVED")
        .map((item) => value(item.role))
        .filter((role) => requiredRoles.includes(role)),
    );
    const approvalCount = approvedRoles.size;
    const quorumApproved = prepared && value(approval.status) === "GRANTED" && approvalCount === requiredRoles.length;
    const hasExecution = prepared && state.events.some((event) => eventType(event) === "execution.completed" && value(event.payload && event.payload.tool) === activeTool);
    // ``execution.verified`` is an incident-level summary.  Once a new intent is
    // prepared (for example invoice release after receipt recovery), it must not
    // make that new action look verified by the completed receipt intent.
    const verified = Boolean(execution.verified) && (!prepared || hasExecution);
    const hasProposal = prepared;
    const hasApproval = quorumApproved;
    const steps = prepared
      ? { proposal: hasProposal, approval: hasApproval, execution: hasExecution, verification: hasExecution && verified }
      : { proposal: false, approval: false, execution: false, verification: false };
    Object.entries(steps).forEach(([name, done]) => {
      const node = document.querySelector(`[data-decision-step="${name}"]`);
      node.classList.toggle("is-done", done);
      node.classList.toggle("is-current", !done && (name === "proposal" || steps[Object.keys(steps)[Object.keys(steps).indexOf(name) - 1]]));
    });
    let status = "Not prepared";
    let rawStatus = "IDLE";
    if (verified && !prepared && completedIntent && noAction) { status = "VERIFIED · CLOSED"; rawStatus = "VERIFIED"; }
    else if (verified && !prepared && completedIntent) { status = "VERIFIED · NEXT ACTION PENDING"; rawStatus = "PENDING_APPROVAL"; }
    else if (verified && prepared) { status = "VERIFIED"; rawStatus = "VERIFIED"; }
    else if (hasExecution) { status = "RECOVERED"; rawStatus = "COMPLETE"; }
    else if (quorumApproved) { status = "APPROVED"; rawStatus = "GRANTED"; }
    else if (approvalCount) { status = `${approvalCount} of ${requiredRoles.length} approved`; rawStatus = "PENDING_APPROVAL"; }
    else if (prepared) { status = "Awaiting two roles"; rawStatus = "PENDING_APPROVAL"; }
    setBadge($("decision-status"), status, rawStatus);
    const intentNode = $("decision-intent");
    intentNode.replaceChildren();
    if (!prepared) {
      if (completedIntent) {
        intentNode.append(
          create("span", "intent-label", "COMPLETED ACTION INTENT"),
          create("strong", "intent-action", actionLabel(completedIntent.tool || "recovery")),
          create("span", "intent-meta", "Verified; approvals are not carried into the next action."),
        );
      }
      if (currentDecision && !noAction) {
        intentNode.append(
          create("span", "intent-label", completedIntent ? "NEXT ACTION — NOT PREPARED" : "CURRENT ACTION — NOT PREPARED"),
          create("strong", "intent-action", actionLabel(currentAction || "pending action")),
          create("span", "intent-meta", `Current deterministic decision · Case v${value(snapshot.case_version)}`),
        );
      } else if (!completedIntent) {
        intentNode.append(create("span", "detail-placeholder", "Prepare a recovery proposal after the investigation returns."));
      }
    } else {
      intentNode.append(create("span", "intent-label", "IMMUTABLE ACTION INTENT"), create("strong", "intent-action", actionLabel(activeTool)));
      const meta = create("div", "intent-meta");
      meta.append(create("span", null, intent), create("span", null, `Case v${value(snapshot.case_version)}`));
      intentNode.append(meta);
    }
    const roles = $("approval-roles");
    roles.replaceChildren();
    if (prepared) {
      ROLE_DEFS.forEach((definition) => {
        const approved = approvals.some((item) => value(item.intent_id) === intent && value(item.principal_id) === definition.principal && value(item.status) === "APPROVED");
        const card = create("div", `approval-role${approved ? " is-approved" : ""}`);
        const copy = create("div", "approval-role-copy");
        copy.append(create("strong", null, definition.name), create("span", null, definition.role));
        card.append(copy);
        if (approved) card.append(create("span", "state-badge state-lime", "APPROVED"));
        else {
          const button = create("button", "button button-approval", `Approve as ${definition.name}`);
          button.type = "button";
          button.disabled = state.commandBusy || !canOperate() || quorumApproved || (verified && hasExecution);
          button.dataset.approvalPrincipal = definition.principal;
          button.addEventListener("click", () => recordApproval(definition.principal));
          card.append(button);
        }
        roles.append(card);
      });
    }
    const prepareButton = $("prepare-button");
    prepareButton.textContent = noAction ? "No further action" : currentAction ? `Prepare ${actionLabel(currentAction)}` : "Prepare recovery";
    prepareButton.disabled = state.commandBusy || !canOperate() || prepared || !currentDecision || currentDecision.eligibility !== "PENDING_APPROVAL";
    const executeButton = $("execute-button");
    executeButton.disabled = state.commandBusy || !canOperate() || !quorumApproved || (verified && hasExecution);
    executeButton.hidden = Boolean(noAction && !prepared && completedIntent);
    if (state.commandError) {
      roles.append(create("p", "command-error", state.commandError));
    }
  }

  async function sendDecision(payload) {
    if (!state.incidentId || state.commandBusy || !canOperate()) return;
    state.commandBusy = true;
    state.commandError = "";
    renderDecision();
    try {
      const response = await requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}/decisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      applySnapshot(response, response.units, false);
      await queueRefresh();
    } catch (error) {
      state.commandError = error.message;
      setConnection(state.connection, `Command stopped safely: ${error.message}`);
    } finally {
      state.commandBusy = false;
      renderAll();
    }
  }

  function prepareRecovery() {
    const decisions = state.snapshot && Array.isArray(state.snapshot.decisions) ? state.snapshot.decisions : [];
    const decision = decisions.find((item) => item && item.eligibility === "PENDING_APPROVAL") || decisions[0];
    const tool = decision && decision.allowed_action;
    if (!tool) return;
    sendDecision({ command: "prepare_recovery", tool, idempotency_key: makeKey("prepare") });
  }

  function recordApproval(principal) {
    const intent = state.snapshot && state.snapshot.approval && state.snapshot.approval.intent_id;
    if (!intent) return;
    sendDecision({ command: "approve", intent_id: intent, principal_id: principal, idempotency_key: makeKey("approve") });
  }

  function executeRecovery() {
    const intent = state.snapshot && state.snapshot.approval && state.snapshot.approval.intent_id;
    if (!intent) return;
    sendDecision({ command: "execute", intent_id: intent, idempotency_key: makeKey("execute") });
  }

  function syncDurableChat() {
    if (state.chatHydrated) return;
    const replies = state.events.filter((item) => eventType(item) === "copilot.message");
    replies.forEach((event) => {
      state.chatMessages.push({ role: "assistant", message: value(event.payload && event.payload.message), citations: Array.isArray(event.payload && event.payload.citations) ? event.payload.citations : [] });
    });
    state.chatHydrated = true;
  }

  function renderChat() {
    syncDurableChat();
    const log = $("chat-log");
    log.replaceChildren();
    if (!state.chatMessages.length) {
      log.append(create("div", "chat-empty", "Ask where the units stopped, why the agents chose a cause, or which evidence supports it."));
    }
    state.chatMessages.slice(-12).forEach((item) => {
      const row = create("article", `chat-message chat-${item.role}`);
      row.append(create("span", "chat-role", item.role === "user" ? "YOU" : "COPILOT"), create("p", null, item.message));
      if (item.citations && item.citations.length) {
        const refs = create("div", "chat-citations");
        refs.append(create("span", "chat-citation-label", "Cites"));
        item.citations.slice(0, 6).forEach((citation) => {
          const button = create("button", "citation", citation);
          button.type = "button";
          button.addEventListener("click", () => focusEvidence(citation));
          refs.append(button);
        });
        row.append(refs);
      }
      log.append(row);
    });
    if (state.chatPending) log.append(create("div", "chat-message chat-assistant chat-pending", "The agents are reading the admitted records…"));
    const chatDisabled = demoMode === "degraded" || state.chatPending || state.replaying || !streamIsLive();
    $("chat-input").disabled = chatDisabled;
    $("chat-submit").disabled = chatDisabled;
    $("chat-input").setAttribute("aria-disabled", String(chatDisabled));
    $("chat-submit").setAttribute("aria-disabled", String(chatDisabled));
    document.querySelectorAll(".suggestion").forEach((button) => {
      button.disabled = chatDisabled;
    });
  }

  function focusEvidence(evidenceId) {
    const packet = [...document.querySelectorAll("[data-evidence-id]")]
      .find((node) => node.dataset.evidenceId === value(evidenceId));
    if (packet) {
      const card = packet.closest(".evidence-packet");
      card.classList.add("is-focused");
      card.scrollIntoView({ behavior: "smooth", block: "nearest" });
      window.setTimeout(() => card.classList.remove("is-focused"), 1800);
    }
  }

  async function askQuestion(question) {
    const textValue = value(question).trim();
    if (!textValue) {
      state.chatMessages.push({
        role: "assistant",
        message: "Enter a question about the incident; Copilot will only read and explain.",
        citations: [],
      });
      renderChat();
      return;
    }
    if (state.chatPending || !state.incidentId || state.replaying || !streamIsLive()) return;
    state.chatMessages.push({ role: "user", message: textValue, citations: [] });
    state.chatPending = true;
    renderChat();
    try {
      const response = await requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: { question: textValue, idempotency_key: makeKey("chat") } });
      state.chatMessages.push({ role: "assistant", message: value(response.message), citations: Array.isArray(response.citations) ? response.citations : [] });
      await queueRefresh();
    } catch (error) {
      state.chatMessages.push({ role: "assistant", message: `The read-only investigation stopped safely: ${error.message}`, citations: [] });
    } finally {
      state.chatPending = false;
      renderAll();
    }
  }

  function renderAgentView() {
    renderAgentGraph();
    renderDecision();
    renderChat();
  }

  function scheduleRender() {
    if (state.renderQueued) return;
    state.renderQueued = true;
    window.requestAnimationFrame(() => {
      state.renderQueued = false;
      renderAll();
    });
  }

  function renderAll() {
    if (!state.snapshot) return;
    applyModeVisibility();
    renderInvestigationControls();
    renderHeader();
    if (state.view === "agent") renderAgentView();
    else renderDashboard();
    $("dashboard-view").hidden = state.view !== "dashboard";
    $("agent-view").hidden = state.view !== "agent";
    bodyReady();
  }

  function bodyReady() {
    document.body.dataset.workspaceReady = state.loaded && state.units.size > 0 ? "true" : "false";
    $("unavailable").hidden = true;
  }

  async function bootstrap() {
    try {
      const listing = await requestJSON("/api/v1/incidents");
      const first = Array.isArray(listing.incidents) ? listing.incidents[0] : null;
      if (!first || !first.incident_id) throw new Error("No synthetic incident is available");
      const id = value(first.incident_id);
      const snapshotQuery = smokeCapture ? "?compact=1" : "";
      const [snapshot, units] = await Promise.all([
        requestJSON(`/api/v1/incidents/${encodeURIComponent(id)}${snapshotQuery}`),
        requestJSON(`/api/v1/incidents/${encodeURIComponent(id)}/units`),
      ]);
      if (demoMode === "invalid") {
        document.body.dataset.demoMode = "invalid";
        document.body.dataset.workspaceReady = "false";
        $("dashboard-view").hidden = true;
        $("agent-view").hidden = true;
        showUnavailable("The demo invalid mode has no admissible authoritative lifecycle evidence; operational claims are hidden.", true);
        setConnection("paused", "Invalid evidence; the workspace is unavailable.");
        return;
      }
      applySnapshot(snapshot, units.units, true);
      showUnavailable("", false);
      setView(state.view);
      if (!smokeCapture) connectEvents();
    } catch (error) {
      state.loaded = false;
      showUnavailable(error.message, true);
      setConnection("paused", `Incident unavailable: ${error.message}`);
      document.body.dataset.workspaceReady = "false";
    }
  }

  $("retry-button").addEventListener("click", () => {
    if (state.source) { state.source.close(); state.source = null; }
    state.streamError = "";
    if (state.loaded) {
      connectEvents();
      queueRefresh();
    } else bootstrap();
  });
  const viewTabs = [...document.querySelectorAll("[data-view]")];
  viewTabs.forEach((button, index) => {
    button.addEventListener("click", () => setView(button.dataset.view));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const nextIndex = event.key === "Home"
        ? 0
        : event.key === "End"
          ? viewTabs.length - 1
          : (index + (event.key === "ArrowRight" ? 1 : -1) + viewTabs.length) % viewTabs.length;
      const next = viewTabs[nextIndex];
      next.focus();
      setView(next.dataset.view);
    });
  });
  $("open-agent").addEventListener("click", () => setView("agent"));
  $("dashboard-to-agent").addEventListener("click", () => setView("agent"));
  $("dashboard-start-investigation").addEventListener("click", startInvestigation);
  $("agent-start-investigation").addEventListener("click", startInvestigation);
  $("dashboard-replay-investigation").addEventListener("click", replayInvestigation);
  $("agent-replay-investigation").addEventListener("click", replayInvestigation);
  $("prepare-button").addEventListener("click", prepareRecovery);
  $("execute-button").addEventListener("click", executeRecovery);
  $("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("chat-input");
    const question = input.value.trim();
    input.value = "";
    askQuestion(question);
  });
  document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => askQuestion(button.dataset.question)));

  window.addEventListener("beforeunload", () => {
    if (state.source) state.source.close();
    if (state.reconnectTimer != null) window.clearTimeout(state.reconnectTimer);
  });

  bootstrap();
})();
