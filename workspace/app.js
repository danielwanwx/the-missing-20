/* The Missing 20 live client. Business state comes from the experiment API and SSE ledger. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const query = new URLSearchParams(window.location.search);
  const smokeCapture = query.get("smoke") === "1";
  const providerPollingDisabled = query.get("polling") === "0";
  const demoMode = ["complete", "degraded", "invalid"].includes(query.get("mode") || "complete")
    ? (query.get("mode") || "complete")
    : "complete";
  const EVENT_TYPES = [
    "telemetry.observed",
    "external.source.changed",
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
    "source.read.started",
    "source.read.completed",
    "effect.started",
    "effect.completed",
    "verification.started",
    "execution.completed",
    "verification.completed",
    "copilot.message",
    "provider.degraded",
    "workflow.blocked",
  ];
  const MAX_EVENT_HISTORY = 2000;
  const OPERATION_TYPES = new Set([
    "external.source.changed",
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
    "source.read.started",
    "source.read.completed",
    "effect.started",
    "effect.completed",
    "verification.started",
    "execution.started",
    "execution.completed",
    "verification.completed",
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
    { role: "MANAGER", principal: "manager", name: "Manager" },
  ];
  const PLATFORM_LAYOUT_KEY = "missing20-command-canvas-v1";
  const PLATFORM_NODE_IDS = ["erpnext", "airtable", "celigo", "jira", "slack", "agent", "manager"];
  const EXTERNAL_SERVICE_LINKS = Object.freeze({
    erpnext: {
      label: "Open ERPNext",
      url: "https://missing20.v.frappe.cloud/app/purchase-order",
    },
    airtable: {
      label: "Open Airtable",
      url: "https://airtable.com/appcV7IwCbuWs8X39",
    },
    celigo: {
      label: "Open Celigo",
      url: "https://integrator.io/flows",
    },
    jira: {
      label: "Open Jira",
      url: "https://shrikisgood.atlassian.net/jira/software/projects/QRC/boards",
    },
    slack: {
      label: "Open Slack",
      url: "https://app.slack.com/client/T0BUCRETR2R/C0BUNV20J6Q",
    },
  });

  function liveERPDocument(kind) {
    const documents = Array.isArray(state.erpEvidence?.documents) ? state.erpEvidence.documents : [];
    return documents.find((item) => value(item?.kind) === kind) || null;
  }

  function liveSaaSRecord(componentId) {
    const sources = Array.isArray(state.saasEvidence?.sources) ? state.saasEvidence.sources : [];
    return sources.find((item) => {
      const haystack = `${value(item?.provider)} ${value(item?.source_id)}`.toLowerCase();
      return haystack.includes(componentId);
    }) || null;
  }

  function erpDocumentLink(kind, route) {
    const document = liveERPDocument(kind);
    const name = value(document?.name);
    return {
      label: "Open ERPNext",
      url: `https://missing20.v.frappe.cloud/app/${route}${name ? `/${encodeURIComponent(name)}` : ""}`,
    };
  }
  const MANAGER_ATTESTATIONS = ["integration-operator", "ap-approver"];
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
    view: new URLSearchParams(window.location.search).get("view") === "agent" ? "agent" : "dashboard",
    demoControlsOpen: false,
    dashboardLatestRenderedSequence: 0,
    dashboardEventFollow: true,
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
    transitionBaseline: null,
    flowStageCounts: new Map(),
    flowStageRunId: "",
    telemetryPulse: false,
    telemetryPulseTimer: null,
    activeToolActors: new Set(),
    chatMessages: [],
    chatHydrated: false,
    chatPending: false,
    nextActions: [],
    caseActionStatus: "",
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
    erpEvidence: null,
    erpEvidenceError: "",
    erpEvidenceTimer: null,
    erpEvidenceBusy: false,
    saasEvidence: null,
    saasEvidenceError: "",
    saasEvidenceTimer: null,
    saasEvidenceBusy: false,
    agentPlatform: null,
    ambiguousReceiptCase: null,
    agentPlatformError: "",
    agentPlatformTimer: null,
    agentPlatformBusy: false,
    agentPlatformDiagnosing: false,
    agentPlatformActionBusy: false,
    agentPlatformAnswer: "",
    agentPlatformAdvisory: null,
    agentPlatformQuestionBusy: false,
    agentPlatformPulseAfter: 0,
    graphEventSequence: 0,
    latestActivitySequence: 0,
    activitySource: "Current stream",
    selectedPoint: null,
    selectedPointSequence: 0,
    focusedChartId: "",
    chartCursor: null,
    chartFocusEpoch: 0,
    chartFocusTimer: null,
    chartKeyListenerInstalled: false,
    chartPulseSequence: 0,
    liveMetricSequence: 0,
    businessMetricSequence: 0,
    recoveryAvailable: false,
    goldenRunning: false,
    rightRailTab: "context",
    focusedEvidenceId: "",
    platformArrangeMode: false,
    platformFocusedModule: "",
    platformSelectedNode: "",
    platformLayout: {},
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
    if (["HEALTHY", "MONITORING", "COMPLETE", "COMPLETED", "OPEN", "PASS", "GRANTED", "APPROVED", "ERP_RECORDED", "VERIFIED", "RECOVERY_COMPLETE", "SAFE_NOOP"].includes(status)) {
      return "state-lime";
    }
    if (["RUNNING", "REASONING", "TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "STARTED", "ADMITTED", "HANDED_OFF", "HANDOFF", "SCRIPTED_SYNTHETIC_PROOF"].includes(status)) {
      return "state-cyan";
    }
    if (["ANOMALY", "QUEUE_FAILED", "PARTIAL", "HELD", "FAILED", "BLOCKED", "DEGRADED", "NOT_PROVEN", "NOT PROVEN", "PENDING_APPROVAL", "DENY", "HARD_STOP", "AGENT_UNAVAILABLE", "VALIDATION_FAILED"].includes(status)) {
      return "state-coral";
    }
    return "state-neutral";
  }

  function isProblemStatus(raw) {
    return [
      "ANOMALY", "CRITICAL", "QUEUE FAILED", "QUEUE_FAILED", "PARTIAL", "HELD",
      "FAILED", "BLOCKED", "DEGRADED", "MISSING", "UNKNOWN", "TIMEOUT",
      "NOT PROVEN", "NOT_PROVEN", "HARD STOP", "HARD_STOP", "AGENT UNAVAILABLE",
      "AGENT_UNAVAILABLE", "VALIDATION FAILED", "VALIDATION_FAILED",
    ].includes(value(raw).toUpperCase());
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

  function readPlatformLayout() {
    try {
      const stored = JSON.parse(window.localStorage.getItem(PLATFORM_LAYOUT_KEY) || "{}");
      if (!stored || typeof stored !== "object" || Array.isArray(stored)) return {};
      return Object.fromEntries(Object.entries(stored).filter(([key, item]) => (
        /^[a-z-]+$/.test(key)
        && item && typeof item === "object"
        && ["x", "y", "width", "height"].every((field) => item[field] == null || Number.isFinite(Number(item[field])))
      )));
    } catch (_error) {
      return {};
    }
  }

  function storePlatformLayout() {
    try {
      window.localStorage.setItem(PLATFORM_LAYOUT_KEY, JSON.stringify(state.platformLayout));
    } catch (_error) {
      // Layout persistence is optional. Operational state never depends on it.
    }
  }

  function applyPlatformLayout() {
    document.querySelectorAll("[data-canvas-module]").forEach((module) => {
      const layout = state.platformLayout[module.dataset.canvasModule] || {};
      const x = Math.max(-240, Math.min(240, number(layout.x)));
      const y = Math.max(-180, Math.min(220, number(layout.y)));
      const width = Math.max(0, Math.min(1400, number(layout.width)));
      const height = Math.max(0, Math.min(1100, number(layout.height)));
      module.style.setProperty("--module-x", `${x}px`);
      module.style.setProperty("--module-y", `${y}px`);
      module.style.width = width ? `${width}px` : "";
      module.style.height = height ? `${height}px` : "";
    });
  }

  function setPlatformArrangeMode(enabled) {
    state.platformArrangeMode = Boolean(enabled);
    const canvas = $("platform-command-canvas");
    const button = $("platform-arrange-mode");
    if (canvas) canvas.dataset.arrange = String(state.platformArrangeMode);
    if (button) {
      button.setAttribute("aria-pressed", String(state.platformArrangeMode));
      button.setAttribute("aria-label", state.platformArrangeMode ? "Finish arranging canvas" : "Arrange canvas");
      button.classList.toggle("is-active", state.platformArrangeMode);
      const label = button.querySelector("span");
      if (label) label.textContent = state.platformArrangeMode ? "Done" : "Arrange";
    }
  }

  function resetPlatformLayout() {
    state.platformLayout = {};
    storePlatformLayout();
    applyPlatformLayout();
    renderPlatformInvestigationLinks();
  }

  function platformNodeAnchor(point, toward) {
    const dx = toward.x - point.x;
    const dy = toward.y - point.y;
    if (Math.abs(dx) < .001 && Math.abs(dy) < .001) return { x: point.x, y: point.y };
    const rx = Math.max(1, point.rx - .75);
    const ry = Math.max(1, point.ry - .75);
    const scale = point.node.classList.contains("platform-agent-node")
      ? 1 / Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry))
      : 1 / Math.max(Math.abs(dx) / rx, Math.abs(dy) / ry);
    return { x: point.x + dx * scale, y: point.y + dy * scale };
  }

  function platformLinkPath(start, end, { curve = false } = {}) {
    const dx = end.x - start.x;
    const dy = end.y - start.y;
    // All current node pairs have an unobstructed sightline. Keep those routes
    // straight; callers must opt into a curve only when a real obstacle exists.
    if (!curve || Math.abs(dx) < 2 || Math.abs(dy) < 2) return `M ${start.x} ${start.y} L ${end.x} ${end.y}`;
    if (Math.abs(dx) >= Math.abs(dy)) {
      const bend = Math.min(140, Math.max(32, Math.abs(dx) * .46));
      const direction = dx >= 0 ? 1 : -1;
      return `M ${start.x} ${start.y} C ${start.x + bend * direction} ${start.y}, ${end.x - bend * direction} ${end.y}, ${end.x} ${end.y}`;
    }
    const bend = Math.min(120, Math.max(28, Math.abs(dy) * .42));
    const direction = dy >= 0 ? 1 : -1;
    return `M ${start.x} ${start.y} C ${start.x} ${start.y + bend * direction}, ${end.x} ${end.y - bend * direction}, ${end.x} ${end.y}`;
  }

  function createSvgPath() {
    return document.createElementNS("http:" + "//www.w3.org/2000/svg", "path");
  }

  function renderPlatformInvestigationLinks() {
    const map = $("platform-investigation-map");
    const svg = $("platform-investigation-links");
    if (!map || !svg || map.offsetParent === null) return;
    const bounds = map.getBoundingClientRect();
    // A view switch and the first hydrated render can happen in the same
    // animation frame. In Chromium that occasionally exposes the map before
    // layout has assigned it usable dimensions. Do not freeze the topology in
    // that transient empty state; the queued second pass below will draw it.
    if (bounds.width < 2 || bounds.height < 2) return;
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, bounds.width)} ${Math.max(1, bounds.height)}`);
    svg.replaceChildren();
    const center = (id) => {
      const node = map.querySelector(`[data-investigation-node="${id}"]`);
      if (!node) return null;
      const rect = node.getBoundingClientRect();
      return {
        x: rect.left - bounds.left + rect.width / 2,
        y: rect.top - bounds.top + rect.height / 2,
        rx: rect.width / 2,
        ry: rect.height / 2,
        node,
      };
    };
    const links = [
      ["erpnext", "agent"], ["airtable", "agent"], ["celigo", "agent"],
      ["jira", "agent"], ["slack", "agent"], ["agent", "manager"],
    ];
    links.forEach(([fromId, toId]) => {
      const from = center(fromId);
      const to = center(toId);
      if (!from || !to) return;
      const start = platformNodeAnchor(from, to);
      const end = platformNodeAnchor(to, from);
      const path = createSvgPath();
      path.setAttribute("d", platformLinkPath(start, end));
      path.setAttribute("class", `platform-investigation-link${from.node.classList.contains("is-live") || to.node.classList.contains("is-live") ? " is-live" : ""}`);
      path.setAttribute("data-platform-link", `${fromId}-${toId}`);
      path.setAttribute("vector-effect", "non-scaling-stroke");
      svg.append(path);
    });
  }

  function schedulePlatformInvestigationLinks() {
    window.requestAnimationFrame(() => {
      renderPlatformInvestigationLinks();
      window.requestAnimationFrame(renderPlatformInvestigationLinks);
    });
  }

  let platformFocusDialog = null;
  let platformFocusAnchor = null;
  let platformFocusTrigger = null;
  function focusPlatformModule(module) {
    const next = module && state.platformFocusedModule !== module.dataset.canvasModule
      ? module.dataset.canvasModule
      : "";
    // Use the browser top layer. A fixed card inside a transformed canvas is
    // otherwise trapped below the body backdrop and can appear entirely dimmed.
    if (platformFocusDialog) {
      const previous = platformFocusDialog.querySelector("[data-canvas-module]");
      if (previous && platformFocusAnchor) platformFocusAnchor.replaceWith(previous);
      platformFocusDialog.close();
      platformFocusDialog.remove();
      platformFocusDialog = null;
      platformFocusAnchor = null;
      platformFocusTrigger?.focus();
      platformFocusTrigger = null;
    }
    state.platformFocusedModule = next;
    document.querySelectorAll("[data-canvas-module]").forEach((item) => {
      const focused = item.dataset.canvasModule === next;
      item.classList.toggle("is-focused", focused);
      item.querySelector("[data-module-focus]")?.setAttribute("aria-label", focused ? "Exit focus view" : `Focus ${item.dataset.canvasModule}`);
    });
    document.body.classList.remove("platform-focus-open");
    if (next && module) {
      platformFocusTrigger = document.activeElement;
      platformFocusAnchor = document.createComment("focused module location");
      module.before(platformFocusAnchor);
      const dialog = document.createElement("dialog");
      dialog.className = "platform-focus-dialog";
      dialog.setAttribute("aria-label", `Expanded ${next}`);
      const close = create("button", "platform-focus-close", "Close expanded view");
      close.type = "button";
      close.addEventListener("click", () => focusPlatformModule(null));
      dialog.append(close, module);
      document.body.append(dialog);
      dialog.addEventListener("cancel", (event) => {
        event.preventDefault();
        focusPlatformModule(null);
      });
      platformFocusDialog = dialog;
      dialog.showModal();
    }
    schedulePlatformInvestigationLinks();
  }

  function platformComponentContext(componentId) {
    const platform = state.agentPlatform || {};
    const demoCase = platform.demo_case && typeof platform.demo_case === "object" ? platform.demo_case.case || {} : {};
    const quantities = demoCase.quantities && typeof demoCase.quantities === "object" ? demoCase.quantities : {};
    const systems = Array.isArray(platform.systems) ? platform.systems : [];
    const constellation = platform.evidence_constellation && typeof platform.evidence_constellation === "object" ? platform.evidence_constellation : {};
    const evidenceNodes = Array.isArray(constellation.nodes) ? constellation.nodes : [];
    const system = systems.find((item) => value(item?.id) === componentId) || {};
    const evidence = evidenceNodes.find((item) => value(item?.id) === componentId) || {};
    const operations = connectedOperationsProjection() || {};
    const risk = operations.risk_signal || {};
    const agentRun = platform.agent_run || {};
    const humanReview = platform.human_review || {};
    const receivingNotification = ["EVENT_DRIVEN_NOTIFICATION", "RECEIVING_REVIEW"].includes(system.write_state);
    const liveRecord = receivingNotification ? system : liveSaaSRecord(componentId);
    const livePO = liveERPDocument("purchase_order");
    const liveReceipt = liveERPDocument("purchase_receipt");
    const liveInvoice = liveERPDocument("purchase_invoice");
    const liveSalesOrder = liveERPDocument("sales_order");
    const liveDelivery = liveERPDocument("delivery_note");
    const liveSalesInvoice = liveERPDocument("sales_invoice");
    const purposes = {
      erpnext: "Authoritative purchase order, stock ledger, receipt and invoice state.",
      airtable: "Exact-lot quality disposition and release eligibility.",
      celigo: "Integration attempt, acknowledgement and receipt business-key lineage.",
      jira: "Case ownership and the exception workflow journal.",
      slack: "Manager notification and human-decision audit trail.",
      agent: "Reads source evidence, tests competing causes and prepares a bounded recommendation.",
      manager: "Reviews only the proposed write scope when the Agent has enough evidence.",
    };
    const titles = {
      erpnext: "ERPNext",
      airtable: "Airtable Quality",
      celigo: "Celigo",
      jira: "Jira",
      slack: "Slack",
      agent: "Agent",
      manager: "Manager",
    };
    const common = {
      title: titles[componentId] || value(system.name || componentId),
      status: value(
        componentId === "erpnext" && state.erpEvidence?.status === "CONNECTED"
          ? "LIVE READ"
          : liveRecord?.status || evidence.status || system.status || "WAITING",
      ).replaceAll("_", " "),
      purpose: purposes[componentId] || "Connected case component.",
      metrics: [],
      external: EXTERNAL_SERVICE_LINKS[componentId] || null,
    };
    if (receivingNotification) return {
      ...common, title: value(system.name), status: value(system.status), purpose: value(system.detail),
      metrics: [["Source record", value(system.record_id) || "Not verified"],
        ["Scope", system.write_state === "RECEIVING_REVIEW" ? "Receiving review" : "Receipt notification"],
        ...(system.arrival_id ? [["Arrival", system.arrival_id]] : []),
        ["Authority", system.write_state === "RECEIVING_REVIEW" ? "Workflow record, not stock authority" : "ERPNext stock ledger"]],
      external: value(system.url).startsWith("https://") ? { url: system.url, label: "Open source record" } : common.external,
    };
    if (componentId === "erpnext") common.external = erpDocumentLink(
      "purchase_order",
      "purchase-order",
    );
    if (componentId === "erpnext") common.metrics = [
      ["Live purchase order", value(livePO?.name || "WAITING")],
      ["Receipt at posting", `${value(liveReceipt?.name || "WAITING")} · ${number(liveReceipt?.accepted)} accepted / ${number(liveReceipt?.rejected)} sent to quality`],
      ["Live invoice", `${value(liveInvoice?.name || "WAITING")} · ${value(liveInvoice?.status || "WAITING")}`],
      ["Customer order", `${value(liveSalesOrder?.name || "WAITING")} · ${value(liveSalesOrder?.status || "WAITING")}`],
      ["Delivery note", value(liveDelivery?.name || "WAITING")],
      ["Customer invoice", value(liveSalesInvoice?.name || "WAITING")],
      ["Read sequence", state.erpEvidence ? `seq ${number(state.erpEvidence.sequence)}` : "WAITING"],
    ];
    if (componentId === "airtable") common.metrics = [
      ["Live record", value(liveRecord?.record_id || "WAITING")],
      ["Status", value(liveRecord?.status || "WAITING")],
      ["Correlation", value(liveRecord?.correlation?.case_id || demoCase.case_id || "—")],
    ];
    if (componentId === "celigo") common.metrics = [
      ["Live run", value(liveRecord?.record_id || "WAITING")],
      ["Outcome", value(liveRecord?.status || platform.integration_receipt?.status || "UNKNOWN")],
      ["ERP acknowledged", liveRecord ? (liveRecord.erp_acknowledged ? "YES" : "NO") : "WAITING"],
    ];
    if (componentId === "jira") common.metrics = [
      ["Live issue", value(liveRecord?.record_id || "WAITING")],
      ["Risk", `${number(risk.score)} · ${value(risk.band || "WAITING")}`],
      ["Read at", value(liveRecord?.occurred_at || "WAITING")],
    ];
    if (componentId === "slack") common.metrics = [
      ["Live message", value(liveRecord?.record_id || "WAITING")],
      ["Review", value(humanReview.status || "WAITING").replaceAll("_", " ")],
      ["Channel read", value(liveRecord?.status || "WAITING")],
    ];
    if (componentId === "agent") {
      common.status = value(agentRun.state || "IDLE").replaceAll("_", " ");
      common.metrics = [
        ["Evidence", String(number(platform.judge_proof?.evidence_records))],
        ["Source checks", String(number(platform.judge_proof?.source_checks))],
        ["Risk in scope", `${number(risk.score)} / 100`],
        ["Confidence", `${Math.round(number(agentRun.confidence) * 100)}%`],
      ];
    }
    if (componentId === "manager") {
      common.status = value(humanReview.status || "STANDBY").replaceAll("_", " ");
      common.metrics = [
        ["Required", humanReview.required ? "YES" : "NO"],
        ["Next action", value(humanReview.action || "NONE").replaceAll("_", " ")],
        ["Can pause", humanReview.can_stop ? "YES" : "NO"],
      ];
    }
    return common;
  }

  function showPlatformNodePopover(node) {
    const popover = $("platform-node-popover");
    if (!popover || !node) return;
    const componentId = value(node.dataset.investigationNode || node.dataset.platformSource);
    const context = platformComponentContext(componentId);
    state.platformSelectedNode = componentId;
    $("platform-node-popover-title").textContent = context.title;
    $("platform-node-popover-status").textContent = context.status;
    $("platform-node-popover-detail").textContent = context.purpose;
    const metrics = $("platform-node-popover-metrics");
    metrics.replaceChildren();
    context.metrics.forEach(([label, metricValue]) => {
      const row = create("div");
      row.append(create("dt", null, label), create("dd", null, metricValue));
      metrics.append(row);
    });
    const action = $("platform-node-popover-action");
    action.dataset.componentId = componentId;
    action.textContent = componentId === "manager" ? "Open decision" : componentId === "agent" ? "Open Agent" : "Ask Agent";
    const external = $("platform-node-popover-external");
    if (external) {
      external.hidden = !context.external;
      external.href = value(context.external?.url || "#");
      const label = external.querySelector("span");
      if (label) label.textContent = value(context.external?.label || "Open service");
      external.setAttribute("aria-label", `${value(context.external?.label || "Open service")} in a new tab`);
    }
    popover.hidden = false;
    const canvasBounds = $("platform-command-canvas").getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    const popoverWidth = popover.getBoundingClientRect().width;
    popover.style.left = `${Math.max(12, Math.min(canvasBounds.width - popoverWidth - 12, rect.left - canvasBounds.left + rect.width + 12))}px`;
    popover.style.top = `${Math.max(72, rect.top - canvasBounds.top - 8)}px`;
    node.setAttribute("aria-expanded", "true");
  }

  function closePlatformNodePopover() {
    const popover = $("platform-node-popover");
    if (popover) popover.hidden = true;
    document.querySelectorAll("[data-investigation-node]").forEach((node) => node.setAttribute("aria-expanded", "false"));
    document.querySelectorAll("[data-platform-source]").forEach((node) => node.setAttribute("aria-expanded", "false"));
    state.platformSelectedNode = "";
  }

  function bindPlatformCanvasInteractions() {
    state.platformLayout = readPlatformLayout();
    applyPlatformLayout();
    $("platform-arrange-mode")?.addEventListener("click", () => setPlatformArrangeMode(!state.platformArrangeMode));
    $("platform-reset-layout")?.addEventListener("click", resetPlatformLayout);
    $("platform-node-popover-close")?.addEventListener("click", closePlatformNodePopover);
    $("platform-node-popover-action")?.addEventListener("click", () => {
      const componentId = value($("platform-node-popover-action").dataset.componentId);
      closePlatformNodePopover();
      if (componentId === "manager") {
        focusPlatformModule(document.querySelector('[data-canvas-module="decision"]'));
        return;
      }
      if (componentId === "agent") {
        focusPlatformModule(document.querySelector('[data-canvas-module="agent-console"]'));
        return;
      }
      const input = $("platform-question");
      if (input) {
        input.value = `Explain the current ${platformComponentContext(componentId).title} evidence, its parameters, and how it affects the risk signal.`;
        focusPlatformModule(document.querySelector('[data-canvas-module="conversation"]'));
        input.focus();
      }
    });
    document.querySelectorAll("[data-module-focus]").forEach((button) => {
      button.addEventListener("click", () => focusPlatformModule(button.closest("[data-canvas-module]")));
    });
    document.querySelectorAll("[data-investigation-node]").forEach((node) => {
      node.setAttribute("aria-expanded", "false");
      node.addEventListener("click", () => showPlatformNodePopover(node));
    });
    document.querySelectorAll("[data-canvas-module]").forEach((module) => {
      const begin = (event, mode) => {
        if (!state.platformArrangeMode || event.button !== 0) return;
        if (event.target.closest("button") && !event.target.closest("[data-module-resize]")) return;
        event.preventDefault();
        const id = module.dataset.canvasModule;
        const current = state.platformLayout[id] || {};
        const rect = module.getBoundingClientRect();
        const start = { x: event.clientX, y: event.clientY, tx: number(current.x), ty: number(current.y), width: rect.width, height: rect.height };
        module.setPointerCapture(event.pointerId);
        module.classList.add("is-manipulating");
        const move = (moveEvent) => {
          const dx = moveEvent.clientX - start.x;
          const dy = moveEvent.clientY - start.y;
          const next = state.platformLayout[id] = { ...current };
          if (mode === "move") {
            next.x = start.tx + dx;
            next.y = start.ty + dy;
          } else {
            next.width = Math.max(220, start.width + dx);
            next.height = Math.max(180, start.height + dy);
          }
          applyPlatformLayout();
          renderPlatformInvestigationLinks();
        };
        const finish = () => {
          module.classList.remove("is-manipulating");
          module.removeEventListener("pointermove", move);
          module.removeEventListener("pointerup", finish);
          module.removeEventListener("pointercancel", finish);
          storePlatformLayout();
        };
        module.addEventListener("pointermove", move);
        module.addEventListener("pointerup", finish);
        module.addEventListener("pointercancel", finish);
      };
      module.querySelector("[data-module-handle]")?.addEventListener("pointerdown", (event) => begin(event, "move"));
      module.querySelector("[data-module-resize]")?.addEventListener("pointerdown", (event) => begin(event, "resize"));
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (state.platformFocusedModule) focusPlatformModule(null);
      closePlatformNodePopover();
      closeDashboardComponentInspector();
    });
  }

  function setBadge(node, label, rawState) {
    if (!node) return;
    node.className = `state-badge ${stateClass(rawState)}`;
    node.textContent = value(label);
  }

  function setConnection(connection, detail) {
    state.connection = connection;
    const liveSequence = platformFlowProjection()?.latestSequence;
    const authoritativeSequence = liveSequence || state.lastSequence;
    const labels = { live: "LIVE", connecting: "CONNECTING", paused: "PAUSED" };
    $("connection-label").textContent = labels[connection] || "PAUSED";
    $("connection-dot").className = `status-dot ${connection === "live" ? "status-dot-lime" : connection === "paused" ? "status-dot-danger" : "status-dot-cyan"}`;
    $("sequence-label").textContent = `seq ${authoritativeSequence || "—"}`;
    $("footer-status").textContent = detail || (connection === "live" ? "Ledger connected." : "Live movement paused.");
    $("live-heartbeat").textContent = connection === "live" ? "Connected" : connection === "connecting" ? "Connecting" : "Paused";
    document.body.dataset.connection = connection;
  }

  function streamIsLive() {
    return state.connection === "live";
  }

  function platformInvoiceStatus(platform) {
    const projection = platform?.case_projection || platform?.demo_case;
    const facts = projection?.case;
    if (projection?.provenance === "live-read") {
      if (platform.source_freshness?.status !== "CURRENT") return "UNKNOWN";
      if (platform.document_lifecycle?.purchase_invoice === "AWAITING_INVOICE"
        && !facts?.purchase_invoice && !facts?.quantities?.invoice_count) return "NOT YET INVOICED";
      if (!facts?.purchase_invoice && !facts?.quantities?.invoice_count) return "UNKNOWN";
    }
    return facts?.invoice_held ? "HELD" : facts ? "OPEN" : "UNKNOWN";
  }

  function receivingNeedsAttention(platform) {
    return platform?.receiving_work?.status === "CONFIGURED"
      && Array.isArray(platform.receiving_work.arrivals)
      && platform.receiving_work.arrivals.some((arrival) =>
        ["NEEDS_REVIEW", "NEEDS_PHOTO", "UNAVAILABLE", "DRAFT_UNKNOWN", "SUBMIT_UNKNOWN"].includes(arrival.status));
  }

  function platformFlowProjection() {
    const platform = state.agentPlatform;
    if (!platform) return null;
    const caseProjection = platform.case_projection && typeof platform.case_projection === "object"
      ? platform.case_projection
      : platform.demo_case;
    const liveAuthority = value(caseProjection?.provenance).toLowerCase() === "live-read";
    // A selected synthetic incident has one Case Console authority in both
    // views. Never label it live or overlay it on the separate normal baseline.
    const syntheticAuthority = value(caseProjection?.provenance) === "synthetic-demo-fixture"
      && state.activeScenario !== "normal";
    if (!liveAuthority && !syntheticAuthority) return null;
    const demoCase = caseProjection && typeof caseProjection === "object"
      ? caseProjection.case
      : null;
    const quantities = demoCase && demoCase.quantities && typeof demoCase.quantities === "object"
      ? demoCase.quantities
      : null;
    if (!quantities) return null;
    const expected = number(quantities.ordered, number(quantities.physically_arrived));
    const recorded = number(quantities.available);
    const received = number(quantities.received_cumulative, number(quantities.received,
      syntheticAuthority ? number(quantities.physically_arrived) : 0));
    const posted = number(quantities.receipt_posted_quantity,
      syntheticAuthority ? recorded + number(quantities.quality_hold) : received);
    const invoiceCount = number(quantities.invoice_count,
      syntheticAuthority ? (demoCase.invoice_held ? 0 : recorded) : 0);
    const qualityHold = number(quantities.quality_hold);
    const receiptUnresolved = number(quantities.receipt_unresolved);
    const gap = qualityHold + receiptUnresolved;
    const execution = platform.execution && typeof platform.execution === "object"
      ? platform.execution
      : {};
    return {
      caseId: value(platform.case_id),
      runId: value(platform.run_id),
      caseVersion: number(platform.case_version),
      expected,
      recorded,
      received,
      posted,
      invoiceCount,
      uom: value(demoCase.uom || "units"),
      gap,
      qualityHold,
      receiptUnresolved,
      invoiceHeld: Boolean(demoCase.invoice_held),
      invoiceStatus: platformInvoiceStatus(platform),
      verified: value(execution.status).toUpperCase() === "VERIFIED",
      sourceCurrent: liveAuthority ? platform.source_freshness?.status === "CURRENT" : true,
      latestSequence: number(platform.latest_sequence),
      provenance: value(caseProjection?.provenance || platform.mode?.provenance),
    };
  }

  function businessImpactProjection() {
    const raw = state.agentPlatform?.business_impact;
    if (!raw || typeof raw !== "object") return null;
    const liveAuthority = value(state.agentPlatform?.case_projection?.provenance).toLowerCase() === "live-read";
    if (state.activeScenario !== "normal" || liveAuthority) return raw;
    return {
      ...raw,
      inventory_availability_percent: 100,
      erp_reconciliation_percent: 100,
      working_capital_at_risk: 0,
      invoice_hold_value: 0,
      quality_hold_value: 0,
      receipt_gap_value: 0,
      receipt_gap_percent: 0,
      quality_hold_percent: 0,
      available_inventory_value: number(raw.po_line_value),
      value_protected: 0,
      supplier_status: value(raw.supplier_status || "ACTIVE"),
      supplier_payment_hold: false,
      invoice_status: "OPEN",
    };
  }

  function valueProofProjection() {
    const raw = state.agentPlatform?.value_proof;
    return raw && typeof raw === "object" ? raw : null;
  }

  function hasLiveSourceAuthority() {
    return value(state.agentPlatform?.case_projection?.provenance).toLowerCase() === "live-read";
  }

  function connectedOperationsProjection() {
    const raw = state.agentPlatform?.connected_operations;
    if (!raw || typeof raw !== "object") return null;
    const liveAuthority = hasLiveSourceAuthority();
    // The 90-day plant window is a disclosed Scenario Lab fixture.  It must
    // never appear beside authoritative ERP records: mixing those two clocks
    // makes a live read look like a fabricated production history.
    if (liveAuthority && value(raw.provenance).toLowerCase().includes("synthetic")) return null;
    if (state.activeScenario !== "normal" || liveAuthority) return raw;
    const currentShift = raw.current_shift && typeof raw.current_shift === "object" ? raw.current_shift : {};
    const customer = raw.customer_commitments && typeof raw.customer_commitments === "object" ? raw.customer_commitments : {};
    const inventory = raw.inventory && typeof raw.inventory === "object" ? raw.inventory : {};
    const history = Array.isArray(raw.history) ? raw.history.map((point) => ({ ...point })) : [];
    if (history.length) {
      const latest = history[history.length - 1];
      latest.actual_units = number(latest.planned_units);
      latest.schedule_attainment_percent = 100;
      latest.risk_score = 0;
      latest.units_at_risk = 0;
      latest.revenue_at_risk = 0;
    }
    return {
      ...raw,
      risk_signal: { ...(raw.risk_signal || {}), score: 0, band: "NORMAL", units_at_risk: 0, reasons: [] },
      current_shift: {
        ...currentShift,
        actual_units: number(currentShift.planned_units),
        component_starved_units: 0,
        schedule_attainment_percent: 100,
        availability_percent: 96.2,
        oee_percent: 92.3,
      },
      customer_commitments: {
        ...customer,
        units_at_risk: 0,
        revenue_at_risk: 0,
        contribution_margin_at_risk: 0,
      },
      inventory: {
        ...inventory,
        available_component_units: 100,
        days_of_supply: 4.2,
      },
      history,
    };
  }

  function formatCurrency(amount, currency = "USD") {
    if (amount == null || amount === "" || typeof amount === "boolean") return "—";
    const numeric = Number(amount);
    if (!Number.isFinite(numeric)) return "—";
    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: value(currency || "USD"),
        maximumFractionDigits: Number.isInteger(numeric) ? 0 : 2,
      }).format(numeric);
    } catch (_error) {
      return `$${numeric.toFixed(Number.isInteger(numeric) ? 0 : 2)}`;
    }
  }

  function incidentStatus() {
    const platform = platformFlowProjection();
    if (platform?.verified) return "CLOSED";
    return value(state.snapshot && state.snapshot.incident && state.snapshot.incident.status);
  }

  function isVerifiedClosedRecovery() {
    const platform = platformFlowProjection();
    if (platform?.verified) return true;
    const snapshot = state.snapshot || {};
    const incidentState = value(snapshot.incident && snapshot.incident.status).toUpperCase();
    return (incidentState === "CLOSED" || state.activeScenario === "recovery")
      && Boolean(snapshot.execution && snapshot.execution.verified);
  }

  function isClosedOrRecovery() {
    const platform = platformFlowProjection();
    if (platform?.verified) return true;
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

  async function refreshEnterpriseEvidence() {
    if (state.erpEvidenceBusy) return;
    state.erpEvidenceBusy = true;
    try {
      state.erpEvidence = await requestJSON("/api/v1/erpnext-evidence");
      state.erpEvidenceError = "";
    } catch (error) {
      state.erpEvidenceError = error.message;
    } finally {
      state.erpEvidenceBusy = false;
      scheduleRender();
    }
  }

  function scheduleEnterpriseEvidenceRefresh() {
    if (smokeCapture || providerPollingDisabled || state.erpEvidenceTimer != null) return;
    state.erpEvidenceTimer = window.setTimeout(() => {
      state.erpEvidenceTimer = null;
      if (document.hidden) {
        scheduleEnterpriseEvidenceRefresh();
        return;
      }
      refreshEnterpriseEvidence().finally(scheduleEnterpriseEvidenceRefresh);
    }, 5000);
  }

  function startEnterpriseEvidenceRefresh() {
    if (smokeCapture || providerPollingDisabled || state.erpEvidenceTimer != null) return;
    refreshEnterpriseEvidence();
    scheduleEnterpriseEvidenceRefresh();
  }

  async function refreshSaasEvidence() {
    if (state.saasEvidenceBusy) return;
    state.saasEvidenceBusy = true;
    try {
      state.saasEvidence = await requestJSON("/api/v1/saas-evidence");
      state.saasEvidenceError = "";
    } catch (error) {
      state.saasEvidenceError = error.message;
    } finally {
      state.saasEvidenceBusy = false;
      scheduleRender();
    }
  }

  function scheduleSaasEvidenceRefresh() {
    if (smokeCapture || providerPollingDisabled || state.saasEvidenceTimer != null) return;
    state.saasEvidenceTimer = window.setTimeout(() => {
      state.saasEvidenceTimer = null;
      if (document.hidden) {
        scheduleSaasEvidenceRefresh();
        return;
      }
      refreshSaasEvidence().finally(scheduleSaasEvidenceRefresh);
    }, 15000);
  }

  function startSaasEvidenceRefresh() {
    if (smokeCapture || providerPollingDisabled || state.saasEvidenceTimer != null) return;
    refreshSaasEvidence();
    scheduleSaasEvidenceRefresh();
  }

  async function refreshAgentPlatform(force = false) {
    if (state.agentPlatformBusy || (smokeCapture && !force)) return;
    state.agentPlatformBusy = true;
    try {
      setAgentPlatformProjection(await requestJSON("/api/v1/agent-platform"));
      try {
        state.ambiguousReceiptCase = await requestJSON("/api/v1/ambiguous-receipt-case");
      } catch (_error) {
        state.ambiguousReceiptCase = null;
      }
      state.agentPlatformError = "";
      state.agentPlatformReadError = "";
    } catch (error) {
      state.agentPlatformError = error.message;
      state.agentPlatformReadError = error.message;
    } finally {
      state.agentPlatformBusy = false;
      scheduleRender();
    }
  }

  function setAgentPlatformProjection(projection) {
    state.agentPlatformPulseAfter = number(state.agentPlatform && state.agentPlatform.latest_sequence);
    state.agentPlatform = projection;
    if (typeof window !== "undefined" && typeof CustomEvent !== "undefined") {
      window.dispatchEvent(new CustomEvent("missing20:projection", { detail: {
        caseId: projection?.case_id, sequence: projection?.latest_sequence,
        sourceStatus: projection?.source_freshness?.status,
        provenance: projection?.mode?.provenance,
      } }));
    }
  }

  window.addEventListener("missing20:receipt-changed", () => {
    scheduleAgentPlatformProjectionRefresh();
  });

  function startAgentPlatformRefresh() {
    if (smokeCapture || providerPollingDisabled || state.agentPlatformTimer != null) return;
    // Use short projection reads instead of a second permanent EventSource.
    // One authoritative incident stream remains live; bounded polling prevents
    // several open demo tabs from exhausting the browser's per-host connection pool.
    state.agentPlatformTimer = window.setTimeout(async () => {
      state.agentPlatformTimer = null;
      if (document.hidden) {
        startAgentPlatformRefresh();
        return;
      }
      await refreshAgentPlatform();
      startAgentPlatformRefresh();
    }, 1500);
  }

  function scheduleAgentPlatformProjectionRefresh() {
    if (smokeCapture || providerPollingDisabled) return;
    if (state.agentPlatformTimer != null) window.clearTimeout(state.agentPlatformTimer);
    state.agentPlatformTimer = window.setTimeout(() => {
      state.agentPlatformTimer = null;
      void refreshAgentPlatform().finally(startAgentPlatformRefresh);
    }, 650);
  }

  async function syncPlatformInvestigation() {
    await refreshAgentPlatform();
    startAgentPlatformRefresh();
  }

  function syncDashboardSourceControl() {
    const control = $("dashboard-inject-incident");
    if (!control) return;
    const liveSourceMode = hasLiveSourceAuthority();
    const leadingLabel = control.querySelector("span:not([aria-hidden])");
    const actionLabel = control.querySelector("strong");
    if (leadingLabel) leadingLabel.textContent = liveSourceMode ? "Source" : "Live";
    if (actionLabel) actionLabel.textContent = liveSourceMode ? "Open ERPNext" : "Inject incident";
    control.title = liveSourceMode
      ? "Open ERPNext; this dashboard advances only after the external records change"
      : "Create the server-backed Scenario Lab incident";
    control.dataset.sourceAuthority = liveSourceMode ? "external" : "scenario";
    const demoControls = $("demo-controls-toggle");
    if (demoControls) {
      demoControls.hidden = liveSourceMode;
      demoControls.setAttribute("aria-hidden", String(liveSourceMode));
    }
  }

  function renderAgentPlatform() {
    const consoleNode = $("agent-platform-console");
    if (!consoleNode) return;
    const platform = state.agentPlatform;
    // A healthy dashboard stays a sparse operational baseline. The case console
    // is an incident workspace: it appears only after the server-backed anomaly
    // transition, then remains available through recovery and verification.
    const liveFlow = platformFlowProjection();
    const sourceAttention = receivingNeedsAttention(platform)
      || Boolean(liveFlow && (liveFlow.gap > 0 || liveFlow.invoiceHeld));
    // Live users can ask evidence questions even without an incident. The sparse
    // normal scene is only the explicitly controlled scenario, never live truth.
    const normalScenario = isNormalScenario() && !sourceAttention && !hasLiveSourceAuthority();
    syncDashboardSourceControl();
    const verifiedHistory = Boolean(
      platform?.resolution_packet?.status === "VERIFIED"
      || platform?.execution?.status === "VERIFIED"
      || platform?.judge_proof?.verified === true
    );
    const enabled = Boolean(platform) && (!normalScenario || verifiedHistory);
    const agentView = $("agent-view");
    if (agentView && consoleNode.parentElement !== agentView) agentView.prepend(consoleNode);
    consoleNode.hidden = !enabled;
    const normalState = $("agent-normal-state");
    if (normalState) normalState.hidden = !Boolean(platform) || !normalScenario || verifiedHistory;
    const normalSequence = $("agent-normal-sequence");
    if (normalSequence) normalSequence.textContent = String(number(platform?.latest_sequence, state.lastSequence));
    const legacyDashboard = document.querySelector("#dashboard-view .dashboard-grid");
    const legacyWorkspace = document.querySelector("#agent-view .workspace-layout");
    if (legacyDashboard) legacyDashboard.hidden = false;
    // The old Operations Map remains only as a compatibility fixture. Every
    // user-visible Agent state now uses the same light command-system shell.
    if (legacyWorkspace) legacyWorkspace.hidden = Boolean(platform) && !smokeCapture;
    document.body.dataset.agentPlatform = platform ? "ready" : "pending";
    if (!enabled) return;

    const correlation = platform.correlation && typeof platform.correlation === "object"
      ? platform.correlation
      : {};
    setBadge($("platform-correlation"), value(correlation.status || "CORRELATION —").replaceAll("_", " "), correlation.status);
    const providerWrites = value(platform.mode && platform.mode.provider_writes || "DISABLED");
    const sourceProvenance = value(platform.mode && platform.mode.provenance);
    const writeLabel = providerWrites === "DISABLED"
      ? "WRITES DISABLED"
      : providerWrites === "LOCAL_SYNTHETIC_ONLY"
        ? "DEMO TENANT"
        : providerWrites.replaceAll("_", " ");
    setBadge(
      $("platform-mode"),
      `${sourceProvenance === "live-read" ? "LIVE READ · " : ""}${writeLabel}`,
      providerWrites,
    );
    const tuple = correlation.tuple && typeof correlation.tuple === "object" ? correlation.tuple : {};
    const platformCase = platform.demo_case && typeof platform.demo_case === "object"
      ? platform.demo_case.case
      : null;
    const caseProjection = platformCase && typeof platformCase === "object"
      ? platformCase
      : (state.ambiguousReceiptCase && typeof state.ambiguousReceiptCase === "object"
        ? state.ambiguousReceiptCase.case
        : null);
    const caseFacts = caseProjection && typeof caseProjection === "object" ? caseProjection : null;
    const caseQuantities = caseFacts && caseFacts.quantities && typeof caseFacts.quantities === "object"
      ? caseFacts.quantities
      : null;
    $("platform-incident-code").textContent = value(caseFacts && caseFacts.case_id || tuple.case_id || "M20");
    const tupleNode = $("platform-case-tuple");
    tupleNode.replaceChildren();
    const caseDisplay = caseFacts && caseQuantities
      ? [
        ["arrived", caseQuantities.physically_arrived],
        ["case balance", caseQuantities.available],
        ["quality", caseQuantities.quality_hold],
        ["receipt gap", caseQuantities.receipt_unresolved],
        ["invoice", platformInvoiceStatus(platform).toLowerCase()],
      ]
      : ["case_id", "purchase_order", "purchase_receipt", "purchase_invoice", "quantity"].map((key) => [key.replaceAll("_", " "), tuple[key]]);
    caseDisplay.forEach(([key, itemValue]) => {
      const item = create("span", "platform-tuple");
      item.append(create("strong", null, key), create("span", null, value(itemValue) || "—"));
      tupleNode.append(item);
    });
    const missing = Array.isArray(correlation.missing_fields) ? correlation.missing_fields : [];
    const mismatched = Array.isArray(correlation.mismatched_fields) ? correlation.mismatched_fields : [];
    const integrationOutcome = value(caseFacts && caseFacts.integration_outcome).toUpperCase();
    const ribbonExecutionStatus = value(platform.execution && platform.execution.status).toUpperCase();
    const inventoryReconciled = Boolean(liveFlow && liveFlow.gap === 0);
    const receivingNormal = platform.receiving_work?.status === "CONFIGURED"
      && !receivingNeedsAttention(platform)
      && inventoryReconciled && liveFlow.sourceCurrent && !liveFlow.invoiceHeld;
    if (receivingNormal) setBadge($("platform-correlation"), "RECEIVING", "HEALTHY");
    else if (receivingNeedsAttention(platform)) setBadge($("platform-correlation"), "REVIEW REQUIRED", "NEEDS_REVIEW");
    $("platform-title").textContent = ribbonExecutionStatus === "VERIFIED"
      ? "Verified recovery"
      : inventoryReconciled && liveFlow.invoiceHeld
        ? "Invoice payment hold"
        : liveFlow?.gap > 0
          ? "Receipt reconciliation"
          : receivingNeedsAttention(platform) ? "Receiving needs review"
            : receivingNormal ? "Receiving operations" : "Connected investigation";
    $("platform-correlation-detail").textContent = caseFacts && caseQuantities
      ? (ribbonExecutionStatus === "VERIFIED"
        ? "Receipt reconciled · recovery independently verified"
        : inventoryReconciled && liveFlow.invoiceHeld
          ? "Inventory reconciled · invoice payment hold awaits agent diagnosis"
          : liveFlow?.gap > 0
            ? `${liveFlow.gap} units require cross-source reconciliation`
            : receivingNeedsAttention(platform) ? "Receiving evidence needs review · posted stock unchanged"
              : receivingNormal ? liveReceivingSummary(liveFlow).detail
              : `Receipt confirmed · integration ${["ACKNOWLEDGED", "VERIFIED"].includes(integrationOutcome) ? "acknowledged" : "requires review"}`)
      : missing.length
      ? `Partial correlation · ${missing.join(", ")}`
      : (mismatched.length
        ? `Correlation mismatch · ${mismatched.join(", ")}`
        : `Full correlation · ${providerWrites === "DEMO_GUARDED" ? "manager-gated execution" : "read only"}`);

    const agentRun = platform.agent_run && typeof platform.agent_run === "object"
      ? platform.agent_run
      : {};
    const diagnosis = platform.diagnosis && typeof platform.diagnosis === "object" ? platform.diagnosis : {};
    const proof = platform.judge_proof && typeof platform.judge_proof === "object" ? platform.judge_proof : {};
    const strands = diagnosis.strands_investigation && typeof diagnosis.strands_investigation === "object"
      ? diagnosis.strands_investigation
      : {};
    const execution = platform.execution && typeof platform.execution === "object" ? platform.execution : {};
    const executionStatus = value(execution.status || "AWAITING_MANAGER_APPROVAL");
    const runState = value(agentRun.state).toUpperCase();
    consoleNode.dataset.phase = executionStatus === "VERIFIED"
      ? "verified"
      : ["PLAN_READY", "COMPLETE", "RECOVERY_READY"].includes(runState)
        ? "decision"
        : runState === "IDLE" ? "idle" : "running";
    setBadge($("platform-run-state"), value(agentRun.state || "IDLE").replaceAll("_", " "), agentRun.state);
    const usage = strands.usage && typeof strands.usage === "object" ? strands.usage : {};
    const provider = proof.provider && typeof proof.provider === "object"
      ? proof.provider
      : (strands.provider && typeof strands.provider === "object" ? strands.provider : {});
    const modelId = value(provider.model);
    const runtimeStatus = value(strands.status).toUpperCase();
    const runtimeLabel = ["AGENT_UNAVAILABLE", "VALIDATION_FAILED"].includes(runtimeStatus)
      ? "Unavailable"
      : modelId.includes("nova-pro")
      ? "Nova Pro"
      : modelId.includes("nova-lite")
        ? "Nova Lite"
        : (modelId.split(/[.:/]/).filter(Boolean).at(-1) || value(proof.runtime) || "—");
    const metricText = (id, text) => {
      const node = $(id);
      if (node) node.textContent = text;
    };
    metricText("platform-metric-runtime", runState === "IDLE" && runtimeLabel === "—" ? "On start" : runtimeLabel);
    metricText("platform-metric-latency", number(strands.latency_ms) ? `${(number(strands.latency_ms) / 1000).toFixed(1)}s` : runState === "IDLE" ? "After run" : "—");
    metricText("platform-metric-tools", String(number(proof.source_checks, Array.isArray(strands.tool_calls) ? strands.tool_calls.length : 0)));
    metricText("platform-metric-evidence", String(number(proof.evidence_records)));
    metricText("platform-metric-cases", Number.isInteger(proof.case_matrix_size) && proof.case_matrix_size >= 0
      ? String(proof.case_matrix_size) : "—");
    metricText("platform-metric-tokens", number(usage.input_tokens) || number(usage.output_tokens)
      ? `${Math.round((number(usage.input_tokens) + number(usage.output_tokens)) / 100) / 10}k`
      : runState === "IDLE" ? "After run" : "—");
    metricText("platform-metric-cost", number(usage.incremental_cost_usd)
      ? `$${number(usage.incremental_cost_usd).toFixed(3)}`
      : runState === "IDLE" ? "After run" : "—");

    const diagnosisState = value(diagnosis.status).toUpperCase();
    const strandsState = value(strands.status).toUpperCase();
    const evaluated = ["PLAN_READY", "COMPLETE", "RECOVERY_READY"].includes(diagnosisState)
      || strandsState === "COMPLETE";
    const approvedOrExecuting = ["AUTHORIZED", "EXECUTING", "VERIFYING", "VERIFIED"].includes(executionStatus);
    const stageState = {
      observe: runState === "IDLE" ? "waiting" : "complete",
      retrieve: strandsState === "COMPLETE" || evaluated ? "complete" : runState === "GATHERING" ? "current" : "waiting",
      reconcile: evaluated ? "complete" : runState === "RECONCILING" ? "current" : "waiting",
      evaluate: evaluated ? "complete" : ["EVALUATING", "SYNTHESIZING"].includes(runState) ? "current" : "waiting",
      decide: executionStatus === "VERIFIED" || approvedOrExecuting ? "complete" : evaluated ? "current" : "waiting",
      verify: executionStatus === "VERIFIED" ? "complete" : ["VERIFYING", "EXECUTING"].includes(executionStatus) ? "current" : "waiting",
    };
    document.querySelectorAll("#platform-loop-stages [data-loop-stage]").forEach((node) => {
      const status = stageState[node.dataset.loopStage] || "waiting";
      node.classList.toggle("is-complete", status === "complete");
      node.classList.toggle("is-current", status === "current");
      node.classList.toggle("is-waiting", status === "waiting");
      node.setAttribute("aria-current", status === "current" ? "step" : "false");
    });
    const constellation = platform.evidence_constellation && typeof platform.evidence_constellation === "object"
      ? platform.evidence_constellation
      : {};
    const conclusion = constellation.conclusion && typeof constellation.conclusion === "object"
      ? constellation.conclusion
      : {};
    const pulseAfter = number(state.agentPlatformPulseAfter);
    const latestSequence = number(platform.latest_sequence);
    const constellationNodes = Array.isArray(constellation.nodes) ? constellation.nodes : [];
    const integration = platform.integration_receipt && typeof platform.integration_receipt === "object"
      ? platform.integration_receipt
      : {};
    const sourceReceipts = $("platform-source-receipts");
    sourceReceipts.replaceChildren();
    const observedDate = new Date(value(platform.received_at));
    const observedTime = Number.isNaN(observedDate.getTime())
      ? "OBSERVED —"
      : `OBSERVED ${observedDate.toLocaleTimeString([], { hour12: false })}`;
    const sourceRecord = {
      erpnext: caseFacts ? `${value(caseFacts.purchase_order_id)} · ${value(caseFacts.invoice_id)}` : "—",
      airtable: caseFacts ? `${value(caseFacts.supplier_lot)} · ${value(caseFacts.quality_release_key)}` : "—",
      celigo: caseFacts ? value(caseFacts.receipt_business_key) : value(integration.record_id),
      slack: caseFacts ? value(caseFacts.case_id) : value(tuple.case_id),
    };
    const platformSystems = Array.isArray(platform.systems) ? platform.systems : [];
    $("platform-signal-count").textContent = `${platformSystems.length} systems`;
    platformSystems.forEach((system) => {
      if (!system || typeof system !== "object") return;
      const systemId = value(system.id);
      const evidenceNode = constellationNodes.find((node) => node && value(node.id) === systemId) || {};
      const status = value(evidenceNode.status || system.status || "UNKNOWN");
      const receipt = create("button", `platform-source-receipt is-${status.toLowerCase()}`);
      receipt.type = "button";
      receipt.dataset.platformSource = systemId;
      receipt.setAttribute("aria-expanded", "false");
      receipt.classList.toggle("is-problem", isProblemStatus(status));
      if (number(evidenceNode.latest_sequence) > pulseAfter) receipt.classList.add("is-live");
      const heading = create("div", "platform-source-receipt-head");
      const systemLabel = system.write_state === "EVENT_DRIVEN_NOTIFICATION" ? value(system.name) : {
        erpnext: "ERPNext",
        airtable: "Airtable Quality",
        celigo: "Celigo",
        jira: "Jira",
        slack: "Slack",
      }[systemId] || value(system.name);
      receipt.setAttribute("aria-label", `${systemLabel}, ${human(status)}. Inspect live parameters.`);
      receipt.addEventListener("click", () => showPlatformNodePopover(receipt));
      heading.append(
        create("strong", null, systemLabel),
        create("span", null, status.replaceAll("_", " ")),
      );
      receipt.append(
        heading,
        create("code", null, value(system.record_id) || sourceRecord[systemId] || "—"),
        create("span", "platform-source-authority", value(system.authority)),
        create("time", "platform-source-time", observedTime),
      );
      sourceReceipts.append(receipt);
    });
    const systemById = new Map(platformSystems.map((system) => [value(system && system.id), system]));
    PLATFORM_NODE_IDS.forEach((nodeId) => {
      const node = document.querySelector(`[data-investigation-node="${nodeId}"]`);
      if (!node) return;
      const evidenceNode = constellationNodes.find((item) => item && value(item.id) === nodeId) || {};
      const system = systemById.get(nodeId) || {};
      let status = value(evidenceNode.status || system.status || "WAITING");
      let detail = value(system.record_id || system.authority || "Waiting for evidence");
      if (nodeId === "agent") {
        status = value(agentRun.state || strands.status || "IDLE");
        detail = value(diagnosis.summary || "Ready to investigate");
      } else if (nodeId === "manager") {
        status = value(platform.human_review && platform.human_review.status || "STANDBY");
        detail = value(platform.human_review && platform.human_review.reason || "No decision required yet");
      }
      node.className = `platform-investigation-node${nodeId === "agent" ? " platform-agent-node" : ""}${nodeId === "manager" ? " platform-manager-node" : ""} ${stateClass(status)}`;
      node.classList.toggle("is-problem", isProblemStatus(status));
      if (latestSequence > pulseAfter && (nodeId === "agent" || value(evidenceNode.status))) node.classList.add("is-live");
      node.dataset.nodeLabel = node.querySelector("strong")?.textContent || nodeId;
      node.dataset.nodeStatus = status.replaceAll("_", " ");
      node.dataset.nodeDetail = detail;
    });
    const conclusionNode = $("platform-conclusion");
    conclusionNode.textContent = receivingNeedsAttention(platform) ? "Review receiving evidence"
      : receivingNormal ? "Receiving in progress"
      : value(conclusion.label || "NO RELEASE");
    const conclusionCard = $("platform-agent-conclusion");
    conclusionCard.className = `platform-agent-conclusion is-${value(conclusion.status).toLowerCase()}`;
    if (latestSequence > pulseAfter) conclusionCard.classList.add("is-live");
    const receivingEvidenceOnly = platform.receiving_work?.status === "CONFIGURED"
      && !["AUTHORIZED", "VERIFYING", "VERIFIED"].includes(executionStatus);
    $("platform-confidence").hidden = receivingEvidenceOnly;
    $("platform-confidence").textContent = executionStatus === "VERIFIED"
      ? "Residual gap · 0 units"
      : number(conclusion.confidence)
        ? `Confidence · ${number(conclusion.confidence).toFixed(2)}`
        : "Not scored";
    $("platform-guard").hidden = receivingEvidenceOnly;
    const guardCopy = executionStatus === "VERIFIED"
      ? "RECOVERY VERIFIED"
      : executionStatus === "VERIFYING"
        ? "ERP RECOVERY COMPLETE · VERIFYING RECEIPT"
        : providerWrites === "DEMO_GUARDED"
          ? (executionStatus === "AUTHORIZED" ? "MANAGER APPROVED · READY TO EXECUTE" : "MANAGER-GATED DEMO WRITE")
          : "READ-ONLY OBSERVER";
    $("platform-guard").lastChild.textContent = ` ${guardCopy}`;

    setBadge($("platform-diagnosis-status"), value(diagnosis.status || "IDLE").replaceAll("_", " "), diagnosis.status);
    const strandsStatus = value(strands.status || "IDLE");
    setBadge(
      $("platform-strands-status"),
      strandsStatus === "COMPLETE" ? "REAL STRANDS" : strandsStatus.replaceAll("_", " "),
      strandsStatus,
    );
    $("platform-diagnosis-summary").textContent = value(diagnosis.summary || "No diagnosis has run.");
    const findingsHost = $("platform-reconciled-findings");
    findingsHost.replaceChildren();
    const findings = strands.evidence_findings && typeof strands.evidence_findings === "object"
      ? strands.evidence_findings
      : {};
    const observations = findings.observations && typeof findings.observations === "object"
      ? findings.observations
      : null;
    if (observations) {
      const verifiedPostState = executionStatus === "VERIFIED";
      const physical = verifiedPostState
        ? number(caseQuantities && caseQuantities.physically_arrived)
        : number(observations.physical_received_quantity);
      const qualityHeld = verifiedPostState
        ? number(caseQuantities && caseQuantities.quality_hold)
        : number(observations.erp_quality_inspection_quantity);
      const receiptGap = verifiedPostState
        ? number(caseQuantities && caseQuantities.receipt_unresolved)
        : Math.max(0, physical - number(observations.erp_accounted_quantity));
      const accounted = verifiedPostState
        ? Math.max(0, physical - receiptGap)
        : number(observations.erp_accounted_quantity);
      const keyState = observations.integration_business_key_present_in_erp;
      const businessKey = value(
        findings.join_keys && findings.join_keys.integration_business_key
        || tuple.receipt_business_key
        || `${value(tuple.purchase_receipt)}:receipt-post`,
      );
      const supplierLot = value(tuple.supplier_lot);
      const lotState = verifiedPostState
        ? `${supplierLot} · CLEARED`
        : Array.isArray(observations.exact_held_lot_quality_dispositions)
          && observations.exact_held_lot_quality_dispositions.length
          ? `${supplierLot} · ${observations.exact_held_lot_quality_dispositions.join(" · ")}`
          : supplierLot || "NOT RETURNED";
      [
        ["Physical", physical, "cyan"],
        ["ERP accounted", accounted, "violet"],
        ["Receipt gap", receiptGap, "coral"],
        ["Quality hold", qualityHeld, "amber"],
        ["Business key", keyState === false ? "ABSENT" : businessKey || "NOT RETURNED", keyState === false ? "coral" : "lime"],
        ["Exact lot", lotState, verifiedPostState ? "lime" : "amber"],
      ].forEach(([label, findingValue, tone]) => {
        const item = create("span", `platform-reconciled-finding is-${tone}`);
        item.append(create("small", null, label), create("strong", null, value(findingValue)));
        findingsHost.append(item);
      });
    }
    const hypotheses = $("platform-hypotheses");
    hypotheses.replaceChildren();
    $("platform-findings-history").hidden = !(diagnosis.hypotheses || []).length;
    (Array.isArray(diagnosis.hypotheses) ? diagnosis.hypotheses : []).forEach((hypothesis) => {
      if (!hypothesis || typeof hypothesis !== "object") return;
      // These are historical claims, not assertions about the current stock state.
      const status = value(hypothesis.status || "OPEN");
      const row = create("div", `platform-hypothesis is-${status.toLowerCase()}`);
      row.append(
        create("span", null, value(hypothesis.label)),
        create("strong", null, status),
      );
      hypotheses.append(row);
    });
    const tools = $("platform-tool-calls");
    tools.replaceChildren();
    const selectedTools = new Set(Array.isArray(strands.tool_calls) ? strands.tool_calls.map(value) : []);
    const plannedTools = Array.isArray(diagnosis.tool_calls) ? diagnosis.tool_calls : [];
    const plannedNames = plannedTools
      .filter((tool) => tool && typeof tool === "object")
      .map((tool) => value(tool.tool))
      .filter(Boolean);
    // Once the investigation has completed, show only tools the agent actually
    // called.  Planned-but-skipped tools are useful in a trace export, but add
    // noise to the judge-facing runtime ledger and can be mistaken for work
    // that happened.
    const visibleToolNames = strandsStatus === "COMPLETE"
      ? [...selectedTools]
      : [...new Set([...selectedTools, ...plannedNames])];
    visibleToolNames.forEach((toolName) => {
      const toolState = strandsStatus === "COMPLETE"
        ? "READ"
        : (strandsStatus === "IDLE" ? "WAITING" : strandsStatus.replaceAll("_", " "));
      const item = create("span", `platform-tool-call is-${toolState.toLowerCase().replaceAll(" ", "-")}`);
      item.append(create("strong", null, toolName), create("small", null, toolState));
      tools.append(item);
    });
    const runtimeEvents = Array.isArray(strands.runtime_events) ? strands.runtime_events : [];
    const runtimeTrace = $("platform-runtime-trace");
    const runtimeSpans = [];
    const openToolSpans = new Map();
    let openModelSpan = null;
    let modelTurn = 0;
    runtimeEvents.forEach((event) => {
      if (!event || typeof event !== "object") return;
      const eventType = value(event.type);
      if (eventType === "model.started") {
        modelTurn += 1;
        openModelSpan = {
          lane: "MODEL",
          name: `Reasoning ${modelTurn}`,
          detail: event.projected_input_tokens ? `${number(event.projected_input_tokens)} tokens in` : "started",
          status: "running",
        };
        runtimeSpans.push(openModelSpan);
      } else if (["model.succeeded", "model.failed"].includes(eventType) && openModelSpan) {
        openModelSpan.status = eventType.endsWith("failed") ? "failed" : "complete";
        openModelSpan.detail = `${number(event.duration_ms)} ms`;
        openModelSpan = null;
      } else if (eventType === "tool.started") {
        const rawName = value(event.tool || "tool");
        const span = {
          lane: rawName === "LiveAdvisoryResult" ? "OUTPUT" : "TOOL",
          name: rawName === "LiveAdvisoryResult"
            ? "Typed result"
            : rawName.replace(/^read_/, "").replaceAll("_", " "),
          detail: "running",
          status: "running",
        };
        runtimeSpans.push(span);
        openToolSpans.set(value(event.tool_use_id), span);
      } else if (["tool.succeeded", "tool.failed"].includes(eventType)) {
        const span = openToolSpans.get(value(event.tool_use_id));
        if (!span) return;
        span.status = eventType.endsWith("failed") ? "failed" : "complete";
        span.detail = `${number(event.duration_ms)} ms`;
        openToolSpans.delete(value(event.tool_use_id));
      }
    });
    runtimeTrace.replaceChildren();
    runtimeSpans.slice(-16).forEach((span) => {
      const item = create("li", `platform-runtime-span is-${span.lane.toLowerCase()} is-${span.status}`);
      item.append(
        create("small", null, span.lane),
        create("strong", null, span.name),
        create("span", null, span.detail),
      );
      runtimeTrace.append(item);
    });
    $("platform-runtime-count").textContent = `${runtimeEvents.length} hooks`;
    const review = platform.human_review && typeof platform.human_review === "object"
      ? platform.human_review
      : {};
    setBadge($("platform-review-status"), value(review.status || "HUMAN_START_REQUIRED").replaceAll("_", " "), review.status);
    $("platform-review-detail").textContent = value(review.reason || "Start the investigation when you are ready.");
    const decisionScope = $("platform-decision-scope");
    decisionScope.replaceChildren();
    const packet = platform.resolution_packet && typeof platform.resolution_packet === "object"
      ? platform.resolution_packet
      : null;
    const packetTuple = packet && packet.case_tuple && typeof packet.case_tuple === "object"
      ? packet.case_tuple
      : {};
    const receiptUnits = number(packetTuple.receipt_post_quantity, number(caseQuantities && caseQuantities.receipt_unresolved));
    const qualityUnits = number(packetTuple.quality_transfer_quantity, number(caseQuantities && caseQuantities.quality_hold));
    const finding = value(diagnosis.finding).toUpperCase();
    const decisionRows = value(agentRun.state) === "PLAN_READY" || ["AUTHORIZED", "VERIFYING", "VERIFIED"].includes(executionStatus)
      ? [
          ["Receipt", receiptUnits ? executionStatus === "VERIFIED"
            ? `${receiptUnits} units posted · verified` : `Post ${receiptUnits} unresolved units`
            : "No new receipt needed"],
          ["Quality", qualityUnits ? executionStatus === "VERIFIED"
            ? `${qualityUnits} units released · verified` : `Transfer ${qualityUnits} approved units`
            : "No new quality transfer needed"],
          ["Invoice", caseFacts && caseFacts.invoice_held ? "Revalidate held invoice" : "Invoice verified open"],
        ]
      : value(agentRun.state) === "BLOCKED"
        ? [["Control", ({
            AGENT_UNAVAILABLE: "Retry the real Strands investigation — no plan released",
            AGENT_VALIDATION_FAILED: "Review validation failure — no plan released",
            EFFECT_ALREADY_PRESENT: "Reconcile acknowledgement — no write",
            PHYSICAL_SHORTAGE_CONFIRMED: "Escalate 20-unit supplier shortage — preserve hold",
            CROSS_SOURCE_QUANTITY_CONFLICT: "Request fresh scoped reads — no write",
            QUALITY_EVIDENCE_INELIGIBLE: "Preserve quality and invoice holds — no transfer",
            NEEDS_ERP_KEY_REREAD: "Restore authoritative ERP lookup — no write",
            DUPLICATE_SUPPLIER_INVOICE: "Route duplicate invoice to AP review — no write",
            COMMERCIAL_TERMS_MISMATCH: "Route price variance to Procurement — no write",
            UOM_CONVERSION_EVIDENCE_REQUIRED: "Obtain approved UOM conversion — no write",
            PO_REVISION_EVIDENCE_REQUIRED: "Refresh the current PO revision — no write",
            SUPPLIER_COMPLIANCE_HOLD: "Route vendor hold to Supplier Management — no write",
            LOT_TRACE_MISMATCH: "Reconcile physical lot identity — no write",
            HUMAN_REJECTED_PLAN: "Manager rejected the plan — no write",
          })[finding] || "Safe stop — no write"]]
        : [];
    decisionRows.forEach(([label, detail]) => {
      const row = create("div", "platform-scope-row");
      row.append(create("span", null, label), create("strong", null, detail));
      decisionScope.append(row);
    });
    const diagnosisButton = $("platform-diagnose");
    const reviewAction = value(review.action);
    const canStartOrResume = ["AUTHORIZE_DIAGNOSIS", "START_INVESTIGATION", "RESUME_INVESTIGATION", "RESUME_AFTER_EVIDENCE", "RETRY_INVESTIGATION"].includes(reviewAction);
    diagnosisButton.disabled = state.agentPlatformDiagnosing || !canStartOrResume;
    diagnosisButton.hidden = !canStartOrResume && !state.agentPlatformDiagnosing;
    diagnosisButton.setAttribute("aria-disabled", String(diagnosisButton.disabled));
    diagnosisButton.textContent = state.agentPlatformDiagnosing
      ? "Running authorized diagnosis…"
      : reviewAction === "AUTHORIZE_DIAGNOSIS"
        ? "Authorize diagnosis"
      : reviewAction === "RESUME_AFTER_EVIDENCE"
        ? "Resume after evidence"
        : reviewAction === "RETRY_INVESTIGATION"
          ? "Retry real Agent"
        : reviewAction === "RESUME_INVESTIGATION"
          ? "Resume investigation"
          : "Start investigation";
    const stopButton = $("platform-stop");
    const automation = platform.automation;
    const automationButton = $("platform-automation");
    const automationStatus = $("platform-automation-status");
    automationButton.hidden = !automation;
    automationStatus.hidden = !automation;
    if (automation) {
      automationButton.disabled = state.agentPlatformActionBusy;
      automationButton.textContent = automation.enabled ? "Pause automatic investigation" : "Auto-investigate";
      automationButton.setAttribute("aria-pressed", String(automation.enabled));
      automationStatus.textContent = ({
        PAUSED: "Paused", WATCHING: "Watching for exceptions", INVESTIGATING: "Investigating",
        WAITING_SOURCE: "Waiting for source access", BUSY: "Investigation in progress",
        AWAITING_REVIEW: "Awaiting manager review", NEEDS_ATTENTION: "Investigation needs attention",
        INTERRUPTED: "Previous run interrupted", CASE_CHANGED: "Case changed — paused",
        BUDGET_EXHAUSTED: "Run limit reached — paused",
      })[automation.status] || "Paused";
    }
    const canStop = Boolean(review.can_stop) && !["IDLE", "STOPPED", "VERIFIED"].includes(value(agentRun.state));
    stopButton.hidden = !canStop;
    stopButton.disabled = state.agentPlatformActionBusy;
    const questionInput = $("platform-question");
    const questionSubmit = $("platform-question-submit");
    questionInput.disabled = state.agentPlatformQuestionBusy;
    questionSubmit.disabled = state.agentPlatformQuestionBusy;
    questionSubmit.textContent = state.agentPlatformQuestionBusy ? "Reading…" : "Ask";
    const answerNode = $("platform-answer");
    const feedback = $("platform-question-feedback");
    const attempt = state.agentPlatformQuestionAttempt;
    feedback.hidden = !attempt || attempt.status === "COMPLETE";
    const feedbackSignature = JSON.stringify(attempt);
    if (attempt && !feedback.hidden && feedback.renderedAttempt !== feedbackSignature) {
      feedback.dataset.status = attempt.status;
      feedback.replaceChildren(
        create("p", null, attempt.question),
        create("strong", null, attempt.status === "READING" ? "Checking the source records…" : "The agent could not verify an answer. No action was taken."),
      );
      if (attempt.status !== "READING" && attempt.detail) {
        const details = create("details", "operator-details");
        details.append(create("summary", null, "Why this stopped"), create("p", null, attempt.detail));
        feedback.append(details);
      }
      if (attempt.retainedViews?.length) {
        feedback.append(create("p", null, "Retained observations only — not a current answer."));
        attempt.retainedViews.forEach((attachment) => {
          const view = window.Missing20Conversation?.renderAttachment(attachment);
          if (view) feedback.append(view);
        });
      }
      feedback.renderedAttempt = feedbackSignature;
    }
    const advisory = state.agentPlatformAdvisory && typeof state.agentPlatformAdvisory === "object"
      ? state.agentPlatformAdvisory
      : {};
    const conversation = Array.isArray(platform.conversation) ? platform.conversation : [];
    const suggestions = $("platform-question-suggestions");
    const suggestedQuestions = window.Missing20Conversation?.questionsFor(conversation) || [];
    const suggestionSignature = JSON.stringify([suggestedQuestions, state.agentPlatformQuestionBusy]);
    if (suggestions && suggestions.renderedSuggestions !== suggestionSignature) {
      suggestions.replaceChildren(...suggestedQuestions.map((question) => {
        const button = create("button", "conversation-question", question);
        button.type = "button"; button.disabled = state.agentPlatformQuestionBusy;
        button.addEventListener("click", () => askPlatformQuestion(question));
        return button;
      }));
      suggestions.renderedSuggestions = suggestionSignature;
    }
    answerNode.hidden = !state.agentPlatformAnswer && conversation.length === 0;
    const conversationStatus = state.agentPlatformQuestionBusy
      ? "READING"
      : value(advisory.status || (conversation.length ? "COMPLETE" : "READY"));
    setBadge($("platform-answer-status"), conversationStatus.replaceAll("_", " "), conversationStatus);
    $("platform-answer-trace").textContent = value(advisory.mode === "real_strands" ? "REAL STRANDS" : "");
    const conversationHost = $("platform-answer-text");
    const conversationSignature = JSON.stringify([conversation, state.agentPlatformAnswer]);
    if (conversationHost.renderedConversation !== conversationSignature) {
    const followConversation = conversationHost.scrollHeight - conversationHost.scrollTop - conversationHost.clientHeight < 40;
    const expandedSources = new Set([...conversationHost.querySelectorAll("details[open]")].map((item) => item.dataset.turnIndex));
    conversationHost.replaceChildren();
    conversation.forEach((turn, turnIndex) => {
      if (!turn || typeof turn !== "object") return;
      const item = create("article", "platform-conversation-turn");
      const humanBubble = create("div", "platform-chat-bubble is-human");
      humanBubble.append(create("small", null, "YOU"), create("p", null, value(turn.question)));
      const agentBubble = create("div", "platform-chat-bubble is-agent");
      agentBubble.append(create("small", null, "EVIDENCE AGENT"), create("p", null, value(turn.answer)));
      (Array.isArray(turn.attachments) ? turn.attachments : []).forEach((attachment) => {
        const view = window.Missing20Conversation?.renderAttachment(attachment);
        if (view) agentBubble.append(view);
      });
      if (value(turn.validation_status)) {
        agentBubble.classList.add("is-rejected-claim");
        agentBubble.append(create("strong", "platform-claim-verdict", human(turn.validation_status)));
      }
      const meta = create("div", "platform-chat-meta");
      meta.append(
        create("span", null, `${number(turn.tool_calls && turn.tool_calls.length)} tools`),
        create("span", null, `${number(turn.evidence_ids && turn.evidence_ids.length)} evidence`),
        create("span", null, number(turn.context_turns) ? `${number(turn.context_turns)} prior turns` : "new thread"),
      );
      item.append(humanBubble, agentBubble);
      const citations = create("div", "platform-tool-calls");
      (Array.isArray(turn.evidence_ids) ? turn.evidence_ids : []).forEach((evidenceId) => {
        const citation = create("button", "platform-tool-call", value(evidenceId));
        citation.type = "button";
        citation.title = `Evidence record ${value(evidenceId)}`;
        citation.dataset.evidenceId = value(evidenceId);
        citations.append(citation);
      });
      const sourceDetails = create("details", "operator-details");
      sourceDetails.dataset.turnIndex = String(turnIndex);
      sourceDetails.open = expandedSources.has(String(turnIndex));
      sourceDetails.append(create("summary", null, `Sources & checks (${citations.childElementCount})`), meta, citations);
      agentBubble.append(sourceDetails);
      conversationHost.append(item);
    });
    if (conversation.length === 0 && state.agentPlatformAnswer) {
      conversationHost.append(create("p", null, state.agentPlatformAnswer));
    }
    conversationHost.renderedConversation = conversationSignature;
    if (followConversation) conversationHost.scrollTop = conversationHost.scrollHeight;
    }
    const answerEvidence = $("platform-answer-evidence");
    answerEvidence.replaceChildren();
    const advisoryResult = advisory.result && typeof advisory.result === "object" ? advisory.result : {};
    (conversation.length === 0 && Array.isArray(advisoryResult.evidence_ids) ? advisoryResult.evidence_ids : []).forEach((evidenceId) => {
      answerEvidence.append(create("span", "platform-tool-call", value(evidenceId)));
    });
    $("platform-write-disabled").lastChild.textContent = ` ${value(platform.execution && platform.execution.detail)}`;
    const actions = $("platform-execution-actions");
    const actionState = value(execution.status);
    const actionBusy = state.agentPlatformActionBusy;
    actions.hidden = !Boolean(platform.mode && platform.mode.execution_available)
      || value(agentRun.state) !== "PLAN_READY" || actionState !== "AWAITING_MANAGER_APPROVAL";
    $("platform-approve-execute").disabled = actionBusy || value(agentRun.state) !== "PLAN_READY" || actionState !== "AWAITING_MANAGER_APPROVAL";
    $("platform-reject-plan").disabled = actionBusy || value(agentRun.state) !== "PLAN_READY" || actionState !== "AWAITING_MANAGER_APPROVAL";
    const packetNode = $("platform-resolution-packet");
    packetNode.hidden = !packet;
    if (packet) {
      $("platform-packet-id").textContent = value(packet.packet_id);
      const postState = packet.post_state && typeof packet.post_state === "object" ? packet.post_state : {};
      $("platform-packet-summary").textContent = `Verified · ${value(packet.guard).replaceAll("_", " ")} · ${Object.entries(postState).map(([key, itemValue]) => `${key.replaceAll("_", " ")}: ${itemValue == null ? "Unknown" : value(itemValue)}`).join(" · ")}`;
      const packetScope = $("platform-packet-scope");
      packetScope.replaceChildren();
      [["Receipt post", packetTuple.receipt_post_quantity], ["Quality transfer", packetTuple.quality_transfer_quantity]].forEach(([label, amount]) => {
        packetScope.append(create("span", "platform-packet-fact", `${label} · ${value(amount)} units`));
      });
      const packetEffects = packet.effects && typeof packet.effects === "object" ? packet.effects : {};
      [
        ["Quality transfer", packetEffects.quality_release_transfer],
        ["Sales order", packetEffects.sales_order],
        ["Delivery note", packetEffects.delivery_note],
        ["Sales invoice", packetEffects.sales_invoice],
        ["Celigo receipt", packetEffects.celigo_receipt],
      ].forEach(([label, recordId]) => {
        if (recordId) packetScope.append(create("span", "platform-packet-fact", `${label} · ${value(recordId)}`));
      });
      const packetTrace = $("platform-packet-trace");
      packetTrace.replaceChildren();
      const packetAgentTrace = packet.agent_trace && typeof packet.agent_trace === "object" ? packet.agent_trace : {};
      const packetAgentProvider = packetAgentTrace.provider && typeof packetAgentTrace.provider === "object" ? packetAgentTrace.provider : {};
      const packetApproval = packet.approval && typeof packet.approval === "object" ? packet.approval : {};
      const packetExecution = packet.execution && typeof packet.execution === "object" ? packet.execution : {};
      const traceToolCount = Array.isArray(packetAgentTrace.tool_calls) ? packetAgentTrace.tool_calls.length : 0;
      const traceModel = value(packetAgentTrace.model || packetAgentProvider.model);
      [
        ["Agent", traceModel ? `${traceModel} · ${traceToolCount} reads` : value(packetAgentTrace.status || "trace unavailable")],
        ["Manager", value(packetApproval.manager_id || "—")],
        ["Idempotency", value(packetExecution.idempotency_key || "—")],
      ].forEach(([label, detail]) => packetTrace.append(create("span", "platform-packet-fact", `${label} · ${detail}`)));
      const packetTimestamps = $("platform-packet-timestamps");
      packetTimestamps.replaceChildren();
      const timestamps = packet.timestamps && typeof packet.timestamps === "object" ? packet.timestamps : {};
      [["Approved", timestamps.approved_at], ["Executed", timestamps.executed_at], ["Verified", timestamps.verified_at]].forEach(([label, timestamp]) => {
        if (timestamp) packetTimestamps.append(create("span", "platform-packet-fact", `${label} · ${value(timestamp)}`));
      });
      const packetEvidence = $("platform-packet-evidence");
      packetEvidence.replaceChildren();
      (Array.isArray(packet.evidence) ? packet.evidence : []).forEach((evidence) => {
        if (!evidence || typeof evidence !== "object") return;
        packetEvidence.append(create("span", "platform-tool-call", `${value(evidence.source_id)} · ${value(evidence.record_id)}`));
      });
    }

    const activity = $("platform-activity");
    const events = Array.isArray(platform.activity) ? platform.activity.slice(-18) : [];
    const activitySignature = JSON.stringify(events);
    if (activity.renderedEvents !== activitySignature) {
    const followActivity = activity.scrollHeight - activity.scrollTop - activity.clientHeight < 40;
    activity.replaceChildren();
    events.forEach((event) => {
      if (!event || typeof event !== "object") return;
      const item = create("li", "platform-activity-item");
      if (number(event.sequence) > pulseAfter) item.classList.add("is-live");
      const main = create("div", "platform-activity-main");
      main.append(create("strong", null, value(event.label)), create("span", null, value(event.detail)));
      const occurredAt = new Date(value(event.occurred_at || event.timestamp || event.created_at));
      const timeLabel = operatorEventTime(occurredAt, event.sequence);
      item.append(
        create("time", "platform-activity-sequence", timeLabel),
        main,
        create("span", "platform-activity-provenance", value(event.provenance) === "synthetic-demo-fixture" ? "DEMO" : value(event.provenance || "live")),
      );
      activity.append(item);
    });
    activity.renderedEvents = activitySignature;
    if (followActivity) window.requestAnimationFrame(() => { activity.scrollTop = activity.scrollHeight; });
    }
    $("platform-event-count").textContent = `${Array.isArray(platform.activity) ? platform.activity.length : 0} events`;
    const outcomeState = executionStatus === "VERIFIED"
      ? "VERIFIED"
      : executionStatus === "VERIFYING"
        ? "VERIFYING"
        : executionStatus === "AUTHORIZED"
          ? "APPROVED"
          : value(agentRun.state) === "BLOCKED"
            ? "SAFE STOP"
            : value(agentRun.state) === "PLAN_READY"
              ? "MANAGER REVIEW"
              : "WAITING";
    $("platform-outcome-status").textContent = outcomeState;
    $("platform-outcome").dataset.status = outcomeState.toLowerCase().replaceAll(" ", "-");
    $("platform-outcome-summary").textContent = value(execution.detail || diagnosis.summary || "No recovery effect has been issued.");
    const transition = $("platform-state-transition");
    const packetPreState = packet && packet.pre_state && typeof packet.pre_state === "object"
      ? packet.pre_state
      : {};
    const packetPostState = packet && packet.post_state && typeof packet.post_state === "object"
      ? packet.post_state
      : {};
    const currentAvailable = packetPreState.available == null ? "Unknown" : number(packetPreState.available);
    const targetAvailable = number(packetPostState.available, number(caseQuantities && caseQuantities.available));
    const priorInvoice = value(packetPreState.invoice_status || "EARLIER STATE NOT RETAINED").replaceAll("_", " ");
    const currentInvoice = value(packetPostState.invoice_status || (caseFacts && caseFacts.invoice_held ? "PAYMENT HOLD" : "OPEN")).replaceAll("_", " ");
    transition.hidden = executionStatus !== "VERIFIED";
    if (!transition.hidden) {
      transition.setAttribute("role", "group");
      transition.setAttribute("aria-label", `Invoice state from ${priorInvoice} to ${currentInvoice}; case balance from ${currentAvailable} to ${targetAvailable}. Verified readback.`);
      transition.replaceChildren(
        create("span", null, priorInvoice),
        create("i", "ph ph-arrow-right", ""),
        create("span", null, currentInvoice),
        create("small", null, `Case balance ${currentAvailable} → ${targetAvailable} · verified readback`),
      );
      transition.querySelector("i")?.setAttribute("aria-hidden", "true");
    } else {
      transition.replaceChildren();
    }
    state.agentPlatformPulseAfter = latestSequence;
    // Draw synchronously when the map already has layout. Headless Chromium
    // can throttle requestAnimationFrame even while the document is visible;
    // the queued passes remain as protection for ordinary view transitions.
    renderPlatformInvestigationLinks();
    schedulePlatformInvestigationLinks();
  }

  async function runPlatformDiagnosis() {
    if (state.agentPlatformDiagnosing) return;
    state.agentPlatformDiagnosing = true;
    scheduleRender();
    try {
      setAgentPlatformProjection(await requestJSON("/api/v1/agent-platform/diagnose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: { operator_id: "M20 Demo Operator" },
      }));
      state.agentPlatformError = "";
    } catch (error) {
      state.agentPlatformError = error.message;
    } finally {
      state.agentPlatformDiagnosing = false;
      scheduleRender();
    }
  }

  async function askPlatformQuestion(question) {
    const cleanQuestion = value(question).trim();
    if (!cleanQuestion || state.agentPlatformQuestionBusy) return;
    state.agentPlatformQuestionBusy = true;
    state.agentPlatformQuestionAttempt = { question: cleanQuestion, status: "READING", detail: "" };
    scheduleRender();
    try {
      const response = await requestJSON("/api/v1/agent-platform/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: { question: cleanQuestion },
      });
      setAgentPlatformProjection(response);
      state.agentPlatformAnswer = value(response.answer);
      state.agentPlatformAdvisory = response.agent_advisory && typeof response.agent_advisory === "object"
        ? response.agent_advisory
        : null;
      state.agentPlatformQuestionAttempt = {
        question: cleanQuestion,
        status: state.agentPlatformAdvisory?.status || "COMPLETE",
        detail: state.agentPlatformAnswer,
        retainedViews: Array.isArray(state.agentPlatformAdvisory?.retained_views)
          ? state.agentPlatformAdvisory.retained_views : [],
      };
      state.agentPlatformError = "";
    } catch (error) {
      state.agentPlatformError = error.message;
      state.agentPlatformAnswer = `Evidence question unavailable: ${error.message}`;
      state.agentPlatformAdvisory = { status: "AGENT_UNAVAILABLE", mode: "real_strands", result: null };
      state.agentPlatformQuestionAttempt = { question: cleanQuestion, status: "AGENT_UNAVAILABLE", detail: error.message };
    } finally {
      state.agentPlatformQuestionBusy = false;
      scheduleRender();
    }
  }

  async function runPlatformAction(path, body = {}) {
    if (state.agentPlatformActionBusy) return;
    state.agentPlatformActionBusy = true;
    scheduleRender();
    try {
      setAgentPlatformProjection(await requestJSON(`/api/v1/agent-platform/${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      }));
      state.agentPlatformError = "";
    } catch (error) {
      state.agentPlatformError = error.message;
      state.agentPlatformAnswer = `Agent action stopped safely: ${error.message}`;
    } finally {
      state.agentPlatformActionBusy = false;
      scheduleRender();
    }
  }

  function scheduleLiveSourceRefresh() {
    if (smokeCapture || providerPollingDisabled || state.liveSourceTimer != null) return;
    state.liveSourceTimer = window.setTimeout(() => {
      state.liveSourceTimer = null;
      if (document.hidden) {
        scheduleLiveSourceRefresh();
        return;
      }
      refreshLiveSources().finally(scheduleLiveSourceRefresh);
    }, 15000);
  }

  function startLiveSourceRefresh() {
    if (smokeCapture || state.liveSourceTimer != null) return;
    refreshLiveSources();
    if (!providerPollingDisabled) scheduleLiveSourceRefresh();
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
    // Bound reads so a stalled source cannot leave first paint waiting forever.
    // Writes retain their existing acknowledgement/reconciliation semantics.
    if (!init.signal && (!init.method || init.method === "GET")) init.signal = AbortSignal.timeout(20000);
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

  function incidentSnapshotPath(incidentId) {
    const projection = smokeCapture ? "compact=1" : "projection=browser";
    return `/api/v1/incidents/${encodeURIComponent(incidentId)}?${projection}`;
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
      "external.source.changed",
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
      const snapshot = await requestJSON(incidentSnapshotPath(state.incidentId));
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
    if (type === "external.source.changed") return;
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
      const snapshot = await requestJSON(incidentSnapshotPath(state.incidentId));
      // Use the unit rows embedded in the same snapshot so reconnect cannot
      // combine a reset projection with a response from another case version.
      applySnapshot(snapshot, snapshot.units, true);
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
    state.latestActivitySequence = sequence;
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
    if (type === "external.source.changed") {
      pulseTelemetry();
      scheduleAgentPlatformProjectionRefresh();
    }
    if (type === "tool.started" && event.actor) state.activeToolActors.add(value(event.actor));
    if (type === "tool.completed" && event.actor) state.activeToolActors.delete(value(event.actor));
    if (["agent.completed", "workflow.blocked", "verification.completed"].includes(type) && event.actor) {
      state.activeToolActors.delete(value(event.actor));
    }
    if (type === "execution.started") state.activeEdges.add("message-queue->erp");
    if (["execution.started", "source.read.started", "source.read.completed", "effect.started", "effect.completed", "verification.started", "verification.completed"].includes(type)) {
      const activityDrawer = $("activity-drawer");
      if (activityDrawer) activityDrawer.open = true;
      state.rightRailTab = "decision";
    }
    if (state.goldenRunning && type === "evaluation.completed") {
      // Evaluation is the terminal event for a fresh Golden Incident.  The
      // event itself, rather than a UI timer, owns the button's idle state.
      state.goldenRunning = false;
    }
    $("sequence-label").textContent = `seq ${state.lastSequence}`;
    scheduleRender();
    if (["evaluation.completed", "execution.completed", "verification.completed"].includes(type)) {
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
      // A server-backed incident is the trigger for the autonomous harness.
      // `startInvestigation` rejects healthy, replay, and closed states, and
      // `startIssued` makes reconnects idempotent.
      void startInvestigation();
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
    const allowedViews = new Set(["dashboard", "agent"]);
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
    $("scenario-view").hidden = !state.demoControlsOpen;
    document.querySelectorAll("[data-view]").forEach((tab) => {
      const selected = tab.dataset.view === state.view;
      tab.classList.toggle("is-selected", selected);
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    window.scrollTo(0, 0);
    document.body.classList.remove("platform-focus-open");
    state.platformFocusedModule = "";
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
    if (scenario === "normal") state.transitionBaseline = null;
    state.flowStageCounts = new Map();
    state.flowStageRunId = "";
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
    state.liveMetricSequence = 0;
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
    state.caseActionStatus = "";
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
      const snapshot = await requestJSON(incidentSnapshotPath(incidentId));
      replaceSession(snapshot, "incident");
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
      if ((scenario === "incident" || scenario === "golden") && state.activeScenario === "normal") {
        const counts = state.snapshot?.unit_counts || {};
        const latest = state.telemetry[state.telemetry.length - 1] || {};
        state.transitionBaseline = {
          sequence: number(latest.sequence, state.lastSequence),
          observed_at: value(latest.observed_at || latest.captured_at) || new Date().toISOString(),
          received_at: value(latest.received_at || latest.observed_at || latest.captured_at) || new Date().toISOString(),
          unit_counts: {
            total: number(counts.total),
            erp_recorded: number(counts.erp_recorded),
            queue_failed: number(counts.queue_failed),
          },
          queue_depth: number(counts.queue_failed),
          invoice_count: number(state.snapshot?.flow?.summary?.invoice, number(counts.erp_recorded)),
          source: "preceding-authoritative-session",
          authoritative: true,
        };
      }
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
      if (scenario === "incident" || scenario === "golden") {
        // Admission exposes the evidence chat immediately. A human explicitly
        // authorizes the bounded diagnosis after questioning the Agent.
        await syncPlatformInvestigation();
      }
      state.scenarioError = "";
    } catch (error) {
      state.scenarioError = `Scenario transition rejected: ${error.message}. Current state: ${scenarioTruthSummary()}. Select Normal to recover when available.`;
      setConnection(state.connection, `Scenario unavailable: ${error.message}`);
    } finally {
      state.commandBusy = false;
      renderAll();
    }
  }

  async function runCounterfactual(variant) {
    if (state.commandBusy || !["incident", "golden"].includes(state.activeScenario)) return;
    state.commandBusy = true;
    state.scenarioError = "";
    renderScenarioControls();
    try {
      setAgentPlatformProjection(await requestJSON("/api/v1/agent-platform/counterfactual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: { variant },
      }));
      await syncPlatformInvestigation();
      state.demoControlsOpen = false;
      setView("agent");
    } catch (error) {
      state.scenarioError = `Counterfactual unavailable: ${error.message}`;
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
    if (type === "telemetry.observed") {
      const trigger = payload.trigger && typeof payload.trigger === "object" ? payload.trigger : {};
      if (trigger.kind === "external_source_baseline") return "Authoritative source baseline";
      if (trigger.kind === "external_scenario_change") return "Scenario source changed";
      return "Source observation recorded";
    }
    if (type === "external.source.changed") return `${human(payload.source_id || event.actor)} changed`;
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
    if (type === "approval.requested") return "Manager approval requested";
    if (type === "approval.recorded") return "Manager approval recorded";
    if (type === "execution.started") return "Controlled recovery started";
    if (type === "source.read.started") return `${human(payload.source || "Authoritative source")} read started`;
    if (type === "source.read.completed") return `${human(payload.source || "Authoritative source")} read completed`;
    if (type === "effect.started") return "Recovery effect started";
    if (type === "effect.completed") return "Recovery effect committed";
    if (type === "verification.started") return "Authoritative verification started";
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
      const stages = payload.stage_counts && typeof payload.stage_counts === "object"
        ? payload.stage_counts
        : null;
      if (stages) {
        return `${telemetryRecordCount(payload)} new records · Warehouse ${number(stages.warehouse)} · Queue ${number(stages.message_queue)} · ERP ${number(stages.erp)} · Invoice ${number(stages.invoice)}`;
      }
      const counts = payload.unit_counts && typeof payload.unit_counts === "object"
        ? payload.unit_counts
        : {};
      const observedRecords = telemetryRecordCount(payload);
      return `${observedRecords} records · queue ${number(payload.queue_depth, number(counts.queue_failed))}`;
    }
    if (type === "external.source.changed") {
      const records = Array.isArray(payload.record_ids) ? payload.record_ids : [];
      return `${number(payload.change_count, records.length)} source records · provider seq ${number(payload.source_sequence)}`;
    }
    if (type === "source.condition.injected") {
      return `${number(payload.queue_depth)} units entered the retryable lock condition`;
    }
    if (type === "tool.started") return "reading records";
    if (type === "tool.completed") return `${countLabel((payload.result_evidence_ids || []).length, "evidence", "evidence")} returned`;
    if (type === "evidence.returned") return `${countLabel((payload.evidence_ids || []).length, "evidence", "evidence")} returned`;
    if (type === "agent.handoff") return `${countLabel((payload.evidence_ids || []).length, "evidence", "evidence")} handed off`;
    if (type === "evaluation.completed") return value(payload.decision || event.status);
    if (type === "approval.recorded") return "Manager · immutable intent";
    if (["source.read.started", "source.read.completed"].includes(type)) return `${number(payload.record_count)} records · ${number(payload.duration_ms)} ms`;
    if (["effect.started", "effect.completed", "verification.started"].includes(type)) return value(payload.execution_id || event.status);
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
    return Number.isNaN(parsed.getTime()) ? "—" : parsed.toLocaleTimeString([], { hour12: false });
  }

  function unitNodeId(unit) {
    if (value(unit.status) === "QUEUE_FAILED" || value(unit.current_stage) === "MESSAGE_QUEUE") return "message-queue";
    if (value(unit.current_stage) === "WAREHOUSE") return "warehouse";
    return "erp";
  }

  function renderUnitDetail() {
    const detailNode = $("unit-detail");
    if (!detailNode) return;
    detailNode.replaceChildren();
    if (platformFlowProjection()) return;
    const detail = state.units.get(state.selectedUnitId);
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
    strip.hidden = Boolean(platformFlowProjection());
    if (strip.hidden) {
      state.selectedUnitId = "";
      strip.replaceChildren();
      strip.removeAttribute("aria-label");
      delete strip.dataset.totalRecords;
      delete strip.dataset.postedRecords;
      delete strip.dataset.backlogRecords;
      return;
    }
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
    const inspector = list.closest("details");
    if (inspector) inspector.hidden = Boolean(platformFlowProjection());
    if (platformFlowProjection()) {
      list.replaceChildren();
      if (inspector) inspector.open = false;
      return;
    }
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

  function liveReceivingSummary(platform) {
    const { expected, posted, gap, uom, invoiceHeld } = platform;
    if (gap > 0) return { title: `${gap} ${uom} need reconciliation`, detail: "Receiving exception", label: "needs reconciliation" };
    if (invoiceHeld) return { title: "Supplier invoice on hold", detail: "Invoice review required", label: "invoice on hold" };
    if (expected <= 0) return { title: "No ordered quantity recorded", detail: "Check the purchase order", label: "order quantity unavailable" };
    if (posted > expected) return { title: `${posted - expected} ${uom} received above order quantity`, detail: "Check over-receipt", label: "over-receipt" };
    const remaining = Math.max(0, expected - posted);
    if (posted === 0) return { title: `Awaiting receipt · ${expected} ${uom} ordered`, detail: `${remaining} ${uom} still to receive`, label: "awaiting receipt" };
    if (remaining > 0) return { title: `${posted} of ${expected} ${uom} received`, detail: `${remaining} ${uom} still to receive`, label: "partially received" };
    return { title: `${posted} ${uom} received`, detail: "Receipt posting complete", label: "receipt posted in ERP" };
  }

  function renderHeader() {
    const snapshot = state.snapshot;
    if (!snapshot) return;
    const incident = snapshot.incident || {};
    const counts = snapshot.unit_counts || {};
    const platform = platformFlowProjection();
    const receivingSummary = platform ? liveReceivingSummary(platform) : null;
    const expected = platform
      ? platform.expected
      : number(incident.expected_quantity, number(counts.total));
    const recorded = platform
      ? platform.recorded
      : number(incident.recorded_quantity, number(counts.erp_recorded));
    const missing = platform
      ? platform.gap
      : number(incident.missing_quantity, number(counts.queue_failed));
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
    if (incidentRowDetail) incidentRowDetail.textContent = receivingSummary?.detail || (normalScenario
      ? `${expected} units moving`
      : missing
        ? `${missing} units held at queue`
        : "Flow reconciled");
    if (heroKicker) {
      heroKicker.textContent = normalScenario
        ? "LIVE SUPPLY FLOW"
        : "LIVE SYNTHETIC INCIDENT";
    }
    $("incident-title").textContent = receivingSummary?.title || (missing
      ? `${missing}-${unit.replace(/s$/, "")} gap. Five systems disagree.`
      : platform?.invoiceHeld
        ? `Invoice hold blocks the ${expected}-${unit.replace(/s$/, "")} receipt.`
        : `All ${expected} ${unit} are accounted for`);
    $("incident-subtitle").textContent = receivingSummary?.detail || (closedRecovery
      ? "Investigation complete"
      : state.replaying
      ? "Ledger replay"
      : missing
        ? "Queue exception"
        : "Flow verified");
    const incidentIdNode = $("incident-id");
    incidentIdNode.textContent = `Incident ${value(platform?.caseId || snapshot.incident_id)}`;
    incidentIdNode.hidden = normalScenario;
    incidentIdNode.setAttribute("aria-hidden", String(normalScenario));
    $("trace-id").textContent = platform?.runId
      ? `Run ${platform.runId}`
      : `Trace ${value(snapshot.trace_id)}`;
    $("missing-count").textContent = String(missing);
    $("expected-count").textContent = String(expected);
    $("recorded-count").textContent = String(recorded);
    $("queue-count").textContent = String(missing);
    $("hero-expected").textContent = String(expected);
    $("hero-recorded").textContent = String(recorded);
    $("hero-queue").textContent = String(missing);
    const authoritativeSequence = platform?.latestSequence
      || state.lastSequence
      || number(snapshot.projection_sequence);
    $("hero-sequence").textContent = String(authoritativeSequence || "—");
    const heroLabel = document.querySelector(".hero-count span");
    if (heroLabel) heroLabel.textContent = receivingSummary?.label
      || (missing ? "stopped at queue" : "verified in ERP");
    const mode = value(snapshot.mode);
    const execution = snapshot.execution || {};
    document.body.dataset.recovered = String(
      missing === 0 && (platform?.verified || execution.verified === true),
    );
    const isScripted = mode === "SCRIPTED_SYNTHETIC";
    const connectionState = state.connection === "live"
      ? "Connected"
      : state.connection === "paused"
        ? "Paused"
        : "Connecting";
    const liveSourceAuthority = hasLiveSourceAuthority();
    $("mode-label").textContent = liveSourceAuthority
      ? `External source ledger · ${connectionState}`
      : isScripted
        ? `Scenario Lab · ${connectionState}`
        : `${human(mode || "Experiment")} · ${connectionState}`;
    $("mode-detail").textContent = demoMode === "degraded"
      ? "advisory degraded"
      : liveSourceAuthority
        ? "provider state"
        : isScripted
          ? "scenario data"
          : "provider state";
    $("mode-dot").className = `status-dot ${liveSourceAuthority || !isScripted ? "status-dot-cyan" : "status-dot-lime"}`;
    $("sequence-label").textContent = `seq ${authoritativeSequence || "—"}`;
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
    if (typeof document !== "undefined") {
      document.querySelectorAll("[data-counterfactual]").forEach((button) => {
        button.disabled = state.commandBusy
          || state.connection !== "live"
          || !["incident", "golden"].includes(state.activeScenario);
        button.setAttribute("aria-disabled", String(button.disabled));
      });
    }
    const error = $("scenario-error");
    if (error) {
      error.hidden = !state.scenarioError;
      error.textContent = state.scenarioError || "";
    }
  }

  function verifiedClosedSnapshot(snapshot) {
    return value(snapshot && snapshot.incident && snapshot.incident.status).toUpperCase() === "CLOSED"
      && Boolean(snapshot && snapshot.execution && snapshot.execution.verified === true);
  }

  function chartTelemetryPoints(snapshot) {
    // The helper is also executed in isolation by the chart contract tests.
    // In the browser it selects the unified Case Console authority; isolated
    // consumers correctly fall back to the legacy immutable telemetry ledger.
    const platform = typeof platformFlowProjection === "function"
      ? platformFlowProjection()
      : null;
    const platformActivity = Array.isArray(state.agentPlatform?.activity)
      ? state.agentPlatform.activity
      : [];
    if (platform && platformActivity.some((event) => event && event.metrics)) {
      return platformActivity
        .filter((event) => event && event.metrics && typeof event.metrics === "object")
        .map((event) => {
          const metrics = event.metrics;
          return {
            sequence: number(event.sequence),
            observed_at: value(event.occurred_at),
            received_at: value(event.occurred_at),
            unit_counts: {
              total: number(metrics.expected),
              erp_recorded: number(metrics.receipt_posted_quantity, number(metrics.received)),
              queue_failed: number(metrics.gap),
            },
            queue_depth: number(metrics.gap),
            recorded_quantity: number(metrics.receipt_posted_quantity, number(metrics.received)),
            invoice_count: number(metrics.invoice_count),
            flow_run_id: value(event.run_id || platform.runId || platform.caseId),
            stage_counts: {
              warehouse: number(metrics.physically_arrived, number(metrics.received)),
              message_queue: number(metrics.receipt_unresolved),
              erp: number(metrics.receipt_posted_quantity, number(metrics.received)),
              invoice: number(metrics.invoice_count),
            },
            business_metrics: {
              working_capital_at_risk: number(metrics.working_capital_at_risk),
              invoice_hold_value: number(metrics.invoice_hold_value),
              purchase_price_variance: number(metrics.purchase_price_variance),
              billed_revenue: number(metrics.billed_revenue, metrics.value_protected),
              booked_revenue: number(metrics.booked_revenue),
              revenue_at_risk: number(metrics.revenue_at_risk),
              po_unit_cost: number(metrics.po_unit_cost),
            },
            source: platform.provenance === "live-read"
              ? "ERPNext semantic source ledger"
              : "synthetic case ledger",
            authoritative: platform.provenance === "live-read",
          };
        });
    }
    const points = state.telemetry.slice();
    const baseline = state.transitionBaseline;
    if (baseline && points.length) {
      const baselineCounts = baseline.unit_counts || {};
      const firstCounts = points[0]?.unit_counts || {};
      const differs = number(baselineCounts.erp_recorded, -1) !== number(firstCounts.erp_recorded, -1)
        || number(baselineCounts.queue_failed, -1) !== number(firstCounts.queue_failed, -1);
      if (differs) points.unshift(baseline);
    }
    // Replay intentionally preserves the historical 80/20 observations while
    // the immutable stream is being drained.  Once the authoritative execution
    // and verification are closed, append a terminal 100/0 point to the chart
    // projection instead of rewriting that incident history in place.
    if (!points.length || state.replaying || !verifiedClosedSnapshot(snapshot)) return points;
    const counts = snapshot && snapshot.unit_counts && typeof snapshot.unit_counts === "object"
      ? snapshot.unit_counts
      : {};
    const current = {
      total: number(counts.total, 0),
      erp_recorded: number(counts.erp_recorded, 0),
      queue_failed: number(counts.queue_failed, 0),
    };
    const last = points[points.length - 1] || {};
    const lastCounts = last.unit_counts && typeof last.unit_counts === "object"
      ? last.unit_counts
      : {};
    const alreadyCurrent = number(lastCounts.total, -1) === current.total
      && number(lastCounts.erp_recorded, -1) === current.erp_recorded
      && number(lastCounts.queue_failed, -1) === current.queue_failed;
    if (alreadyCurrent) return points;
    const latest = snapshot && snapshot.telemetry && snapshot.telemetry.latest;
    points.push({
      sequence: number(snapshot && snapshot.projection_sequence, number(last.sequence, 0)),
      observed_at: value(latest && (latest.observed_at || latest.received_at))
        || value(last.observed_at || last.captured_at),
      received_at: value(latest && latest.received_at)
        || value(last.received_at || last.observed_at || last.captured_at),
      unit_counts: current,
      queue_depth: current.queue_failed,
      recorded_quantity: current.erp_recorded,
      invoice_count: number(
        snapshot && snapshot.flow && snapshot.flow.summary && snapshot.flow.summary.invoice,
        current.erp_recorded,
      ),
      flow_run_id: value(last.flow_run_id),
      stage_counts: {
        warehouse: current.total,
        message_queue: current.total,
        erp: current.erp_recorded,
        invoice: current.erp_recorded,
      },
      source: "authoritative-verified-state",
      authoritative: true,
    });
    return points;
  }

  function latestStageProjection(snapshot) {
    const latest = [...chartTelemetryPoints(snapshot)].reverse().find((point) => (
      point
      && point.stage_counts
      && typeof point.stage_counts === "object"
    ));
    if (!latest) return { runId: "", counts: {} };
    const raw = latest.stage_counts;
    return {
      runId: value(latest.flow_run_id),
      counts: {
        warehouse: number(raw.warehouse),
        "message-queue": number(raw.message_queue),
        erp: number(raw.erp),
        invoice: number(raw.invoice),
      },
    };
  }

  function currentFlowTelemetry(snapshot) {
    const points = chartTelemetryPoints(snapshot);
    const currentRunId = value([...points].reverse().find((point) => value(point.flow_run_id))?.flow_run_id);
    if (!currentRunId) return points;
    return points.filter((point) => value(point.flow_run_id) === currentRunId);
  }

  function sparklineValues(kind, snapshot) {
    const telemetryKind = {
      recorded: "observed_record_count",
      missing: "queue_depth",
    }[kind];
    const telemetry = currentFlowTelemetry(snapshot);
    if (telemetryKind && telemetry.length) {
      return telemetry.map((point) => kind === "recorded"
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
    if (tone === "coral") return "#ff796a";
    if (tone === "lime") return "#d9f85e";
    if (tone === "violet") return "#845adf";
    if (tone === "amber") return "#e09a2d";
    return "#5cdeea";
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
    const label = document.body.dataset.sourceFreshness === "unavailable" ? "HISTORY"
      : point && pointTime(point)
      ? shortTime(pointTime(point))
      : state.connection === "live" ? "LIVE" : "PAUSED";
    ["trend-time", "flow-health-cursor", "source-status-summary", "business-trend-time"].forEach((id) => {
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
    if (!surface) return renderSvgLineChart(canvas, series, tones, options);
    canvas.classList.remove("has-svg-fallback");
    canvas.parentElement?.querySelector(`[data-chart-fallback="${canvas.id}"]`)?.remove();
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

  function renderSvgLineChart(canvas, series, tones, options = {}) {
    if (!canvas) return;
    const width = Math.max(240, Math.round(canvas.getBoundingClientRect().width || canvas.width || 600));
    const height = Math.max(96, Math.round(canvas.getBoundingClientRect().height || canvas.height || 180));
    const pad = { top: options.top || 14, right: options.right || 12, bottom: options.bottom || 22, left: options.left || 31 };
    const plotWidth = Math.max(1, width - pad.left - pad.right);
    const plotHeight = Math.max(1, height - pad.top - pad.bottom);
    const values = series.flatMap((line) => line.map((item) => number(item)));
    const points = (options.points || []).map((point, pointIndex, allPoints) => ({
      ...point,
      x: allPoints.length === 1
        ? pad.left + plotWidth / 2
        : pad.left + (pointIndex / (allPoints.length - 1)) * plotWidth,
      value: point.value == null ? number(series[0] && series[0][pointIndex]) : point.value,
    }));
    canvas.__chartMeta = {
      points,
      metric: options.metric || "Flow",
      unit: options.unit || "units",
      source: options.source || "synthetic-enterprise-snapshot",
      left: pad.left,
      right: width - pad.right,
    };
    canvas.classList.add("has-svg-fallback");
    let svg = canvas.parentElement?.querySelector(`[data-chart-fallback="${canvas.id}"]`);
    if (!svg) {
      svg = document.createElementNS("http:" + "//www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", `chart-svg-fallback ${canvas.classList.contains("mini-chart-canvas") ? "mini-chart-svg-fallback" : "diagram-svg-fallback"}`);
      svg.setAttribute("data-chart-fallback", canvas.id);
      svg.setAttribute("aria-hidden", "true");
      canvas.insertAdjacentElement("afterend", svg);
    }
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.replaceChildren();
    const make = (tag, attributes = {}) => {
      const node = document.createElementNS("http:" + "//www.w3.org/2000/svg", tag);
      Object.entries(attributes).forEach(([key, item]) => node.setAttribute(key, String(item)));
      return node;
    };
    if (!values.length || (options.points && options.points.length < 2)) {
      const label = make("text", { x: width / 2, y: height / 2, class: "chart-svg-empty", "text-anchor": "middle" });
      label.textContent = options.emptyLabel || "Insufficient live history";
      svg.append(label);
      return;
    }
    const max = Math.max(...values, 1);
    const min = Math.min(...values, 0);
    const span = Math.max(1, max - min);
    for (let row = 0; row <= 4; row += 1) {
      const y = pad.top + (plotHeight * row) / 4;
      svg.append(make("line", { x1: pad.left, y1: y, x2: width - pad.right, y2: y, class: "chart-svg-grid" }));
    }
    series.forEach((line, lineIndex) => {
      if (!line.length) return;
      const coordinates = line.map((item, pointIndex) => {
        const x = line.length === 1
          ? pad.left + plotWidth / 2
          : pad.left + (pointIndex / (line.length - 1)) * plotWidth;
        const y = pad.top + plotHeight - ((number(item) - min) / span) * plotHeight;
        return { x, y };
      });
      const path = make("path", {
        d: coordinates.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" "),
        class: "chart-svg-series",
        stroke: chartColor(tones[lineIndex] || "cyan"),
      });
      svg.append(path);
      const last = coordinates.at(-1);
      svg.append(make("circle", { cx: last.x, cy: last.y, r: 3, fill: chartColor(tones[lineIndex] || "cyan"), class: "chart-svg-latest" }));
    });
  }

  function reconciliationSeries(snapshot) {
    const telemetry = currentFlowTelemetry(snapshot);
    const snapshotCounts = snapshot && snapshot.unit_counts && typeof snapshot.unit_counts === "object"
      ? snapshot.unit_counts
      : {};
    if (telemetry.length) {
      return {
        // Stage counts are committed with each telemetry observation. They
        // reveal the current flow window without rewriting inventory truth.
        expected: telemetry.map((point) => number(point.stage_counts?.warehouse, number(point.unit_counts?.total, number(snapshotCounts.total, 0)))),
        recorded: telemetry.map((point) => number(point.stage_counts?.erp, number(point.unit_counts?.erp_recorded, number(snapshotCounts.erp_recorded, 0)))),
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
    const telemetry = currentFlowTelemetry(snapshot);
    if (telemetry.length) {
      return telemetry.map((point) => ({
        sequence: point.sequence,
        timestamp: point.observed_at || point.captured_at,
        observed_at: point.observed_at || point.captured_at,
        received_at: point.received_at || point.observed_at || point.captured_at,
        expected: number(point.stage_counts?.warehouse, number(point.unit_counts?.total, 0)),
        recorded: number(point.stage_counts?.erp, number(point.unit_counts?.erp_recorded, 0)),
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
    const points = chartTelemetryPoints(snapshot);
    // A one-point snapshot is not a trend. Do not attach a wall-clock value to
    // it: that would make an apparently live line without a server observation.
    if (!points.length) return [];
    return points.map((point) => {
      const unitCounts = point.unit_counts || {};
      let valueForMetric;
      let unit = "units";
      if (metric === "queue") valueForMetric = number(unitCounts.queue_failed, number(point.queue_depth));
      else if (metric === "erp") valueForMetric = number(point.stage_counts?.erp, number(unitCounts.erp_recorded));
      else valueForMetric = number(point.stage_counts?.invoice, number(point.invoice_count, number(unitCounts.erp_recorded)));
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
      source: platformFlowProjection()?.provenance === "live-read"
        ? "ERPNext semantic source ledger"
        : "synthetic enterprise snapshot",
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

  function renderBusinessImpact() {
    const impact = businessImpactProjection();
    const proof = valueProofProjection();
    const observed = proof?.observed && typeof proof.observed === "object" ? proof.observed : {};
    const counterfactual = proof?.counterfactual && typeof proof.counterfactual === "object" ? proof.counterfactual : {};
    const currency = value(proof?.currency || impact?.currency || "USD");
    const latestSequence = number(platformFlowProjection()?.latestSequence
      ?? state.snapshot?.projection_sequence ?? state.lastSequence);
    const advanced = latestSequence > state.businessMetricSequence;
    const entries = [
      ["business-availability", impact?.inventory_availability_percent != null ? `${number(impact.inventory_availability_percent).toFixed(1)}%` : "—", false],
      ["business-reconciliation", impact?.erp_reconciliation_percent != null ? `${number(impact.erp_reconciliation_percent).toFixed(1)}%` : "—", false],
      ["business-working-capital", impact ? formatCurrency(impact.working_capital_at_risk, currency) : "—", number(impact?.working_capital_at_risk) > 0],
      ["business-invoice-hold", impact ? formatCurrency(impact.invoice_hold_value, currency) : "—", number(impact?.invoice_hold_value) > 0],
      ["business-unit-cost", impact ? formatCurrency(impact.po_unit_cost, currency) : "—", false],
      ["business-price-variance", impact ? `${number(impact.purchase_price_variance) > 0 ? "+" : ""}${formatCurrency(impact.purchase_price_variance, currency)}` : "—", number(impact?.purchase_price_variance) !== 0],
      ["business-quality-hold", impact ? formatCurrency(impact.quality_hold_value, currency) : "—", number(impact?.quality_hold_value) > 0],
      ["business-value-protected", proof ? formatCurrency(observed.billed_revenue, currency) : "—", false],
      ["business-booked-revenue", proof ? formatCurrency(observed.booked_revenue, currency) : "—", false],
      ["business-revenue-at-risk", proof ? formatCurrency(counterfactual.revenue_at_risk_if_hold_persists, currency) : "—", number(counterfactual.revenue_at_risk_if_hold_persists) > 0],
      ["business-delivered-quantity", proof && observed.delivered_quantity != null && observed.order_quantity != null ? `${number(observed.delivered_quantity)} / ${number(observed.order_quantity)}` : "—", false],
      ["business-gross-spread", proof && value(proof.status) === "BILLED_VERIFIED" ? formatCurrency(proof.estimated?.gross_spread, currency) : "—", false],
    ];
    entries.forEach(([id, text, alert]) => {
      const node = $(id);
      if (!node) return;
      const changed = node.textContent !== text;
      node.textContent = text;
      const metric = node.closest(".business-metric");
      if (metric) {
        metric.dataset.tone = alert ? "alert" : id === "business-value-protected" && number(observed.billed_revenue) > 0 ? "success" : "neutral";
      }
      if (advanced && changed) {
        node.classList.remove("is-live-update");
        void node.offsetWidth;
        node.classList.add("is-live-update");
      }
    });
    const detailAlert = $("business-detail-alert");
    if (detailAlert) detailAlert.hidden = !document.querySelector('#business-all-metrics .business-metric[data-tone="alert"]');
    const detailValues = [
      ["business-receipt-gap", impact ? formatCurrency(impact.receipt_gap_value, currency) : "—"],
      ["business-quality-hold-detail", impact ? formatCurrency(impact.quality_hold_value, currency) : "—"],
      ["business-working-capital-detail", impact ? formatCurrency(impact.working_capital_at_risk, currency) : "—"],
      ["business-po-line-value", impact ? formatCurrency(impact.po_line_value, currency) : "—"],
      ["business-invoice-value", impact ? formatCurrency(impact.invoice_value, currency) : "—"],
      ["business-invoice-unit-price", impact ? formatCurrency(impact.invoice_unit_price, currency) : "—"],
      ["business-price-delta", impact ? `${number(impact.invoice_price_delta_percent) > 0 ? "+" : ""}${number(impact.invoice_price_delta_percent).toFixed(1)}%` : "—"],
      ["business-available-value", impact ? formatCurrency(impact.available_inventory_value, currency) : "—"],
      ["business-delivery-completion", impact ? `${number(impact.supplier_delivery_completion_percent).toFixed(1)}%` : "—"],
    ];
    detailValues.forEach(([id, text]) => { if ($(id)) $(id).textContent = text; });
    const exposureTotal = Math.max(1, number(impact?.working_capital_at_risk));
    [
      ["receipt-gap-bar", number(impact?.receipt_gap_value)],
      ["quality-hold-bar", number(impact?.quality_hold_value)],
      ["working-capital-bar", number(impact?.working_capital_at_risk)],
    ].forEach(([id, amount]) => {
      const bar = $(id);
      if (bar) bar.style.setProperty("--exposure-width", `${Math.max(0, Math.min(100, amount * 100 / exposureTotal))}%`);
    });
    const supplier = $("business-supplier-status");
    if (supplier) {
      const status = value(impact?.supplier_status || "—").toUpperCase();
      supplier.textContent = status === "UNKNOWN" ? "SUPPLIER NOT CHECKED" : `SUPPLIER ${status}`;
      supplier.dataset.tone = status === "UNKNOWN" ? "neutral" : impact?.supplier_payment_hold ? "alert" : "healthy";
    }
    const invoice = $("business-invoice-status");
    if (invoice) {
      const status = value(impact?.invoice_status || "—").toUpperCase();
      invoice.textContent = `INVOICE ${status}`;
      invoice.dataset.tone = ["HELD", "BLOCKED", "PAYMENT HOLD"].includes(status) ? "alert" : status === "UNKNOWN" ? "neutral" : "healthy";
    }
    const order = $("business-order-status");
    if (order) {
      const status = value(proof?.status || "—").replaceAll("_", " ").toUpperCase();
      order.textContent = `ORDER ${status}`;
      order.dataset.tone = ["ORDER HELD", "ORDER OPEN", "DELIVERED"].includes(status) ? "alert" : status === "BILLED VERIFIED" ? "healthy" : "neutral";
    }
    const sequence = $("business-impact-sequence");
    if (sequence) sequence.textContent = `LEDGER ${latestSequence || "—"}`;
    if (advanced) state.businessMetricSequence = latestSequence;
  }

  function renderConnectedOperations() {
    const operations = connectedOperationsProjection();
    const section = document.querySelector(".connected-operations");
    const historyPanel = document.querySelector(".diagram-operations");
    if (section) section.hidden = !operations || isNormalScenario();
    if (historyPanel) historyPanel.hidden = !operations;
    const latestSequence = number(state.agentPlatform?.latest_sequence);
    const advanced = latestSequence > number(state.operationsMetricSequence);
    const risk = operations?.risk_signal || {};
    const shift = operations?.current_shift || {};
    const customer = operations?.customer_commitments || {};
    const supplier = operations?.supplier_performance || {};
    const inventory = operations?.inventory || {};
    const currency = value(businessImpactProjection()?.currency || "USD");
    const entries = [
      ["operations-risk-score", operations ? number(risk.score).toFixed(0) : "—"],
      ["operations-risk-band", operations ? value(risk.band || "NORMAL") : "WAITING"],
      ["operations-oee", operations ? `${number(shift.oee_percent).toFixed(1)}%` : "—"],
      ["operations-schedule", operations ? `${number(shift.schedule_attainment_percent).toFixed(1)}%` : "—"],
      ["operations-units-risk", operations ? String(number(customer.units_at_risk)) : "—"],
      ["operations-revenue-risk", operations ? formatCurrency(customer.revenue_at_risk, currency) : "—"],
      ["operations-margin-risk", operations ? formatCurrency(customer.contribution_margin_at_risk, currency) : "—"],
      ["operations-days-supply", operations ? `${number(inventory.days_of_supply).toFixed(1)}d` : "—"],
      ["operations-inbound-otif", operations ? `${number(supplier.inbound_otif_percent_90d).toFixed(1)}%` : "—"],
      ["operations-supplier-ppm", operations ? new Intl.NumberFormat("en-US").format(number(supplier.supplier_ppm_90d)) : "—"],
    ];
    entries.forEach(([id, content]) => { if ($(id)) $(id).textContent = content; });
    const signal = $("operations-risk-signal");
    if (signal) {
      signal.dataset.tone = value(risk.band || "normal").toLowerCase();
      if (advanced) {
        signal.classList.remove("is-live-update");
        void signal.offsetWidth;
        signal.classList.add("is-live-update");
      }
    }
    const reasons = Array.isArray(risk.reasons) ? risk.reasons : [];
    const reasonHost = $("operations-risk-reasons");
    if (reasonHost) {
      reasonHost.replaceChildren(...(
        reasons.length
          ? reasons.map((reason) => create("span", "", value(reason)))
          : [create("span", "is-clear", operations ? "No cross-system exposure detected" : "Waiting for connected records")]
      ));
    }
    if (advanced) state.operationsMetricSequence = latestSequence;
  }

  function bindDashboardMetricInspectors() {
    document.querySelectorAll(".business-metric, .operations-metric-grid article, .operations-risk-signal").forEach((card) => {
      card.setAttribute("role", "button");
      card.tabIndex = 0;
      const inspect = () => {
        const label = value(card.querySelector("span")?.textContent || card.querySelector("small")?.textContent || "Operational metric");
        const metricValue = value(card.querySelector("strong")?.textContent || "—");
        const supporting = value(card.querySelector("small")?.textContent);
        const isBusiness = card.classList.contains("business-metric");
        const businessMetric = value(card.dataset.businessMetric);
        const tone = value(card.dataset.tone);
        const exactERPLink = (kind, route) => erpDocumentLink(kind, route);
        const externalByMetric = {
          "booked-revenue": exactERPLink("sales_order", "sales-order"),
          "revenue-risk": exactERPLink("sales_order", "sales-order"),
          delivered: exactERPLink("delivery_note", "delivery-note"),
          "value-protected": exactERPLink("sales_invoice", "sales-invoice"),
          "gross-spread": exactERPLink("sales_invoice", "sales-invoice"),
          "invoice-hold": exactERPLink("purchase_invoice", "purchase-invoice"),
          "price-variance": exactERPLink("purchase_invoice", "purchase-invoice"),
        };
        openDashboardComponentInspector({
          kind: isBusiness ? "Financial control" : "Connected operations",
          title: label,
          status: tone === "alert" || ["critical", "elevated"].includes(tone) ? "ANOMALY" : state.connection === "live" ? "LIVE" : "PAUSED",
          tone,
          purpose: supporting || (isBusiness
            ? "Observed or explicitly counterfactual value derived from ERPNext order, delivery, invoice, stock and GL evidence."
            : "Operating signal derived from the connected 90-day plant, supplier and demand window."),
          metrics: [
            ["Current value", metricValue],
            ["Ledger sequence", number(state.agentPlatform?.latest_sequence, state.lastSequence) || "—"],
            ["Source", isBusiness ? "ERPNext authoritative reread" : "MES + demand + supplier evidence"],
          ],
          external: isBusiness
            ? externalByMetric[businessMetric] || erpDocumentLink("purchase_order", "purchase-order")
            : null,
        });
      };
      card.addEventListener("click", inspect);
      card.addEventListener("keydown", (event) => {
        if (!["Enter", " "].includes(event.key)) return;
        event.preventDefault();
        inspect();
      });
    });
  }

  function drawConnectedOperationsChart() {
    const operations = connectedOperationsProjection();
    const history = Array.isArray(operations?.history) ? operations.history : [];
    const points = history.map((point, index) => ({
      ...point,
      timestamp: `${value(point.date)}T12:00:00Z`,
      sequence: index + 1,
      value: number(point.risk_score),
      metric: "Operational risk score",
      unit: "/100",
      source: "synthetic-mes-demand-ledger",
    }));
    drawLineChart(
      $("operations-history-chart"),
      [
        points.map((point) => number(point.risk_score)),
        points.map((point) => number(point.schedule_attainment_percent)),
        points.map((point) => number(point.oee_percent)),
      ],
      ["coral", "cyan", "violet"],
      {
        points,
        metric: "Operational risk score",
        unit: "/100",
        source: "synthetic-mes-demand-ledger",
        emptyLabel: "Waiting for connected operating history",
        startLabel: history.length ? value(history[0].date) : "",
        endLabel: history.length ? value(history[history.length - 1].date) : "",
      },
    );
  }

  function drawBusinessImpactChart(snapshot) {
    const impactPoints = chartTelemetryPoints(snapshot)
      .filter((point) => point && point.business_metrics)
      .map((point) => ({
        ...point,
        value: number(point.business_metrics.working_capital_at_risk),
        metric: "Working capital at risk",
        unit: value(businessImpactProjection()?.currency || "USD"),
        source: "agent-platform-event-ledger",
      }));
    const series = [
      impactPoints.map((point) => number(point.business_metrics.working_capital_at_risk)),
      impactPoints.map((point) => number(point.business_metrics.invoice_hold_value)),
      impactPoints.map((point) => number(point.business_metrics.billed_revenue)),
    ];
    const labels = lineLabels(impactPoints);
    drawLineChart($("business-impact-chart"), series, ["violet", "coral", "lime"], {
      points: impactPoints,
      metric: "Event-time financial evidence",
      unit: value(businessImpactProjection()?.currency || "USD"),
      source: "agent-platform-event-ledger",
      emptyLabel: "Waiting for event-time financial history",
      ...labels,
    });
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
      source: platformFlowProjection()?.provenance === "live-read"
        ? "ERPNext semantic source ledger"
        : "synthetic enterprise snapshot",
      emptyLabel: "Insufficient live history",
      ...labels,
    });
    // The old chart ID remains as an aria-hidden compatibility surface for the
    // existing smoke client.  It is never mounted as a second visible diagram.
    drawLineChart($("reconciliation-chart"), [series.expected, series.recorded, series.gap], ["cyan", "lime", "coral"], {
      points,
      metric: "Gap",
      unit: "units",
      source: platformFlowProjection()?.provenance === "live-read"
        ? "ERPNext semantic source ledger"
        : "synthetic enterprise snapshot",
      gridColor: "rgba(143, 185, 153, .16)",
    });
    renderMiniChart("queue-health-chart", "queue-health-value", telemetryPoints(snapshot, "queue"), "Queue backlog", "coral");
    renderMiniChart("erp-health-chart", "erp-health-value", telemetryPoints(snapshot, "erp"), "ERP posting", "cyan");
    renderMiniChart("invoice-health-chart", "invoice-health-value", telemetryPoints(snapshot, "invoice"), "Invoice completion", "lime");
    renderBusinessImpact();
    drawBusinessImpactChart(snapshot);
    renderConnectedOperations();
    drawConnectedOperationsChart();
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
    const platform = platformFlowProjection();
    const counts = platform ? {
      total: platform.expected,
      erp_recorded: platform.recorded,
      queue_failed: platform.gap,
    } : snapshot.unit_counts || {};
    const agentCount = allAgentStates().filter((item) => ["TRIGGERED", "INVESTIGATING", "WAITING FOR EVIDENCE", "HANDOFF"].includes(item.status)).length;
    const platformMetricEvents = Array.isArray(state.agentPlatform?.activity)
      ? state.agentPlatform.activity.filter((event) => event?.metrics)
      : [];
    const latestPlatformMetric = platformMetricEvents.at(-1);
    const latestTelemetry = latestPlatformMetric
      ? {
        ...latestPlatformMetric.metrics,
        sequence: latestPlatformMetric.sequence,
        received_at: latestPlatformMetric.occurred_at,
        trigger: {
          kind: "external_source_change",
          source_system: "erpnext",
          change_count: number(latestPlatformMetric.change_count),
        },
      }
      : state.telemetry.length ? state.telemetry[state.telemetry.length - 1] : null;
    const values = {
      observedRecords: latestTelemetry
        ? number(latestTelemetry.trigger?.change_count, telemetryRecordCount(latestTelemetry))
        : 0,
      queue: number(counts.queue_failed),
      agents: agentCount,
      sequence: platform?.latestSequence || state.lastSequence || number(snapshot.projection_sequence),
    };
    const telemetrySequence = latestTelemetry
      ? number(latestTelemetry.sequence, values.sequence)
      : values.sequence;
    const metricAdvanced = telemetrySequence > state.liveMetricSequence;
    const flowWindowCount = $("flow-window-count");
    if (flowWindowCount) {
      flowWindowCount.textContent = latestTelemetry
        ? String(number(latestTelemetry.trigger?.change_count, telemetryRecordCount(latestTelemetry)))
        : "—";
    }
    const flowLedgerSequence = $("flow-ledger-sequence");
    if (flowLedgerSequence) {
      flowLedgerSequence.textContent = values.sequence ? String(values.sequence) : "—";
    }
    if (metricAdvanced) {
      [flowWindowCount, flowLedgerSequence].filter(Boolean).forEach((node) => {
        node.classList.remove("is-live-update");
        void node.offsetWidth;
        node.classList.add("is-live-update");
      });
      state.liveMetricSequence = telemetrySequence;
    }
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
        ? `${number(latestTelemetry.trigger?.change_count, telemetryRecordCount(latestTelemetry))} changed records · event ${value(latestTelemetry.sequence)} · source ledger`
        : "Waiting for the first source observation.";
    }
    const provenanceSequence = $("provenance-sequence");
    if (provenanceSequence) provenanceSequence.textContent = `seq ${values.sequence || "—"}`;
    const provenanceDetail = $("provenance-detail");
    if (provenanceDetail) {
      provenanceDetail.textContent = latestTelemetry
        ? `Source-triggered observation · received ${shortTime(latestTelemetry.received_at || latestTelemetry.observed_at)} · source cursor ${value(values.sequence)}`
        : "Awaiting the first external source observation.";
    }
    renderOperationalCharts(snapshot);
    const timeline = $("reconciliation-timeline");
    if (timeline) {
      timeline.replaceChildren();
      const chartPoints = chartTelemetryPoints(snapshot);
      const points = chartPoints.length
        ? chartPoints.map((point) => ({
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
    const flow = snapshot.flow || { nodes: [] };
    const map = $("flow-map");
    map.replaceChildren();
    const rawNodes = Array.isArray(flow.nodes) ? flow.nodes : [];
    const nodeMap = new Map(rawNodes.map((item) => [value(item.id), item]));
    // The control-room route is a fixed four-component supply chain.  Keep
    // the visual order and one card per component even if a future payload
    // contains auxiliary projection nodes or duplicate compatibility rows.
    const nodes = ["warehouse", "message-queue", "erp", "invoice"]
      .map((id) => nodeMap.get(id))
      .filter(Boolean);
    const flowSummary = flow.summary || {};
    const snapshotCounts = snapshot.unit_counts && typeof snapshot.unit_counts === "object" ? snapshot.unit_counts : {};
    const platform = platformFlowProjection();
    const expected = platform
      ? platform.expected
      : number(snapshotCounts.total, number(flowSummary.expected, number(nodeMap.get("warehouse")?.count)));
    const recorded = platform
      ? platform.posted
      : number(snapshotCounts.erp_recorded, number(flowSummary.recorded, number(nodeMap.get("erp")?.count)));
    const queueException = platform
      ? platform.receiptUnresolved
      : number(snapshotCounts.queue_failed, number(flowSummary.queue_exception, number(nodeMap.get("message-queue")?.count)));
    const stageProjection = latestStageProjection(snapshot);
    const stageCounts = stageProjection.counts;
    const projectedCount = (nodeId, fallback) => platform
      ? fallback
      : Object.hasOwn(stageCounts, nodeId)
        ? number(stageCounts[nodeId], fallback)
        : fallback;
    $("expected-count").textContent = String(expected);
    $("recorded-count").textContent = String(recorded);
    $("queue-count").textContent = String(queueException);
    const recordedLabel = $("recorded-count").parentElement?.querySelector("small");
    if (recordedLabel) recordedLabel.textContent = platform ? "RECEIPT POSTED" : "RECORDED";
    const queueLabel = $("queue-count").parentElement?.querySelector("small");
    if (queueLabel) queueLabel.textContent = platform ? "receipt unresolved" : "gap";
    const allNodesHealthy = platform
      ? platform.sourceCurrent && platform.gap === 0 && !platform.invoiceHeld && platform.posted <= platform.expected
      : nodes.length > 0 && nodes.every((item) => ["HEALTHY", "RELEASED"].includes(value(item.status).toUpperCase()));
    const projectedStatus = (item) => {
      if (!platform) return value(item.status).toUpperCase();
      if (value(item.id) === "invoice") return platform.invoiceStatus;
      if (allNodesHealthy) return "HEALTHY";
      if (value(item.id) === "warehouse") return "HEALTHY";
      if (value(item.id) === "message-queue") return platform.receiptUnresolved > 0 ? "ANOMALY" : "HEALTHY";
      if (value(item.id) === "erp") return platform.gap > 0 ? "PARTIAL" : "HEALTHY";
      return platform.invoiceHeld ? "HELD" : "OPEN";
    };
    const receivingAttention = receivingNeedsAttention(state.agentPlatform);
    setBadge($("path-status"), platform && !platform.sourceCurrent ? "Source unavailable"
      : receivingAttention ? "Receiving review" : allNodesHealthy ? "Healthy" : "Attention needed",
      allNodesHealthy && !receivingAttention ? "HEALTHY" : "ANOMALY");
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
        ? projectedCount("warehouse", platform ? platform.received : expected)
        : value(item.id) === "message-queue"
          ? projectedCount("message-queue", queueException)
          : value(item.id) === "erp"
            ? projectedCount("erp", recorded)
            : projectedCount("invoice", platform ? platform.invoiceCount : number(item.count));
      [projection.healthId, projection.sourceId].forEach((id) => {
        const target = $(id);
        if (target) target.textContent = String(count);
      });
      const status = projectedStatus(item);
      const alert = !["HEALTHY", "OPEN", "RELEASED", "NOT YET INVOICED"].includes(status);
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
      const queueHealthy = platform
        ? platform.gap === 0
        : value(nodeMap.get("message-queue")?.status).toUpperCase() === "HEALTHY";
      healthCore.classList.toggle("is-alert", !queueHealthy);
      healthCore.classList.toggle("is-healthy", queueHealthy);
    }
    const rightErp = $("health-erp-right");
    if (rightErp) rightErp.textContent = String(recorded);
    const nextStageCounts = new Map();
    nodes.forEach((item) => {
      const column = create("div", "flow-column");
      const nodeId = value(item.id);
      const count = nodeId === "warehouse"
        ? projectedCount("warehouse", platform ? platform.received : expected)
        : nodeId === "message-queue"
          ? projectedCount("message-queue", queueException)
          : nodeId === "erp"
            ? projectedCount("erp", recorded)
          : projectedCount("invoice", platform ? platform.invoiceCount : number(item.count));
      const previousCount = state.flowStageCounts.get(nodeId);
      const stageUpdated = previousCount != null && previousCount !== count;
      const node = create(
        "article",
        `flow-node ${stateClass(projectedStatus(item))}${stageUpdated ? " is-stage-updated" : ""}`,
        null,
      );
      nextStageCounts.set(nodeId, count);
      node.dataset.nodeId = value(item.id);
      node.dataset.stageCount = String(count);
      node.dataset.flowRunId = stageProjection.runId;
      node.setAttribute("role", "button");
      node.tabIndex = 0;
      node.setAttribute("aria-label", `${value(item.label)}, ${count} records, ${human(projectedStatus(item))}`);
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
      const nodeStatus = projectedStatus(item);
      badge.classList.add(stateClass(nodeStatus));
      const badgeIcon = nodeStatus === "NOT YET INVOICED" ? "ph-bold ph-clock"
        : ["HEALTHY", "OPEN", "RELEASED"].includes(nodeStatus)
        ? "ph-bold ph-check"
        : "ph-bold ph-warning";
      badge.append(create("i", badgeIcon));
      badge.setAttribute("aria-label", nodeStatus);
      header.append(badge);
      const countNode = create(
        "strong",
        `flow-node-count${stageUpdated ? " is-stage-updated" : ""}`,
        String(count),
      );
      const semantics = nodeId === "warehouse"
        ? "received"
        : nodeId === "message-queue"
          ? platform ? "unresolved" : "published"
          : nodeId === "erp"
            ? "posted"
            : nodeId === "invoice"
              ? platform?.provenance === "live-read" ? "invoices" : "matched"
              : "records";
      const countLabel = create("span", "flow-node-count-label", semantics);
      node.setAttribute(
        "aria-label",
        `${value(item.label)}, ${count} ${semantics}, ${human(nodeStatus)}`,
      );
      node.append(header, countNode, countLabel);
      if (nodeId === "message-queue" && queueException > 0) {
        const exception = create("span", "flow-node-exception", `${queueException} held`);
        exception.setAttribute("aria-label", `${queueException} units held before ERP`);
        node.append(exception);
      }
      column.append(node);
      map.append(column);
    });
    state.flowStageCounts = nextStageCounts;
    state.flowStageRunId = stageProjection.runId;
    renderUnitDensity();
    renderUnitAnomalies();
    renderUnitDetail();
  }

  function selectUnit(unitId) {
    if (platformFlowProjection()) return;
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

  function openDashboardComponentInspector(context) {
    const inspector = $("dashboard-component-inspector");
    if (!inspector || !context) return;
    $("dashboard-component-inspector-kind").textContent = value(context.kind || "LIVE COMPONENT").toUpperCase();
    $("dashboard-component-inspector-title").textContent = value(context.title || "Component");
    const status = value(context.status || "WAITING").replaceAll("_", " ");
    setBadge($("dashboard-component-inspector-status"), status, status);
    $("dashboard-component-inspector-purpose").textContent = value(context.purpose || "Live operational component.");
    const metrics = $("dashboard-component-inspector-metrics");
    metrics.replaceChildren();
    (Array.isArray(context.metrics) ? context.metrics : []).forEach(([label, metricValue]) => {
      const row = create("div");
      row.append(create("dt", null, value(label)), create("dd", null, value(metricValue) || "—"));
      metrics.append(row);
    });
    inspector.dataset.tone = isProblemStatus(context.status) || context.tone === "alert" ? "alert" : "normal";
    const external = $("dashboard-component-inspector-external");
    if (external) {
      external.hidden = !context.external;
      external.href = value(context.external?.url || "#");
      const label = external.querySelector("span");
      if (label) label.textContent = value(context.external?.label || "Open service");
      external.setAttribute("aria-label", `${value(context.external?.label || "Open service")} in a new tab`);
    }
    inspector.hidden = false;
  }

  function closeDashboardComponentInspector() {
    const inspector = $("dashboard-component-inspector");
    if (inspector) inspector.hidden = true;
  }

  function flowComponentContext(item) {
    const id = value(item?.id);
    const flow = platformFlowProjection();
    const caseFacts = state.agentPlatform?.demo_case?.case || {};
    const impact = businessImpactProjection();
    const operations = connectedOperationsProjection();
    const risk = operations?.risk_signal || {};
    const ledger = state.erpEvidence?.ledger_evidence || {};
    const stockLedger = Array.isArray(ledger.stock_entries) ? ledger.stock_entries : [];
    const generalLedger = Array.isArray(ledger.general_ledger_entries)
      ? ledger.general_ledger_entries
      : [];
    const ledgerTotals = ledger.totals && typeof ledger.totals === "object" ? ledger.totals : {};
    const currency = value(impact?.currency || "USD");
    const renderedStatus = document.querySelector(`[data-node-id="${id}"] .state-badge`)?.getAttribute("aria-label");
    const status = value(renderedStatus || item?.status || "WAITING");
    const contexts = {
      warehouse: {
        purpose: "Physical receipt and available inventory entering the control loop.",
        external: { label: "Open ERPNext stock", url: "https://missing20.v.frappe.cloud/app/stock-entry" },
        metrics: [
          ["Received", `${number(flow?.received, item?.count)} ${flow?.uom || "units"}`],
          ["Case balance after issues", `${number(flow?.recorded)} ${flow?.uom || "units"}`],
          ["Days of supply", operations ? `${number(operations.inventory?.days_of_supply).toFixed(1)} days` : "—"],
          ["Stock ledger rows", String(stockLedger.length)],
        ],
      },
      "message-queue": {
        purpose: "Carries the receipt event and exposes acknowledgements, retries and unresolved records.",
        external: EXTERNAL_SERVICE_LINKS.celigo,
        metrics: [
          ["Receipt posted", `${number(flow?.posted, item?.count)} ${flow?.uom || "units"}`],
          ["Unresolved", `${number(flow?.receiptUnresolved)} units`],
          ["Business key", value(caseFacts.receipt_business_key || "—")],
        ],
      },
      erp: {
        purpose: "Authoritative inventory ledger used to reconcile physical receipt, quality and financial state.",
        external: erpDocumentLink("purchase_order", "purchase-order"),
        metrics: [
          ["Receipt posted", `${number(flow?.posted, item?.count)} ${flow?.uom || "units"}`],
          ["Reconciled", impact ? `${number(impact.erp_reconciliation_percent).toFixed(1)}%` : "—"],
          ["Live source", value(liveERPDocument("purchase_order")?.name || "WAITING")],
          ["GL rows", String(generalLedger.length)],
          ["Debits / credits", ledger.status === "CONNECTED"
            ? `${formatCurrency(ledgerTotals.debit, currency)} / ${formatCurrency(ledgerTotals.credit, currency)}`
            : "Ledger read unavailable"],
        ],
      },
      invoice: {
        purpose: "Current supplier invoice payment control, checked against receipt and exact-lot evidence.",
        external: erpDocumentLink("purchase_invoice", "purchase-invoice"),
        metrics: [
          ["Invoice", value(impact?.invoice_status || (flow?.invoiceHeld ? "HELD" : "OPEN"))],
          ["Invoice value", impact ? formatCurrency(impact.invoice_value, currency) : "—"],
          ["Live source", value(liveERPDocument("purchase_invoice")?.name || "WAITING")],
          ["Balanced posting", ledger.assertions?.debits_equal_credits ? "Verified" : "Not verified"],
        ],
      },
    };
    const context = contexts[id] || { purpose: "Live supply-chain stage.", metrics: [] };
    return { kind: "Supply chain", title: value(item?.label || human(id)), status, ...context };
  }

  function selectFlowEntity(item) {
    if (!item) return;
    const liveFlow = platformFlowProjection();
    const platformMetrics = liveFlow && Array.isArray(state.agentPlatform?.activity)
      ? state.agentPlatform.activity.filter((event) => event?.metrics && typeof event.metrics === "object")
      : [];
    const latestSourceEvent = platformMetrics.at(-1) || null;
    const latest = latestSourceEvent || (state.telemetry.length ? state.telemetry[state.telemetry.length - 1] : null);
    const liveValues = {
      warehouse: liveFlow?.received,
      "message-queue": liveFlow?.receiptUnresolved,
      erp: liveFlow?.posted,
      invoice: liveFlow ? liveFlow.invoiceCount : latestSourceEvent?.metrics?.invoice_count,
    };
    const selectedValue = liveFlow
      ? number(liveValues[value(item.id)])
      : number(item.count);
    const occurredAt = liveFlow
      ? value(latestSourceEvent?.occurred_at)
      : value(latest?.observed_at || latest?.captured_at);
    const point = {
      sequence: liveFlow?.latestSequence || (latest ? latest.sequence : number(state.snapshot && state.snapshot.projection_sequence)),
      timestamp: occurredAt,
      observed_at: occurredAt,
      received_at: liveFlow ? occurredAt : latest && (latest.received_at || latest.observed_at || latest.captured_at),
      value: selectedValue,
      unit: "records",
      metric: `${value(item.label || item.id)} records`,
      source: liveFlow?.provenance === "live-read"
        ? "ERPNext semantic source ledger"
        : "synthetic enterprise snapshot",
      entity: value(item.id),
    };
    state.selectedPoint = point;
    state.selectedPointSequence = pointSequence(point);
    renderFlowSelectionDetail(point);
    renderDiagramCursorLabels(point);
    renderOperationalCharts(state.snapshot);
    openDashboardComponentInspector(flowComponentContext(item));
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
        create("span", "graph-port graph-port-out", null),
      );
      card.querySelector(".graph-port-in").dataset.port = `${item.id}-in`;
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
      input.placeholder = "Ask the agent team…";
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
    input.placeholder = `Ask ${item.name}…`;
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
      supply: { kind: "cubic-bezier", lane: "orthogonal-data-plane" },
      boundary: { kind: "cubic-bezier", lane: "read-only-boundary" },
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
    // Route shape follows the relationship instead of forcing decoration:
    // aligned source/incident edges stay straight; only fan-out, fan-in,
    // obstacle avoidance, and the outer return use visible curvature.
    if (["supply", "incident", "source"].includes(route.type)) {
      const thirdY = (y2 - y1) / 3;
      return [[[x1, y1], [x1, y1 + thirdY], [x2, y2 - thirdY], [x2, y2]]];
    }
    if (route.type === "boundary") {
      if (Math.abs(x2 - x1) < 8 || Math.abs(y2 - y1) < 8) {
        const thirdX = (x2 - x1) / 3;
        const thirdY = (y2 - y1) / 3;
        return [[[x1, y1], [x1 + thirdX, y1 + thirdY], [x2 - thirdX, y2 - thirdY], [x2, y2]]];
      }
      const spanY = y2 - y1;
      return [[[x1, y1], [x1, y1 + spanY * .42], [x2, y2 - spanY * .42], [x2, y2]]];
    }
    if (route.type === "orchestrator") {
      if (route.lane === "coord-middle") {
        const thirdY = (y2 - y1) / 3;
        return [[[x1, y1], [x1, y1 + thirdY], [x2, y2 - thirdY], [x2, y2]]];
      }
      const spanX = x2 - x1;
      const spanY = y2 - y1;
      return [[[x1, y1], [x1 + spanX * .34, y1 + spanY * .12], [x2 - spanX * .2, y2 - spanY * .14], [x2, y2]]];
    }
    if (route.type === "investigator") {
      if (Math.abs(x2 - x1) < 8) {
        const thirdY = (y2 - y1) / 3;
        return [[[x1, y1], [x1, y1 + thirdY], [x2, y2 - thirdY], [x2, y2]]];
      }
      const spanX = x2 - x1;
      const spanY = y2 - y1;
      return [[[x1, y1], [x1 + spanX * .28, y1 + spanY * .08], [x2 - spanX * .28, y2 - spanY * .08], [x2, y2]]];
    }
    if (route.type === "synthesis") {
      const spanX = x2 - x1;
      const spanY = y2 - y1;
      return [[[x1, y1], [x1 + spanX * .28, y1 + spanY * .08], [x2 - spanX * .24, y2 - spanY * .12], [x2, y2]]];
    }
    if (route.type === "lifecycle") {
      const span = (x2 - x1) * .38;
      return [[[x1, y1], [x1 + span, y1], [x2 - span, y2], [x2, y2]]];
    }
    if (route.type === "return") {
      // Verification exits into a private right-hand rail, rises beside the
      // graph, then enters the incident capsule from its right port. Short
      // cubic corner turns keep the return visually rounded without creating
      // the old bottom/left drag tail or crossing the control row.
      const rightOuter = Math.max(x1 + 36, Math.min(width - 12, width - 12));
      const topLane = Math.max(16, Math.min(y2 - 30, y1 - 72));
      const corner = Math.max(14, Math.min(24, (y1 - topLane) / 8));
      const horizontal = Math.max(18, Math.min(32, (rightOuter - x1) * .16));
      const entryLead = 30;
      const railSpan = Math.max(1, rightOuter - corner - x1);
      const turnControl = railSpan * .35;
      return [
        [[x1, y1], [x1 + turnControl, y1], [rightOuter - corner - turnControl, y1], [rightOuter - corner, y1]],
        [[rightOuter - corner, y1], [rightOuter - corner + corner * .55, y1], [rightOuter, y1 - corner * .55], [rightOuter, y1 - corner]],
        [[rightOuter, y1 - corner], [rightOuter, y1 - corner - (y1 - topLane - corner * 2) * .34], [rightOuter, topLane + corner + (y1 - topLane - corner * 2) * .34], [rightOuter, topLane + corner]],
        [[rightOuter, topLane + corner], [rightOuter, topLane + corner * .45], [rightOuter - corner * .55, topLane], [rightOuter - corner, topLane]],
        [[rightOuter - corner, topLane], [rightOuter - corner - horizontal, topLane], [x2 + entryLead + horizontal, topLane], [x2 + entryLead, topLane]],
        [[x2 + entryLead, topLane], [x2 + entryLead * .45, topLane], [x2, y2 - entryLead * .45], [x2, y2]],
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
      path.add("verification->supply-chain");
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
      path.add("incident-packet->orchestrator");
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
      path.add("verification->supply-chain");
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
      `orchestrator->${agentId}`,
      `${agentId}->synthesis`,
      "synthesis->safety",
      "safety->approval",
      "approval->execution",
      "execution->verification",
      "verification->supply-chain",
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
    const evidenceApi = $("evidence-api-node");
    if (!graph || !links || !orchestrator || !synthesis || !incidentPacket || !evidenceApi) return;
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
    const warehouse = graph.querySelector('[data-supply-node="warehouse"]');
    const queue = graph.querySelector('[data-supply-node="queue"]');
    const erp = graph.querySelector('[data-supply-node="erp"]');
    const invoice = graph.querySelector('[data-supply-node="invoice"]');
    add("warehouse->queue", warehouse, ".graph-port-flow-out", queue, ".graph-port-flow-in", "supply", "supply-chain");
    add("queue->erp", queue, ".graph-port-flow-out", erp, ".graph-port-flow-in", "supply", "supply-chain");
    add("erp->invoice", erp, ".graph-port-flow-out", invoice, ".graph-port-flow-in", "supply", "supply-chain");
    add("erp->incident-packet", erp, ".graph-port-boundary-out", incidentPacket, ".graph-port-in", "boundary", "supply-incident");
    add("incident-packet->evidence-api", incidentPacket, ".graph-port-out", evidenceApi, ".graph-port-in", "boundary", "incident-evidence");
    add("incident-packet->orchestrator", evidenceApi, ".graph-port-out", orchestrator, ".graph-port-in", "boundary", "evidence-orchestrator");
    agents.forEach((agent) => {
      const card = graph.querySelector(`.agent-nodes [data-agent-id="${CSS.escape(agent.id)}"]`);
      if (!card) return;
      const coordinationLane = agent.id === "retryable_message_investigator"
        ? "coord-left"
        : agent.id === "short_shipment_investigator"
          ? "coord-middle"
          : "coord-right";
      add(`orchestrator->${agent.id}`, orchestrator, ".graph-port-out", card, ".graph-port-in", "orchestrator", coordinationLane);
      add(`${agent.id}->synthesis`, card, ".graph-port-out", synthesis, ".graph-port-in", "investigator", `handoff-${coordinationLane.slice(6)}`);
    });
    const safety = graph.querySelector('[data-graph-node="safety"]');
    const approval = graph.querySelector('[data-graph-node="approval"]');
    const execution = graph.querySelector('[data-graph-node="execution"]');
    const verification = graph.querySelector('[data-graph-node="verification"]');
    add("synthesis->safety", synthesis, ".graph-port-out", safety, ".graph-port-in", "synthesis", "lifecycle-entry");
    add("safety->approval", safety, ".graph-port-out", approval, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("approval->execution", approval, ".graph-port-out", execution, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("execution->verification", execution, ".graph-port-out", verification, ".graph-port-in", "lifecycle", "lifecycle-chain");
    add("verification->supply-chain", verification, ".graph-port-out", invoice, ".graph-port-return-in", "return", "outer-return");
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
    const isLatest = number(item.sequence) === state.latestActivitySequence;
    const row = create("li", `operation-item operation-${slug(eventType(item))}${isLatest ? " is-new" : ""}`);
    const dot = create("span", `operation-dot ${stateClass(item.status)}`, null);
    dot.setAttribute("aria-hidden", "true");
    const copy = create("div", "operation-copy");
    copy.append(create("strong", null, eventLabel(item)), create("span", null, eventDetail(item)));
    const meta = create("span", "operation-meta", `#${value(item.sequence).padStart(2, "0")} · ${shortTime(item.occurred_at)}`);
    row.append(dot, copy, meta);
    return row;
  }

  function renderEnterpriseOperationItem(item, sequence, provider = "ERP") {
    const row = create("li", `operation-item operation-enterprise-evidence is-new`);
    const dot = create("span", `operation-dot ${stateClass(item.status)}`, null);
    dot.setAttribute("aria-hidden", "true");
    const copy = create("div", "operation-copy");
    copy.append(create("strong", null, value(item.label)), create("span", null, value(item.detail)));
    const meta = create("span", "operation-meta", `${provider} · #${String(sequence).padStart(2, "0")} · ${shortTime(item.occurred_at)}`);
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
    const synthesisBadge = $("synthesis-status");
    const synthesisReached = state.events.some((event) => [
      "synthesis.started",
      "synthesis.completed",
      "evaluation.started",
      "evaluation.completed",
    ].includes(eventType(event))) || persistedLifecycleProjection().stagesComplete;
    if (synthesisBadge) {
      synthesisBadge.hidden = !synthesisReached;
      if (synthesisReached) setBadge(synthesisBadge, synthesis.label, synthesis.raw);
    }
    const packet = $("incident-packet-node");
    if (packet) {
      packet.classList.toggle("is-alert", hasIncidentDetected() && !isClosedOrRecovery());
    }
    const supplyChain = supplyChainStatus();
    setBadge($("workspace-state"), supplyChain.label, supplyChain.raw);
    const operations = state.events.filter((item) => OPERATION_TYPES.has(eventType(item)) || ["copilot.message", "provider.degraded", "workflow.blocked"].includes(eventType(item)));
    const activityRows = operations.length ? operations : state.events;
    const enterpriseRows = state.erpEvidence && Array.isArray(state.erpEvidence.activity)
      && value(state.erpEvidence.status) === "CONNECTED"
      ? state.erpEvidence.activity
      : [];
    const saasRows = state.saasEvidence && Array.isArray(state.saasEvidence.activity)
      && value(state.saasEvidence.status) !== "NOT_CONFIGURED"
      ? state.saasEvidence.activity.filter((item) => value(item.status) !== "NOT_CONFIGURED")
      : [];
    const sourceRows = [
      ...enterpriseRows.map((item) => ({ item, sequence: number(state.erpEvidence.sequence), provider: "ERP" })),
      ...saasRows.map((item) => ({ item, sequence: number(state.saasEvidence.sequence), provider: value(item.provider).split(" · ")[0] || "SaaS" })),
    ];
    $("operation-count").textContent = operations.length || sourceRows.length
      ? `${operations.length + sourceRows.length} events`
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
    if (!state.selectedAgentId || state.selectedAgentId === "orchestrator") {
      sourceRows.slice().reverse().forEach((row) => {
        feed.append(renderEnterpriseOperationItem(row.item, row.sequence, row.provider));
      });
    }
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
      if (!state.selectedAgentId || state.selectedAgentId === "orchestrator") {
        sourceRows.slice().reverse().forEach((row) => {
          fullFeed.append(renderEnterpriseOperationItem(row.item, row.sequence, row.provider));
        });
      }
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
      const stopped = name === "safety" && latestType === "workflow.blocked";
      step.classList.toggle("is-done", done);
      step.classList.toggle("is-active", Boolean(active || stopped));
      const statusNode = step.querySelector("[data-graph-step-status]");
      if (statusNode) {
        const reached = done || active || stopped;
        statusNode.hidden = !reached;
        const status = done ? "COMPLETE" : stopped ? "SAFE STOP" : "ACTIVE";
        statusNode.textContent = status;
      }
    });
    const loopVerified = document.querySelector(".graph-loop-label");
    if (loopVerified) loopVerified.hidden = !lifecycleDone.verification;
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

  function evidenceChipLabel(evidenceId) {
    const id = value(evidenceId);
    const record = Array.isArray(state.snapshot && state.snapshot.evidence)
      ? state.snapshot.evidence.find((item) => value(item && item.evidence_id) === id)
      : null;
    const sourceType = value(record && record.source_type).toUpperCase();
    const sourceNames = {
      FAILED_MESSAGE_QUEUE: "Failed message",
      WAREHOUSE: "Warehouse",
      ERP_RECEIPT: "ERP receipt",
      INVOICE: "Invoice",
      MATERIAL_DOCUMENT: "Material document",
      KNOWLEDGE_BASE: "Knowledge record",
    };
    if (sourceNames[sourceType]) return sourceNames[sourceType];
    const normalized = id.toLowerCase();
    if (normalized.includes("failed") || normalized.includes("queue")) return "Failed message";
    if (normalized.includes("warehouse") || normalized.includes("ship")) return "Warehouse";
    if (normalized.includes("erp") || normalized.includes("receipt")) return "ERP receipt";
    if (normalized.includes("invoice")) return "Invoice";
    return "Evidence";
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

  function dashboardEventSource(event) {
    const payload = event && event.payload && typeof event.payload === "object" ? event.payload : {};
    if (["receiving-scan", "receiving-photo"].includes(value(event.source_id || payload.source_id))) return "Receiving";
    const haystack = `${value(event.source_id || payload.source_id)} ${value(event.actor)} ${value(event.provider)} ${value(event.type)} ${value(event.label)} ${value(event.detail)}`.toLowerCase();
    if (haystack.includes("airtable")) return "Airtable";
    if (haystack.includes("celigo")) return "Celigo";
    if (haystack.includes("jira")) return "Jira";
    if (haystack.includes("slack")) return "Slack";
    if (haystack.includes("erp") || haystack.includes("receipt")) return "ERPNext";
    if (haystack.includes("invoice")) return "Invoice";
    if (haystack.includes("manager") || haystack.includes("approval")) return "Manager";
    if (haystack.includes("agent") || haystack.includes("strand") || haystack.includes("investigation")) return "Agent";
    return "Control plane";
  }

  function operatorEventTime(occurredAt, sequence) {
    if (Number.isNaN(occurredAt.getTime())) return `#${value(sequence)}`;
    const time = occurredAt.toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
    return occurredAt.toDateString() === new Date().toDateString()
      ? time
      : `${occurredAt.toLocaleDateString([], { month: "short", day: "numeric" })} · ${time}`;
  }

  function renderDashboardEventRail() {
    const feed = $("dashboard-event-feed");
    if (!feed) return;
    const platformEvents = Array.isArray(state.agentPlatform?.activity) ? state.agentPlatform.activity : [];
    const ledgerEvents = Array.isArray(state.events) ? state.events : [];
    // Normal uses its session ledger; a selected case uses its platform ledger.
    // Provider polling and unrelated scenario events are not new case effects.
    const combinedEvents = (platformFlowProjection() ? platformEvents : ledgerEvents)
      .filter((event) => event && typeof event === "object");
    const deduplicated = new Map();
    combinedEvents.forEach((event) => {
      const key = [
        number(event.sequence),
        value(event.type),
        value(event.label),
        value(event.occurred_at || event.timestamp || event.created_at),
      ].join("|");
      deduplicated.set(key, event);
    });
    const allEvents = [...deduplicated.values()].sort((left, right) => {
      const leftTime = Date.parse(value(left.occurred_at || left.timestamp || left.created_at));
      const rightTime = Date.parse(value(right.occurred_at || right.timestamp || right.created_at));
      if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
        return leftTime - rightTime;
      }
      return number(left.sequence) - number(right.sequence);
    });
    // Keep one newest receipt per source so fast control-plane pulses cannot
    // drown out the slower external reads that prove the Agent touched real
    // demo records. During an investigation the Agent replaces the generic
    // control-plane row; otherwise the operator sees five sources plus flow.
    const newestBySource = new Map();
    allEvents.forEach((event) => newestBySource.set(dashboardEventSource(event), event));
    // A completed answer is still a new event; do not hide it when the agent
    // returns to VERIFIED/idle after a live conversation.
    const preferredSources = newestBySource.has("Agent")
      ? ["ERPNext", "Airtable", "Celigo", "Jira", "Slack", "Receiving", "Agent"]
      : ["ERPNext", "Airtable", "Celigo", "Jira", "Slack", "Receiving", "Control plane"];
    const events = preferredSources
      .map((source) => newestBySource.get(source))
      .filter(Boolean)
      .sort((left, right) => Date.parse(value(left.occurred_at || left.timestamp || left.created_at))
        - Date.parse(value(right.occurred_at || right.timestamp || right.created_at)));
    const previousLatest = state.dashboardLatestRenderedSequence;
    const latest = events.reduce((maximum, event) => Math.max(maximum, number(event.sequence)), 0);
    feed.replaceChildren();
    // newest-at-bottom: rows stay chronological so real SSE arrivals push older evidence upward.
    events.forEach((event) => {
      const sequence = number(event.sequence);
      const row = create("li", "dashboard-event-row");
      row.dataset.source = slug(dashboardEventSource(event));
      if (previousLatest > 0 && sequence > previousLatest) row.classList.add("is-new");
      const occurredAt = new Date(value(event.occurred_at || event.timestamp || event.created_at));
      const timeLabel = operatorEventTime(occurredAt, event.sequence);
      const body = create("div", "dashboard-event-copy");
      body.append(
        create("span", "dashboard-event-source", dashboardEventSource(event)),
        create("strong", null, value(event.label || eventLabel(event))),
        create("p", null, value(event.detail || eventDetail(event))),
      );
      row.append(create("time", null, timeLabel), body);
      feed.append(row);
    });
    $("dashboard-event-count").textContent = `${allEvents.length} events`;
    const newest = events[events.length - 1];
    const latestLabel = $("dashboard-event-now")?.firstElementChild;
    if (latestLabel) latestLabel.textContent = newest
      ? `Latest · ${operatorEventTime(new Date(value(newest.occurred_at || newest.timestamp || newest.created_at)), newest.sequence)}`
      : "Waiting for events";
    if (latest > state.dashboardLatestRenderedSequence) state.dashboardLatestRenderedSequence = latest;
    if (state.dashboardEventFollow) window.requestAnimationFrame(() => { feed.scrollTop = feed.scrollHeight; });
  }

  function renderDashboardAgentStatus() {
    const liveFlow = platformFlowProjection();
    const platform = liveFlow ? state.agentPlatform || {} : {};
    const sourceAttention = receivingNeedsAttention(platform)
      || Boolean(liveFlow && (liveFlow.gap > 0 || liveFlow.invoiceHeld));
    const agentRun = platform.agent_run && typeof platform.agent_run === "object" ? platform.agent_run : {};
    const diagnosis = platform.diagnosis && typeof platform.diagnosis === "object" ? platform.diagnosis : {};
    const proof = platform.judge_proof && typeof platform.judge_proof === "object" ? platform.judge_proof : {};
    const execution = platform.execution && typeof platform.execution === "object" ? platform.execution : {};
    const executionStatus = value(execution.status).toUpperCase();
    const runState = value(agentRun.state).toUpperCase();
    const finding = value(diagnosis.finding).toUpperCase();
    const stage = executionStatus === "VERIFIED"
      ? "Recovery verified"
      : executionStatus === "VERIFYING"
        ? "Verifying recovery"
        : executionStatus === "AUTHORIZED"
          ? "Manager approved"
          : runState === "PLAN_READY"
            ? "Awaiting manager review"
            : runState === "BLOCKED" && ["AGENT_UNAVAILABLE", "AGENT_VALIDATION_FAILED"].includes(finding)
              ? "Agent unavailable · retry required"
              : runState === "BLOCKED"
                ? "Safe stop"
            : ["RUNNING", "REASONING", "INVESTIGATING"].includes(runState)
              ? "Investigating"
              : platform.receiving_work?.status === "CONFIGURED"
                ? (sourceAttention ? "Receiving needs review" : "Monitoring receiving")
              : isNormalScenario() && !sourceAttention
                ? "Monitoring"
                : "Incident detected";
    $("dashboard-agent-stage").textContent = stage;
    const sources = Array.isArray(state.saasEvidence?.sources) ? state.saasEvidence.sources : [];
    $("dashboard-agent-evidence").textContent = String(number(proof.evidence_records, sources.length + (state.erpEvidence ? 1 : 0)));
    const strands = diagnosis.strands_investigation && typeof diagnosis.strands_investigation === "object"
      ? diagnosis.strands_investigation
      : {};
    const toolCalls = Array.isArray(strands.tool_calls)
      ? strands.tool_calls
      : Array.isArray(diagnosis.tool_calls) ? diagnosis.tool_calls : [];
    $("dashboard-agent-tool-count").textContent = String(number(proof.source_checks, toolCalls.length));
    const platformActivity = Array.isArray(platform.activity) ? platform.activity : [];
    const visibleEventTotal = liveFlow
      ? platformActivity.length
      : new Set(
        [...state.events, ...platformActivity].map((event) => [
          number(event && event.sequence),
          value(event && event.type),
          value(event && event.label),
          value(event && (event.occurred_at || event.timestamp || event.created_at)),
        ].join("|")),
      ).size;
    $("dashboard-agent-event-count").textContent = String(
      liveFlow
        ? visibleEventTotal
        : Math.max(visibleEventTotal, number(proof.ledger_events, platform.latest_sequence)),
    );
    const provider = strands.provider && typeof strands.provider === "object" ? strands.provider : {};
    const proofProvider = proof.provider && typeof proof.provider === "object" ? proof.provider : {};
    const providerLabel = value(provider.model_id || provider.model || proofProvider.model_id || proofProvider.model || strands.mode || proof.runtime);
    const strandsStatus = value(strands.status).toUpperCase();
    $("dashboard-agent-provider").textContent = strandsStatus === "COMPLETE" && providerLabel
      ? providerLabel.includes("nova-pro")
        ? "Amazon Nova Pro"
        : providerLabel.replace("us.amazon.", "").replace("-v1:0", "")
      : strandsStatus.includes("UNAVAILABLE")
        ? "Unavailable"
        : "Strands";
    const confidence = number(diagnosis.confidence, -1);
    $("dashboard-agent-confidence").textContent = confidence >= 0
      ? `${Math.round(confidence <= 1 ? confidence * 100 : confidence)}%`
      : "—";
    const status = $("dashboard-agent-status");
    status.dataset.stage = slug(stage);
    const facts = status.querySelector(".dashboard-agent-facts");
    if (facts) facts.hidden = (isNormalScenario() && !sourceAttention)
      || (platform.receiving_work?.status === "CONFIGURED" && ["", "NOT_EVALUATED"].includes(finding));
    const openInvestigation = $("dashboard-open-investigation");
    if (openInvestigation) {
      openInvestigation.hidden = isNormalScenario()
        && !sourceAttention;
    }
  }

  function renderDashboardEvidenceLinks() {
    const stage = document.querySelector("#dashboard-view .flow-stage");
    const map = $("dashboard-evidence-map");
    const svg = $("dashboard-evidence-links");
    if (!stage || !map || !svg || stage.offsetParent === null) return;
    const stageBounds = stage.getBoundingClientRect();
    const mapBounds = map.getBoundingClientRect();
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, stageBounds.width)} ${Math.max(1, stageBounds.height)}`);
    svg.replaceChildren();
    if (state.agentPlatform?.receiving_work?.status === "CONFIGURED") {
      // Receipt notifications are linked from their verified records, not an
      // invented warehouse→Jira or invoice→Slack physical-goods route.
      map.dataset.layout = "standalone";
      return;
    }
    const links = [
      ["jira", "warehouse"],
      ["celigo", "message-queue"],
      ["airtable", "erp"],
      ["slack", "invoice"],
    ];
    // Source access remains useful while operational quantities are unknown.
    // Hidden targets have zero bounds: positioning against them stacks every
    // source at x=0 and draws dangling lines across the heading.
    const connected = links.every(([, targetId]) => {
      const target = $("flow-map")?.querySelector(`[data-node-id="${targetId}"]`);
      const bounds = target?.getBoundingClientRect();
      return bounds && bounds.width > 0 && bounds.height > 0;
    });
    map.dataset.layout = connected ? "connected" : "standalone";
    if (!connected) return;
    links.forEach(([sourceId, targetId]) => {
      const source = map.querySelector(`[data-dashboard-evidence="${sourceId}"]`);
      const target = $("flow-map")?.querySelector(`[data-node-id="${targetId}"]`);
      if (!source || !target) return;
      const targetBounds = target.getBoundingClientRect();
      const sourceWidth = source.getBoundingClientRect().width;
      const targetCenterX = targetBounds.left - mapBounds.left + targetBounds.width / 2;
      source.style.left = `${Math.max(0, Math.min(mapBounds.width - sourceWidth, targetCenterX - sourceWidth / 2))}px`;
    });
    links.forEach(([sourceId, targetId]) => {
      const source = map.querySelector(`[data-dashboard-evidence="${sourceId}"]`);
      const target = $("flow-map")?.querySelector(`[data-node-id="${targetId}"]`);
      if (!source || !target) return;
      const sourceBounds = source.getBoundingClientRect();
      const targetBounds = target.getBoundingClientRect();
      const start = {
        x: targetBounds.left - stageBounds.left + targetBounds.width / 2,
        y: targetBounds.bottom - stageBounds.top,
      };
      const end = {
        x: sourceBounds.left - stageBounds.left + sourceBounds.width / 2,
        y: sourceBounds.top - stageBounds.top,
      };
      const path = createSvgPath();
      path.setAttribute("d", platformLinkPath(start, end));
      path.setAttribute("class", "dashboard-evidence-link");
      path.setAttribute("data-dashboard-link", `${sourceId}-${targetId}`);
      path.setAttribute("vector-effect", "non-scaling-stroke");
      svg.append(path);
    });
  }

  function renderDashboardEvidence() {
    const liveSystems = hasLiveSourceAuthority() && Array.isArray(state.agentPlatform?.systems)
      ? state.agentPlatform.systems : null;
    const sources = liveSystems || (Array.isArray(state.saasEvidence?.sources) ? state.saasEvidence.sources : []);
    const platformNodes = Array.isArray(state.agentPlatform?.evidence_constellation?.nodes)
      ? state.agentPlatform.evidence_constellation.nodes
      : [];
    const platformSourceIds = { jira: "jira", celigo: "celigo", airtable: "airtable", slack: "slack" };
    const usePlatformTruth = Boolean(platformFlowProjection());
    const evidenceMap = $("dashboard-evidence-map");
    const hasProviderRecords = sources.some((item) => Boolean(item?.record_id));
    const hideEvidenceMap = isNormalScenario() && !hasProviderRecords;
    if (evidenceMap) evidenceMap.hidden = hideEvidenceMap;
    const evidenceLinks = $("dashboard-evidence-links");
    if (evidenceLinks) evidenceLinks.hidden = hideEvidenceMap;
    document.querySelectorAll("[data-dashboard-evidence]").forEach((node) => {
      const id = value(node.dataset.dashboardEvidence);
      const evidence = sources.find((item) => `${value(item.id)} ${value(item.provider)} ${value(item.source_id)}`.toLowerCase().includes(id));
      const platformEvidence = platformNodes.find((item) => value(item?.id) === platformSourceIds[id]);
      const hasLiveRead = Boolean(evidence?.record_id);
      const titleNode = node.querySelector("strong");
      if (titleNode && id === "airtable") titleNode.textContent = evidence?.name === "Airtable Receiving" ? "Airtable Receiving" : "Airtable Quality";
      const status = value(
        (liveSystems || hasLiveRead)
          ? evidence?.status || (liveSystems ? "NOT CONFIGURED" : "CONNECTED")
          : usePlatformTruth
            ? platformEvidence?.status || "WAITING"
            : state.saasEvidence ? "CONNECTED" : "WAITING",
      ).replaceAll("_", " ");
      const statusNode = node.querySelector("span");
      if (statusNode) statusNode.textContent = status;
      node.dataset.sourceStatus = status;
      node.dataset.sourceDetail = value(
        (liveSystems || hasLiveRead)
          ? `${value(evidence?.name || evidence?.provider)} · ${value(evidence?.record_id)} · ${value(evidence?.detail)}`
          : usePlatformTruth
            ? platformEvidence?.detail || `${value(platformEvidence?.role || id)} evidence · sequence ${value(platformEvidence?.latest_sequence || "—")}`
            : evidence?.detail || evidence?.label || "No source event received yet",
      );
      node.dataset.sourceSequence = value(evidence?.record_id || platformEvidence?.latest_sequence || state.lastSequence || "—");
      node.dataset.sourceRecordId = value(evidence?.record_id);
      node.dataset.sourceUrl = value(evidence?.url || "");
      node.classList.toggle("is-live", hasLiveRead || (usePlatformTruth ? Boolean(platformEvidence) : Boolean(evidence)));
      node.classList.toggle("is-attention", ["UNKNOWN", "TIMEOUT", "HELD", "BLOCKED", "DEGRADED", "NOT CONFIGURED"].includes(status.toUpperCase()));
    });
    window.requestAnimationFrame(renderDashboardEvidenceLinks);
  }

  function renderDashboard() {
    renderFlow();
    renderDashboardEventRail();
    renderDashboardAgentStatus();
    renderDashboardEvidence();
    const normalScenario = isNormalScenario();
    const closedRecovery = isVerifiedClosedRecovery();
    const incidentVisible = !normalScenario && !closedRecovery;
    const inject = $("dashboard-inject-incident");
    if (inject) {
      const liveSourceMode = hasLiveSourceAuthority();
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
      if (!liveSourceMode && injectLabel) injectLabel.textContent = hasActiveIncident
          ? "Resume active incident"
          : hasHistoricalIncident
            ? "View completed investigation"
            : "Inject incident";
      const sourceActionAllowed = liveSourceMode && Boolean(EXTERNAL_SERVICE_LINKS.erpnext?.url);
      inject.disabled = liveSourceMode ? !sourceActionAllowed : !injectAllowed;
      inject.setAttribute("aria-disabled", String(liveSourceMode ? !sourceActionAllowed : !injectAllowed));
      inject.title = liveSourceMode
        ? "Open ERPNext; this dashboard advances only after the external records change"
        : injectAllowed
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
      syncDashboardSourceControl();
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
      : ["INTEGRATION_OPERATOR", "AP_APPROVER"];
    const approvedRoles = new Set(
      approvals
        .filter((item) => value(item.intent_id) === intent && value(item.status) === "APPROVED")
        .map((item) => value(item.role))
        .filter((role) => requiredRoles.includes(role)),
    );
    const approvalCount = approvedRoles.size;
    const quorumApproved = prepared && value(approval.status) === "GRANTED" && approvalCount === requiredRoles.length;
    const hasExecution = prepared && state.events.some((event) => eventType(event) === "execution.completed" && value(event.payload && event.payload.tool) === activeTool);
    const executionStarted = prepared && state.events.some((event) => eventType(event) === "execution.started" && value(event.payload && event.payload.tool) === activeTool);
    const effectStarted = prepared && state.events.some((event) => eventType(event) === "effect.started" && value(event.payload && event.payload.tool) === activeTool);
    const verificationStarted = prepared && state.events.some((event) => eventType(event) === "verification.started");
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
    else if (verificationStarted) { status = "VERIFYING"; rawStatus = "RUNNING"; }
    else if (hasExecution) { status = "RECOVERED"; rawStatus = "COMPLETE"; }
    else if (effectStarted) { status = "APPLYING RECOVERY"; rawStatus = "RUNNING"; }
    else if (executionStarted) { status = "EXECUTING"; rawStatus = "RUNNING"; }
    else if (quorumApproved) { status = "APPROVED"; rawStatus = "GRANTED"; }
    else if (approvalCount) { status = `${approvalCount} of ${requiredRoles.length} approved`; rawStatus = "PENDING_APPROVAL"; }
    else if (prepared) { status = "Awaiting Manager"; rawStatus = "PENDING_APPROVAL"; }
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
        const approved = quorumApproved;
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
          button.addEventListener("click", recordManagerApproval);
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
    executeButton.disabled = state.commandBusy || !canOperate() || !quorumApproved || executionStarted || (verified && hasExecution);
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
      if (response.accepted === true && !state.source) connectEvents();
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

  async function recordManagerApproval() {
    const intent = state.snapshot && state.snapshot.approval && state.snapshot.approval.intent_id;
    if (!intent) return;
    for (const principal of MANAGER_ATTESTATIONS) {
      const approved = (state.snapshot?.approvals || []).some((item) => value(item.intent_id) === intent && value(item.principal_id) === principal && value(item.status) === "APPROVED");
      if (!approved) {
        const response = await sendDecision({ command: "approve", intent_id: intent, principal_id: principal, idempotency_key: makeKey(`manager-${principal}`) });
        if (!response) return;
      }
    }
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
    const actions = currentCaseActions().filter((action) => action.id !== "continue_investigation" && action.enabled);
    const actionRail = host.closest(".case-console-actions");
    if (actionRail) actionRail.hidden = actions.length === 0;
    actions.forEach((action) => {
      const button = create("button", `case-action case-action-${slug(action.id)}`, action.label);
      button.type = "button";
      button.setAttribute("data-case-action-id", action.id);
      button.disabled = state.commandBusy || state.chatPending || !streamIsLive();
      button.setAttribute("aria-disabled", String(button.disabled));
      if (action.reason) button.title = action.reason;
      button.addEventListener("click", () => invokeCaseAction(action.id));
      host.append(button);
    });
    if (status) {
      status.textContent = isVerifiedClosedRecovery()
        ? "Recovery verified · No further action"
        : state.caseActionStatus || "";
    }
  }

  function renderChat() {
    syncDurableChat();
    const log = $("chat-log");
    log.replaceChildren();
    state.chatMessages.slice(-12).forEach((item) => {
      const row = create("article", `chat-message chat-${item.role}`);
      const messageAgent = item.agentId && item.agentId !== "orchestrator"
        ? agentDefinition(item.agentId)
        : null;
      const assistantLabel = messageAgent ? messageAgent.name.toUpperCase() : "AGENT TEAM";
      row.append(create("span", "chat-role", item.role === "user" ? "YOU" : assistantLabel), create("p", null, item.message));
      if (item.citations && item.citations.length) {
        const refs = create("div", "chat-citations");
        item.citations.slice(0, 6).forEach((citation) => {
          const evidenceId = value(citation);
          const label = evidenceChipLabel(evidenceId);
          const button = create("button", "citation", label);
          button.type = "button";
          button.setAttribute("aria-label", `${label} evidence: ${evidenceId}`);
          button.addEventListener("click", () => focusEvidence(evidenceId));
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
        button.hidden = false;
        button.textContent = "Evidence";
        button.dataset.question = roleQuestion[1];
        button.setAttribute("aria-label", roleQuestion[0]);
      } else if (index === 1) {
        button.hidden = false;
        button.textContent = "Compare causes";
        button.dataset.question = "Compare the alternative hypotheses.";
        button.setAttribute("aria-label", "Compare the alternative hypotheses");
      } else {
        button.hidden = true;
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
    const cited = citations.length ? " Evidence is attached below." : "";
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
    // Keep the autonomous trace current even while the dashboard remains in
    // focus. Switching to the Agent Workspace then reveals the same ordered
    // trace instead of a stale, post-hoc reconstruction.
    renderAgentView();
    renderAgentPlatform();
    if (state.view === "dashboard") renderDashboard();
    $("dashboard-view").hidden = state.view !== "dashboard";
    $("agent-view").hidden = state.view !== "agent";
    $("scenario-view").hidden = !state.demoControlsOpen;
    $("demo-controls-toggle")?.setAttribute("aria-expanded", String(state.demoControlsOpen));
    renderSourceFreshness();
    bodyReady();
  }

  function renderSourceFreshness() {
    const sourceCase = state.agentPlatform?.case_projection;
    const sourceQuantities = sourceCase?.case?.quantities;
    const quantitiesUnknown = sourceCase?.provenance === "live-read" && sourceQuantities
      && ["ordered", "available", "quality_hold", "receipt_unresolved"].some((key) => sourceQuantities[key] == null);
    const unavailable = state.agentPlatform?.source_freshness?.status === "UNAVAILABLE"
      || Boolean(state.agentPlatformReadError) || Boolean(quantitiesUnknown);
    const wasUnavailable = document.body.dataset.sourceFreshness === "unavailable";
    document.body.dataset.sourceFreshness = unavailable ? "unavailable" : "current";
    $("source-unavailable").hidden = !unavailable;
    $("source-unavailable-title").textContent = state.agentPlatform?.source_freshness?.error_code === "RATE_LIMITED"
      ? "ERPNext is rate-limiting reads. Retrying after its cooldown." : "ERP data is temporarily unavailable.";
    if (!unavailable) return;
    // Missing source records are not zero stock. Keep historical events/proof,
    // but do not manufacture a current healthy state from null quantities.
    $("incident-title").textContent = quantitiesUnknown ? "Receipt quantities need verification" : "Waiting for ERP data";
    $("header-incident-state").textContent = "SOURCE UNAVAILABLE";
    setBadge($("path-status"), "UNKNOWN", "BLOCKED");
    ["expected-count", "recorded-count", "queue-count"].forEach((id) => { $(id).textContent = "—"; });
    $("platform-title").textContent = "Current evidence unavailable";
    $("platform-correlation-detail").textContent = "Earlier investigation retained · waiting for a fresh ERP read";
    setBadge($("platform-run-state"), "HISTORY", "NEUTRAL");
    setBadge($("platform-diagnosis-status"), "HISTORY", "NEUTRAL");
    $("platform-diagnosis-summary").textContent = "Waiting for current source evidence.";
    if (!state.agentPlatformQuestionBusy && !state.agentPlatformQuestionAttempt
      && state.agentPlatform?.conversation?.length) {
      setBadge($("platform-answer-status"), "HISTORY", "NEUTRAL");
    }
    $("platform-confidence").textContent = "Current quantities unknown";
    $("platform-conclusion").textContent = "FRESH EVIDENCE REQUIRED";
    $("platform-outcome-status").textContent = "HISTORICAL RESULT";
    $("platform-outcome-summary").textContent = "The prior result is retained; the current ERP state could not be verified.";
    $("platform-state-transition").hidden = true;
    $("platform-execution-actions").hidden = true;
    $("platform-diagnose").hidden = true;
    $("business-supplier-status").textContent = "SUPPLIER UNKNOWN";
    $("business-invoice-status").textContent = "INVOICE UNKNOWN";
    $("business-order-status").textContent = "ORDER UNKNOWN";
    document.querySelectorAll(".business-status-chip").forEach((item) => { item.dataset.tone = "alert"; });
    document.querySelectorAll(".business-metric strong").forEach((item) => { item.textContent = "—"; });
    $("business-detail-alert").hidden = true;
    ["trend-time", "business-trend-time"].forEach((id) => { $(id).textContent = "HISTORY"; });
    $("platform-case-tuple").querySelectorAll(".platform-tuple > span").forEach((item) => { item.textContent = "—"; });
    $("platform-reconciled-findings").replaceChildren();
    if (!wasUnavailable) closeDashboardComponentInspector();
  }

  function bodyReady() {
    const ready = state.loaded && state.units.size > 0
      && Boolean(state.agentPlatform || state.agentPlatformError);
    document.body.dataset.workspaceReady = ready ? "true" : "false";
    if (ready) document.body.dataset.bootState = "ready";
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
      const agentPlatformReady = refreshAgentPlatform(true);
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
      const requestedStatus = value(requested && requested.status).toUpperCase();
      const requestedIsRegistered = Boolean(requested) && (
        requestedScenario === "normal"
        || (requestedScenario === "incident" && requestedStatus === "ACTIVE")
        || (requestedScenario === "recovery" && requestedStatus === "READY")
      );
      const requestedIncidentIsExplicit = Boolean(
        requestedIncidentId
        && ["incident", "recovery"].includes(requestedScenario)
      );
      const initialScenario = requestedIncidentIsExplicit
        ? { ...(requested || {}), id: requestedScenario, incident_id: requestedIncidentId }
        : requestedIsRegistered ? requested : normal;
      if (!initialScenario || !initialScenario.incident_id) throw new Error("No healthy synthetic scenario is available");
      const id = value(initialScenario.incident_id);
      state.activeScenario = value(initialScenario.id) || "normal";
      const snapshot = await requestJSON(incidentSnapshotPath(id));
      // Prefer one coherent first paint over briefly showing the legacy
      // compatibility totals. External reads may be slower, so cap the wait
      // and let the independent projection refresh continue in the background.
      await Promise.race([
        agentPlatformReady,
        new Promise((resolve) => window.setTimeout(resolve, 15000)),
      ]);
      if (demoMode === "invalid") {
        document.body.dataset.demoMode = "invalid";
        document.body.dataset.workspaceReady = "false";
        document.body.dataset.bootState = "error";
        $("dashboard-view").hidden = true;
        $("agent-view").hidden = true;
        $("scenario-view").hidden = true;
        showUnavailable("The demo invalid mode has no admissible authoritative lifecycle evidence; operational claims are hidden.", true);
        setConnection("paused", "Invalid evidence; the workspace is unavailable.");
        return;
      }
      applySnapshot(snapshot, snapshot.units, true);
      startEnterpriseEvidenceRefresh();
      startSaasEvidenceRefresh();
      startLiveSourceRefresh();
      showUnavailable("", false);
      setView(state.view);
      if (!smokeCapture) {
        connectEvents();
        startAgentPlatformRefresh();
      }
    } catch (error) {
      state.loaded = false;
      document.body.dataset.bootState = "error";
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
  $("demo-controls-toggle")?.addEventListener("click", () => {
    state.demoControlsOpen = !state.demoControlsOpen;
    $("scenario-view").hidden = !state.demoControlsOpen;
    $("demo-controls-toggle").setAttribute("aria-expanded", String(state.demoControlsOpen));
    if (state.demoControlsOpen) $("demo-controls-close")?.focus();
  });
  $("demo-controls-close")?.addEventListener("click", () => {
    state.demoControlsOpen = false;
    $("scenario-view").hidden = true;
    $("demo-controls-toggle")?.setAttribute("aria-expanded", "false");
    $("demo-controls-toggle")?.focus();
  });
  $("dashboard-open-investigation")?.addEventListener("click", () => setView("agent"));
  $("dashboard-component-inspector-close")?.addEventListener("click", closeDashboardComponentInspector);
  $("dashboard-component-inspector-action")?.addEventListener("click", () => {
    closeDashboardComponentInspector();
    setView("agent");
  });
  $("dashboard-event-feed")?.addEventListener("scroll", (event) => {
    const feed = event.currentTarget;
    state.dashboardEventFollow = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 28;
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
  $("dashboard-inject-incident").addEventListener("click", () => {
    const liveFlow = platformFlowProjection();
    if (liveFlow?.provenance === "live-read") {
      window.open(erpDocumentLink("purchase_order", "purchase-order").url, "_blank", "noopener,noreferrer");
      return;
    }
    selectScenario("incident");
  });
  $("platform-diagnose")?.addEventListener("click", runPlatformDiagnosis);
  $("platform-stop")?.addEventListener("click", () => runPlatformAction("stop"));
  $("platform-automation")?.addEventListener("click", async () => {
    const platform = state.agentPlatform;
    if (!platform?.automation || state.agentPlatformActionBusy) return;
    state.agentPlatformActionBusy = true;
    scheduleRender();
    try {
      const automation = await requestJSON("/api/v1/agent-platform/automation", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: { enabled: !platform.automation.enabled, case_id: platform.case_id, operator_id: "M20 Demo Operator" },
      });
      setAgentPlatformProjection({ ...platform, automation });
      state.agentPlatformError = "";
    } catch (error) {
      state.agentPlatformError = error.message;
    } finally {
      state.agentPlatformActionBusy = false;
      scheduleRender();
    }
  });
  $("platform-approve-execute")?.addEventListener("click", () => runPlatformAction("approve-and-execute", { manager_id: "M20 Demo Manager", idempotency_key: makeKey("m20-platform-execute") }));
  $("platform-reject-plan")?.addEventListener("click", () => runPlatformAction("reject", {
    manager_id: "M20 Demo Manager",
    reason: "Evidence is understood, but the proposed recovery is not authorized for execution.",
  }));
  $("platform-question-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("platform-question");
    const question = input.value;
    input.value = "";
    askPlatformQuestion(question);
  });
  $("platform-answer-text")?.addEventListener("click", (event) => {
    const citation = event.target.closest("[data-evidence-id]");
    if (!citation) return;
    const evidenceId = value(citation.dataset.evidenceId);
    const catalog = state.agentPlatform?.evidence_catalog || {};
    const record = catalog[evidenceId] || {
      evidence_id: evidenceId,
      provider: "Scoped evidence",
      summary: "This citation belongs to the active case/run.",
      revision: "—",
      observed_at: "—",
      provenance: "synthetic-demo-fixture",
    };
    $("platform-evidence-provider").textContent = value(record.provider);
    $("platform-evidence-id").textContent = value(record.evidence_id || evidenceId);
    $("platform-evidence-summary").textContent = value(record.summary);
    $("platform-evidence-revision").textContent = value(record.revision || "—");
    $("platform-evidence-observed").textContent = value(record.observed_at || "—");
    $("platform-evidence-provenance").textContent = value(record.provenance || "—");
    const details = $("platform-evidence-details");
    details.replaceChildren();
    const fields = Array.isArray(record.fields) ? record.fields : [];
    if (fields.length) {
      const fieldList = create("dl", "platform-evidence-field-list");
      fields.forEach((field) => {
        if (!field || typeof field !== "object") return;
        const row = create("div");
        row.append(
          create("dt", null, human(value(field.label))),
          create("dd", null, Array.isArray(field.value) ? field.value.join(" · ") : value(field.value)),
        );
        fieldList.append(row);
      });
      details.append(fieldList);
    }
    const assertions = record.assertions && typeof record.assertions === "object"
      ? record.assertions
      : null;
    const totals = record.totals && typeof record.totals === "object" ? record.totals : null;
    if (assertions || totals) {
      const proof = create("section", "platform-ledger-proof");
      proof.append(create("h3", null, "Ledger assertions"));
      if (totals) {
        proof.append(create("p", "platform-ledger-balance", `Debit ${formatCurrency(totals.debit, "USD")} · Credit ${formatCurrency(totals.credit, "USD")} · Difference ${formatCurrency(Math.abs(number(totals.debit) - number(totals.credit)), "USD")}`));
      }
      if (assertions) {
        const chips = create("div", "platform-ledger-assertions");
        Object.entries(assertions).forEach(([key, passed]) => {
          chips.append(create("span", passed ? "is-pass" : "is-fail", `${passed ? "✓" : "×"} ${human(key)}`));
        });
        proof.append(chips);
      }
      details.append(proof);
    }
    const ledgerTable = (title, rows, columns) => {
      if (!Array.isArray(rows) || !rows.length) return;
      const section = create("section", "platform-ledger-table");
      section.append(create("h3", null, title));
      rows.forEach((row) => {
        const item = create("article");
        columns.forEach(([key, label, format]) => {
          const raw = row && row[key];
          if (raw === undefined || raw === null || raw === "") return;
          const rendered = format === "currency" ? formatCurrency(raw, "USD") : value(raw);
          const field = create("div");
          field.append(create("small", null, label), create("strong", null, rendered));
          item.append(field);
        });
        section.append(item);
      });
      details.append(section);
    };
    ledgerTable("Stock Ledger Entry", record.stock_entries, [
      ["name", "Entry"], ["voucher_no", "Voucher"], ["posting_date", "Posted"],
      ["posting_time", "Time"], ["company", "Company"], ["item_code", "Item"],
      ["warehouse", "Warehouse"], ["actual_qty", "Quantity"],
      ["qty_after_transaction", "Balance"], ["stock_value_difference", "Value", "currency"],
    ]);
    ledgerTable("General Ledger", record.general_ledger_entries, [
      ["name", "Entry"], ["voucher_no", "Voucher"], ["posting_date", "Posted"],
      ["company", "Company"], ["account", "Account"], ["debit", "Debit", "currency"],
      ["credit", "Credit", "currency"], ["party", "Party"],
    ]);
    $("platform-evidence-drawer").hidden = false;
  });
  $("platform-evidence-drawer-close")?.addEventListener("click", () => {
    $("platform-evidence-drawer").hidden = true;
  });
  document.querySelectorAll("[data-dashboard-evidence]").forEach((node) => {
    node.addEventListener("click", () => {
      const latest = state.telemetry.length ? state.telemetry[state.telemetry.length - 1] : null;
      const point = {
        sequence: number(node.dataset.sourceSequence, number(latest && latest.sequence)),
        timestamp: value(latest && (latest.observed_at || latest.captured_at)),
        observed_at: value(latest && (latest.observed_at || latest.captured_at)),
        received_at: value(latest && (latest.received_at || latest.observed_at || latest.captured_at)),
        value: value(node.dataset.sourceStatus || "WAITING"),
        unit: "status",
        metric: `${value(node.querySelector("strong")?.textContent)} source`,
        source: value(node.dataset.sourceDetail),
      };
      state.selectedPoint = point;
      state.selectedPointSequence = pointSequence(point);
      renderFlowSelectionDetail(point);
      renderDiagramCursorLabels(point);
      openDashboardComponentInspector({
        kind: "Evidence source",
        title: value(node.querySelector("strong")?.textContent || node.dataset.dashboardEvidence),
        status: value(node.dataset.sourceStatus || "WAITING"),
        purpose: value(node.dataset.sourceDetail || "Connected source evidence for the active case."),
        external: node.dataset.sourceUrl?.startsWith("https://")
          ? { url: node.dataset.sourceUrl, label: "Open source record" }
          : EXTERNAL_SERVICE_LINKS[value(node.dataset.dashboardEvidence)] || null,
        metrics: [
          ["Status", value(node.dataset.sourceStatus || "WAITING")],
          [node.dataset.sourceRecordId ? "Source record" : "Ledger sequence", value(node.dataset.sourceSequence || "—")],
          ["Case", value(state.agentPlatform?.case_id || state.snapshot?.incident_id || "—")],
        ],
      });
    });
  });
  $("workspace-run-incident-demo")?.addEventListener("click", () => selectScenario("incident"));
  $("agent-normal-run-incident")?.addEventListener("click", () => selectScenario("incident"));
  $("dashboard-replay-investigation").addEventListener("click", replayInvestigation);
  $("agent-replay-investigation").addEventListener("click", replayInvestigation);
  $("prepare-button").addEventListener("click", prepareRecovery);
  $("execute-button").addEventListener("click", executeRecovery);
  ["normal", "incident", "recovery"].forEach((scenario) => {
    const button = $(`scenario-${scenario}`);
    if (button) button.addEventListener("click", () => selectScenario(scenario));
  });
  document.querySelectorAll("[data-counterfactual]").forEach((button) => {
    button.addEventListener("click", () => runCounterfactual(button.dataset.counterfactual));
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
    if (!document.hidden && !smokeCapture && !providerPollingDisabled) {
      void refreshAgentPlatform();
      void refreshEnterpriseEvidence();
      void refreshSaasEvidence();
      void refreshLiveSources();
    }
  });
  document.body.dataset.hidden = String(document.hidden);

  window.addEventListener("resize", () => {
    if (state.view === "agent") scheduleRender();
    window.requestAnimationFrame(renderPlatformInvestigationLinks);
    window.requestAnimationFrame(renderDashboardEvidenceLinks);
  });

  window.addEventListener("beforeunload", () => {
    if (state.source) state.source.close();
    if (state.reconnectTimer != null) window.clearTimeout(state.reconnectTimer);
    if (state.agentPlatformTimer != null) window.clearTimeout(state.agentPlatformTimer);
  });

  bindPlatformCanvasInteractions();
  bindDashboardMetricInspectors();
  bootstrap();
})();
