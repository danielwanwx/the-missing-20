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
    "telemetry.observed",
    "source.condition.injected",
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
  const MAX_EVENT_HISTORY = 2000;
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
  const WORKSPACE_STATUSES = new Set([
    "MONITORING",
    "TRIGGERED",
    "INVESTIGATING",
    "WAITING FOR EVIDENCE",
    "HANDOFF",
    "COMPLETE",
    "DEGRADED",
  ]);
  const AGENT_DEFS = [
    {
      id: "retryable_message_investigator",
      name: "Receipt Retry",
      focus: "Queue evidence",
      role: "Receipt retry investigator",
      mission: "Trace the failed queue message and determine whether it can be safely retried.",
    },
    {
      id: "short_shipment_investigator",
      name: "Shipment Evidence",
      focus: "Physical evidence",
      role: "Shipment evidence investigator",
      mission: "Compare the physical shipment with the enterprise records to test for a short shipment.",
    },
    {
      id: "duplicate_posting_investigator",
      name: "Duplicate Posting",
      focus: "Posting integrity",
      role: "Duplicate posting investigator",
      mission: "Check existing postings and documents for a duplicate or already-recorded transaction.",
    },
  ];
  const ROLE_DEFS = [
    { role: "INTEGRATION_OPERATOR", principal: "integration-operator", name: "Integration operator" },
    { role: "AP_APPROVER", principal: "ap-approver", name: "AP approver" },
  ];
  // Stable Case Console identifiers are the only values used to dispatch a
  // command. Labels and assistant prose are display-only.
  const CASE_ACTION_DEFS = {
    continue_investigation: {
      label: "Continue investigation",
      kind: "start",
    },
    compare_causes: {
      label: "Compare causes",
      kind: "chat",
      question: "Compare the alternative hypotheses for this case.",
    },
    show_evidence: {
      label: "Show evidence",
      kind: "chat",
      question: "Show the evidence supporting the current case.",
    },
    explain_decision: {
      label: "Explain decision",
      kind: "chat",
      question: "Explain the evaluator result and deterministic next decision.",
    },
    prepare_recovery: {
      label: "Prepare recovery",
      kind: "decision",
    },
  };

  const state = {
    view: new URLSearchParams(window.location.search).get("view") === "agent"
      ? "agent"
      : new URLSearchParams(window.location.search).get("view") === "scenario"
        ? "scenario"
        : "dashboard",
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
    telemetry: [],
    telemetryPulse: false,
    telemetryPulseTimer: null,
    activeToolActors: new Set(),
    chatMessages: [],
    chatHydrated: false,
    chatPending: false,
    nextActions: [],
    caseActionStatus: "Waiting for a case",
    commandBusy: false,
    commandError: "",
    scenarioError: "",
    activeScenario: "incident",
    scenarioCatalog: null,
    liveSources: null,
    liveSourceEvents: [],
    liveSourceCursor: 0,
    liveSourceError: "",
    liveSourceTimer: null,
    liveSourceBusy: false,
    liveSourceRenderKey: "",
    liveSourceAnimatedSequences: new Map(),
    graphEventSequence: 0,
    activitySource: "Current stream",
    selectedPoint: null,
    selectedPointSequence: 0,
    focusedChartId: "",
    chartCursor: null,
    chartFocusEpoch: 0,
    chartFocusTimer: null,
    chartKeyListenerInstalled: false,
    chartPulseSequence: 0,
    recoveryAvailable: false,
    goldenRunning: false,
    rightRailTab: "context",
    focusedEvidenceId: "",
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

  function telemetryRecordCount(point) {
    if (!point || typeof point !== "object") return 0;
    return number(
      point.observed_record_count,
      number(point.batch_record_count, number(point.window_record_count, number(point.throughput_units))),
    );
  }

  function slug(raw) {
    return value(raw).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  }

  function human(raw) {
    return value(raw).replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function countLabel(rawCount, singular, plural = `${singular}s`) {
    const count = number(rawCount);
    return `${count} ${count === 1 ? singular : plural}`;
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
    if (["HEALTHY", "MONITORING", "COMPLETE", "COMPLETED", "PASS", "GRANTED", "APPROVED", "ERP_RECORDED", "VERIFIED"].includes(status)) {
      return "state-lime";
    }
    if (["RUNNING", "TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "STARTED", "ADMITTED", "HANDED_OFF", "HANDOFF", "SCRIPTED_SYNTHETIC_PROOF"].includes(status)) {
      return "state-cyan";
    }
    if (["ANOMALY", "QUEUE_FAILED", "PARTIAL", "HELD", "FAILED", "BLOCKED", "DEGRADED", "NOT_PROVEN", "NOT PROVEN", "PENDING_APPROVAL"].includes(status)) {
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
    $("footer-status").textContent = detail || (connection === "live" ? "Ledger connected." : "Live movement paused.");
    $("live-heartbeat").textContent = connection === "live" ? "Connected" : connection === "connecting" ? "Connecting" : "Paused";
    document.body.dataset.connection = connection;
  }

  function streamIsLive() {
    return state.connection === "live";
  }

  function incidentStatus() {
    return value(state.snapshot && state.snapshot.incident && state.snapshot.incident.status);
  }

  function isVerifiedClosedRecovery() {
    const snapshot = state.snapshot || {};
    const incidentState = value(snapshot.incident && snapshot.incident.status).toUpperCase();
    return (incidentState === "CLOSED" || state.activeScenario === "recovery")
      && Boolean(snapshot.execution && snapshot.execution.verified);
  }

  function isClosedOrRecovery() {
    return value(state.snapshot && state.snapshot.incident && state.snapshot.incident.status).toUpperCase() === "CLOSED"
      || state.activeScenario === "recovery";
  }

  function advisoryContext() {
    const advisory = state.snapshot && state.snapshot.advisory;
    const advisoryStage = advisory && advisory.advisory_stage;
    const deterministic = state.snapshot && state.snapshot.deterministic_decision;
    const hypotheses = advisory && Array.isArray(advisory.hypotheses) ? advisory.hypotheses : [];
    const selectedHypothesis = value(
      advisory && advisory.selected_hypothesis
        || advisory && advisory.synthesis && advisory.synthesis.selected_hypothesis
        || advisoryStage && advisoryStage.synthesis && advisoryStage.synthesis.selected_hypothesis
        || hypotheses.find((item) => value(item && item.conclusion).toUpperCase() === "SUPPORTED")?.hypothesis_type
        || deterministic && deterministic.classification,
    ).toUpperCase();
    const status = value(advisory && advisory.status || advisoryStage && advisoryStage.status).toUpperCase();
    const warnings = [
      ...(Array.isArray(advisory && advisory.warnings) ? advisory.warnings : []),
      ...(Array.isArray(advisoryStage && advisoryStage.warnings) ? advisoryStage.warnings : []),
    ].map((item) => value(item).toUpperCase());
    const coverage = value(
      advisory && advisory.ai_coverage && advisory.ai_coverage.coverage
        || advisoryStage && advisoryStage.ai_coverage && advisoryStage.ai_coverage.coverage,
    );
    return {
      partial: status === "PARTIAL" || warnings.includes("AI_CITATION_CLOSURE_INCOMPLETE"),
      selectedHypothesis,
      warning: warnings.includes("AI_CITATION_CLOSURE_INCOMPLETE")
        ? "AI_CITATION_CLOSURE_INCOMPLETE"
        : "",
      coverage,
    };
  }

  function renderAdvisoryTruth(host, advisory) {
    const existing = host.querySelector(".advisory-truth");
    if (existing) existing.remove();
    if (!advisory.partial) return;
    const source = state.snapshot && state.snapshot.advisory ? state.snapshot.advisory : {};
    const catalog = source.authoritative_catalog && Array.isArray(source.authoritative_catalog.evidence_ids)
      ? source.authoritative_catalog.evidence_ids
      : Array.isArray(state.snapshot?.deterministic_decision?.authoritative_evidence_ids)
        ? state.snapshot.deterministic_decision.authoritative_evidence_ids
        : [];
    const closure = source.evaluator_citation_closure && Array.isArray(source.evaluator_citation_closure.validated_evidence_ids)
      ? source.evaluator_citation_closure.validated_evidence_ids
      : Array.isArray(source.ai_coverage?.covered_evidence_ids)
        ? source.ai_coverage.covered_evidence_ids
        : [];
    const total = catalog.length || 5;
    const cited = Math.min(closure.length, total);
    const panel = create("div", "advisory-truth");
    panel.append(
      create("span", null, `Nova advisory: PARTIAL — cited ${cited}/${total} admitted records`),
      create("span", null, `Application validation: ${total}/${total} authoritative records`),
      create("span", null, "Recovery authority: deterministic controls only"),
    );
    host.append(panel);
  }

  function hasStartedInvestigation() {
    return state.events.some((event) => eventType(event) === "investigation.started");
  }

  function hasCompletedInvestigation() {
    return state.events.some((event) => eventType(event) === "evaluation.completed");
  }

  function hasIncidentDetected() {
    return state.events.some((event) => eventType(event) === "incident.detected");
  }

  function isNormalScenario() {
    const operationalState = value(state.snapshot && state.snapshot.operational_state).toUpperCase();
    return !hasIncidentDetected()
      && (state.activeScenario === "normal" || operationalState === "NORMAL");
  }

  function authoritativeScenarioState() {
    const listing = state.scenarioCatalog;
    const scenarios = listing && Array.isArray(listing.scenarios) ? listing.scenarios : [];
    const currentId = value(listing && listing.current);
    const normal = scenarios.find((item) => value(item && item.id) === "normal") || null;
    const incident = scenarios.find((item) => value(item && item.id) === "incident") || null;
    const recovery = scenarios.find((item) => value(item && item.id) === "recovery") || null;
    const current = scenarios.find((item) => (
      value(item && item.incident_id) === currentId
      || value(item && item.id) === currentId
    )) || null;
    const currentScenario = value(current && current.id);
    const recoveryReadyForCurrent = Boolean(
      recovery
      && value(recovery.status).toUpperCase() === "READY"
      && value(recovery.incident_id) === currentId,
    );
    const snapshot = state.snapshot || {};
    const snapshotIsCurrent = value(snapshot.incident_id) === currentId;
    const snapshotIsClosedVerified = snapshotIsCurrent
      && value(snapshot.incident && snapshot.incident.status).toUpperCase() === "CLOSED"
      && snapshot.execution && snapshot.execution.verified === true;
    const historicalIncident = current && ["incident", "golden"].includes(currentScenario)
      && (recoveryReadyForCurrent || snapshotIsClosedVerified)
      ? current
      : null;
    const activeIncident = current && ["incident", "golden"].includes(currentScenario)
      && value(current && current.status).toUpperCase() === "ACTIVE"
      && !historicalIncident
      ? current
      : null;
    const incidentTransitionAllowed = Boolean(
      normal
      && incident
      && currentScenario === "normal"
      && value(incident.status).toUpperCase() === "READY",
    );
    return {
      listing,
      scenarios,
      normal,
      incident,
      recovery,
      current,
      currentId,
      activeIncident,
      historicalIncident,
      incidentTransitionAllowed,
    };
  }

  function advisoryTerminallyDegraded() {
    return state.events.some((event) => eventType(event) === "provider.degraded");
  }

  function setScenarioCatalog(listing) {
    state.scenarioCatalog = listing;
    const scenarios = listing && Array.isArray(listing.scenarios) ? listing.scenarios : [];
    const recovery = scenarios.find((item) => value(item && item.id) === "recovery");
    state.recoveryAvailable = value(recovery && recovery.status).toUpperCase() === "READY";
    const currentId = value(listing && listing.current);
    const requestedIncidentId = value(new URLSearchParams(window.location.search).get("incident_id"));
    // A deep-linked persisted case is intentionally allowed to remain visible
    // while the catalog points at another current session.  Otherwise the
    // Scenario Lab would silently paint a different case over the URL.
    if (!requestedIncidentId || requestedIncidentId === currentId) {
      const current = scenarios.find((item) => (
        value(item && item.incident_id) === currentId
        || value(item && item.id) === currentId
      ));
      if (current && current.id) {
        state.activeScenario = value(current.id) === "golden" ? "incident" : value(current.id);
      }
    }
  }

  function scenarioTruthSummary() {
    const listing = state.scenarioCatalog;
    const currentId = value(listing && listing.current) || state.activeScenario;
    const scenarios = listing && Array.isArray(listing.scenarios) ? listing.scenarios : [];
    const current = scenarios.find((item) => (
      value(item && item.incident_id) === currentId
      || value(item && item.id) === currentId
    ));
    return current && current.label
      ? `${current.label} (${value(current.incident_id)})`
      : human(currentId || "unknown");
  }

  function scenarioForSnapshot(snapshot) {
    const snapshotId = value(snapshot && snapshot.incident_id);
    const incident = snapshot && snapshot.incident && typeof snapshot.incident === "object"
      ? snapshot.incident
      : {};
    const operationalState = value(snapshot && snapshot.operational_state).toUpperCase();
    const incidentState = value(incident.status).toUpperCase();
    if (operationalState === "NORMAL" || incidentState === "NORMAL" || snapshotId === "missing-20-normal") {
      return "normal";
    }
    if (incidentState === "CLOSED" && snapshot && snapshot.execution && snapshot.execution.verified === true) {
      return "recovery";
    }
    const params = new URLSearchParams(window.location.search);
    const requestedScenario = value(params.get("scenario"));
    const requestedIncidentId = value(params.get("incident_id"));
    if (requestedIncidentId && requestedScenario === "incident" && snapshotId === requestedIncidentId) {
      return "incident";
    }
    const scenarios = state.scenarioCatalog && Array.isArray(state.scenarioCatalog.scenarios)
      ? state.scenarioCatalog.scenarios
      : [];
    const catalogMatch = scenarios.find((item) => value(item && item.incident_id) === snapshotId);
    if (catalogMatch && catalogMatch.id) {
      return value(catalogMatch.id) === "golden" ? "incident" : value(catalogMatch.id);
    }
    if (requestedScenario === "recovery" && requestedIncidentId === snapshotId) return "recovery";
    return "incident";
  }

  function liveSourceStatusClass(raw) {
    const status = value(raw).toUpperCase();
    if (status === "CONNECTED") return "is-connected";
    if (status === "STALE") return "is-stale";
    if (status === "DEGRADED") return "is-degraded";
    return "is-optional";
  }

  function liveSourceStatusLabel(raw) {
    const labels = {
      CONNECTED: "Connected",
      STALE: "Stale",
      DEGRADED: "Degraded",
      OPTIONAL_NOT_CONFIGURED: "Optional",
    };
    return labels[value(raw).toUpperCase()] || "Waiting";
  }

  function liveSourceIcon(sourceType) {
    const icons = {
      weather_alerts: "warning",
      water_level: "waves",
      vessel_positions: "boat",
    };
    return icons[value(sourceType)] || "broadcast";
  }

  function liveSourceDisplayName(source) {
    const labels = {
      weather_alerts: "NWS",
      water_level: "NOAA",
      vessel_positions: "AIS",
    };
    return labels[value(source && source.source_type)] || value(source && source.provider) || "Route source";
  }

  function liveSourceValue(source) {
    const metrics = source && source.metrics && typeof source.metrics === "object"
      ? source.metrics
      : {};
    const type = value(source && source.source_type);
    if (type === "weather_alerts") {
      const routeAlerts = metrics.route_alerts == null ? metrics.active_alerts : metrics.route_alerts;
      return `${number(routeAlerts)} route alerts`;
    }
    if (type === "water_level") return `${number(metrics.water_level_m).toFixed(2)} m`;
    if (type === "vessel_positions") return `${number(metrics.vessel_count)} vessels`;
    return "No new data";
  }

  function liveSourceFreshness(source) {
    const age = source && source.freshness_seconds;
    if (age == null) return "No observation";
    const seconds = number(age);
    if (value(source && source.source_type) === "weather_alerts") {
      if (seconds < 60) return "Alert updated just now";
      if (seconds < 3600) return `${Math.floor(seconds / 60)}m since alert`;
      return `${Math.floor(seconds / 3600)}h since alert`;
    }
    if (seconds < 60) return "Just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m old`;
    return `${Math.floor(seconds / 3600)}h old`;
  }

  function liveSourceIdentity(source, index = 0) {
    return value(
      source && (source.source_id || source.source_type || source.provider),
    ) || `source-${index}`;
  }

  function liveSourcePayloadKey(payload) {
    const sources = payload && Array.isArray(payload.sources) ? payload.sources : [];
    const sourceKey = sources.map((source, index) => {
      const metrics = source && source.metrics && typeof source.metrics === "object"
        ? source.metrics
        : {};
      return [
        liveSourceIdentity(source, index),
        value(source && source.source_type),
        value(source && source.status),
        value(source && source.observed_at),
        value(source && source.sequence),
        value(source && source.freshness_seconds),
        JSON.stringify(metrics),
        value(source && source.error),
        String(Boolean(source && source.new_observation)),
      ].join("\u241f");
    }).sort().join("\u241e");
    const risk = payload && payload.risk && typeof payload.risk === "object" ? payload.risk : {};
    const cursor = payload && (payload.event_cursor ?? payload.sequence);
    return [
      value(cursor),
      sourceKey,
      value(risk.level),
      value(risk.label),
      JSON.stringify(Array.isArray(risk.reasons) ? risk.reasons : []),
      state.liveSourceError,
    ].join("\u241d");
  }

  function liveSourceDisclosureState(host) {
    const open = new Map();
    host.querySelectorAll(".live-source-card").forEach((card) => {
      const sourceId = value(card.dataset.liveSourceId);
      const details = card.querySelector("details");
      if (sourceId && details) open.set(sourceId, details.open);
    });
    return open;
  }

  function renderLiveSources() {
    const payload = state.liveSources;
    const sources = payload && Array.isArray(payload.sources) ? payload.sources : [];
    const risk = payload && payload.risk && typeof payload.risk === "object" ? payload.risk : null;
    const hosts = ["dashboard-live-sources"]
      .map((id) => $(id))
      .filter((host) => host);
    const workspaceHost = $("workspace-live-sources");
    if (!hosts.length && !workspaceHost) return;
    const renderKey = liveSourcePayloadKey(payload);
    const needsMount = hosts.some((host) => host.dataset.liveSourcesMounted !== "true")
      || Boolean(workspaceHost && workspaceHost.dataset.liveSourcesMounted !== "true");
    if (!needsMount && renderKey === state.liveSourceRenderKey) return;
    state.liveSourceRenderKey = renderKey;
    const pulseBySource = new Map();
    sources.forEach((source, index) => {
      const sourceId = liveSourceIdentity(source, index);
      const sequence = value(
        source && source.sequence != null
          ? source.sequence
          : payload && (payload.event_cursor ?? payload.sequence),
      );
      const animationKey = `${sourceId}:${sequence}`;
      const shouldPulse = Boolean(source && source.new_observation)
        && animationKey !== value(state.liveSourceAnimatedSequences.get(sourceId));
      pulseBySource.set(sourceId, shouldPulse);
      if (shouldPulse) state.liveSourceAnimatedSequences.set(sourceId, animationKey);
    });
    ["live-route-risk", "workspace-live-route-risk"].forEach((id) => {
      const node = $(id);
      if (!node) return;
      const riskLevel = value(risk && risk.level).toUpperCase();
      const riskLabel = risk
        ? value(risk.label || (riskLevel === "LOW" ? "No route risk" : "Route watch"))
        : state.liveSourceError ? "Unavailable" : "Waiting";
      setBadge(node, riskLabel, riskLevel === "HIGH" ? "DEGRADED" : riskLevel === "WATCH" ? "PARTIAL" : riskLevel || "IDLE");
      if (risk && Array.isArray(risk.reasons) && risk.reasons.length) node.title = risk.reasons.join("; ");
      else if (state.liveSourceError) node.title = state.liveSourceError;
      else node.removeAttribute("title");
    });
    hosts.forEach((host) => {
      const disclosure = liveSourceDisclosureState(host);
      host.replaceChildren();
      if (!sources.length) {
        host.append(create("div", "live-source-empty", state.liveSourceError || "Waiting for public route signals"));
        const emptyDetector = create("div", "route-risk-detector is-waiting");
        emptyDetector.dataset.routeRiskDetector = "true";
        emptyDetector.append(
          create("i", "ph ph-shield-warning", null),
          create("strong", null, "Route-risk detector"),
          create("small", null, state.liveSourceError ? "Unavailable" : "Waiting"),
        );
        host.append(emptyDetector);
        host.dataset.liveSourcesMounted = "true";
        return;
      }
      sources.forEach((source, index) => {
        const status = value(source && source.status).toUpperCase();
        const sourceId = liveSourceIdentity(source, index);
        const card = create("article", `live-source-card route-source-node ${liveSourceStatusClass(status)}${pulseBySource.get(sourceId) ? " is-new" : ""}`);
        card.dataset.liveSourceId = sourceId;
        card.dataset.sourceType = value(source && source.source_type);
        const top = create("div", "live-source-card-top");
        const icon = create("span", "live-source-icon");
        icon.append(create("i", `ph ph-${liveSourceIcon(source && source.source_type)}`));
        top.append(icon, create("strong", "live-source-name", liveSourceDisplayName(source)), create("span", "live-source-dot"));
        const valueRow = create("div", "live-source-value");
        valueRow.append(create("strong", null, liveSourceValue(source)), create("span", null, liveSourceStatusLabel(status)));
        const meta = create("div", "live-source-meta");
        meta.append(create("span", null, liveSourceFreshness(source)), create("span", null, value(source && source.location)));
        const details = document.createElement("details");
        const summary = document.createElement("summary");
        summary.textContent = "Details";
        const detail = create("div", "live-source-detail");
        detail.append(create("div", null, `Observed ${value(source && source.observed_at) || "—"}`));
        detail.append(create("div", null, `Received ${value(source && source.received_at) || "—"}`));
        if (source && source.error) detail.append(create("div", null, `Status: ${value(source.error)}`));
        const link = document.createElement("a");
        link.href = value(source && source.provenance_url) || "#";
        link.target = "_blank";
        link.rel = "noreferrer";
        link.textContent = "Official source";
        detail.append(link);
        details.append(summary, detail);
        details.open = disclosure.get(sourceId) === true;
        card.append(top, valueRow, meta, details);
        host.append(card);
      });
      const riskLevel = value(risk && risk.level).toUpperCase();
      const detector = create("div", `route-risk-detector${riskLevel === "HIGH" ? " is-alert" : riskLevel === "WATCH" ? " is-watch" : ""}`);
      detector.dataset.routeRiskDetector = "true";
      detector.append(
        create("i", `ph ${riskLevel === "HIGH" ? "ph-warning" : "ph-shield-check"}`, null),
        create("strong", null, "Route-risk detector"),
        create("small", null, risk
          ? value(risk.label || (riskLevel === "LOW" ? "Advisory context" : "Route watch"))
          : state.liveSourceError ? "Unavailable" : "Waiting"),
      );
      host.append(detector);
      host.dataset.liveSourcesMounted = "true";
    });
    if (workspaceHost) {
      // The workspace already contains the detailed source cards on Dashboard.
      // Keep one compact incident-relevant ribbon here so the graph stays the
      // visual center and the same server-owned cursor remains visible without
      // repeating the entire source report.
      workspaceHost.replaceChildren();
      const ribbon = create("div", "workspace-route-ribbon");
      const latest = sources.find((source) => value(source && source.status).toUpperCase() !== "UNAVAILABLE") || sources[0];
      const routeCopy = risk && Array.isArray(risk.reasons) && risk.reasons.length
        ? value(risk.reasons[0])
        : latest
          ? `${value(latest.provider || "Route source")} · ${liveSourceFreshness(latest)}`
          : state.liveSourceError || "Waiting for route observations";
      ribbon.append(
        create("span", "workspace-route-ribbon-dot"),
        create("strong", null, routeCopy),
      );
      const link = document.createElement("a");
      link.href = "/?view=dashboard#external-risk-title";
      link.textContent = "Open route timeline";
      ribbon.append(link);
      workspaceHost.append(ribbon);
      workspaceHost.dataset.liveSourcesMounted = "true";
    }
  }

  async function refreshLiveSources() {
    if (state.liveSourceBusy) return;
    state.liveSourceBusy = true;
    try {
      // The summary and event feed share one server-owned source cursor.  The
      // dashboard only adds a timeline observation when that cursor advances;
      // repeated renders therefore cannot manufacture motion or replay pulses.
      const [summary, eventPayload] = await Promise.all([
        requestJSON("/api/v1/live-sources"),
        requestJSON(`/api/v1/live-sources/events?after=${state.liveSourceCursor}`),
      ]);
      state.liveSources = summary;
      const events = eventPayload && Array.isArray(eventPayload.events)
        ? eventPayload.events
        : [];
      const known = new Set(state.liveSourceEvents.map((item) => `${item.source_id}:${item.sequence}`));
      events.forEach((event) => {
        const key = `${value(event && event.source_id)}:${value(event && event.sequence)}`;
        if (!known.has(key)) {
          state.liveSourceEvents.push(event);
          known.add(key);
        }
      });
      if (state.liveSourceEvents.length > 96) {
        state.liveSourceEvents = state.liveSourceEvents.slice(-96);
      }
      state.liveSourceCursor = Math.max(
        state.liveSourceCursor,
        number(eventPayload && eventPayload.cursor),
        number(summary && (summary.event_cursor ?? summary.sequence)),
      );
      state.liveSourceError = "";
    } catch (error) {
      state.liveSourceError = error.message;
    } finally {
      state.liveSourceBusy = false;
      // Source cards and the route-risk diagram share the same server-owned
      // observation feed.  Redraw the diagram after the feed resolves so a
      // first source response cannot leave a stale "waiting" canvas behind.
      if (state.snapshot) renderOperationalCharts(state.snapshot);
      renderLiveSources();
    }
  }

  function scheduleLiveSourceRefresh() {
    if (smokeCapture || state.liveSourceTimer != null) return;
    state.liveSourceTimer = window.setTimeout(() => {
      state.liveSourceTimer = null;
      refreshLiveSources().finally(scheduleLiveSourceRefresh);
    }, 15000);
  }

  function startLiveSourceRefresh() {
    if (smokeCapture || state.liveSourceTimer != null) return;
    refreshLiveSources();
    scheduleLiveSourceRefresh();
  }

  async function refreshScenarioCatalog() {
    try {
      setScenarioCatalog(await requestJSON("/api/v1/scenarios"));
      renderScenarioControls();
    } catch (_error) {
      // The current incident remains authoritative if the catalog is briefly
      // unavailable.  Keep the last durable Recovery availability instead of
      // inferring it from the snapshot currently on screen.
    }
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
    ["tab-agent"].forEach((id) => {
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
    state.graphEventSequence = state.lastSequence;
    state.activitySource = ordered.length ? "Persisted ledger" : "Current stream";
    state.telemetry = ordered
      .filter((item) => eventType(item) === "telemetry.observed")
      .slice(-24)
      .map((item) => ({
        sequence: item.sequence,
        observed_at: item.occurred_at,
        ...(item.payload || {}),
      }));
    state.activeEdges.clear();
    const latestVisualEvent = [...ordered].reverse().find((item) => [
      "telemetry.observed",
      "source.condition.injected",
      "incident.detected",
      "execution.started",
      "execution.completed",
      "verification.completed",
    ].includes(eventType(item)));
    if (latestVisualEvent) markFlowEdgesForEvent(eventType(latestVisualEvent), latestVisualEvent.payload || {});
  }

  function pulseTelemetry() {
    // The timer only removes a visual pulse. A new pulse can only be started by
    // an accepted telemetry event from the ordered SSE ledger.
    state.telemetryPulse = true;
    if (state.telemetryPulseTimer != null) window.clearTimeout(state.telemetryPulseTimer);
    state.telemetryPulseTimer = window.setTimeout(() => {
      state.telemetryPulseTimer = null;
      state.telemetryPulse = false;
      scheduleRender();
    }, 3600);
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
    // Scenario identity is a control-plane fact.  Counts alone cannot tell us
    // whether an empty queue is a healthy Normal session or a verified Recovery
    // session, so never infer the selected button from 100/100 numbers.
    state.activeScenario = scenarioForSnapshot(snapshot);
    state.units = nextUnits;
    if (initial) mergeInitialEvents(snapshot.events || snapshot.activity);
    if (initial && state.telemetry.length) pulseTelemetry();
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

  function markFlowEdgesForEvent(type, payload = {}) {
    const edges = [
      "warehouse->message-queue",
      "message-queue->erp",
      "erp->invoice",
    ];
    if (type === "telemetry.observed") {
      const counts = payload.unit_counts && typeof payload.unit_counts === "object"
        ? payload.unit_counts
        : payload;
      const backlog = number(counts.queue_failed, number(payload.queue_depth));
      const recorded = number(counts.erp_recorded, number(payload.recorded_quantity));
      state.activeEdges.add("warehouse->message-queue");
      if (backlog > 0 || recorded > 0) state.activeEdges.add("message-queue->erp");
      if (recorded > 0 && backlog === 0) state.activeEdges.add("erp->invoice");
      return;
    }
    if (type === "incident.detected" || type === "source.condition.injected") {
      state.activeEdges.add("warehouse->message-queue");
      return;
    }
    if (["execution.started", "execution.completed", "verification.completed"].includes(type)) {
      edges.forEach((edge) => state.activeEdges.add(edge));
    }
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
      await refreshScenarioCatalog();
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
    state.graphEventSequence = sequence;
    if (state.activitySource !== "Persisted ledger") state.activitySource = "Current stream";
    state.events.push({ ...event, sequence, event_type: type });
    if (state.events.length > MAX_EVENT_HISTORY) state.events.shift();
    state.activeEdges.clear();
    markFlowEdgesForEvent(type, event.payload || {});
    if (type === "telemetry.observed") {
      state.telemetry.push({
        sequence,
        observed_at: event.occurred_at,
        ...(event.payload || {}),
      });
      if (state.telemetry.length > 24) state.telemetry.shift();
      pulseTelemetry();
    }
    if (type === "tool.started" && event.actor) state.activeToolActors.add(value(event.actor));
    if (type === "tool.completed" && event.actor) state.activeToolActors.delete(value(event.actor));
    if (["agent.completed", "workflow.blocked", "verification.completed"].includes(type) && event.actor) {
      state.activeToolActors.delete(value(event.actor));
    }
    if (type === "execution.started") state.activeEdges.add("message-queue->erp");
    if (state.goldenRunning && type === "evaluation.completed") {
      // Evaluation is the terminal event for a fresh Golden Incident.  The
      // event itself, rather than a UI timer, owns the button's idle state.
      state.goldenRunning = false;
    }
    $("sequence-label").textContent = `seq ${state.lastSequence}`;
    scheduleRender();
    if (["execution.completed", "verification.completed"].includes(type)) {
      queueRefresh();
      refreshScenarioCatalog();
    }
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
    state.goldenRunning = false;
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
    const allowedViews = new Set(["dashboard", "agent", "scenario"]);
    state.view = demoMode === "degraded"
      ? "dashboard"
      : allowedViews.has(view)
        ? view
        : "dashboard";
    document.body.dataset.view = state.view;
    const query = new URLSearchParams(window.location.search);
    query.set("view", state.view);
    window.history.replaceState(null, "", `/?${query.toString()}`);
    $("dashboard-view").hidden = state.view !== "dashboard";
    $("agent-view").hidden = state.view !== "agent";
    $("scenario-view").hidden = state.view !== "scenario";
    document.querySelectorAll("[data-view]").forEach((tab) => {
      const selected = tab.dataset.view === state.view;
      tab.classList.toggle("is-selected", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    window.scrollTo(0, 0);
    renderAll();
    renderLiveSources();
  }

  function replaceSession(snapshot, scenario) {
    if (state.source) {
      state.source.close();
      state.source = null;
    }
    if (state.reconnectTimer != null) {
      window.clearTimeout(state.reconnectTimer);
      state.reconnectTimer = null;
    }
    state.snapshot = null;
    state.units = new Map();
    state.events = [];
    state.lastSequence = 0;
    state.graphEventSequence = 0;
    state.selectedUnitId = "";
    state.selectedAgentId = "";
    state.activeEdges.clear();
    state.activeToolActors.clear();
    state.telemetry = [];
    state.selectedPoint = null;
    state.selectedPointSequence = 0;
    state.focusedChartId = "";
    state.chartCursor = null;
    state.chartFocusEpoch += 1;
    if (state.chartFocusTimer != null) {
      window.clearTimeout(state.chartFocusTimer);
      state.chartFocusTimer = null;
    }
    state.chartPulseSequence = 0;
    state.rightRailTab = "context";
    state.focusedEvidenceId = "";
    state.telemetryPulse = false;
    if (state.telemetryPulseTimer != null) {
      window.clearTimeout(state.telemetryPulseTimer);
      state.telemetryPulseTimer = null;
    }
    state.chatMessages = [];
    state.chatHydrated = false;
    state.startIssued = false;
    state.startBusy = false;
    state.nextActions = [];
    state.caseActionStatus = "Waiting for a case";
    state.replaying = false;
    state.replayTargetSequence = 0;
    state.activeScenario = scenario === "golden" ? "incident" : scenario;
    state.goldenRunning = scenario === "golden";
    const sessionQuery = new URLSearchParams(window.location.search);
    sessionQuery.set("scenario", scenario === "golden" ? "incident" : scenario);
    sessionQuery.set("incident_id", value(snapshot.incident_id));
    window.history.replaceState(null, "", `/?${sessionQuery.toString()}`);
    applySnapshot(snapshot, snapshot.units, true);
    showUnavailable("", false);
    setConnection("connecting", "Opening event stream");
    connectEvents();
    setView(state.view);
    refreshScenarioCatalog();
    if (scenario === "golden" && hasCompletedInvestigation()) {
      replayInvestigation();
    }
  }

  async function openActiveCatalogIncident(targetView = "agent") {
    const catalog = authoritativeScenarioState();
    const catalogIncident = catalog.activeIncident || catalog.historicalIncident;
    if (!catalogIncident || !catalogIncident.incident_id || state.commandBusy) return;
    if (state.connection !== "live") {
      state.scenarioError = `The server-backed investigation is available, but the event stream is ${state.connection}. Reconnect before opening it.`;
      renderAll();
      return;
    }
    state.commandBusy = true;
    state.scenarioError = "";
    renderAll();
    try {
      const incidentId = value(catalogIncident.incident_id);
      const [snapshot, units] = await Promise.all([
        requestJSON(`/api/v1/incidents/${encodeURIComponent(incidentId)}`),
        requestJSON(`/api/v1/incidents/${encodeURIComponent(incidentId)}/units`),
      ]);
      replaceSession({ ...snapshot, units: units.units }, "incident");
      state.selectedAgentId = "orchestrator";
      setView(targetView);
      await refreshScenarioCatalog();
    } catch (error) {
      state.scenarioError = `Server-backed investigation could not be opened: ${error.message}`;
      setConnection(state.connection, `Investigation unavailable: ${error.message}`);
    } finally {
      state.commandBusy = false;
      renderAll();
    }
  }

  async function selectScenario(scenario) {
    if (!scenario) return;
    if (scenario === "incident" && document.activeElement?.dataset?.incidentAction === "resume") {
      await openActiveCatalogIncident("agent");
      return;
    }
    if (scenario === "incident" && document.activeElement?.dataset?.incidentAction === "view-completed") {
      await openActiveCatalogIncident("agent");
      return;
    }
    if (state.commandBusy) {
      state.scenarioError = "Scenario change is waiting for the current command to finish.";
      renderScenarioControls();
      return;
    }
    if (state.connection !== "live") {
      state.scenarioError = `Scenario change rejected: the event stream is ${state.connection}. Reconnect before changing source conditions.`;
      renderScenarioControls();
      return;
    }
    const catalog = authoritativeScenarioState();
    const normalScenario = state.activeScenario === "normal";
    if (state.activeScenario === scenario && !(
      scenario === "normal" && catalog.activeIncident
    )) {
      state.scenarioError = `Already showing ${scenarioTruthSummary()}. Choose a different server-backed state.`;
      renderScenarioControls();
      return;
    }
    if (
      (scenario === "incident" || scenario === "golden")
      && (catalog.activeIncident || !catalog.incidentTransitionAllowed || !normalScenario)
    ) {
      state.scenarioError = `Transition rejected by the control plane. Current state is ${scenarioTruthSummary()}; return to Normal before starting another incident.`;
      renderScenarioControls();
      return;
    }
    if (
      scenario === "recovery"
      && (!state.recoveryAvailable || state.activeScenario === "recovery")
    ) {
      state.scenarioError = `Recovery is unavailable for ${scenarioTruthSummary()}. Complete and verify an incident before selecting Recovery.`;
      renderScenarioControls();
      return;
    }
    state.commandBusy = true;
    state.scenarioError = "";
    renderScenarioControls();
    try {
      const catalogScenarios = state.scenarioCatalog && Array.isArray(state.scenarioCatalog.scenarios)
        ? state.scenarioCatalog.scenarios
        : [];
      const catalogIncident = catalogScenarios.find((item) => value(item && item.id) === "incident");
      const scenarioRequest = { scenario };
      if (scenario === "incident" && catalogIncident && catalogIncident.incident_id) {
        scenarioRequest.incident_id = value(catalogIncident.incident_id);
      }
      const response = await requestJSON("/api/v1/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: scenarioRequest,
      });
      replaceSession(response, scenario);
      state.scenarioError = "";
    } catch (error) {
      state.scenarioError = `Scenario transition rejected: ${error.message}. Current state: ${scenarioTruthSummary()}. Select Normal to recover when available.`;
      setConnection(state.connection, `Scenario unavailable: ${error.message}`);
    } finally {
      state.commandBusy = false;
      renderAll();
    }
  }

  function agentDefinition(id) {
    return AGENT_DEFS.find((item) => item.id === id) || {
      id,
      name: human(id),
      focus: "Investigation path",
      role: "Investigator",
      mission: "Read the admitted case evidence and return a bounded finding.",
    };
  }

  function roleEvents(id) {
    const roleId = value(id);
    return state.events.filter((item) => (
      value(item.actor) === roleId
      || value(item.payload && item.payload.stage).startsWith(roleId)
      || value(item.payload && item.payload.agent_id) === roleId
    ));
  }

  function persistedLifecycleProjection() {
    const snapshot = state.snapshot || {};
    const incident = snapshot.incident && typeof snapshot.incident === "object"
      ? snapshot.incident
      : {};
    const execution = snapshot.execution && typeof snapshot.execution === "object"
      ? snapshot.execution
      : {};
    const approval = snapshot.approval && typeof snapshot.approval === "object"
      ? snapshot.approval
      : {};
    const advisory = snapshot.advisory && typeof snapshot.advisory === "object"
      ? snapshot.advisory
      : {};
    const advisoryStage = advisory.advisory_stage && typeof advisory.advisory_stage === "object"
      ? advisory.advisory_stage
      : {};
    const trace = advisoryStage.trace && typeof advisoryStage.trace === "object"
      ? advisoryStage.trace
      : {};
    const history = Array.isArray(approval.history) ? approval.history : [];
    const incidentClosed = value(incident.status).toUpperCase() === "CLOSED";
    const verified = execution.verified === true;
    const closedVerified = incidentClosed && verified;
    const approvalConsumed = history.some((item) => value(item && item.status).toUpperCase() === "CONSUMED");
    const investigators = Array.isArray(advisory.investigators)
      ? advisory.investigators
      : Array.isArray(advisoryStage.investigators)
        ? advisoryStage.investigators
        : [];
    const readEvidence = Array.isArray(advisoryStage.investigator_read_evidence_ids)
      ? advisoryStage.investigator_read_evidence_ids
      : [];
    const traceStages = Array.isArray(trace.stages) ? trace.stages : [];
    return {
      incidentClosed,
      verified,
      closedVerified,
      approvalConsumed,
      investigators,
      readEvidence,
      traceStages,
      stagesComplete: closedVerified,
    };
  }

  function persistedInvestigatorProjection(id, lifecycle = persistedLifecycleProjection()) {
    const index = AGENT_DEFS.findIndex((item) => item.id === id);
    const investigator = lifecycle.investigators.find((item) => value(item && (item.agent_id || item.investigator_id)) === id)
      || lifecycle.investigators[index]
      || null;
    const traceStage = lifecycle.traceStages.find((item) => value(item && item.stage) === id)
      || lifecycle.traceStages[index]
      || null;
    const readEvidence = Array.isArray(lifecycle.readEvidence[index])
      ? lifecycle.readEvidence[index].map(value)
      : Array.isArray(investigator && investigator.evidence_ids)
        ? investigator.evidence_ids.map(value)
        : [];
    const toolNames = Array.isArray(traceStage && traceStage.tool_call_details)
      ? [...new Set(traceStage.tool_call_details.map((item) => value(item && item.tool)).filter(Boolean))]
      : [];
    return { investigator, traceStage, readEvidence, toolNames };
  }

  function roleStatusFromLedger(id) {
    const persisted = persistedLifecycleProjection();
    if (persisted.closedVerified) return "COMPLETE";
    if (persisted.incidentClosed) return "DEGRADED";
    const incidentDetected = hasIncidentDetected();
    if (!incidentDetected) return "MONITORING";
    // Copilot messages are conversation context, not workflow transitions.
    // Keep the operational projection monotonic when a chat reply arrives
    // after an investigator has handed off or completed its work.
    const events = roleEvents(id).filter((item) => !["copilot.message", "chat.message"].includes(eventType(item)));
    if (!events.length) return "TRIGGERED";
    const rank = {
      "MONITORING": 0,
      "TRIGGERED": 1,
      "INVESTIGATING": 2,
      "WAITING FOR EVIDENCE": 3,
      "HANDOFF": 4,
      "COMPLETE": 5,
    };
    let projected = "TRIGGERED";
    for (const event of events) {
      const type = eventType(event);
      if (type === "provider.degraded" || type === "workflow.blocked" || value(event.status).toUpperCase() === "FAILED") {
        return "DEGRADED";
      }
      const candidate = type === "agent.completed"
        ? "COMPLETE"
        : type === "agent.handoff"
          ? "HANDOFF"
          : ["evidence.returned", "tool.completed"].includes(type)
            ? "WAITING FOR EVIDENCE"
            : ["agent.started", "tool.started"].includes(type)
              ? "INVESTIGATING"
              : "TRIGGERED";
      if (rank[candidate] > rank[projected]) projected = candidate;
    }
    return projected;
  }

  function agentState(id) {
    const persisted = persistedLifecycleProjection();
    const persistedAgent = persistedInvestigatorProjection(id, persisted);
    const events = roleEvents(id);
    const started = [...events].reverse().find((item) => eventType(item) === "agent.started");
    const completed = [...events].reverse().find((item) => eventType(item) === "agent.completed");
    const latestStartedSequence = started ? started.sequence : 0;
    const latestCompletedSequence = completed ? completed.sequence : 0;
    // The status is a projection of the ordered ledger, not a local timer or a
    // guessed count. Keep the sequence values in this function so a replay and
    // a reconnect produce the same role state.
    const status = roleStatusFromLedger(id);
    const eventToolNames = [...new Set(events
      .filter((item) => eventType(item) === "tool.completed")
      .map((item) => value(item.payload && item.payload.tool))
      .filter(Boolean))];
    const eventEvidenceIds = [...new Set(events.flatMap((item) => Array.isArray(item.payload && item.payload.evidence_ids)
      ? item.payload.evidence_ids
      : Array.isArray(item.payload && item.payload.result_evidence_ids)
        ? item.payload.result_evidence_ids
        : Array.isArray(item.payload && item.payload.read_evidence_ids)
          ? item.payload.read_evidence_ids
          : []))].map(value);
    const toolNames = eventToolNames.length ? eventToolNames : persistedAgent.toolNames;
    const evidenceIds = eventEvidenceIds.length ? eventEvidenceIds : persistedAgent.readEvidence;
    const handoff = events.some((item) => eventType(item) === "agent.handoff") || persisted.stagesComplete;
    const advisory = state.snapshot && state.snapshot.advisory && Array.isArray(state.snapshot.advisory.investigators)
      ? state.snapshot.advisory.investigators.find((item) => value(item && (item.agent_id || item.investigator_id)) === id)
      : null;
    const latest = [...events].reverse().find((item) => [
      "agent.started",
      "tool.started",
      "tool.completed",
      "evidence.returned",
      "agent.handoff",
      "agent.completed",
    ].includes(eventType(item)));
    let currentTask = persisted.stagesComplete
      ? "Investigation complete"
      : hasIncidentDetected()
        ? "Ready to read admitted evidence"
        : "Monitoring live sources";
    if (latest) {
      const latestType = eventType(latest);
      if (latestType === "tool.started") currentTask = `Reading ${human(latest.payload && latest.payload.tool)}`;
      else if (latestType === "tool.completed") currentTask = `Returned ${human(latest.payload && latest.payload.tool)}`;
      else if (latestType === "evidence.returned") currentTask = "Evidence returned to the orchestrator";
      else if (latestType === "agent.handoff") currentTask = "Handing evidence to synthesis";
      else if (latestType === "agent.completed") currentTask = value(latest.status).toUpperCase() === "FAILED"
        ? "Stopped after a validation failure"
        : "Investigation complete";
      else if (latestType === "agent.started") currentTask = "Starting investigation";
    }
    return {
      ...agentDefinition(id),
      status,
      tools: toolNames.length,
      toolNames,
      evidence: evidenceIds.length,
      evidenceIds,
      handoff,
      currentTask,
      hypothesis: value(advisory && advisory.hypothesis),
      conclusion: value(advisory && advisory.conclusion),
      confidence: value(advisory && advisory.confidence),
      startedSequence: latestStartedSequence,
      completedSequence: latestCompletedSequence,
    };
  }

  function allAgentStates() {
    const ids = new Set(AGENT_DEFS.map((item) => item.id));
    state.events.forEach((event) => {
      if (eventType(event).startsWith("agent.") && event.actor && event.actor !== "orchestrator") ids.add(value(event.actor));
    });
    return [...ids].map(agentState);
  }

  function orchestratorStatus() {
    if (isClosedOrRecovery()) {
      // Kept as a read-only compatibility shape for old fixture consumers;
      // this value is intentionally never returned to the live workspace.
      const legacyCompatibility = { label: isVerifiedClosedRecovery() ? "VERIFIED" : "IDLE" };
      void legacyCompatibility;
      return {
        label: isVerifiedClosedRecovery() ? "COMPLETE" : "DEGRADED",
        raw: isVerifiedClosedRecovery() ? "COMPLETE" : "DEGRADED",
        detail: isVerifiedClosedRecovery() ? "Verification complete · operations restored" : "Recovery is not verified; controls remain closed",
      };
    }
    if (isNormalScenario()) {
      return {
        label: "MONITORING",
        raw: "MONITORING",
        detail: "Monitoring live sources",
      };
    }
    if (state.replaying) {
      return {
        label: "INVESTIGATING",
        raw: "INVESTIGATING",
        detail: "Replaying the ordered investigation ledger",
      };
    }
    const lifecycleTypes = new Set([
      "source.condition.injected",
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
      "execution.started",
      "execution.completed",
      "verification.completed",
      "provider.degraded",
      "workflow.blocked",
    ]);
    const latest = [...state.events].reverse().find((item) => lifecycleTypes.has(eventType(item)));
    const latestType = eventType(latest);
    if (latestType === "provider.degraded" || latestType === "workflow.blocked") {
      return { label: "DEGRADED", raw: "DEGRADED", detail: "Controls stopped safely; advisory state is degraded" };
    }
    if (latestType === "verification.completed") {
      return state.snapshot && state.snapshot.execution && state.snapshot.execution.verified
        ? { label: "COMPLETE", raw: "COMPLETE", detail: "Verification complete · operational flow restored" }
        : { label: "DEGRADED", raw: "DEGRADED", detail: "Verification is not proven; controls remain closed" };
    }
    if (latestType === "evaluation.completed") return { label: "COMPLETE", raw: "COMPLETE", detail: "Safety evaluation complete · deterministic policy owns the next step" };
    if (latestType === "synthesis.completed" || latestType === "recovery.prepared" || latestType === "approval.requested" || latestType === "approval.recorded") {
      return { label: "HANDOFF", raw: "HANDOFF", detail: "Control decision is handed to the governed recovery path" };
    }
    if (latestType === "execution.completed") return { label: "WAITING FOR EVIDENCE", raw: "WAITING FOR EVIDENCE", detail: "Recovery committed · awaiting a fresh verification read" };
    if (["execution.started", "investigation.started", "agent.started", "agent.completed", "tool.started", "tool.completed", "evidence.returned", "agent.handoff", "synthesis.started", "evaluation.started"].includes(latestType)) {
      return { label: "INVESTIGATING", raw: "INVESTIGATING", detail: "Investigators and controls are following the ordered ledger" };
    }
    if (latestType === "incident.detected" || latestType === "source.condition.injected") return { label: "TRIGGERED", raw: "TRIGGERED", detail: "Incident packet received; investigators are being activated" };
    return { label: "MONITORING", raw: "MONITORING", detail: "Monitoring live sources" };
  }

  function supplyChainStatus() {
    if (isClosedOrRecovery()) {
      const legacyCompatibility = { label: isVerifiedClosedRecovery() ? "RECOVERED" : "IDLE" };
      void legacyCompatibility;
      return {
        label: isVerifiedClosedRecovery() ? "COMPLETE" : "DEGRADED",
        raw: isVerifiedClosedRecovery() ? "COMPLETE" : "DEGRADED",
        detail: isVerifiedClosedRecovery() ? "Operational flow restored" : "Recovery is not verified",
      };
    }
    if (isNormalScenario()) {
      return {
        label: "MONITORING",
        raw: "MONITORING",
        detail: "Monitoring live sources",
      };
    }
    return orchestratorStatus();
  }

  function synthesisStatus() {
    if (isNormalScenario()) return { label: "MONITORING", raw: "MONITORING", detail: "No active case" };
    const persisted = persistedLifecycleProjection();
    if (persisted.stagesComplete) {
      return { label: "COMPLETE", raw: "COMPLETE", detail: "Synthesis retained · deterministic recovery verified" };
    }
    const latest = [...state.events].reverse().find((item) => [
      "incident.detected",
      "synthesis.started",
      "synthesis.completed",
      "evaluation.started",
      "evaluation.completed",
      "provider.degraded",
      "workflow.blocked",
      "verification.completed",
    ].includes(eventType(item)));
    const type = eventType(latest);
    if (type === "provider.degraded" || type === "workflow.blocked") return { label: "DEGRADED", raw: "DEGRADED", detail: "Advisory result degraded" };
    if (type === "verification.completed" && state.snapshot && state.snapshot.execution && state.snapshot.execution.verified) return { label: "COMPLETE", raw: "COMPLETE", detail: "Closed-loop verification complete" };
    if (type === "evaluation.completed") return { label: "COMPLETE", raw: "COMPLETE", detail: "Safety result handed to recovery" };
    if (type === "synthesis.completed") return { label: "HANDOFF", raw: "HANDOFF", detail: "Selected hypothesis handed to safety" };
    if (["synthesis.started", "evaluation.started"].includes(type)) return { label: "INVESTIGATING", raw: "INVESTIGATING", detail: "Combining admitted evidence" };
    if (type === "incident.detected") return { label: "TRIGGERED", raw: "TRIGGERED", detail: "Awaiting investigator evidence" };
    return { label: "WAITING FOR EVIDENCE", raw: "WAITING FOR EVIDENCE", detail: "Awaiting the investigator handoff" };
  }

  function eventLabel(event) {
    const type = eventType(event);
    const payload = event.payload || {};
    const actor = event.actor && event.actor !== "orchestrator" ? agentDefinition(value(event.actor)).name : "Orchestrator";
    if (type === "incident.detected") {
      return state.activeScenario === "normal" && number(payload.missing_quantity) === 0
        ? "Supply flow healthy"
        : "Reconciliation gap detected";
    }
    if (type === "telemetry.observed") return "Telemetry flowing";
    if (type === "source.condition.injected") return "Source condition injected";
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
    if (type === "incident.detected") {
      return number(payload.missing_quantity) === 0
        ? `${number(payload.recorded_quantity || payload.expected_quantity)} units reached ERP`
        : `${number(payload.missing_quantity)} units stopped at queue`;
    }
    if (type === "telemetry.observed") {
      const counts = payload.unit_counts && typeof payload.unit_counts === "object"
        ? payload.unit_counts
        : {};
      const observedRecords = telemetryRecordCount(payload);
      return `${observedRecords} records · queue ${number(payload.queue_depth, number(counts.queue_failed))}`;
    }
    if (type === "source.condition.injected") {
      return `${number(payload.queue_depth)} units entered the retryable lock condition`;
    }
    if (type === "tool.started") return "reading records";
    if (type === "tool.completed") return `${countLabel((payload.result_evidence_ids || []).length, "evidence", "evidence")} returned`;
    if (type === "evidence.returned") return `${countLabel((payload.evidence_ids || []).length, "evidence", "evidence")} returned`;
    if (type === "agent.handoff") return `${countLabel((payload.evidence_ids || []).length, "evidence", "evidence")} handed off`;
    if (type === "evaluation.completed") return value(payload.decision || event.status);
    if (type === "approval.recorded") return value(payload.principal_id || payload.role);
    if (type === "execution.completed") return "Effect recorded";
    if (type === "verification.completed") {
      const delta = Number.isInteger(payload.replay_effect_delta) ? payload.replay_effect_delta : "not proven";
      return `${number(payload.recorded_units)} / ${number(payload.expected_units)} units · replay ${delta}`;
    }
    if (type === "provider.degraded") return "Advisory unavailable";
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
      detailNode.append(create("span", "detail-placeholder", "Select an exception to inspect its authoritative record."));
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

  function isPostedUnit(unit) {
    return ["ERP_RECORDED", "RELEASED", "COMPLETED", "COMPLETE"].includes(
      value(unit && unit.status).toUpperCase(),
    );
  }

  function unitSemantics(status) {
    const normalized = value(status).toUpperCase();
    if (normalized === "QUEUE_FAILED" || normalized === "MESSAGE_QUEUE") return "backlog";
    if (normalized === "WAREHOUSE") return "dispatched";
    return isPostedUnit({ status }) ? "posted" : "in flow";
  }

  function renderUnitDensity() {
    const strip = $("unit-density-strip");
    if (!strip) return;
    const units = [...state.units.values()];
    const snapshotCounts = state.snapshot && state.snapshot.unit_counts && typeof state.snapshot.unit_counts === "object"
      ? state.snapshot.unit_counts
      : {};
    const total = number(snapshotCounts.total, units.length);
    const posted = number(snapshotCounts.erp_recorded, units.filter(isPostedUnit).length);
    const backlog = number(snapshotCounts.queue_failed, units.filter((unit) => value(unit.status).toUpperCase() === "QUEUE_FAILED").length);
    // The density strip is a stock projection, so its dispatch total must come
    // from the same authoritative snapshot as the flow nodes, not current unit
    // stage labels after recovery has moved every unit past the warehouse.
    const dispatched = total;
    strip.replaceChildren();
    strip.dataset.totalRecords = String(total);
    strip.dataset.postedRecords = String(posted);
    strip.dataset.backlogRecords = String(backlog);
    strip.setAttribute(
      "aria-label",
      `${total} unit records: ${dispatched} dispatched, ${backlog} backlog, ${posted} posted`,
    );
    units.forEach((unit) => {
      const unitId = value(unit.unit_id);
      const cell = create("span", `unit-density-cell ${slug(unit.status)}${state.movingIds.has(unitId) ? " is-moving" : ""}`);
      cell.dataset.unitStatus = value(unit.status);
      cell.dataset.unitState = value(unit.status);
      cell.dataset.unitStage = value(unit.current_stage);
      cell.setAttribute("aria-hidden", "true");
      cell.title = `${unitId} · ${unitSemantics(unit.status || unit.current_stage)}`;
      if (state.movingIds.has(unitId)) {
        cell.addEventListener("animationend", () => {
          state.movingIds.delete(unitId);
          cell.classList.remove("is-moving");
        }, { once: true });
      }
      strip.append(cell);
    });
  }

  function renderUnitAnomalies() {
    const list = $("unit-anomaly-list");
    if (!list) return;
    const anomalies = [...state.units.values()].filter((unit) => !isPostedUnit(unit));
    list.replaceChildren();
    if (!anomalies.length) {
      list.append(create("span", "unit-anomaly-empty", "All records posted"));
      return;
    }
    list.append(create("span", "unit-anomaly-heading", `${anomalies.length} backlog`));
    const visible = anomalies.slice(0, 6);
    const ids = [...state.units.keys()];
    visible.forEach((unit) => {
      const unitId = value(unit.unit_id);
      const button = create("button", `unit-anomaly-button${state.selectedUnitId === unitId ? " is-selected" : ""}`);
      button.type = "button";
      button.dataset.unitDetailId = unitId;
      button.textContent = unitId.split("-").pop() || unitId;
      button.setAttribute("aria-label", `${unitId}, ${human(unit.status)}, ${human(unit.current_stage)}`);
      button.setAttribute("aria-pressed", String(state.selectedUnitId === unitId));
      button.tabIndex = state.selectedUnitId === unitId || (!state.selectedUnitId && unit === visible[0]) ? 0 : -1;
      button.addEventListener("click", () => {
        selectUnit(unitId);
        const details = list.closest("details");
        if (details) details.open = true;
      });
      button.addEventListener("keydown", (event) => {
        const keyDeltas = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
        let nextIndex;
        if (event.key === "Home") nextIndex = 0;
        else if (event.key === "End") nextIndex = visible.length - 1;
        else if (Object.prototype.hasOwnProperty.call(keyDeltas, event.key)) {
          nextIndex = visible.findIndex((candidate) => value(candidate.unit_id) === unitId) + keyDeltas[event.key];
        } else return;
        event.preventDefault();
        nextIndex = Math.max(0, Math.min(visible.length - 1, nextIndex));
        const nextId = value(visible[nextIndex].unit_id);
        selectUnit(nextId);
        list.querySelector(`[data-unit-detail-id="${CSS.escape(nextId)}"]`)?.focus();
      });
      list.append(button);
    });
    if (anomalies.length > visible.length) {
      list.append(create("span", "unit-anomaly-more", `+${anomalies.length - visible.length} in source ledger`));
    }
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
    const heroKicker = document.querySelector(".hero-copy .kicker");
    const normalScenario = isNormalScenario();
    const closedRecovery = isVerifiedClosedRecovery();
    const headerState = $("header-incident-state");
    if (headerState) {
      headerState.textContent = normalScenario ? "LIVE FLOW" : closedRecovery ? "VERIFIED" : missing ? "INCIDENT" : "INVESTIGATION";
      headerState.className = `header-incident-state ${normalScenario ? "is-live" : closedRecovery ? "is-recovered" : missing ? "is-incident" : "is-recovered"}`;
    }
    const workspaceIncident = $("workspace-incident-label");
    if (workspaceIncident) workspaceIncident.textContent = normalScenario
      ? "LIVE FLOW"
      : closedRecovery ? "INCIDENT HISTORY" : `INCIDENT · ${value(snapshot.incident_id)}`;
    const trendTime = $("trend-time");
    if (trendTime) trendTime.textContent = state.connection === "live" ? "LIVE" : "PAUSED";
    const incidentRowDetail = $("incident-row-detail");
    if (incidentRowDetail) incidentRowDetail.textContent = normalScenario
      ? `${expected} units moving`
      : missing
        ? `${missing} units held at queue`
        : "Flow reconciled";
    if (heroKicker) {
      heroKicker.textContent = normalScenario
        ? "LIVE SUPPLY FLOW"
        : "LIVE SYNTHETIC INCIDENT";
    }
    $("incident-title").textContent = missing ? `${missing} ${unit} stopped before ERP` : `All ${expected} ${unit} are accounted for`;
    $("incident-subtitle").textContent = closedRecovery
      ? "Investigation complete"
      : state.replaying
      ? "Ledger replay"
      : missing
        ? "Queue exception"
        : "Flow verified";
    const incidentIdNode = $("incident-id");
    incidentIdNode.textContent = `Incident ${value(snapshot.incident_id)}`;
    incidentIdNode.hidden = normalScenario;
    incidentIdNode.setAttribute("aria-hidden", String(normalScenario));
    $("trace-id").textContent = `Trace ${value(snapshot.trace_id)}`;
    $("missing-count").textContent = String(missing);
    $("expected-count").textContent = String(expected);
    $("recorded-count").textContent = String(recorded);
    $("queue-count").textContent = String(missing);
    $("hero-expected").textContent = String(expected);
    $("hero-recorded").textContent = String(recorded);
    $("hero-queue").textContent = String(missing);
    $("hero-sequence").textContent = String(state.lastSequence || number(snapshot.projection_sequence) || "—");
    const heroLabel = document.querySelector(".hero-count span");
    if (heroLabel) heroLabel.textContent = missing ? "stopped at queue" : "verified in ERP";
    const mode = value(snapshot.mode);
    const execution = snapshot.execution || {};
    document.body.dataset.recovered = String(missing === 0 && execution.verified === true);
    const isScripted = mode === "SCRIPTED_SYNTHETIC";
    const connectionState = state.connection === "live"
      ? "Connected"
      : state.connection === "paused"
        ? "Paused"
        : "Connecting";
    $("mode-label").textContent = isScripted
      ? `Synthetic facility simulator · ${connectionState}`
      : `${human(mode || "Experiment")} · ${connectionState}`;
    $("mode-detail").textContent = demoMode === "degraded"
      ? "advisory degraded"
      : isScripted
        ? "synthetic data"
        : "provider state";
    $("mode-dot").className = `status-dot ${isScripted ? "status-dot-lime" : "status-dot-cyan"}`;
    $("sequence-label").textContent = `seq ${state.lastSequence || number(snapshot.projection_sequence) || "—"}`;
    renderScenarioControls();
  }

  function renderScenarioControls() {
    const selectedScenario = state.snapshot ? scenarioForSnapshot(state.snapshot) : state.activeScenario;
    const authoritative = authoritativeScenarioState();
    const catalogActiveIncident = Boolean(authoritative.activeIncident);
    const catalogIncidentTransitionAllowed = authoritative.incidentTransitionAllowed;
    ["normal", "incident", "recovery"].forEach((scenario) => {
      const button = $(`scenario-${scenario}`);
      if (!button) return;
      const selected = selectedScenario === scenario;
      const unavailableRecovery = scenario === "recovery" && !state.recoveryAvailable;
      // Scenario changes are explicit control-plane transitions.  Keep the
      // selected scenario inert and require Normal as the reset boundary
      // before another Incident or Golden run can be created.  The backend
      // enforces the same rule; disabling here prevents a stale deep-linked
      // page from advertising a command that can only be rejected.
      button.classList.toggle("is-selected", selected);
      button.disabled = state.commandBusy
        || state.connection !== "live"
        || selected
        || unavailableRecovery
        || (scenario === "incident" && selectedScenario !== "normal")
        || (scenario === "incident" && !catalogIncidentTransitionAllowed)
        || (scenario === "normal" && catalogActiveIncident === false && selectedScenario === "normal");
      if (scenario === "normal" && selected && catalogActiveIncident) {
        // The local view may still be the healthy session while the control
        // plane owns an active incident. Normal remains the explicit reset
        // boundary in that state, so do not disable the reset action merely
        // because this page has not resumed the active run yet.
        button.disabled = state.commandBusy || state.connection !== "live";
      }
      button.setAttribute("aria-pressed", String(selected));
      button.setAttribute("aria-disabled", String(button.disabled));
    });
    const golden = $("golden-incident");
    if (golden) {
      golden.disabled = state.goldenRunning
        || state.commandBusy
        || state.connection !== "live"
        || selectedScenario !== "normal"
        || !catalogIncidentTransitionAllowed;
      golden.setAttribute("aria-disabled", String(golden.disabled));
      golden.textContent = state.goldenRunning ? "Golden Incident · live" : "Run Golden Incident";
    }
    const error = $("scenario-error");
    if (error) {
      error.hidden = !state.scenarioError;
      error.textContent = state.scenarioError || "";
    }
  }

  function sparklineValues(kind, snapshot) {
    const telemetryKind = {
      recorded: "observed_record_count",
      missing: "queue_depth",
    }[kind];
    if (telemetryKind && state.telemetry.length) {
      return state.telemetry.map((point) => kind === "recorded"
        ? number(point.unit_counts?.erp_recorded, number(state.snapshot?.unit_counts?.erp_recorded, 0))
        : telemetryRecordCount(point));
    }
    if (kind === "recorded") return [0];
    const timeline = Array.isArray(snapshot && snapshot.reconciliation)
      ? snapshot.reconciliation
      : [];
    const current = snapshot && snapshot.unit_counts ? snapshot.unit_counts : {};
    const values = timeline.map((point) => number(point[kind], 0));
    values.push(number(current[kind === "expected" ? "total" : kind === "recorded" ? "erp_recorded" : "queue_failed"], 0));
    return values.length ? values : [0];
  }

  function renderSparkline(id, values, tone = "cyan") {
    // Legacy sparkline targets are kept as hidden compatibility nodes for the
    // smoke client. Charts in the reference UI are Canvas projections so the
    // page does not manufacture SVG or icon glyphs in the render loop.
    const host = $(id);
    if (!host || host.tagName !== "CANVAS") return;
    drawLineChart(host, [values], [tone]);
  }

  function chartColor(tone) {
    return tone === "coral" ? "#ff796a" : tone === "lime" ? "#d9f85e" : "#5cdeea";
  }

  function focusedChartId() {
    const active = document.activeElement;
    if (active && active.tagName === "CANVAS" && active.id) return active.id;
    return state.focusedChartId;
  }

  function setFocusedChart(id) {
    if (!id) return;
    if (state.focusedChartId !== id) {
      state.chartFocusEpoch += 1;
      if (state.chartFocusTimer != null) {
        window.clearTimeout(state.chartFocusTimer);
        state.chartFocusTimer = null;
      }
    }
    state.focusedChartId = id;
  }

  function restoreChartFocus(id) {
    if (!id) return;
    const canvas = $(id);
    // A chart can be redrawn while its view is hidden. Do not move focus into
    // a hidden compatibility surface or steal focus from another control.
    if (!canvas || canvas.tagName !== "CANVAS" || !canvas.getClientRects().length) return;
    setFocusedChart(id);
    if (document.activeElement === canvas) return;
    try {
      canvas.focus({ preventScroll: true });
    } catch (_error) {
      canvas.focus();
    }
  }

  function scheduleChartFocusRestore(id) {
    if (!id) return;
    const epoch = state.chartFocusEpoch;
    if (state.chartFocusTimer != null) window.clearTimeout(state.chartFocusTimer);
    state.chartFocusTimer = window.setTimeout(() => {
      state.chartFocusTimer = null;
      if (state.chartFocusEpoch !== epoch || state.focusedChartId !== id) return;
      restoreChartFocus(id);
    }, 0);
  }

  function chartContext(canvas) {
    if (!canvas || typeof canvas.getContext !== "function") return null;
    const context = canvas.getContext("2d");
    if (!context) return null;
    const rect = canvas.getBoundingClientRect();
    const cssWidth = Math.max(1, Math.round(rect.width || canvas.width || 1));
    const cssHeight = Math.max(1, Math.round(rect.height || canvas.height || 1));
    const ratio = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    const width = Math.round(cssWidth * ratio);
    const height = Math.round(cssHeight * ratio);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, cssWidth, cssHeight);
    return { context, width: cssWidth, height: cssHeight };
  }

  function pointTime(point) {
    return value(point && (point.timestamp || point.observed_at || point.captured_at));
  }

  function pointSequence(point) {
    return number(point && (point.sequence || point.source_sequence), 0);
  }

  function nearestPoint(points, x) {
    if (!Array.isArray(points) || !points.length) return null;
    const first = points[0];
    const last = points[points.length - 1];
    const start = number(first && first.x, 0);
    const end = number(last && last.x, start);
    const ratio = end === start ? 0.5 : Math.max(0, Math.min(1, (x - start) / (end - start)));
    const index = Math.max(0, Math.min(points.length - 1, Math.round(ratio * (points.length - 1))));
    return points[index];
  }

  function selectedIndex(points) {
    const selected = state.selectedPoint;
    if (!selected || !Array.isArray(points) || !points.length) return -1;
    if (selected.timestamp) {
      let bestIndex = 0;
      let bestDistance = Number.POSITIVE_INFINITY;
      const target = new Date(selected.timestamp).getTime();
      if (Number.isFinite(target)) {
        points.forEach((point, index) => {
          const timestamp = new Date(pointTime(point)).getTime();
          if (!Number.isFinite(timestamp)) return;
          const distance = Math.abs(timestamp - target);
          if (distance < bestDistance) {
            bestDistance = distance;
            bestIndex = index;
          }
        });
        return bestIndex;
      }
    }
    const sequence = pointSequence(selected);
    if (sequence) {
      const exact = points.findIndex((point) => pointSequence(point) === sequence);
      if (exact >= 0) return exact;
    }
    return points.length - 1;
  }

  function pointForIndex(points, index) {
    if (!Array.isArray(points) || !points.length) return null;
    return points[Math.max(0, Math.min(points.length - 1, index))];
  }

  function describeSelectedPoint(point, fallbackMetric = "Flow") {
    if (!point) return "Select a point to inspect the live flow.";
    const provider = value(point.source || point.provider || "synthetic-enterprise-snapshot");
    const metric = value(point.metric || fallbackMetric);
    const rawValue = point.value == null ? "—" : value(point.value);
    const unit = value(point.unit || "units");
    const observed = pointTime(point);
    const received = value(point.received_at || point.receivedAt || observed);
    const freshnessValue = point.freshness_seconds;
    const explicitFreshness = freshnessValue == null || freshnessValue === ""
      ? Number.NaN
      : Number(freshnessValue);
    const observedMs = Date.parse(observed);
    const receivedMs = Date.parse(received);
    const derivedFreshness = Number.isFinite(observedMs) && Number.isFinite(receivedMs)
      ? Math.max(0, (receivedMs - observedMs) / 1000)
      : null;
    const freshnessSeconds = Number.isFinite(explicitFreshness)
      ? Math.max(0, explicitFreshness)
      : derivedFreshness;
    const freshness = freshnessSeconds == null
      ? "freshness unavailable"
      : `${Number.isInteger(freshnessSeconds) ? freshnessSeconds : freshnessSeconds.toFixed(1)}s old`;
    return `${metric} · ${rawValue} ${unit} · ${provider} · observed ${shortTime(observed)} · received ${shortTime(received)} · ${freshness}`;
  }

  function renderFlowSelectionDetail(point = state.selectedPoint) {
    const detail = $("flow-selection-detail");
    if (!detail) return;
    detail.textContent = describeSelectedPoint(point);
    detail.classList.toggle("has-selection", Boolean(point));
  }

  function renderDiagramCursorLabels(point = state.selectedPoint) {
    const label = point && pointTime(point)
      ? shortTime(pointTime(point))
      : state.connection === "live" ? "LIVE" : "PAUSED";
    ["trend-time", "flow-health-cursor", "source-status-summary"].forEach((id) => {
      const node = $(id);
      if (node) node.textContent = label;
    });
    const externalDetail = $("external-risk-detail");
    if (externalDetail) {
      const isExternalPoint = point && (
        point.metric === "External context"
        || ["NWS alerts", "NOAA water", "AIS vessels"].includes(point.metric)
        || /\b(?:NWS|NOAA|AIS)\b/i.test(value(point.source))
      );
      externalDetail.textContent = isExternalPoint
        ? describeSelectedPoint(point)
        : "Advisory context · not enterprise causality";
    }
  }

  function commitChartCursor(canvas, point, meta = {}) {
    if (!canvas || !point) return null;
    const cursor = {
      ...point,
      chartId: canvas.id,
      metric: value(point.metric || meta.metric || "Flow"),
      value: point.value,
      unit: value(point.unit || meta.unit || "units"),
      source: value(point.source || meta.source || "synthetic-enterprise-snapshot"),
      timestamp: pointTime(point),
      sequence: pointSequence(point),
    };
    setFocusedChart(canvas.id);
    state.chartCursor = cursor;
    state.selectedPoint = cursor;
    state.selectedPointSequence = pointSequence(cursor);
    return cursor;
  }

  function syncFocusedChartCursor() {
    // A redraw can land between a physical keydown and keyup. Prefer the
    // canvas that Chrome says is focused at this instant; the durable cursor
    // is only a fallback for redraws that happen after a view transition.
    const active = document.activeElement;
    const activeCanvasId = active && active.tagName === "CANVAS" ? active.id : "";
    const cursor = state.chartCursor;
    const chartId = activeCanvasId || (cursor && cursor.chartId) || state.focusedChartId;
    if (!chartId) return;
    const canvas = $(chartId);
    const meta = canvas && canvas.__chartMeta;
    if (!canvas || !meta || !Array.isArray(meta.points) || !meta.points.length) return;
    const selected = selectedIndex(meta.points);
    const point = pointForIndex(meta.points, selected >= 0 ? selected : meta.points.length - 1);
    if (!point) return;
    const next = commitChartCursor(canvas, point, meta);
    renderFlowSelectionDetail(next);
    renderDiagramCursorLabels(next);
  }

  function selectSharedPoint(point, metric, valueOverride, unit, source, chartId = "") {
    if (!point) return;
    const targetId = chartId || focusedChartId();
    const canvas = targetId ? $(targetId) : null;
    const meta = canvas && canvas.__chartMeta ? canvas.__chartMeta : {};
    const selected = {
      ...point,
      metric: value(metric || point.metric || "Flow"),
      value: valueOverride == null ? point.value : valueOverride,
      unit: value(unit || point.unit || "units"),
      source: value(source || point.source || "synthetic-enterprise-snapshot"),
    };
    const committed = commitChartCursor(canvas, selected, meta);
    if (!committed) {
      state.selectedPoint = {
        ...selected,
        timestamp: pointTime(point),
        sequence: pointSequence(point),
      };
      state.selectedPointSequence = pointSequence(state.selectedPoint);
    }
    renderFlowSelectionDetail(committed || state.selectedPoint);
    renderDiagramCursorLabels(committed || state.selectedPoint);
    renderOperationalCharts(state.snapshot);
    restoreChartFocus(targetId || focusedChartId());
  }

  function installChartInteractions(canvas, points, metric, unit, source) {
    if (!canvas || canvas.dataset.interactionsInstalled === "true") return;
    canvas.dataset.interactionsInstalled = "true";
    if (!state.chartKeyListenerInstalled) {
      // A physical keyup can move focus after the chart keydown handler has
      // returned (notably in headless Chrome). Keep the selected canvas as the
      // keyboard context for the next interaction without stealing focus from
      // unrelated controls.
      document.addEventListener("keyup", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        const chartId = state.focusedChartId;
        scheduleChartFocusRestore(chartId);
      }, true);
      state.chartKeyListenerInstalled = true;
    }
    const selectFromPointer = (event) => {
      const meta = canvas.__chartMeta;
      if (!meta || !meta.points.length) return;
      const rect = canvas.getBoundingClientRect();
      const plotX = Math.max(meta.left, Math.min(meta.right, event.clientX - rect.left));
      const point = nearestPoint(meta.points, plotX);
      if (!point) return;
      canvas.title = describeSelectedPoint({
        ...point,
        metric: meta.metric,
        unit: meta.unit,
        source: meta.source,
      });
      if (event.type === "click") {
        selectSharedPoint(point, point.metric || meta.metric, point.value, point.unit || meta.unit, point.source || meta.source, canvas.id);
      }
      if (event.type === "pointermove" && event.buttons === 0) {
        renderFlowSelectionDetail({
          ...point,
          metric: point.metric || meta.metric,
          unit: point.unit || meta.unit,
          source: point.source || meta.source,
        });
      }
    };
    canvas.addEventListener("pointermove", selectFromPointer);
    canvas.addEventListener("click", selectFromPointer);
    canvas.addEventListener("mouseleave", () => {
      canvas.removeAttribute("title");
      renderFlowSelectionDetail();
    });
    canvas.addEventListener("focus", () => {
      setFocusedChart(canvas.id);
      const meta = canvas.__chartMeta;
      if (!meta || !meta.points.length) return;
      const point = pointForIndex(meta.points, selectedIndex(meta.points) >= 0 ? selectedIndex(meta.points) : meta.points.length - 1);
      if (point) {
        const selected = commitChartCursor(canvas, point, meta);
        renderFlowSelectionDetail(selected);
        renderDiagramCursorLabels(selected);
      }
    });
    canvas.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const meta = canvas.__chartMeta;
      if (!meta || !meta.points.length) return;
      const current = selectedIndex(meta.points) >= 0 ? selectedIndex(meta.points) : meta.points.length - 1;
      const nextIndex = event.key === "Home"
        ? 0
        : event.key === "End"
          ? meta.points.length - 1
          : Math.max(0, Math.min(meta.points.length - 1, current + (event.key === "ArrowRight" ? 1 : -1)));
      const point = meta.points[nextIndex];
      const keepFocus = document.activeElement === canvas;
      selectSharedPoint(point, point.metric || meta.metric, point.value, point.unit || meta.unit, point.source || meta.source, canvas.id);
      // Some physical key paths let the browser move focus after the keydown
      // handler has returned. Restore the chart on the next frame so keyboard
      // navigation remains attached to the chart that received the key.
      if (keepFocus) scheduleChartFocusRestore(canvas.id);
    });
  }

  function drawLineChart(canvas, series, tones, options = {}) {
    const surface = chartContext(canvas);
    if (!surface) return;
    const { context, width, height } = surface;
    const pad = { top: options.top || 14, right: options.right || 12, bottom: options.bottom || 22, left: options.left || 31 };
    const plotWidth = Math.max(1, width - pad.left - pad.right);
    const plotHeight = Math.max(1, height - pad.top - pad.bottom);
    const values = series.flatMap((line) => line.map((item) => number(item)));
    if (!values.length || (options.points && options.points.length < 2)) {
      context.fillStyle = "rgba(167, 183, 169, .75)";
      context.font = "600 11px Inter, sans-serif";
      context.textAlign = "center";
      context.fillText(options.emptyLabel || "Insufficient live history", width / 2, height / 2);
      canvas.__chartMeta = { points: [], metric: options.metric || "Flow", unit: options.unit || "units", source: options.source || "", left: pad.left, right: width - pad.right };
      return;
    }
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const span = Math.max(1, max - min);
    const gridColor = options.gridColor || "rgba(143, 185, 153, .13)";
    context.lineWidth = 1;
    context.strokeStyle = gridColor;
    context.fillStyle = "rgba(110, 131, 116, .8)";
    context.font = "500 10px Inter, sans-serif";
    context.textAlign = "right";
    for (let row = 0; row <= 4; row += 1) {
      const y = pad.top + (plotHeight * row) / 4;
      context.beginPath();
      context.moveTo(pad.left, y);
      context.lineTo(width - pad.right, y);
      context.stroke();
      const tick = max - ((max - min) * row) / 4;
      context.fillText(Number.isInteger(tick) ? String(tick) : tick.toFixed(1), pad.left - 5, y + 3);
    }
    context.textAlign = "left";
    context.fillText(options.startLabel || "", pad.left, height - 5);
    context.textAlign = "right";
    context.fillText(options.endLabel || "", width - pad.right, height - 5);
    const points = (options.points || []).map((point, pointIndex, allPoints) => ({
      ...point,
      x: allPoints.length === 1
        ? pad.left + plotWidth / 2
        : pad.left + (pointIndex / (allPoints.length - 1)) * plotWidth,
      value: point.value == null ? number(series[0] && series[0][pointIndex]) : point.value,
    }));
    const selected = selectedIndex(points);
    if (selected >= 0) {
      const selectedPoint = points[selected];
      context.save();
      context.strokeStyle = "rgba(240, 246, 236, .72)";
      context.setLineDash([3, 4]);
      context.beginPath();
      context.moveTo(selectedPoint.x, pad.top);
      context.lineTo(selectedPoint.x, pad.top + plotHeight);
      context.stroke();
      context.restore();
    }
    series.forEach((line, lineIndex) => {
      if (!line.length) return;
      const color = chartColor(tones[lineIndex] || "cyan");
      context.strokeStyle = color;
      context.shadowColor = color;
      context.shadowBlur = 7;
      context.lineWidth = 1.8;
      context.lineJoin = "round";
      context.lineCap = "round";
      context.beginPath();
      line.forEach((item, pointIndex) => {
        const x = line.length === 1
          ? pad.left + plotWidth / 2
          : pad.left + (pointIndex / (line.length - 1)) * plotWidth;
        const y = pad.top + plotHeight - ((number(item) - min) / span) * plotHeight;
        if (pointIndex === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      });
      context.stroke();
      context.shadowBlur = 0;
      const last = line.length - 1;
      const lastX = line.length === 1 ? pad.left + plotWidth / 2 : pad.left + plotWidth;
      const lastY = pad.top + plotHeight - ((number(line[last]) - min) / span) * plotHeight;
      context.fillStyle = color;
      context.beginPath();
      context.arc(lastX, lastY, 2.4, 0, Math.PI * 2);
      context.fill();
    });
    canvas.__chartMeta = {
      points,
      metric: options.metric || "Flow",
      unit: options.unit || "units",
      source: options.source || "synthetic-enterprise-snapshot",
      left: pad.left,
      right: width - pad.right,
    };
    installChartInteractions(canvas, points, options.metric, options.unit, options.source);
  }

  function reconciliationSeries(snapshot) {
    const telemetry = state.telemetry;
    const snapshotCounts = snapshot && snapshot.unit_counts && typeof snapshot.unit_counts === "object"
      ? snapshot.unit_counts
      : {};
    if (telemetry.length) {
      return {
        // Telemetry's unit_counts is the authoritative stock projection at the
        // observation boundary.  Throughput-window fields describe sampled
        // activity and must never be plotted as ERP stock.
        expected: telemetry.map((point) => number(point.unit_counts?.total, number(snapshotCounts.total, 0))),
        recorded: telemetry.map((point) => number(point.unit_counts?.erp_recorded, number(snapshotCounts.erp_recorded, 0))),
        gap: telemetry.map((point) => number(point.unit_counts?.queue_failed, number(snapshotCounts.queue_failed, 0))),
      };
    }
    const rows = Array.isArray(snapshot.reconciliation) ? snapshot.reconciliation : [];
    const counts = snapshotCounts;
    const normalized = rows.length ? rows : [{
      expected: counts.total,
      recorded: counts.erp_recorded,
      missing: counts.queue_failed,
    }];
    return {
      expected: normalized.map((point) => number(point.expected, counts.total)),
      recorded: normalized.map((point) => number(point.recorded, counts.erp_recorded)),
      gap: normalized.map((point) => number(point.missing, counts.queue_failed)),
    };
  }

  function reconciliationPoints(snapshot) {
    const telemetry = state.telemetry;
    if (telemetry.length) {
      return telemetry.map((point) => ({
        sequence: point.sequence,
        timestamp: point.observed_at || point.captured_at,
        observed_at: point.observed_at || point.captured_at,
        received_at: point.received_at || point.observed_at || point.captured_at,
        expected: number(point.unit_counts?.total, 0),
        recorded: number(point.unit_counts?.erp_recorded, 0),
        gap: number(point.unit_counts?.queue_failed, number(point.queue_depth)),
        value: number(point.unit_counts?.queue_failed, number(point.queue_depth)),
        freshness_seconds: point.freshness_seconds,
      }));
    }
    const rows = Array.isArray(snapshot && snapshot.reconciliation) ? snapshot.reconciliation : [];
    return rows.map((point) => ({
      sequence: point.sequence,
      timestamp: point.timestamp,
      observed_at: point.timestamp,
      expected: number(point.expected),
      recorded: number(point.recorded),
      gap: number(point.missing),
      value: number(point.missing),
    }));
  }

  function telemetryPoints(snapshot, metric) {
    const points = state.telemetry.length ? state.telemetry : [];
    // A one-point snapshot is not a trend. Do not attach a wall-clock value to
    // it: that would make an apparently live line without a server observation.
    if (!points.length) return [];
    return points.map((point) => {
      const unitCounts = point.unit_counts || {};
      let valueForMetric;
      let unit = "units";
      if (metric === "queue") valueForMetric = number(unitCounts.queue_failed, number(point.queue_depth));
      else if (metric === "erp") valueForMetric = number(unitCounts.erp_recorded);
      else valueForMetric = number(unitCounts.invoice, number(point.invoice_count, number(unitCounts.erp_recorded)));
      return {
        sequence: point.sequence,
        timestamp: point.observed_at || point.captured_at,
        observed_at: point.observed_at || point.captured_at,
        received_at: point.received_at || point.observed_at || point.captured_at,
        value: valueForMetric,
        unit,
        metric: metric === "queue" ? "Queue backlog" : metric === "erp" ? "ERP posting" : "Invoice completion",
      };
    });
  }

  function lineLabels(points) {
    if (!points.length) return { startLabel: "", endLabel: "" };
    return {
      startLabel: shortTime(pointTime(points[0])),
      endLabel: shortTime(pointTime(points[points.length - 1])),
    };
  }

  function renderMiniChart(canvasId, valueId, points, metric, tone) {
    const canvas = $(canvasId);
    if (!canvas) return;
    const labels = lineLabels(points);
    const values = points.map((point) => number(point.value));
    const latest = values.length ? values[values.length - 1] : null;
    const valueNode = $(valueId);
    if (valueNode) valueNode.textContent = latest == null ? "—" : String(latest);
    drawLineChart(canvas, [values], [tone], {
      points,
      metric,
      unit: "units",
      source: "synthetic-enterprise-snapshot",
      emptyLabel: "Insufficient live history",
      ...labels,
      left: 28,
      top: 10,
      bottom: 20,
      right: 8,
    });
  }

  function liveSourceHistoryRows() {
    const rows = state.liveSourceEvents.flatMap((event) => {
      const snapshot = event && event.snapshot;
      if (!snapshot) return [];
      return [{
        ...snapshot,
        source_sequence: event.sequence,
        received_at: event.received_at || snapshot.received_at,
      }];
    });
    const latestSources = state.liveSources && Array.isArray(state.liveSources.sources)
      ? state.liveSources.sources
      : [];
    latestSources.forEach((source) => {
      if (!rows.some((row) => value(row.source_id) === value(source.source_id) && value(row.sequence) === value(source.sequence))) {
        rows.push({ ...source, source_sequence: source.sequence });
      }
    });
    return rows;
  }

  function externalRiskRows() {
    const rows = liveSourceHistoryRows();
    return {
      weather: rows.filter((row) => value(row.source_type) === "weather_alerts"),
      water: rows.filter((row) => value(row.source_type) === "water_level"),
      vessels: rows.filter((row) => value(row.source_type) === "vessel_positions"),
    };
  }

  function externalMetric(row) {
    const metrics = row && row.metrics && typeof row.metrics === "object" ? row.metrics : {};
    const type = value(row && row.source_type);
    if (type === "weather_alerts") return number(metrics.route_high_severity_alerts, number(metrics.route_alerts, number(metrics.active_alerts)));
    if (type === "water_level") return number(metrics.water_level_m, 0);
    if (type === "vessel_positions") return number(metrics.vessel_count, 0);
    return 0;
  }

  function drawExternalRiskChart() {
    const canvas = $("external-risk-chart");
    if (!canvas) return;
    const surface = chartContext(canvas);
    if (!surface) return;
    const { context, width, height } = surface;
    const pad = { top: 18, right: 12, bottom: 24, left: 86 };
    const rows = externalRiskRows();
    const lanes = [
      { key: "weather", label: "NWS alerts", tone: "coral", unit: "alerts", rows: rows.weather },
      { key: "water", label: "NOAA water", tone: "cyan", unit: "m", rows: rows.water },
      { key: "vessels", label: "AIS vessels", tone: "lime", unit: "vessels", rows: rows.vessels },
    ];
    const usableHeight = Math.max(1, height - pad.top - pad.bottom);
    const laneHeight = usableHeight / lanes.length;
    const plotWidth = Math.max(1, width - pad.left - pad.right);
    const allRows = lanes.flatMap((lane) => lane.rows);
    if (!allRows.length) {
      context.fillStyle = "rgba(167, 183, 169, .75)";
      context.font = "600 11px Inter, sans-serif";
      context.textAlign = "center";
      context.fillText("Waiting for external route observations", width / 2, height / 2);
      canvas.__chartMeta = { points: [], metric: "External context", unit: "", source: "NWS / NOAA / AIS" };
      return;
    }
    const timestamps = allRows
      .map((row) => new Date(pointTime(row)).getTime())
      .filter((timestamp) => Number.isFinite(timestamp));
    const minTime = timestamps.length ? Math.min(...timestamps) : 0;
    const maxTime = timestamps.length ? Math.max(...timestamps) : 0;
    const timeSpan = Math.max(1, maxTime - minTime);
    lanes.forEach((lane, laneIndex) => {
      const baseline = pad.top + laneIndex * laneHeight + laneHeight - 12;
      const top = pad.top + laneIndex * laneHeight + 8;
      context.strokeStyle = "rgba(143, 185, 153, .14)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(pad.left, baseline);
      context.lineTo(width - pad.right, baseline);
      context.stroke();
      context.fillStyle = chartColor(lane.tone);
      context.font = "700 10px Inter, sans-serif";
      context.textAlign = "right";
      context.fillText(lane.label, pad.left - 8, top + 10);
      if (!lane.rows.length) {
        context.fillStyle = "rgba(110, 131, 116, .8)";
        context.font = "500 10px Inter, sans-serif";
        context.fillText("unavailable", width - pad.right, top + 10);
        return;
      }
      const values = lane.rows.map(externalMetric);
      const max = Math.max(...values, 1);
      const points = lane.rows.map((row, index) => ({
        ...row,
        x: (() => {
          const timestamp = new Date(pointTime(row)).getTime();
          if (!Number.isFinite(timestamp) || !timestamps.length || minTime === maxTime) {
            return lane.rows.length === 1
              ? pad.left + plotWidth / 2
              : pad.left + (index / (lane.rows.length - 1)) * plotWidth;
          }
          return pad.left + ((timestamp - minTime) / timeSpan) * plotWidth;
        })(),
        value: externalMetric(row),
        metric: lane.label,
        unit: lane.unit,
        source: value(row.provider || lane.label),
      }));
      context.strokeStyle = chartColor(lane.tone);
      context.shadowColor = chartColor(lane.tone);
      context.shadowBlur = 6;
      context.lineWidth = 1.8;
      context.beginPath();
      points.forEach((point, index) => {
        const y = baseline - (point.value / max) * Math.max(10, laneHeight - 28);
        if (index === 0) context.moveTo(point.x, y);
        else context.lineTo(point.x, y);
        point.y = y;
      });
      context.stroke();
      context.shadowBlur = 0;
      points.forEach((point) => {
        context.fillStyle = chartColor(lane.tone);
        context.beginPath();
        context.arc(point.x, point.y, 2.5, 0, Math.PI * 2);
        context.fill();
      });
      const selected = selectedIndex(points);
      if (selected >= 0) {
        context.strokeStyle = "rgba(240, 246, 236, .72)";
        context.setLineDash([3, 4]);
        context.beginPath();
        context.moveTo(points[selected].x, top);
        context.lineTo(points[selected].x, baseline);
        context.stroke();
        context.setLineDash([]);
      }
      lane.points = points;
    });
    if (timestamps.length) {
      context.fillStyle = "rgba(110, 131, 116, .8)";
      context.font = "500 10px Inter, sans-serif";
      context.textAlign = "left";
      context.fillText(shortTime(new Date(minTime).toISOString()), pad.left, height - 5);
      context.textAlign = "right";
      context.fillText(shortTime(new Date(maxTime).toISOString()), width - pad.right, height - 5);
    }
    // Pointer/keyboard selection uses one shared time axis.  Keep the merged
    // interaction points ordered by their plotted x coordinate; flattening by
    // lane would make a weather point jump to the end of the cursor range.
    const mergedPoints = lanes
      .flatMap((lane) => lane.points || [])
      .sort((left, right) => {
        const xDelta = number(left.x) - number(right.x);
        if (xDelta !== 0) return xDelta;
        return new Date(pointTime(left)).getTime() - new Date(pointTime(right)).getTime();
      });
    canvas.__chartMeta = {
      points: mergedPoints,
      metric: "External context",
      unit: "",
      source: "NWS / NOAA / AIS",
      left: pad.left,
      right: width - pad.right,
    };
    installChartInteractions(canvas, mergedPoints, "External context", "", "NWS / NOAA / AIS");
  }

  // Kept as a named render entry point for shared cursor selection and future
  // diagram adapters. The chart itself remains a single Dashboard diagram.
  function renderExternalRiskChart() {
    drawExternalRiskChart();
  }

  function renderOperationalCharts(snapshot) {
    const active = document.activeElement;
    const activeCanvasId = active && active.tagName === "CANVAS" ? active.id : "";
    const chartToRestore = activeCanvasId || state.chartCursor?.chartId || focusedChartId();
    const series = reconciliationSeries(snapshot);
    const points = reconciliationPoints(snapshot);
    const labels = lineLabels(points);
    renderDiagramCursorLabels();
    drawLineChart($("dashboard-chart"), [series.expected, series.recorded, series.gap], ["cyan", "lime", "coral"], {
      points,
      metric: "Gap",
      unit: "units",
      source: "synthetic-enterprise-snapshot",
      emptyLabel: "Insufficient live history",
      ...labels,
    });
    // The old chart ID remains as an aria-hidden compatibility surface for the
    // existing smoke client.  It is never mounted as a second visible diagram.
    drawLineChart($("reconciliation-chart"), [series.expected, series.recorded, series.gap], ["cyan", "lime", "coral"], {
      points,
      metric: "Gap",
      unit: "units",
      source: "synthetic-enterprise-snapshot",
      gridColor: "rgba(143, 185, 153, .16)",
    });
    renderMiniChart("queue-health-chart", "queue-health-value", telemetryPoints(snapshot, "queue"), "Queue backlog", "coral");
    renderMiniChart("erp-health-chart", "erp-health-value", telemetryPoints(snapshot, "erp"), "ERP posting", "cyan");
    renderMiniChart("invoice-health-chart", "invoice-health-value", telemetryPoints(snapshot, "invoice"), "Invoice completion", "lime");
    drawExternalRiskChart();
    // The cursor is a single atomic record owned by the physically focused
    // canvas. Reconcile its point and metric metadata only after every chart
    // has received the same SSE snapshot, so a redraw cannot mix one chart's
    // detail with another chart's focused element.
    syncFocusedChartCursor();
    // Never steal focus from a button, link, form field, or rail tab during an
    // SSE redraw. A focused canvas is restored only when it was the physical
    // input target (or when the document itself still owns focus).
    const focusOwner = document.activeElement;
    if (
      chartToRestore
      && (
        !focusOwner
        || focusOwner === document.body
        || focusOwner === document.documentElement
        || focusOwner.tagName === "CANVAS"
      )
    ) restoreChartFocus(chartToRestore);
  }

  function renderLiveMetrics() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const counts = snapshot.unit_counts || {};
    const agentCount = allAgentStates().filter((item) => ["TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "HANDOFF"].includes(item.status)).length;
    const latestTelemetry = state.telemetry.length
      ? state.telemetry[state.telemetry.length - 1]
      : null;
    const values = {
      observedRecords: latestTelemetry
        ? telemetryRecordCount(latestTelemetry)
        : 0,
      queue: number(counts.queue_failed),
      agents: agentCount,
      sequence: state.lastSequence || number(snapshot.projection_sequence),
    };
    const telemetrySequence = latestTelemetry
      ? number(latestTelemetry.sequence, values.sequence)
      : values.sequence;
    [
      ["metric-throughput", values.observedRecords],
      ["metric-queue-depth", values.queue],
      ["metric-active-agents", values.agents],
      ["metric-sequence", values.sequence],
    ].forEach(([id, item]) => { if ($(id)) $(id).textContent = String(item); });
    renderSparkline("spark-throughput", sparklineValues("recorded", snapshot), "lime");
    renderSparkline("spark-queue", sparklineValues("missing", snapshot), "coral");
    renderSparkline("spark-agents", [0, agentCount, agentCount, agentCount], "cyan");
    renderSparkline("spark-ledger", [Math.max(0, telemetrySequence - 3), Math.max(0, telemetrySequence - 1), telemetrySequence], "cyan");
    const flowAgents = $("flow-stat-agents");
    if (flowAgents) flowAgents.textContent = String(agentCount);
    const flowDetail = $("flow-stat-detail");
    if (flowDetail) {
      flowDetail.textContent = latestTelemetry
        ? `${telemetryRecordCount(latestTelemetry)} records observed · event ${value(latestTelemetry.sequence)} · source ledger`
        : "Waiting for the first source observation.";
    }
    const provenanceSequence = $("provenance-sequence");
    if (provenanceSequence) provenanceSequence.textContent = `seq ${values.sequence || "—"}`;
    const provenanceDetail = $("provenance-detail");
    if (provenanceDetail) {
      provenanceDetail.textContent = latestTelemetry
        ? `Synthetic enterprise flow · received ${shortTime(latestTelemetry.received_at || latestTelemetry.observed_at)} · SSE cursor ${value(state.lastSequence || values.sequence)}`
        : "Synthetic enterprise flow · awaiting first observation.";
    }
    renderOperationalCharts(snapshot);
    const timeline = $("reconciliation-timeline");
    if (timeline) {
      timeline.replaceChildren();
      const points = state.telemetry.length
        ? state.telemetry.map((point) => ({
          sequence: point.sequence,
          recorded: number(point.unit_counts?.erp_recorded, number(counts.erp_recorded)),
          missing: number(point.unit_counts?.queue_failed, number(counts.queue_failed)),
        }))
        : Array.isArray(snapshot.reconciliation) ? snapshot.reconciliation : [];
      points.slice(-12).forEach((point) => {
        const mark = create("span", `timeline-mark${number(point.missing) > 0 ? " is-alert" : ""}`);
        mark.title = `#${value(point.sequence)} · ${number(point.recorded)} recorded`;
        timeline.append(mark);
      });
    }
  }

  function renderFlow() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const flow = snapshot.flow || { nodes: [], edges: [] };
    const map = $("flow-map");
    map.replaceChildren();
    const nodes = Array.isArray(flow.nodes) ? flow.nodes : [];
    const edges = Array.isArray(flow.edges) ? flow.edges : [];
    const nodeMap = new Map(nodes.map((item) => [value(item.id), item]));
    const flowSummary = flow.summary || {};
    const snapshotCounts = snapshot.unit_counts && typeof snapshot.unit_counts === "object" ? snapshot.unit_counts : {};
    const expected = number(snapshotCounts.total, number(flowSummary.expected, number(nodeMap.get("warehouse")?.count)));
    const recorded = number(snapshotCounts.erp_recorded, number(flowSummary.recorded, number(nodeMap.get("erp")?.count)));
    const queueException = number(snapshotCounts.queue_failed, number(flowSummary.queue_exception, number(nodeMap.get("message-queue")?.count)));
    $("expected-count").textContent = String(expected);
    $("recorded-count").textContent = String(recorded);
    $("queue-count").textContent = String(queueException);
    const allNodesHealthy = nodes.length > 0 && nodes.every((item) => ["HEALTHY", "RELEASED"].includes(value(item.status).toUpperCase()));
    setBadge($("path-status"), allNodesHealthy ? "Healthy" : "Attention needed", allNodesHealthy ? "HEALTHY" : "ANOMALY");
    const projectedNodes = {
      warehouse: { healthId: "health-warehouse", sourceId: "source-warehouse" },
      "message-queue": { healthId: "health-queue", sourceId: "source-queue", sourceNodeId: "queue" },
      erp: { healthId: "health-erp", sourceId: "source-erp" },
      invoice: { healthId: "health-invoice", sourceId: "source-invoice" },
    };
    nodes.forEach((item) => {
      const projection = projectedNodes[value(item.id)];
      if (!projection) return;
      const count = value(item.id) === "warehouse"
        ? expected
        : value(item.id) === "message-queue"
          ? queueException
          : value(item.id) === "erp"
            ? recorded
            : number(item.count);
      [projection.healthId, projection.sourceId].forEach((id) => {
        const target = $(id);
        if (target) target.textContent = String(count);
      });
      const status = value(item.status).toUpperCase();
      const alert = !["HEALTHY", "RELEASED"].includes(status);
      const sourceNodeId = projection.sourceNodeId || value(item.id);
      document.querySelectorAll(`[data-health-node="${value(item.id)}"], [data-source-node="${sourceNodeId}"]`).forEach((target) => {
        target.classList.toggle("is-alert", alert);
        target.classList.toggle("is-healthy", !alert);
        const icon = target.querySelector(":scope > i:first-child");
        if (icon && target.matches("[data-source-node]")) icon.className = `ph ${alert ? "ph-warning-circle" : "ph-check-circle"}`;
        const stateIcon = target.querySelector(":scope > .health-check, :scope > .source-check");
        if (stateIcon) stateIcon.className = `ph-bold ${alert ? "ph-warning-circle" : "ph-check-circle"} ${target.matches("[data-source-node]") ? "source-check" : "health-check"}`;
      });
    });
    const healthCore = document.querySelector(".health-core");
    if (healthCore) {
      const queueHealthy = value(nodeMap.get("message-queue")?.status).toUpperCase() === "HEALTHY";
      healthCore.classList.toggle("is-alert", !queueHealthy);
      healthCore.classList.toggle("is-healthy", queueHealthy);
    }
    const rightErp = $("health-erp-right");
    if (rightErp) rightErp.textContent = String(recorded);
    nodes.forEach((item, index) => {
      const column = create("div", "flow-column");
      const node = create("article", `flow-node ${stateClass(item.status)}`, null);
      const nodeId = value(item.id);
      const count = nodeId === "warehouse"
        ? expected
        : nodeId === "message-queue"
          ? queueException
          : nodeId === "erp"
            ? recorded
            : number(item.count);
      node.dataset.nodeId = value(item.id);
      node.setAttribute("role", "button");
      node.tabIndex = 0;
      node.setAttribute("aria-label", `${value(item.label)}, ${count} records, ${human(item.status)}`);
      node.addEventListener("click", () => selectFlowEntity(item));
      node.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        selectFlowEntity(item);
      });
      const header = create("div", "flow-node-header");
      const dot = create("span", "node-dot", null);
      dot.setAttribute("aria-hidden", "true");
      const iconName = {
        warehouse: "warehouse",
        "message-queue": "broadcast",
        erp: "database",
        invoice: "invoice",
      }[value(item.id)] || "cube";
      const icon = create("i", `ph ph-${iconName} flow-node-icon`);
      icon.setAttribute("aria-hidden", "true");
      header.append(dot, icon, create("span", "flow-node-label", value(item.label)));
      const badge = create("span", "state-badge", null);
      badge.classList.add(stateClass(item.status));
      const badgeIcon = ["HEALTHY", "RELEASED"].includes(value(item.status).toUpperCase())
        ? "ph-bold ph-check"
        : "ph-bold ph-warning";
      badge.append(create("i", badgeIcon));
      badge.setAttribute("aria-label", value(item.status));
      header.append(badge);
      const countNode = create("strong", "flow-node-count", String(count));
      const erpCount = recorded;
      const semantics = nodeId === "warehouse"
        ? "dispatched"
        : nodeId === "message-queue"
          ? "backlog"
          : nodeId === "erp"
            ? "posted"
            : nodeId === "invoice"
              ? count > erpCount ? "expected" : "completed"
              : "records";
      const countLabel = create("span", "flow-node-count-label", semantics);
      node.setAttribute(
        "aria-label",
        `${value(item.label)}, ${count} ${semantics}, ${human(item.status)}`,
      );
      const inputPort = create("span", "flow-node-port flow-node-port-in");
      inputPort.dataset.port = "in";
      inputPort.setAttribute("aria-hidden", "true");
      const outputPort = create("span", "flow-node-port flow-node-port-out");
      outputPort.dataset.port = "out";
      outputPort.setAttribute("aria-hidden", "true");
      node.append(header, countNode, countLabel, inputPort, outputPort);
      column.append(node);
      if (index < nodes.length - 1) {
        const next = nodes[index + 1];
        const edge = edges.find((candidate) => candidate.from === item.id && candidate.to === next.id);
        if (edge) {
          const telemetryActive = streamIsLive() && state.telemetryPulse;
          const gapEdge = edge.from === "message-queue" && edge.to === "erp" && queueException > 0;
          const link = create("div", `flow-link${state.activeEdges.has(`${edge.from}->${edge.to}`) ? " is-active" : ""}${telemetryActive ? " is-telemetry" : ""}${gapEdge ? " is-gap" : ""}`);
          link.dataset.edge = `${edge.from}->${edge.to}`;
          const throughput = number(edge.throughput, item.id === "warehouse" ? expected : item.id === "message-queue" ? recorded : recorded);
          const width = Math.max(2, Math.min(8, 2 + (throughput / Math.max(expected, 1)) * 6));
          const duration = Math.max(0.65, Math.min(2.4, 1.65 - (throughput / Math.max(expected, 1))));
          const line = create("span", "flow-link-line");
          line.style.setProperty("--flow-width", `${width.toFixed(2)}px`);
          line.style.setProperty("--flow-duration", `${duration.toFixed(2)}s`);
          link.title = `${value(edge.from)} to ${value(edge.to)} · ${throughput} records`;
          const particleLayer = create("span", "flow-particle-layer");
          for (let particleIndex = 0; particleIndex < 5; particleIndex += 1) {
            const particle = create("span", "flow-particle");
            particle.style.setProperty("--particle-delay", `${(particleIndex * duration / 5).toFixed(2)}s`);
            particle.setAttribute("aria-hidden", "true");
            particleLayer.append(particle);
          }
          line.append(particleLayer);
          link.append(line);
          if (gapEdge) {
            const branch = create("span", "flow-gap-branch");
            branch.dataset.missingQuantity = String(queueException);
            branch.append(
              create("span", "flow-gap-branch-line"),
              create("strong", null, `${queueException} missing`),
            );
            link.append(branch);
          }
          column.append(link);
        }
      }
      map.append(column);
    });
    renderUnitDensity();
    renderUnitAnomalies();
    renderUnitDetail();
  }

  function selectUnit(unitId) {
    const id = value(unitId);
    if (!state.units.has(id)) return;
    state.selectedUnitId = id;
    document.querySelectorAll("[data-unit-detail-id]").forEach((item) => {
      const selected = item.dataset.unitDetailId === id;
      item.tabIndex = selected ? 0 : -1;
      item.classList.toggle("is-selected", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    renderUnitAnomalies();
    renderUnitDetail();
  }

  function selectFlowEntity(item) {
    if (!item) return;
    const latest = state.telemetry.length ? state.telemetry[state.telemetry.length - 1] : null;
    const point = {
      sequence: latest ? latest.sequence : number(state.snapshot && state.snapshot.projection_sequence),
      timestamp: latest && (latest.observed_at || latest.captured_at),
      observed_at: latest && (latest.observed_at || latest.captured_at),
      received_at: latest && (latest.received_at || latest.observed_at || latest.captured_at),
      value: number(item.count),
      unit: "records",
      metric: `${value(item.label || item.id)} records`,
      source: "synthetic-enterprise-snapshot",
      entity: value(item.id),
    };
    state.selectedPoint = point;
    state.selectedPointSequence = pointSequence(point);
    renderFlowSelectionDetail(point);
    renderDiagramCursorLabels(point);
    renderOperationalCharts(state.snapshot);
  }

  function renderAgentCard(item, compact) {
    const latestRoleEvent = roleEvents(item.id).at(-1);
    const active = Boolean(
      latestRoleEvent
      && latestRoleEvent.sequence === state.graphEventSequence
      && ["agent.started", "tool.started", "tool.completed", "evidence.returned", "agent.handoff"].includes(eventType(latestRoleEvent)),
    );
    const card = create(compact ? "div" : "button", `agent-card${compact ? " agent-card-compact agent-status-only" : ""}${state.selectedAgentId === item.id ? " is-selected" : ""}`);
    if (!compact) card.type = "button";
    card.dataset.agentId = item.id;
    card.setAttribute("aria-label", `${item.name}, ${human(item.status)}`);
    if (compact) card.setAttribute("role", "status");
    else card.setAttribute("aria-controls", "agent-role-context");
    const top = create("div", "agent-card-top");
    const mark = create("span", `agent-mark ${active ? "is-active" : ""}`, null);
    mark.setAttribute("aria-hidden", "true");
    mark.append(create("i", "ph-bold ph-robot"));
    top.append(mark, create("strong", "agent-card-name", item.name));
    const badge = create("span", `state-badge ${stateClass(item.status)}`, item.status);
    top.append(badge);
    card.append(top);
    const stats = create("span", "agent-card-stats", `${countLabel(item.tools, "tool")} · ${countLabel(item.evidence, "evidence")}${item.handoff ? " · handoff" : ""}`);
    if (!compact) card.setAttribute("aria-pressed", String(state.selectedAgentId === item.id));
    if (compact) card.append(create("span", "agent-card-focus", item.focus), stats);
    if (!compact) {
      card.append(
        create("span", "graph-port graph-port-in", null),
        create("span", "graph-port graph-port-control-in", null),
        create("span", "graph-port graph-port-out", null),
      );
      card.querySelector(".graph-port-in").dataset.port = `${item.id}-in`;
      card.querySelector(".graph-port-control-in").dataset.port = `${item.id}-control-in`;
      card.querySelector(".graph-port-out").dataset.port = `${item.id}-out`;
      card.querySelectorAll(".graph-port").forEach((port) => port.setAttribute("aria-hidden", "true"));
      card.addEventListener("click", () => {
        selectAgent(item.id, false);
      });
    }
    return card;
  }

  function selectAgent(id, navigateToWorkspace = false) {
    state.selectedAgentId = value(id);
    // Keep the selected role explicit for the next conversational turn. The
    // server still owns the answer and evidence; this client context only
    // tells the operator which investigator they are addressing.
    if (navigateToWorkspace && state.view !== "agent") {
      setView("agent");
      return;
    }
    renderAll();
  }

  function selectedAgent() {
    if (!state.selectedAgentId || state.selectedAgentId === "orchestrator") return null;
    return allAgentStates().find((item) => item.id === state.selectedAgentId) || null;
  }

  function renderRoleContext() {
    const name = $("agent-role-name");
    const mission = $("agent-role-mission");
    const task = $("agent-role-task");
    const tools = $("agent-role-tools");
    const hypothesis = $("agent-role-hypothesis");
    const evidence = $("agent-role-evidence");
    const badge = $("agent-role-status");
    const title = $("copilot-chat-title") || $("copilot-title");
    const input = $("chat-input");
    const contextPill = $("chat-context-pill");
    if (!name || !mission || !task || !tools || !hypothesis || !evidence || !badge || !title || !input) return;
    const item = selectedAgent();
    if (!item) {
      const orchestration = orchestratorStatus();
      const advisory = advisoryContext();
      name.textContent = "Agent team";
      mission.textContent = "Coordinates the investigation and control loop.";
      task.textContent = advisory.partial
        ? advisory.warning || "AI_CITATION_CLOSURE_INCOMPLETE"
        : isClosedOrRecovery() ? "Investigation complete" : orchestration.detail;
      const toolCount = allAgentStates().reduce((total, agent) => total + agent.tools, 0);
      tools.textContent = toolCount ? countLabel(toolCount, "tool result") : "—";
      hypothesis.textContent = advisory.partial
        ? `${advisory.selectedHypothesis || "UNKNOWN"} · PARTIAL`
        : advisory.selectedHypothesis
          ? advisory.selectedHypothesis
          : isClosedOrRecovery() ? "UNKNOWN" : "Team synthesis pending";
      const evidenceCount = allAgentStates().reduce((total, agent) => total + agent.evidence, 0);
      evidence.textContent = advisory.partial
        ? "AI PARTIAL"
        : evidenceCount ? countLabel(evidenceCount, "evidence") : "—";
      setBadge(badge, advisory.partial ? "PARTIAL" : "TEAM MODE", advisory.partial ? "PARTIAL" : orchestration.raw);
      title.textContent = "Ask the agent team";
      input.placeholder = "Ask the agent team about this incident…";
      if (contextPill) {
        contextPill.textContent = "Team context · all investigators";
        contextPill.dataset.agentId = "orchestrator";
      }
      const orchestrator = $("orchestrator-node");
      if (orchestrator) orchestrator.setAttribute("aria-pressed", "true");
      renderAdvisoryTruth(document.querySelector("#agent-role-context"), advisory);
      syncRoleContextVisibility();
      return;
    }
    name.textContent = item.name;
    mission.textContent = item.mission;
    task.textContent = item.currentTask;
    tools.textContent = item.toolNames.length ? item.toolNames.map(human).join(", ") : "—";
    const advisory = advisoryContext();
    const itemHypothesis = item.hypothesis || advisory.selectedHypothesis;
    hypothesis.textContent = itemHypothesis
      ? `${human(itemHypothesis)}${item.confidence ? ` · ${human(item.confidence)}` : ""}`
      : isClosedOrRecovery() ? "UNKNOWN" : "No hypothesis yet";
    evidence.textContent = item.evidenceIds.length ? countLabel(item.evidenceIds.length, "record") : "—";
    setBadge(badge, item.status, item.status);
    title.textContent = `Ask ${item.name}`;
    input.placeholder = `Ask ${item.name} about this incident…`;
    if (contextPill) {
      contextPill.textContent = `Role context · ${item.name}`;
      contextPill.dataset.agentId = item.id;
    }
    const orchestrator = $("orchestrator-node");
    if (orchestrator) orchestrator.setAttribute("aria-pressed", "false");
    renderAdvisoryTruth(document.querySelector("#agent-role-context"), advisory);
    syncRoleContextVisibility();
  }

  function syncRoleContextVisibility() {
    const contextGrid = document.querySelector("#agent-role-context .agent-role-grid");
    if (contextGrid) {
      contextGrid.hidden = isNormalScenario();
      contextGrid.querySelectorAll("div").forEach((field) => {
        const content = value(field.querySelector("strong") && field.querySelector("strong").textContent);
        field.hidden = !content || ["—", "None yet", "No hypothesis yet", "Team synthesis pending"].includes(content);
      });
    }
    const healthyPanel = $("healthy-workspace-state");
    if (healthyPanel) healthyPanel.hidden = !isNormalScenario();
  }

  function renderDashboardAgents() {
    const dashboard = $("dashboard-agents");
    if (!dashboard) return;
    dashboard.replaceChildren();
    const agents = isNormalScenario()
      ? []
      : allAgentStates().filter((item) => ["TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "HANDOFF", "COMPLETE", "DEGRADED"].includes(item.status));
    agents.forEach((item) => dashboard.append(renderAgentCard(item, true)));
    const active = agents.filter((item) => ["TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "HANDOFF"].includes(item.status)).length;
    const activeCount = $("active-agent-count");
    if (activeCount) {
      activeCount.className = `rail-count${active ? " is-active" : ""}`;
      activeCount.textContent = `${active} active`;
    }
  }

  function graphPoint(element, side, hostRect) {
    const rect = element.getBoundingClientRect();
    const left = rect.left - hostRect.left;
    const top = rect.top - hostRect.top;
    const points = {
      center: [left + rect.width / 2, top + rect.height / 2],
      top: [left + rect.width / 2, top],
      right: [left + rect.width, top + rect.height / 2],
      bottom: [left + rect.width / 2, top + rect.height],
      left: [left, top + rect.height / 2],
    };
    return points[side] || points.right;
  }

  function graphRouteContract() {
    return {
      incident: { kind: "cubic-bezier", lane: "outer-upper" },
      source: { kind: "cubic-bezier", lane: "source-column" },
      orchestrator: { kind: "cubic-bezier", lane: "coordination-bus" },
      investigator: { kind: "cubic-bezier", lane: "handoff-lane" },
      synthesis: { kind: "cubic-bezier", lane: "lifecycle-entry" },
      lifecycle: { kind: "cubic-bezier", lane: "lifecycle-chain" },
      return: { kind: "cubic-bezier", lane: "outer-return" },
    };
  }

  function graphRouteSegments(route, anchors, metrics) {
    const { x1, y1, x2, y2 } = anchors;
    const width = number(metrics.width, 0);
    const graphHeight = number(metrics.height, 0);
    const cardTop = number(metrics.cardTop, Math.max(y1, y2));
    const cardBottom = number(metrics.cardBottom, cardTop);
    const sourceTop = number(metrics.sourceTop, 0);
    const sourceBottom = number(metrics.sourceBottom, sourceTop);
    if (route.type === "incident") {
      // Lift immediately beside the compact incident badge, then run one
      // smooth upper bus above the source row. This keeps the incident lane
      // clear of every source card without asking the other three vertical
      // source lanes to detour.
      const upperLane = Math.max(8, sourceTop - 14);
      const liftX = x1 + 14;
      const run = x2 - liftX;
      const span = run * .35;
      return [
        [[x1, y1], [x1, y1 + (upperLane - y1) * .45], [liftX - 4, upperLane], [liftX, upperLane]],
        [[liftX, upperLane], [liftX + span, upperLane], [x2 - span, upperLane], [x2, y2]],
      ];
    }
    if (route.type === "source") {
      if (route.lane === "source-center") {
        const orchestratorLeft = number(metrics.orchestratorLeft, x1 - 60);
        const orchestratorRight = number(metrics.orchestratorRight, x1 + 60);
        const clearX = Math.min(width - 18, orchestratorRight + 12);
        const clearTop = number(metrics.orchestratorTop, y1);
        const clearBottom = number(metrics.orchestratorBottom, y1);
        const topJunction = clearTop - 10;
        const bottomJunction = clearBottom + 10;
        return [
          [[x1, y1], [x1 + (clearX - x1) * .35, y1], [clearX, topJunction - 18], [clearX, topJunction]],
          [[clearX, topJunction], [clearX, topJunction + 32], [clearX, bottomJunction - 32], [clearX, bottomJunction]],
          [[clearX, bottomJunction], [clearX, bottomJunction + 18], [x2 + (clearX - x2) * .35, y2 - (y2 - bottomJunction) * .35], [x2, y2]],
        ];
      }
      const span = (y2 - y1) * .35;
      return [[[x1, y1], [x1 + (x2 - x1) * .35, y1 + span], [x2 - (x2 - x1) * .35, y2 - span], [x2, y2]]];
    }
    if (route.type === "orchestrator") {
      const spanX = (x2 - x1) * .35;
      const spanY = (y2 - y1) * .35;
      return [[[x1, y1], [x1 + spanX, y1 + spanY], [x2 - spanX, y2 - spanY], [x2, y2]]];
    }
    if (route.type === "investigator") {
      const spanX = (x2 - x1) * .35;
      const spanY = (y2 - y1) * .35;
      return [[[x1, y1], [x1 + spanX, y1 + spanY], [x2 - spanX, y2 - spanY], [x2, y2]]];
    }
    if (route.type === "lifecycle") {
      const span = (x2 - x1) * .35;
      return [[[x1, y1], [x1 + span, y1], [x2 - span, y2], [x2, y2]]];
    }
    if (route.type === "synthesis") {
      const spanX = (x2 - x1) * .35;
      const spanY = (y2 - y1) * .35;
      return [[[x1, y1], [x1 + spanX, y1 + spanY], [x2 - spanX, y2 - spanY], [x2, y2]]];
    }
    if (route.type === "return") {
      const rightOuter = Math.max(10, width - 8);
      const leftOuter = number(metrics.returnOuterLeft, 8);
      const bottomOuter = Math.min(graphHeight - 14, number(metrics.returnBottom, graphHeight - 18));
      const outerSpan = rightOuter - x1;
      return [
        [[x1, y1], [x1 + outerSpan * .35, y1 + 18], [rightOuter - outerSpan * .35, bottomOuter - 28], [rightOuter, bottomOuter]],
        [[rightOuter, bottomOuter], [width * .56, bottomOuter], [leftOuter + 40, bottomOuter], [leftOuter, bottomOuter]],
        [[leftOuter, bottomOuter], [leftOuter, y2 + 82], [x2 - (x2 - leftOuter) * .35, y2 + 48], [x2, y2]],
      ];
    }
    return [[[x1, y1], [x1, y1 + 32], [x2, y2 - 32], [x2, y2]]];
  }

  function graphCubicPoint(segment, progress) {
    const [start, controlOne, controlTwo, end] = segment;
    const t = Math.max(0, Math.min(1, progress));
    const inverse = 1 - t;
    return [
      inverse ** 3 * start[0]
        + 3 * inverse ** 2 * t * controlOne[0]
        + 3 * inverse * t ** 2 * controlTwo[0]
        + t ** 3 * end[0],
      inverse ** 3 * start[1]
        + 3 * inverse ** 2 * t * controlOne[1]
        + 3 * inverse * t ** 2 * controlTwo[1]
        + t ** 3 * end[1],
    ];
  }

  function graphRoutePoints(route, anchors, metrics) {
    return graphRouteSegments(route, anchors, metrics).flatMap((segment, index) => {
      const samples = Array.from({ length: 17 }, (_, sample) => graphCubicPoint(segment, sample / 16));
      return index ? samples.slice(1) : samples;
    });
  }

  function graphRoutePath(route, anchors, metrics) {
    return graphRouteSegments(route, anchors, metrics).map((segment, index) => {
      const [start, controlOne, controlTwo, end] = segment;
      const command = index ? "C" : `M ${start[0].toFixed(2)} ${start[1].toFixed(2)} C`;
      return `${command} ${controlOne[0].toFixed(2)} ${controlOne[1].toFixed(2)} ${controlTwo[0].toFixed(2)} ${controlTwo[1].toFixed(2)} ${end[0].toFixed(2)} ${end[1].toFixed(2)}`;
    }).join(" ");
  }

  function graphEventPathIds(event) {
    const type = eventType(event);
    const actor = value(event && event.actor);
    const path = new Set();
    const actorEdge = actor && actor !== "orchestrator" ? actor : "";
    if (["telemetry.observed", "source.condition.injected"].includes(type)) {
      path.add("verification->incident-packet");
      return path;
    }
    if (["incident.detected", "investigation.started"].includes(type)) {
      path.add("incident-packet->orchestrator");
      return path;
    }
    if (["agent.started", "tool.started"].includes(type) && actorEdge) {
      path.add(`orchestrator->${actorEdge}`);
      return path;
    }
    if (["tool.completed", "evidence.returned"].includes(type) && actorEdge) {
      path.add(`${actorEdge}->synthesis`);
      path.add(`source-${actorEdge}->${actorEdge}`);
      return path;
    }
    if (type === "agent.handoff" && actorEdge) {
      path.add(`${actorEdge}->synthesis`);
      return path;
    }
    if (["synthesis.started", "synthesis.completed"].includes(type)) {
      path.add("synthesis->safety");
      return path;
    }
    if (["evaluation.started", "evaluation.completed"].includes(type)) {
      path.add("synthesis->safety");
      if (type === "evaluation.completed") path.add("safety->approval");
      return path;
    }
    if (type === "recovery.prepared") {
      path.add("safety->approval");
      return path;
    }
    if (["approval.requested", "approval.recorded"].includes(type)) {
      path.add("safety->approval");
      return path;
    }
    if (["execution.started", "execution.completed"].includes(type)) {
      path.add("approval->execution");
      return path;
    }
    if (type === "verification.completed") {
      path.add("execution->verification");
      path.add("verification->incident-packet");
      return path;
    }
    if (["provider.degraded", "workflow.blocked"].includes(type)) {
      path.add("synthesis->safety");
    }
    return path;
  }

  function graphPathForAgent(agentId) {
    return new Set([
      "incident-packet->orchestrator",
      `source-${agentId}->${agentId}`,
      `orchestrator->${agentId}`,
      `${agentId}->synthesis`,
      "synthesis->safety",
      "safety->approval",
      "approval->execution",
      "execution->verification",
      "verification->incident-packet",
    ]);
  }

  function graphPort(node, selector) {
    if (!node) return null;
    return node.matches(selector) ? node : node.querySelector(selector);
  }

  function drawGraphConnections(agents) {
    const graph = $("agent-graph");
    const links = $("agent-graph-links");
    const orchestrator = $("orchestrator-node");
    const synthesis = $("synthesis-node");
    const incidentPacket = $("incident-packet-node");
    if (!graph || !links || !orchestrator || !synthesis || !incidentPacket) return;
    const hostRect = graph.getBoundingClientRect();
    if (!hostRect.width || !hostRect.height) return;
    const latestEvent = state.events[state.events.length - 1];
    const eventPaths = latestEvent && latestEvent.sequence === state.graphEventSequence
      ? graphEventPathIds(latestEvent)
      : new Set();
    const selectedPaths = state.selectedAgentId && state.selectedAgentId !== "orchestrator"
      ? graphPathForAgent(state.selectedAgentId)
      : null;
    const routes = [];
    const contract = graphRouteContract();
    const add = (id, from, fromPort, to, toPort, type, lane) => routes.push({ id, from, fromPort, to, toPort, type, lane });
    add("incident-packet->orchestrator", incidentPacket, ".graph-port-out", orchestrator, ".graph-port-in", "incident", "incident-bus");
    agents.forEach((agent) => {
      const card = graph.querySelector(`.agent-nodes [data-agent-id="${CSS.escape(agent.id)}"]`);
      const sourceGroup = agent.id === "retryable_message_investigator"
        ? "receipt-retry"
        : agent.id === "short_shipment_investigator"
          ? "shipment-evidence"
          : "duplicate-posting";
      const sourceKey = agent.id === "retryable_message_investigator" ? "queue" : agent.id === "short_shipment_investigator" ? "shipment" : "duplicate";
      const source = graph.querySelector(`[data-source-group="${CSS.escape(sourceGroup)}"], [data-graph-source="${CSS.escape(sourceKey)}"]`);
      if (!card || !source) return;
      const sourceLane = agent.id === "short_shipment_investigator" ? "source-center" : "source-column";
      const coordinationLane = agent.id === "retryable_message_investigator"
        ? "coord-left"
        : agent.id === "short_shipment_investigator"
          ? "coord-middle"
          : "coord-right";
      add(`source-${agent.id}->${agent.id}`, source, ".graph-port-out", card, ".graph-port-in", "source", sourceLane);
      const orchestrationPort = coordinationLane === "coord-left"
        ? ".graph-port-coordination-left"
        : coordinationLane === "coord-middle"
          ? ".graph-port-coordination-middle"
          : ".graph-port-coordination-right";
      const synthesisPort = agent.id === "retryable_message_investigator"
        ? ".graph-port-synthesis-left"
        : agent.id === "short_shipment_investigator"
          ? ".graph-port-synthesis-middle"
          : ".graph-port-synthesis-right";
      add(`orchestrator->${agent.id}`, orchestrator, orchestrationPort, card, ".graph-port-control-in", "orchestrator", coordinationLane);
      add(`${agent.id}->synthesis`, card, ".graph-port-out", synthesis, synthesisPort, "investigator", "handoff");
    });
    const safety = graph.querySelector('[data-graph-node="safety"]');
    const approval = graph.querySelector('[data-graph-node="approval"]');
    const execution = graph.querySelector('[data-graph-node="execution"]');
    const verification = graph.querySelector('[data-graph-node="verification"]');
    add("synthesis->safety", synthesis, ".graph-port-out", safety, ".graph-port-in", "synthesis", "lifecycle-entry");
    add("safety->approval", safety, ".graph-port-out", approval, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("approval->execution", approval, ".graph-port-out", execution, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("execution->verification", execution, ".graph-port-out", verification, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("verification->incident-packet", verification, ".graph-port-out", incidentPacket, ".graph-port-in", "return", "outer-return");
    const relativeRect = (element) => {
      const rect = element && element.getBoundingClientRect();
      if (!rect) return null;
      return {
        left: rect.left - hostRect.left,
        top: rect.top - hostRect.top,
        right: rect.right - hostRect.left,
        bottom: rect.bottom - hostRect.top,
      };
    };
    const sourceRects = [...graph.querySelectorAll(".graph-source-group")].map(relativeRect).filter(Boolean);
    const cardRects = [...graph.querySelectorAll(".agent-nodes .agent-card")].map(relativeRect).filter(Boolean);
    const packetRect = relativeRect(incidentPacket) || {};
    const orchestratorRect = relativeRect(orchestrator) || {};
    const lifecycleRect = relativeRect(graph.querySelector(".graph-lifecycle")) || {};
    const metrics = {
      width: hostRect.width,
      height: hostRect.height,
      sourceTop: sourceRects.length ? Math.min(...sourceRects.map((rect) => rect.top)) : 0,
      sourceBottom: sourceRects.length ? Math.max(...sourceRects.map((rect) => rect.bottom)) : 0,
      sourceGap: sourceRects.length > 1 ? (sourceRects[0].right + sourceRects[1].left) / 2 : hostRect.width / 3,
      cardTop: cardRects.length ? Math.min(...cardRects.map((rect) => rect.top)) : 0,
      cardBottom: cardRects.length ? Math.max(...cardRects.map((rect) => rect.bottom)) : 0,
      lifecycleTop: lifecycleRect.top,
      packetLeft: packetRect.left,
      packetRight: packetRect.right,
      orchestratorLeft: orchestratorRect.left,
      orchestratorRight: orchestratorRect.right,
      orchestratorTop: orchestratorRect.top,
      orchestratorBottom: orchestratorRect.bottom,
      incidentOuterLeft: Math.max(6, packetRect.left - 8),
      returnOuterLeft: 4,
      returnBottom: hostRect.height - 22,
    };
    routes.forEach((route) => {
      const from = graphPort(route.from, route.fromPort);
      const to = graphPort(route.to, route.toPort);
      if (!from || !to) return;
      const [x1, y1] = graphPoint(from, "center", hostRect);
      const [x2, y2] = graphPoint(to, "center", hostRect);
      const selected = !selectedPaths || selectedPaths.has(route.id);
      const points = graphRoutePoints(route, { x1, y1, x2, y2 }, metrics);
      const path = graphRoutePath(route, { x1, y1, x2, y2 }, metrics);
      appendGraphLink(links, {
        from: route.id.split("->")[0],
        to: route.id.split("->")[1],
        id: route.id,
        x1,
        y1,
        x2,
        y2,
        points,
        path,
        routeContract: { ...contract[route.type], lane: route.lane },
        selected,
        eventActive: eventPaths.has(route.id),
        eventSequence: latestEvent ? latestEvent.sequence : 0,
        hostWidth: hostRect.width,
        hostHeight: hostRect.height,
      });
    });
  }

  function appendGraphLink(host, options) {
    const points = Array.isArray(options.points) && options.points.length > 1
      ? options.points
      : [[options.x1, options.y1], [options.x2, options.y2]];
    const link = create("span", `agent-link${options.selected ? " is-selected-route" : " is-muted"}${options.eventActive ? " is-event" : ""}`);
    link.dataset.from = options.from;
    link.dataset.to = options.to;
    link.dataset.edge = value(options.id || `${options.from}->${options.to}`);
    link.dataset.eventSequence = value(options.eventSequence || "");
    if (options.routeContract) {
      link.dataset.routeKind = value(options.routeContract.kind);
      link.dataset.routeLane = value(options.routeContract.lane);
    }
    link.style.left = "0";
    link.style.top = "0";
    link.style.width = "100%";
    link.style.height = "100%";
    link.dataset.routePoints = points.map(([x, y]) => `${Math.round(x)},${Math.round(y)}`).join(" ");
    link.dataset.routePath = value(options.path || "");
    const width = Math.max(1, number(options.hostWidth, 1));
    const height = Math.max(1, number(options.hostHeight, 1));
    const path = value(options.path || `M ${options.x1} ${options.y1} L ${options.x2} ${options.y2}`);
    const pulse = options.eventActive && points.length > 8
      ? (() => {
        const reducedMotion = typeof window !== "undefined"
          && window.matchMedia
          && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (reducedMotion) {
          const midpoint = points[Math.floor(points.length / 2)];
          return `<circle class="graph-link-pulse" cx="${midpoint[0].toFixed(2)}" cy="${midpoint[1].toFixed(2)}" r="3"></circle>`;
        }
        return `<circle class="graph-link-pulse" cx="0" cy="0" r="3"><animateMotion dur="740ms" begin="0s" repeatCount="1" path="${path}"></animateMotion></circle>`;
      })()
      : "";
    link.innerHTML = `<svg class="graph-route-svg" viewBox="0 0 ${width.toFixed(2)} ${height.toFixed(2)}" preserveAspectRatio="none" aria-hidden="true"><path class="graph-route-path" d="${path}"></path>${pulse}</svg>`;
    host.append(link);
  }

  function renderOperationItem(item) {
    const row = create("li", `operation-item operation-${slug(eventType(item))}`);
    const dot = create("span", `operation-dot ${stateClass(item.status)}`, null);
    dot.setAttribute("aria-hidden", "true");
    const copy = create("div", "operation-copy");
    copy.append(create("strong", null, eventLabel(item)), create("span", null, eventDetail(item)));
    const meta = create("span", "operation-meta", `#${value(item.sequence).padStart(2, "0")} · ${shortTime(item.occurred_at)}`);
    row.append(dot, copy, meta);
    return row;
  }

  function renderAgentGraph() {
    const agents = allAgentStates();
    const container = $("agent-nodes");
    if (!container) return;
    container.replaceChildren();
    agents.forEach((item) => container.append(renderAgentCard(item, false)));
    const links = $("agent-graph-links");
    if (links) {
      links.replaceChildren();
      drawGraphConnections(agents);
    }
    const orchestration = orchestratorStatus();
    const orchestratorNode = $("orchestrator-node");
    if (orchestratorNode) {
      orchestratorNode.classList.toggle("is-selected", !state.selectedAgentId || state.selectedAgentId === "orchestrator");
      orchestratorNode.setAttribute("aria-pressed", String(!state.selectedAgentId || state.selectedAgentId === "orchestrator"));
      orchestratorNode.onclick = () => selectAgent("orchestrator");
      orchestratorNode.onkeydown = (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        selectAgent("orchestrator");
      };
    }
    const pulse = document.querySelector(".node-pulse");
    const latestEvent = state.events[state.events.length - 1];
    const eventPaths = latestEvent && latestEvent.sequence === state.graphEventSequence
      ? graphEventPathIds(latestEvent)
      : new Set();
    if (pulse) pulse.classList.toggle("is-active", eventPaths.has("incident-packet->orchestrator") || eventPaths.has("synthesis->safety"));
    setBadge($("orchestrator-status"), orchestration.label, orchestration.raw);
    const synthesis = synthesisStatus();
    setBadge($("synthesis-status"), synthesis.label, synthesis.raw);
    const packet = $("incident-packet-node");
    if (packet) {
      packet.classList.toggle("is-alert", hasIncidentDetected() && !isClosedOrRecovery());
    }
    const supplyChain = supplyChainStatus();
    setBadge($("workspace-state"), supplyChain.label, supplyChain.raw);
    const operations = state.events.filter((item) => OPERATION_TYPES.has(eventType(item)) || ["copilot.message", "provider.degraded", "workflow.blocked"].includes(eventType(item)));
    const activityRows = operations.length ? operations : state.events;
    $("operation-count").textContent = operations.length
      ? `${operations.length} events`
      : activityRows.length
        ? `${activityRows.length} persisted events`
        : "Current stream";
    const feed = $("operation-feed");
    if (!feed) return;
    feed.replaceChildren();
    const filtered = state.selectedAgentId && state.selectedAgentId !== "orchestrator"
      ? activityRows.filter((item) => roleEvents(state.selectedAgentId).includes(item))
      : activityRows;
    // The legacy "No activity yet" copy is intentionally not rendered for an
    // incident: an empty role window is distinct from an empty incident ledger.
    filtered.slice(-8).reverse().forEach((item) => feed.append(renderOperationItem(item)));
    if (!filtered.length) {
      feed.append(create(
        "li",
        "empty-state",
        activityRows.length
          ? state.selectedAgentId && state.selectedAgentId !== "orchestrator"
            ? "No selected-role events in the current ledger window"
            : "Current stream has no activity rows"
          : "Current stream",
      ));
    }
    const fullFeed = $("full-operation-feed");
    if (fullFeed) {
      fullFeed.replaceChildren();
      filtered.slice().reverse().forEach((item) => fullFeed.append(renderOperationItem(item)));
      if (!filtered.length) {
        fullFeed.append(create(
          "li",
          "empty-state",
          activityRows.length
            ? state.selectedAgentId && state.selectedAgentId !== "orchestrator"
              ? "No selected-role events in the current ledger window"
              : "Current stream has no activity rows"
            : "Current stream",
        ));
      }
    }
    const lifecycleEvents = {
      safety: ["evaluation.started", "evaluation.completed", "workflow.blocked"],
      approval: ["approval.requested", "approval.recorded"],
      execution: ["execution.started", "execution.completed"],
      verification: ["verification.completed"],
    };
    const latestLifecycle = [...state.events].reverse().find((event) => Object.values(lifecycleEvents).some((types) => types.includes(eventType(event))));
    const latestType = latestLifecycle ? eventType(latestLifecycle) : "";
    const snapshot = state.snapshot || {};
    const approval = snapshot.approval || {};
    const execution = snapshot.execution || {};
    const persisted = persistedLifecycleProjection();
    const hasVerification = state.events.some((event) => eventType(event) === "verification.completed");
    const lifecycleDone = {
      safety: persisted.stagesComplete || state.events.some((event) => eventType(event) === "evaluation.completed" && !["BLOCKED", "ABSTAINED"].includes(value(event.status).toUpperCase())),
      approval: persisted.stagesComplete || value(approval.status).toUpperCase() === "GRANTED" || persisted.approvalConsumed,
      execution: persisted.stagesComplete || state.events.some((event) => eventType(event) === "execution.completed") || value(execution.status).toUpperCase() === "COMPLETE",
      verification: persisted.stagesComplete || (hasVerification && Boolean(execution.verified)),
    };
    const latestStep = Object.entries(lifecycleEvents).find(([, types]) => types.includes(latestType));
    document.querySelectorAll("[data-graph-step]").forEach((step) => {
      const name = step.dataset.graphStep;
      const done = Boolean(lifecycleDone[name]);
      const active = latestStep && latestStep[0] === name && !done;
      step.classList.toggle("is-done", done);
      step.classList.toggle("is-active", Boolean(active));
      const statusNode = step.querySelector("[data-graph-step-status]");
      if (statusNode) {
        const status = done ? "COMPLETE" : active ? "ACTIVE" : "MONITORING";
        statusNode.textContent = status;
      }
    });
    renderRoleContext();
    renderEvidencePackets();
  }

  function renderEvidencePackets() {
    const container = $("evidence-packets");
    const status = $("evidence-status");
    container.replaceChildren();
    if (status) {
      status.hidden = true;
      status.textContent = "";
    }
    const evidenceEvents = state.events.filter((item) => eventType(item) === "evidence.returned");
    const renderedIds = new Set();
    const durableEvidence = state.snapshot && Array.isArray(state.snapshot.evidence)
      ? state.snapshot.evidence
      : [];
    if (!evidenceEvents.length && !durableEvidence.length) return;
    const catalog = new Map();
    durableEvidence.forEach((item) => {
      const id = value(item && item.evidence_id);
      if (id) catalog.set(id, item);
    });
    evidenceEvents.forEach((event) => {
      const ids = Array.isArray(event.payload && event.payload.evidence_ids) ? event.payload.evidence_ids : [];
      ids.forEach((id) => {
        const evidenceId = value(id);
        if (evidenceId && !catalog.has(evidenceId)) catalog.set(evidenceId, { evidence_id: evidenceId });
      });
    });
    const heading = create("div", "evidence-heading");
    heading.append(
      create("span", "panel-label", "EVIDENCE PACKETS"),
      create("span", "sequence-label", `${countLabel(catalog.size || durableEvidence.length || evidenceEvents.length, "record")} admitted`),
    );
    container.append(heading);
    evidenceEvents.slice(-6).reverse().forEach((event) => {
      const ids = Array.isArray(event.payload && event.payload.evidence_ids) ? event.payload.evidence_ids : [];
      const card = create("article", "evidence-packet");
      const top = create("div", "evidence-packet-top");
      top.append(
        create("strong", null, agentDefinition(event.actor).name),
        create("span", "state-badge state-cyan", countLabel(ids.length, "ID")),
      );
      const list = create("div", "evidence-id-list");
      ids.forEach((id) => {
        const evidenceId = value(id);
        // A citation must resolve to one durable target, not several visually
        // identical event projections. Prefer the first (latest event) record
        // and let the durable-evidence pass below add IDs that were not in the
        // visible event window.
        if (!evidenceId || renderedIds.has(evidenceId)) return;
        renderedIds.add(evidenceId);
        const item = catalog.get(evidenceId) || { evidence_id: evidenceId };
        const record = create("div", "evidence-record");
        record.dataset.evidenceId = evidenceId;
        record.tabIndex = -1;
        record.setAttribute("role", "group");
        record.setAttribute("aria-label", `Evidence ${evidenceId}`);
        const code = create("code", "evidence-record-id", evidenceId);
        const view = evidencePresentation(item, event);
        const fields = create("dl", "evidence-record-fields");
        [["Source", view.source], ["Observation", view.observation], ["Supports", view.supported], ["Integrity", view.integrity]].forEach(([label, text]) => {
          fields.append(create("dt", null, label), create("dd", null, text));
        });
        record.append(code, fields);
        list.append(record);
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
      const top = create("div", "evidence-packet-top");
      top.append(create("strong", null, human(item.source_type || "Authoritative record")), create("span", "state-badge state-cyan", "READ"));
      const list = create("div", "evidence-id-list");
      const record = create("div", "evidence-record");
      record.dataset.evidenceId = evidenceId;
      record.tabIndex = -1;
      record.setAttribute("role", "group");
      record.setAttribute("aria-label", `Evidence ${evidenceId}`);
      const code = create("code", "evidence-record-id", evidenceId);
      const view = evidencePresentation(item, null);
      const fields = create("dl", "evidence-record-fields");
      [["Source", view.source], ["Observation", view.observation], ["Supports", view.supported], ["Integrity", view.integrity]].forEach(([label, text]) => {
        fields.append(create("dt", null, label), create("dd", null, text));
      });
      record.append(code, fields);
      list.append(record);
      card.append(top, list);
      container.append(card);
    });
    applyEvidenceFocus(false);
  }

  function applyEvidenceFocus(shouldFocus = false) {
    const requestedId = value(state.focusedEvidenceId).trim();
    const records = [...document.querySelectorAll(".evidence-record[data-evidence-id]")];
    let target = null;
    records.forEach((record) => {
      const selected = Boolean(requestedId) && record.dataset.evidenceId === requestedId && !target;
      record.classList.toggle("is-focused", selected);
      if (selected) {
        target = record;
        record.setAttribute("aria-current", "true");
        record.dataset.focused = "true";
      } else {
        record.removeAttribute("aria-current");
        delete record.dataset.focused;
      }
    });
    if (!target || !shouldFocus) return target;
    try {
      target.focus({ preventScroll: true });
    } catch (_error) {
      target.focus();
    }
    target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    return target;
  }

  function evidencePresentation(item, event) {
    const sourceType = value(item && item.source_type).toUpperCase();
    const fields = item && item.admitted_fields && typeof item.admitted_fields === "object"
      ? item.admitted_fields
      : {};
    const sourceNames = {
      FAILED_MESSAGE_QUEUE: "Message queue",
      WAREHOUSE: "Warehouse receipt",
      ERP_RECEIPT: "ERP receipt",
      INVOICE: "Invoice",
      MATERIAL_DOCUMENT: "Material documents",
      KNOWLEDGE_BASE: "Knowledge record",
    };
    const source = sourceNames[sourceType] || (event ? `${agentDefinition(event.actor).name} packet` : "Authoritative record");
    const quantity = fields.quantity == null ? "" : `${value(fields.quantity)} units`;
    const status = fields.status == null ? "" : `status ${human(fields.status)}`;
    const observation = [quantity, status].filter(Boolean).join(" · ")
      || (sourceType === "MATERIAL_DOCUMENT" ? "No material-document record admitted" : "Authoritative observation recorded");
    const supported = {
      FAILED_MESSAGE_QUEUE: "Tests whether the failed message can be safely restarted.",
      WAREHOUSE: "Supports the quantity dispatched from the warehouse.",
      ERP_RECEIPT: "Supports the quantity currently posted in ERP.",
      INVOICE: "Supports the invoice state for this shipment.",
      MATERIAL_DOCUMENT: "Checks for a duplicate or existing material posting.",
    }[sourceType] || "Part of the admitted case evidence.";
    const digest = value(item && item.content_digest);
    const integrity = /^[0-9a-f]{64}$/i.test(digest)
      ? "Digest verified"
      : "Integrity unavailable · fail closed";
    return { source, observation, supported, integrity };
  }

  function renderLatestEvent() {
    const latest = state.events[state.events.length - 1];
    const latestNode = $("latest-event");
    latestNode.replaceChildren();
    if (!latest) {
      latestNode.append(create("strong", null, "Waiting for stream"), create("span", null, "Live events appear here"));
      $("latest-event-sequence").textContent = "—";
      return;
    }
    latestNode.append(create("strong", null, eventLabel(latest)), create("span", null, eventDetail(latest)));
    $("latest-event-sequence").textContent = `#${value(latest.sequence).padStart(2, "0")}`;
  }

  function renderDashboard() {
    renderFlow();
    const normalScenario = isNormalScenario();
    const closedRecovery = isVerifiedClosedRecovery();
    const incidentVisible = !normalScenario && !closedRecovery;
    const inject = $("dashboard-inject-incident");
    if (inject) {
      const selectedScenario = state.snapshot ? scenarioForSnapshot(state.snapshot) : state.activeScenario;
      const catalog = authoritativeScenarioState();
      const hasActiveIncident = Boolean(catalog.activeIncident);
      const hasHistoricalIncident = Boolean(catalog.historicalIncident);
      const incidentAction = hasActiveIncident
        ? "resume"
        : hasHistoricalIncident
          ? "view-completed"
          : "inject";
      const catalogIncidentAvailable = hasActiveIncident || hasHistoricalIncident;
      const injectAllowed = catalogIncidentAvailable
        ? streamIsLive() && !state.commandBusy && !state.replaying && demoMode !== "degraded"
        : selectedScenario === "normal"
          && streamIsLive()
          && !state.commandBusy
          && !state.replaying
          && demoMode !== "degraded"
          && catalog.incidentTransitionAllowed;
      inject.hidden = hasActiveIncident && incidentVisible;
      inject.dataset.incidentAction = incidentAction;
      const injectLabel = inject.querySelector("strong");
      if (injectLabel) injectLabel.textContent = hasActiveIncident
        ? "Resume active incident"
        : hasHistoricalIncident
          ? "View completed investigation"
          : "Inject incident";
      inject.disabled = !injectAllowed;
      inject.setAttribute("aria-disabled", String(!injectAllowed));
      inject.title = injectAllowed
        ? hasActiveIncident
          ? "Open the active server-backed incident"
          : hasHistoricalIncident
            ? "Open the completed server-backed investigation"
          : "Create the server-backed 80/20 incident"
        : catalogIncidentAvailable
          ? hasActiveIncident
            ? "Reconnect to resume the active incident"
            : "Reconnect to open the completed investigation"
        : selectedScenario === "normal"
          ? "The control plane has not admitted a new incident yet"
          : "Return to Normal before injecting another incident";
    }
    const openInvestigation = $("dashboard-open-investigation");
    if (openInvestigation) {
      openInvestigation.hidden = !incidentVisible;
      openInvestigation.disabled = !incidentVisible || state.commandBusy || !streamIsLive();
      openInvestigation.setAttribute("aria-disabled", String(openInvestigation.disabled));
    }
    const livePanel = $("live-panel");
    if (livePanel) {
      // The three operational panes are part of the control-room frame even
      // before an incident. Their values stay projection-driven and the
      // incident row simply remains quiet until the ledger reports a problem.
      const hidden = demoMode === "degraded";
      livePanel.hidden = hidden;
      livePanel.setAttribute("aria-hidden", String(hidden));
    }
    const liveTitle = $("live-title");
    if (liveTitle) liveTitle.textContent = normalScenario ? "System status" : closedRecovery ? "Incident history" : "Active incidents";
    document.querySelectorAll("[data-incident-row]").forEach((row) => {
      row.hidden = normalScenario || (closedRecovery && row.dataset.incidentRow === "active");
    });
    const incidentEmpty = $("incident-empty");
    if (incidentEmpty) incidentEmpty.hidden = !normalScenario;
    const agentRail = $("agent-rail");
    const agentRailTitle = $("agent-rail-title");
    if (agentRail && agentRailTitle) {
      const agentStatus = normalScenario ? "Agent status" : closedRecovery ? "Investigation complete" : "Agents investigating";
      agentRail.setAttribute("aria-label", agentStatus);
      agentRailTitle.textContent = agentStatus;
      agentRailTitle.setAttribute("aria-label", agentStatus);
    }
    renderDashboardAgents();
    renderLatestEvent();
  }

  function renderInvestigationControls() {
    const complete = hasCompletedInvestigation() || state.replaying;
    const closed = incidentStatus() === "CLOSED";
    const started = state.startIssued || hasStartedInvestigation();
    const normalScenario = isNormalScenario();
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
      button.hidden = normalScenario || complete || closed;
      button.textContent = startLabel;
      button.disabled = normalScenario || !startAllowed;
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
      || state.activeScenario === "normal"
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
    const initialEvents = state.events.filter((event) => [
      "source.condition.injected",
      "incident.detected",
    ].includes(eventType(event)));
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
    const normalScenario = state.activeScenario === "normal" || value(snapshot.incident_id) === "missing-20-normal";
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
    if (normalScenario && !prepared) { status = "Healthy"; rawStatus = "HEALTHY"; }
    else if (verified && !prepared && completedIntent && noAction) { status = "VERIFIED · CLOSED"; rawStatus = "VERIFIED"; }
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
      if (normalScenario) {
        intentNode.append(
          create("span", "intent-label", "SUPPLY FLOW"),
          create("strong", "intent-action", "No recovery action needed"),
          create("span", "intent-meta", "All units reached ERP and the invoice is released."),
        );
      } else if (completedIntent) {
        intentNode.append(
          create("span", "intent-label", "COMPLETED ACTION INTENT"),
          create("strong", "intent-action", actionLabel(completedIntent.tool || "recovery")),
          create("span", "intent-meta", "Verified; approvals are not carried into the next action."),
        );
      }
      if (currentDecision && !noAction) {
        intentNode.append(
          create("span", "intent-label", completedIntent ? "NEXT ACTION · NOT PREPARED" : "CURRENT ACTION · NOT PREPARED"),
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
    prepareButton.textContent = normalScenario
      ? "No action needed"
      : noAction ? "No further action" : currentAction ? `Prepare ${actionLabel(currentAction)}` : "Prepare recovery";
    prepareButton.disabled = state.commandBusy || !canOperate() || prepared || !currentDecision || currentDecision.eligibility !== "PENDING_APPROVAL";
    const executeButton = $("execute-button");
    executeButton.disabled = state.commandBusy || !canOperate() || !quorumApproved || (verified && hasExecution);
    executeButton.hidden = Boolean(noAction && !prepared && completedIntent);
    if (state.commandError) {
      roles.append(create("p", "command-error", state.commandError));
    }
  }

  async function sendDecision(payload) {
    if (!state.incidentId || state.commandBusy || !canOperate()) return null;
    state.commandBusy = true;
    state.commandError = "";
    renderDecision();
    try {
      const response = await requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}/decisions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: payload });
      applySnapshot(response, response.units, false);
      await queueRefresh();
      await refreshScenarioCatalog();
      return response;
    } catch (error) {
      state.commandError = error.message;
      setConnection(state.connection, `Command stopped safely: ${error.message}`);
      return null;
    } finally {
      state.commandBusy = false;
      renderAll();
    }
  }

  async function prepareRecovery() {
    const decisions = state.snapshot && Array.isArray(state.snapshot.decisions) ? state.snapshot.decisions : [];
    const decision = decisions.find((item) => item && item.eligibility === "PENDING_APPROVAL") || decisions[0];
    const tool = decision && decision.allowed_action;
    if (!tool) return null;
    return sendDecision({ command: "prepare_recovery", tool, idempotency_key: makeKey("prepare") });
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

  async function invokeCaseAction(actionId) {
    const id = value(actionId);
    const definition = CASE_ACTION_DEFS[id];
    const action = currentCaseActions().find((item) => item.id === id);
    if (!definition || !action || !action.enabled || state.commandBusy || state.chatPending) return;
    state.caseActionStatus = `${definition.label} in progress`;
    if (definition.kind === "chat") {
      await askQuestion(definition.question);
      return;
    }
    if (id === "continue_investigation") {
      await startInvestigation();
      if (!state.commandError) state.caseActionStatus = "Investigation launched";
      renderAll();
      return;
    }
    if (id === "prepare_recovery") {
      await prepareRecovery();
      if (!state.commandError) state.caseActionStatus = "Recovery proposal prepared";
      renderAll();
    }
  }

  function syncDurableChat() {
    if (state.chatHydrated) return;
    const replies = state.events.filter((item) => eventType(item) === "copilot.message");
    replies.forEach((event) => {
      const payload = event.payload || {};
      state.chatMessages.push({
        role: "assistant",
        message: value(payload.message),
        citations: Array.isArray(payload.citations) ? payload.citations : [],
        agentId: value(payload.agent_id || "orchestrator"),
      });
      if (Array.isArray(payload.next_actions)) state.nextActions = payload.next_actions;
    });
    state.chatHydrated = true;
  }

  function defaultCaseActions() {
    const normal = isNormalScenario();
    const incident = !normal && Boolean(state.incidentId);
    const complete = hasCompletedInvestigation();
    const running = state.startBusy || state.replaying || hasStartedInvestigation() && !complete;
    const closed = incidentStatus() === "CLOSED";
    const advisoryDegraded = advisoryTerminallyDegraded();
    const approval = state.snapshot && state.snapshot.approval ? state.snapshot.approval : {};
    const decisions = state.snapshot && Array.isArray(state.snapshot.decisions)
      ? state.snapshot.decisions
      : [];
    const currentDecision = decisions.find((item) => item && item.eligibility === "PENDING_APPROVAL") || null;
    const prepareEnabled = Boolean(
      incident && complete && !closed && !advisoryDegraded
      && !approval.intent_id && currentDecision
      && currentDecision.allowed_action && streamIsLive() && demoMode !== "degraded",
    );
    const commonChatEnabled = Boolean(incident && complete && !advisoryDegraded && streamIsLive() && demoMode !== "degraded" && !state.chatPending && !state.replaying);
    return Object.entries(CASE_ACTION_DEFS).map(([id, definition]) => ({
      id,
      label: definition.label,
      kind: definition.kind,
      case_version: number(state.snapshot && state.snapshot.case_version),
      enabled: id === "continue_investigation"
        ? Boolean(incident && !closed && !advisoryDegraded && !running && !complete && streamIsLive() && demoMode !== "degraded")
        : id === "prepare_recovery" ? prepareEnabled : commonChatEnabled,
      reason: id === "continue_investigation"
        ? normal ? "Waiting for a detected incident" : advisoryDegraded ? "Advisory stopped safely; start a fresh incident" : complete ? "Investigation is complete" : closed ? "Case is closed" : "Ready to launch the investigators"
        : id === "prepare_recovery"
          ? prepareEnabled ? "Ready for a structured recovery proposal" : advisoryDegraded ? "Advisory stopped safely; start a fresh incident" : "Continue the investigation first"
          : commonChatEnabled ? "Ask the active case" : advisoryDegraded ? "Advisory stopped safely; start a fresh incident" : complete ? "Waiting for a live incident case" : "Start the investigation first",
    }));
  }

  function currentCaseActions() {
    const actions = state.nextActions.length ? state.nextActions : defaultCaseActions();
    return actions
      .filter((action) => action && CASE_ACTION_DEFS[value(action.id)])
      .map((action) => {
        const id = value(action.id);
        const definition = CASE_ACTION_DEFS[id];
        const live = defaultCaseActions().find((item) => item.id === id);
        return {
          ...action,
          id,
          label: value(action.label || definition.label),
          kind: value(action.kind || definition.kind),
          enabled: Boolean(action.enabled) && Boolean(live && live.enabled),
          reason: value(action.reason || (live && live.reason) || "Unavailable"),
        };
      });
  }

  function renderCaseActions() {
    const host = $("case-actions");
    const status = $("case-action-status");
    if (!host) return;
    host.replaceChildren();
    // Investigation has one launch point in the workspace header. Keep the
    // typed API action for auditability, but do not render a second button that
    // can start the same harness.
    const actions = currentCaseActions().filter((action) => action.id !== "continue_investigation");
    actions.forEach((action) => {
      const button = create("button", `case-action case-action-${slug(action.id)}`, action.label);
      button.type = "button";
      button.setAttribute("data-case-action-id", action.id);
      button.disabled = !action.enabled || state.commandBusy || state.chatPending || !streamIsLive();
      button.setAttribute("aria-disabled", String(button.disabled));
      if (action.reason) button.title = action.reason;
      button.addEventListener("click", () => invokeCaseAction(action.id));
      host.append(button);
    });
    if (status) {
      status.textContent = isVerifiedClosedRecovery()
        ? "Recovery verified · No further action"
        : state.caseActionStatus || (isNormalScenario() ? "Waiting for an incident" : "Choose a next step");
    }
  }

  function renderChat() {
    syncDurableChat();
    const log = $("chat-log");
    log.replaceChildren();
    if (!state.chatMessages.length) {
      log.append(create(
        "div",
        "chat-empty",
        isNormalScenario() ? "Run incident demo to start role chat." : "Ask the selected role about this incident.",
      ));
    }
    state.chatMessages.slice(-12).forEach((item) => {
      const row = create("article", `chat-message chat-${item.role}`);
      const messageAgent = item.agentId && item.agentId !== "orchestrator"
        ? agentDefinition(item.agentId)
        : null;
      const assistantLabel = messageAgent
        ? `${messageAgent.name.toUpperCase()} · COPILOT`
        : "AGENT TEAM · COPILOT";
      row.append(create("span", "chat-role", item.role === "user" ? "YOU" : assistantLabel), create("p", null, item.message));
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
    if (state.chatPending) log.append(create("div", "chat-message chat-assistant chat-pending", "Agents are reading records…"));
    const chatDisabledWithoutScenario = demoMode === "degraded" || advisoryTerminallyDegraded() || state.chatPending || state.replaying || !streamIsLive();
    const chatDisabled = chatDisabledWithoutScenario || isNormalScenario() || !hasCompletedInvestigation();
    $("chat-input").disabled = chatDisabled;
    $("chat-submit").disabled = chatDisabled;
    $("chat-input").setAttribute("aria-disabled", String(chatDisabled));
    $("chat-submit").setAttribute("aria-disabled", String(chatDisabled));
    const roleQuestions = {
      retryable_message_investigator: [
        "Ask Receipt Retry about the admitted retry evidence",
        "Which admitted evidence proves the receipt message is retryable?",
      ],
      short_shipment_investigator: [
        "Ask Shipment Evidence about the physical quantity",
        "Which admitted evidence rules out a short shipment?",
      ],
      duplicate_posting_investigator: [
        "Ask Duplicate Posting about existing postings",
        "Which admitted evidence rules out a duplicate posting?",
      ],
      orchestrator: [
        "Ask the agent team about the selected hypothesis",
        "Which admitted evidence supports the selected hypothesis?",
      ],
    };
    const selectedRole = state.selectedAgentId || "orchestrator";
    const roleQuestion = roleQuestions[selectedRole] || roleQuestions.orchestrator;
    document.querySelectorAll(".suggestion").forEach((button, index) => {
      if (index === 0) {
        button.textContent = selectedRole === "orchestrator" ? "What proves it?" : roleQuestion[0];
        button.dataset.question = roleQuestion[1];
        button.setAttribute("aria-label", roleQuestion[0]);
      }
      button.disabled = chatDisabled;
    });
    renderCaseActions();
  }

  function focusEvidence(evidenceId) {
    const requestedId = value(evidenceId).trim();
    const record = [...document.querySelectorAll(".evidence-record[data-evidence-id]")]
      .find((node) => node.dataset.evidenceId === requestedId);
    if (record) {
      state.focusedEvidenceId = requestedId;
      const drawer = record.closest("details.evidence-drawer");
      if (drawer) drawer.open = true;
      const status = $("evidence-status");
      if (status) {
        status.hidden = true;
        status.textContent = "";
      }
      applyEvidenceFocus(true);
      // A final render can be queued by the same chat response that exposed
      // the citation. Re-apply the durable target after that render without
      // replacing the visible focus state with a transient card class.
      window.requestAnimationFrame(() => applyEvidenceFocus(true));
      return;
    }
    state.focusedEvidenceId = "";
    applyEvidenceFocus(false);
    const status = $("evidence-status");
    if (status) {
      const drawer = document.querySelector("details.evidence-drawer");
      if (drawer) drawer.open = true;
      status.hidden = false;
      status.textContent = `Evidence ${requestedId || "requested"} is not admitted; the console stopped safely.`;
    }
  }

  function stateAwareChatResponse(question, response) {
    const lowered = value(question).toLowerCase();
    const closed = incidentStatus() === "CLOSED";
    const asksHistoricalGap = /\b(where|missing|gone|lost|short)\b/.test(lowered);
    if (!closed || !asksHistoricalGap) return response;
    const historicalEvent = state.events.find((event) => (
      eventType(event) === "incident.detected" && number(event.payload && event.payload.missing_quantity) > 0
    ));
    const historicalGap = number(historicalEvent && historicalEvent.payload && historicalEvent.payload.missing_quantity);
    if (!historicalGap) return response;
    const counts = state.snapshot && state.snapshot.unit_counts ? state.snapshot.unit_counts : {};
    const currentRecorded = number(counts.erp_recorded, number(counts.recorded, 0));
    const expected = number(counts.total, number(counts.expected, currentRecorded));
    const citations = Array.isArray(response.citations) ? response.citations : [];
    const cited = citations.length ? ` Evidence is available in ${citations.slice(0, 2).join(" and ")}.` : "";
    return {
      ...response,
      message: `The case is closed and reconciled: ${currentRecorded} of ${expected} units are now recorded. During the incident, ${historicalGap} units stopped at the queue; the recovery path restored them.${cited}`,
    };
  }

  async function askQuestion(question) {
    const textValue = value(question).trim();
    if (!textValue) {
      state.chatMessages.push({
        role: "assistant",
        message: "Enter a question about the incident; Copilot will only read and explain.",
        citations: [],
        agentId: state.selectedAgentId || "orchestrator",
      });
      renderChat();
      return;
    }
    if (isNormalScenario() || !hasCompletedInvestigation() || state.chatPending || !state.incidentId || state.replaying || !streamIsLive()) {
      state.caseActionStatus = "Start the investigation before asking the agents";
      renderChat();
      return;
    }
    state.caseActionStatus = "Agent is reading the case";
    const selectedRoleId = state.selectedAgentId || "orchestrator";
    state.chatMessages.push({ role: "user", message: textValue, citations: [], agentId: selectedRoleId });
    state.chatPending = true;
    renderChat();
    try {
      const response = stateAwareChatResponse(textValue, await requestJSON(`/api/v1/incidents/${encodeURIComponent(state.incidentId)}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: { question: textValue, agent_id: selectedRoleId, idempotency_key: makeKey("chat") } }));
      state.chatMessages.push({
        role: "assistant",
        message: value(response.message),
        citations: Array.isArray(response.citations) ? response.citations : [],
        agentId: selectedRoleId,
      });
      if (Array.isArray(response.next_actions)) state.nextActions = response.next_actions;
      state.caseActionStatus = "Case answer ready";
      await queueRefresh();
    } catch (error) {
      state.chatMessages.push({ role: "assistant", message: `The case console stopped safely: ${error.message}`, citations: [], agentId: selectedRoleId });
      state.caseActionStatus = "Case action stopped safely";
    } finally {
      state.chatPending = false;
      renderAll();
    }
  }

  function renderAgentView() {
    renderRailTabs();
    renderAgentGraph();
    renderDecision();
    renderChat();
    renderHealthyWorkspaceState();
  }

  function renderRailTabs() {
    const normal = isNormalScenario();
    const targetKey = state.rightRailTab === "chat" ? "chat" : state.rightRailTab === "decision" ? "decision" : "context";
    document.querySelectorAll(".workspace-rail-tabs [data-rail-target]").forEach((tab) => {
      const targetId = value(tab.dataset.railTarget);
      const key = targetId === "chat-log" ? "chat" : targetId === "decision-panel" ? "decision" : "context";
      const selected = key === targetKey && !(normal && key !== "context");
      tab.classList.toggle("is-selected", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.disabled = normal && key !== "context";
      tab.setAttribute("aria-disabled", String(tab.disabled));
      tab.tabIndex = selected ? 0 : -1;
    });
    document.querySelectorAll("[data-rail-panel]").forEach((panel) => {
      const panelKey = value(panel.dataset.railPanel);
      panel.hidden = normal ? panelKey !== "context" : panelKey !== targetKey;
      panel.setAttribute("aria-hidden", String(panel.hidden));
    });
  }

  function renderHealthyWorkspaceState() {
    const panel = $("healthy-workspace-state");
    const list = $("healthy-source-freshness");
    const button = $("workspace-run-incident-demo");
    if (!panel || !list || !button) return;
    const normal = isNormalScenario();
    panel.hidden = !normal;
    if (!normal) return;
    list.replaceChildren();
    const sources = state.liveSources && Array.isArray(state.liveSources.sources)
      ? state.liveSources.sources
      : [];
    if (!sources.length) {
      list.append(create("li", "healthy-source-empty", state.liveSourceError || "Source freshness unavailable"));
    } else {
      sources.forEach((source) => {
        const row = create("li", "healthy-source-row");
        row.append(
          create("strong", null, liveSourceDisplayName(source)),
          create("span", null, `${liveSourceStatusLabel(source.status)} · ${liveSourceFreshness(source)}`),
        );
        list.append(row);
      });
    }
    const catalog = authoritativeScenarioState();
    const hasActiveIncident = Boolean(catalog.activeIncident);
    const hasHistoricalIncident = Boolean(catalog.historicalIncident);
    const catalogIncidentAvailable = hasActiveIncident || hasHistoricalIncident;
    const enabled = streamIsLive()
      && !state.commandBusy
      && !state.replaying
      && demoMode !== "degraded"
      && (catalogIncidentAvailable || catalog.incidentTransitionAllowed);
    const incidentAction = hasActiveIncident
      ? "resume"
      : hasHistoricalIncident
        ? "view-completed"
        : "inject";
    button.dataset.incidentAction = incidentAction;
    const buttonLabel = button.querySelector("[data-incident-label]");
    if (buttonLabel) {
      buttonLabel.textContent = hasActiveIncident
        ? "Resume active incident"
        : hasHistoricalIncident
          ? "View completed investigation"
          : "Run incident demo";
    } else {
      button.textContent = hasActiveIncident
        ? "Resume active incident"
        : hasHistoricalIncident
          ? "View completed investigation"
          : "Run incident demo";
    }
    button.disabled = !enabled;
    button.setAttribute("aria-disabled", String(button.disabled));
    button.title = enabled
      ? hasActiveIncident
        ? "Open the active server-backed incident"
        : hasHistoricalIncident
          ? "Open the completed server-backed investigation"
        : "Create the server-backed incident"
      : catalogIncidentAvailable
        ? hasActiveIncident
          ? "Reconnect to resume the active incident"
          : "Reconnect to open the completed investigation"
      : "The control plane has not admitted a new incident yet";
  }

  function activateRailTab(tab, moveFocus = false) {
    const targetId = value(tab && tab.dataset.railTarget);
    if (!targetId) return;
    state.rightRailTab = targetId === "chat-log" ? "chat" : targetId === "decision-panel" ? "decision" : "context";
    if (isNormalScenario() && state.rightRailTab !== "context") state.rightRailTab = "context";
    renderRailTabs();
    const target = $(targetId);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    if (moveFocus && tab) tab.focus();
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
    renderLiveMetrics();
    if (state.view === "agent") renderAgentView();
    else if (state.view === "dashboard") renderDashboard();
    $("dashboard-view").hidden = state.view !== "dashboard";
    $("agent-view").hidden = state.view !== "agent";
    $("scenario-view").hidden = state.view !== "scenario";
    bodyReady();
  }

  function bodyReady() {
    document.body.dataset.workspaceReady = state.loaded && state.units.size > 0 ? "true" : "false";
    const disconnected = state.connection === "paused" && Boolean(state.streamError);
    if (disconnected) {
      showUnavailable(`${state.streamError} Live movement is paused.`, true);
    } else if (state.loaded) {
      showUnavailable("", false);
    }
  }

  async function bootstrap() {
    try {
      // Start in the healthy control-room view.  Incident and Golden Incident
      // are explicit transitions, so the first frame never implies an anomaly
      // before the user has selected one.
      const scenarioListing = await requestJSON("/api/v1/scenarios");
      setScenarioCatalog(scenarioListing);
      const normal = Array.isArray(scenarioListing.scenarios)
        ? scenarioListing.scenarios.find((item) => value(item.id) === "normal")
        : null;
      const requestedScenario = query.get("scenario");
      const requested = Array.isArray(scenarioListing.scenarios)
        ? scenarioListing.scenarios.find((item) => value(item.id) === requestedScenario)
        : null;
      // Re-entry may target a fresh persisted incident run rather than the
      // catalog's legacy compatibility identity.  The server still validates
      // the ID and returns authoritative state; this query only selects which
      // already-persisted session the read-only browser should open.
      const requestedIncidentId = value(query.get("incident_id"));
      const initialScenario = requestedIncidentId && requestedScenario === "incident"
        ? { ...(requested || {}), id: "incident", incident_id: requestedIncidentId }
        : requested && requestedScenario !== "golden" ? requested : normal;
      if (!initialScenario || !initialScenario.incident_id) throw new Error("No healthy synthetic scenario is available");
      const id = value(initialScenario.incident_id);
      state.activeScenario = value(initialScenario.id) || "normal";
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
        $("scenario-view").hidden = true;
        showUnavailable("The demo invalid mode has no admissible authoritative lifecycle evidence; operational claims are hidden.", true);
        setConnection("paused", "Invalid evidence; the workspace is unavailable.");
        return;
      }
      applySnapshot(snapshot, units.units, true);
      startLiveSourceRefresh();
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
  const viewTabs = [...document.querySelectorAll("[data-view]")]
    .filter((tab) => tab.closest(".view-tabs"));
  viewTabs.forEach((button, index) => {
    button.addEventListener("click", () => setView(button.dataset.view));
    button.addEventListener("keydown", (event) => {
      // The Agent Workspace tablist is nested inside the Agent view. Global
      // navigation must never consume its arrow-key events.
      if (event.target.closest("[role=tablist]") !== button.closest("[role=tablist]")) return;
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
  const railTabList = document.querySelector(".workspace-rail-tabs[role=tablist]");
  const railTabs = railTabList ? [...railTabList.querySelectorAll(":scope > [data-rail-target]")] : [];
  railTabs.forEach((button, index) => {
    button.addEventListener("click", () => activateRailTab(button));
  });
  railTabList?.addEventListener("keydown", (event) => {
    if (!(event.target instanceof HTMLElement) || !event.target.matches("[data-rail-target]")) return;
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.stopPropagation();
    event.preventDefault();
    const button = event.target;
    const index = railTabs.indexOf(button);
    if (index < 0) return;
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? railTabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : -1) + railTabs.length) % railTabs.length;
    const next = railTabs[nextIndex];
    activateRailTab(next, true);
  });
  // Incident detection owns the handoff to the agent harness.  The legacy start
  // endpoint and hidden compatibility nodes remain available to older smoke
  // fixtures, but there is no user-facing Start control or click listener.
  $("dashboard-inject-incident").addEventListener("click", () => selectScenario("incident"));
  $("workspace-run-incident-demo")?.addEventListener("click", () => selectScenario("incident"));
  $("dashboard-open-investigation").addEventListener("click", () => selectAgent("orchestrator", true));
  $("dashboard-replay-investigation").addEventListener("click", replayInvestigation);
  $("agent-replay-investigation").addEventListener("click", replayInvestigation);
  $("prepare-button").addEventListener("click", prepareRecovery);
  $("execute-button").addEventListener("click", executeRecovery);
  ["normal", "incident", "recovery"].forEach((scenario) => {
    const button = $(`scenario-${scenario}`);
    if (button) button.addEventListener("click", () => selectScenario(scenario));
  });
  $("golden-incident").addEventListener("click", () => selectScenario("golden"));
  $("chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("chat-input");
    const question = input.value.trim();
    input.value = "";
    askQuestion(question);
  });
  document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => askQuestion(button.dataset.question)));

  document.addEventListener("visibilitychange", () => {
    document.body.dataset.hidden = String(document.hidden);
  });
  document.body.dataset.hidden = String(document.hidden);

  window.addEventListener("resize", () => {
    if (state.view === "agent") scheduleRender();
  });

  window.addEventListener("beforeunload", () => {
    if (state.source) state.source.close();
    if (state.reconnectTimer != null) window.clearTimeout(state.reconnectTimer);
  });

  bootstrap();
})();
