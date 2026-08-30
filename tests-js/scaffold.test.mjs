import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("package is private during development", async () => {
  const raw = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const pkg = JSON.parse(raw);
  assert.equal(pkg.private, true);
});

test("workspace exposes the real-time views and scenario lab", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  assert.match(html, /data-view="dashboard"/);
  assert.match(html, /data-view="agent"/);
  assert.match(html, /data-view="scenario"/);
  assert.match(html, /id="flow-map"/);
  assert.match(html, /id="incident-empty"/);
  assert.match(html, /class="agent-rail"/);
  assert.match(html, /class="flow-stage"/);
  assert.match(html, /id="dashboard-chart"/);
  assert.match(html, /id="reconciliation-chart"/);
  assert.match(html, /id="dashboard-live-sources"/);
  assert.match(html, /id="workspace-live-sources"/);
  assert.match(html, /id="live-route-risk"/);
  assert.match(html, /id="workspace-live-route-risk"/);
  assert.match(html, /class="dashboard-lower"/);
  assert.match(html, /id="agent-graph"/);
  assert.match(html, /class="source-rail"/);
  assert.match(html, /class="[^"]*operations-map[^"]*"/);
  assert.match(html, /class="workspace-right"/);
  assert.match(html, /id="chat-form"/);
  assert.match(html, /INCIDENT COPILOT/);
  assert.match(html, /data-graph-step="safety"/);
  assert.match(html, /data-graph-step="approval"/);
  assert.match(html, /data-graph-step="execution"/);
  assert.match(html, /data-graph-step="verification"/);
  assert.match(html, /id="case-actions"/);
  assert.match(html, /data-question="Compare the alternative hypotheses/);
  assert.match(html, /id="dashboard-start-investigation"/);
  assert.match(html, /id="agent-start-investigation"/);
  assert.match(html, /id="dashboard-replay-investigation"/);
  assert.match(html, /id="agent-replay-investigation"/);
  assert.match(html, /id="scenario-normal"/);
  assert.match(html, /id="scenario-incident"/);
  assert.match(html, /id="scenario-recovery"/);
  assert.match(html, /id="golden-incident"/);
  assert.match(html, /id="scenario-normal"[^>]*aria-pressed="true"/);
  assert.match(html, /id="scenario-incident"[^>]*disabled/);
  assert.match(html, /id="golden-incident"[^>]*disabled/);
  assert.match(html, /Which evidence proves the queue message is retryable/);
  assert.match(html, /id="observability-link"[^>]*href="\/metrics"[^>]*>Metrics/);
  assert.match(html, /id="main-content"[^>]*tabindex="-1"/);
  assert.match(html, /id="metric-throughput"/);
  assert.match(html, /id="reconciliation-timeline"/);
  assert.match(html, /assets\/phosphor-regular\.css/);
  assert.match(html, /assets\/phosphor-bold\.css/);
  assert.doesNotMatch(html, /incident-hero|truth-strip|section-heading|truth-mode/);
});

test("dashboard has four coordinated diagrams with honest empty states", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  for (const id of [
    "flow-map",
    "dashboard-chart",
    "queue-health-chart",
    "erp-health-chart",
    "invoice-health-chart",
    "external-risk-chart",
  ]) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /class="diagram-deck"[\s\S]*class="diagram-panel diagram-reconciliation"/);
  assert.match(html, /class="diagram-panel diagram-health"[\s\S]*class="small-multiples"/);
  assert.match(html, /class="diagram-panel diagram-risk"[\s\S]*id="external-risk-chart"/);
  assert.match(app, /function renderOperationalCharts\(snapshot\)/);
  assert.match(app, /function selectSharedPoint\(/);
  assert.match(app, /liveSourceEvents/);
  assert.match(app, /live-sources\/events\?after=/);
  assert.match(app, /Insufficient live history/);
  assert.match(app, /function renderDiagramCursorLabels\(/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(css, /transition\s*:\s*all/);
});

test("dashboard density and topology expose bounded, truthful access", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="unit-density-strip"[^>]*role="img"/);
  assert.match(html, /id="unit-anomaly-list"/);
  assert.doesNotMatch(html, /<button[^>]*data-unit-id=/);
  assert.match(app, /function renderUnitDensity\(/);
  assert.match(app, /function renderUnitAnomalies\(/);
  assert.match(app, /data-unit-detail-id/);
  assert.match(app, /receivedMs - observedMs/);
  assert.match(app, /nodeId === "warehouse"[\s\S]*?"dispatched"/);
  assert.match(app, /nodeId === "invoice"[\s\S]*?"expected"/);
  assert.match(css, /\.unit-density-strip\s*\{[^}]*repeat\(50,\s*minmax\(0,\s*1fr\)/s);
  assert.match(css, /\.flow-link-line::after[\s\S]*animation:\s*none\s*!important/);
});

test("dashboard status rail and incident row do not duplicate workspace routing", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(app, /compact \? "div" : "button"/);
  assert.match(html, /role="status"[^>]*data-incident-row="active"/);
  assert.doesNotMatch(html, /data-incident-row="active"[^>]*type="button"/);
  assert.match(css, /\.incident-row-static\s*\{[^}]*cursor:\s*default/s);
  assert.match(app, /\["tab-agent"\]/);
  assert.doesNotMatch(app, /\["tab-agent",\s*"open-agent"/);
});

test("scenario rejection stays visible and names an authoritative recovery path", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(html, /id="scenario-error"[^>]*role="alert"/);
  assert.match(app, /Scenario transition rejected:/);
  assert.match(app, /Current state: \$\{scenarioTruthSummary\(\)\}/);
  assert.match(app, /Select Normal to recover/);
});

test("client binds the API and ordered event ledger rather than timers", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /\/api\/v1\/incidents/);
  assert.match(app, /\/api\/v1\/live-sources/);
  assert.match(app, /new_observation/);
  assert.match(app, /scheduleLiveSourceRefresh/);
  assert.doesNotMatch(app, /api\.weather\.gov|tidesandcurrents\.noaa\.gov/);
  assert.match(app, /EventSource/);
  assert.match(app, /events\?after=/);
  assert.match(app, /replay=1/);
  assert.match(app, /tool\.started/);
  assert.match(app, /evidence\.returned/);
  assert.match(app, /dataset\.unitDetailId/);
  assert.match(app, /\/chat/);
  assert.match(app, /\/decisions/);
  assert.match(app, /data-case-action-id/);
  assert.match(app, /continue_investigation/);
  assert.match(app, /compare_causes/);
  assert.match(app, /show_evidence/);
  assert.match(app, /explain_decision/);
  assert.match(app, /prepare_recovery/);
  assert.match(app, /response\.next_actions/);
  assert.doesNotMatch(app, /setInterval\s*\(/);
  assert.match(app, /state\.goldenRunning && type === "evaluation\.completed"/);
  assert.match(app, /state\.recoveryAvailable/);
  assert.match(app, /ArrowRight: 1/);
  assert.match(app, /card\.setAttribute\("aria-pressed"/);
  assert.match(app, /drawLineChart\(/);
  assert.match(app, /dashboard-chart/);
  assert.match(app, /reconciliation-chart/);
  assert.doesNotMatch(app, /createElementNS/);
});

test("dashboard rebaseline exposes one live incident control and component ports", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="dashboard-inject-incident"[^>]*disabled/);
  assert.match(html, /Live[\s\S]*Inject incident/);
  assert.doesNotMatch(html, /dashboard-open-investigation|Open investigation/);
  assert.match(html, /id="dashboard-component-graph"/);
  assert.match(html, /data-health-node="message-queue"/);
  assert.match(html, /id="dashboard-live-sources"[^>]*route-risk detector/);
  assert.match(app, /\$\("dashboard-inject-incident"\)\.addEventListener\("click", \(\) => selectScenario\("incident"\)\)/);
  assert.match(app, /route-risk-detector/);
  assert.match(app, /flow-node-port/);
  assert.match(app, /flow-particle/);
  assert.match(css, /\.component-graph\s*\{/);
  assert.match(css, /\.flow-node-port\s*\{/);
  assert.match(css, /\.flow-particle\s*\{/);
});

test("client recovers a reset stream from a fresh authoritative cursor", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /stream\.reset/);
  assert.match(app, /async function reconnectStream\(/);
  assert.match(app, /applySnapshot\(snapshot, snapshot\.units \|\| units\.units, true\)/);
  assert.match(app, /source\.onerror = \(\) =>/);
});

test("scenario controls fail closed on an active deep-linked run", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /const selectedScenario = state\.snapshot \? scenarioForSnapshot\(state\.snapshot\) : state\.activeScenario/);
  assert.match(app, /const selected = selectedScenario === scenario/);
  assert.match(app, /selected\s*\|\|\s*unavailableRecovery/);
  assert.match(app, /scenario === "incident" && selectedScenario !== "normal"/);
  assert.match(app, /scenario === "recovery"[\s\S]*state\.activeScenario === "recovery"/);
  assert.match(app, /golden\.disabled = state\.goldenRunning[\s\S]*selectedScenario !== "normal"/);
  assert.match(app, /const normalScenario = state\.activeScenario === "normal"/);
  assert.match(app, /button\.setAttribute\("aria-disabled", String\(button\.disabled\)\)/);
});

test("incident controls follow the authoritative scenario catalog", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /function authoritativeScenarioState\(\)/);
  assert.match(app, /catalog\.incidentTransitionAllowed/);
  assert.match(app, /const incidentAction = hasActiveIncident[\s\S]*"view-completed"/);
  assert.match(app, /dataset\.incidentAction = incidentAction/);
  assert.match(app, /openActiveCatalogIncident/);
  assert.match(app, /Resume active incident/);
  assert.match(app, /View completed investigation/);
  assert.match(html, /data-incident-label>Run incident demo/);
});

test("closed catalog history is never advertised as an active resume", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const start = app.indexOf("  function authoritativeScenarioState() {");
  const end = app.indexOf("  function advisoryTerminallyDegraded", start);
  assert.ok(start >= 0 && end > start, "authoritative catalog projection is present");
  const state = {
    snapshot: {
      incident_id: "closed-run",
      incident: { status: "CLOSED" },
      execution: { verified: true },
    },
    scenarioCatalog: {
      current: "closed-run",
      scenarios: [
        { id: "normal", incident_id: "missing-20-normal", status: "READY" },
        { id: "incident", incident_id: "closed-run", status: "ACTIVE" },
        { id: "recovery", incident_id: "closed-run", status: "READY" },
      ],
    },
  };
  const authoritativeScenarioState = new Function(
    "state",
    "value",
    `${app.slice(start, end)}; return authoritativeScenarioState;`,
  )(
    state,
    (input) => input == null ? "" : String(input),
  );
  const historical = authoritativeScenarioState();
  assert.equal(historical.activeIncident, null);
  assert.equal(historical.historicalIncident.incident_id, "closed-run");
  assert.equal(historical.incidentTransitionAllowed, false);

  state.snapshot = { incident_id: "missing-20-normal", operational_state: "NORMAL" };
  state.scenarioCatalog = {
    current: "missing-20-normal",
    scenarios: [
      { id: "normal", incident_id: "missing-20-normal", status: "READY" },
      { id: "incident", incident_id: "next-run", status: "READY" },
      { id: "recovery", incident_id: "closed-run", status: "READY" },
    ],
  };
  const normal = authoritativeScenarioState();
  assert.equal(normal.activeIncident, null);
  assert.equal(normal.historicalIncident, null);
  assert.equal(normal.incidentTransitionAllowed, true);
});

test("copilot role chat cannot regress handoff, completion, or degraded status", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const helperStart = app.indexOf("  function roleEvents(id) {");
  const helperEnd = app.indexOf("  function agentState(id) {", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, "role status helpers are present");
  const roleId = "retryable_message_investigator";
  const state = {
    snapshot: {},
    events: [
      { event_type: "incident.detected", sequence: 1 },
      { event_type: "agent.handoff", actor: roleId, sequence: 2 },
      { event_type: "copilot.message", actor: "incident-copilot", sequence: 3, payload: { agent_id: roleId } },
    ],
  };
  const helpers = new Function(
    "state",
    "value",
    "eventType",
    "hasIncidentDetected",
    `${app.slice(helperStart, helperEnd)}; return roleStatusFromLedger;`,
  )(
    state,
    (input) => input == null ? "" : String(input),
    (event) => String(event?.event_type || event?.event || ""),
    () => true,
  );
  assert.equal(helpers(roleId), "HANDOFF");

  state.events = [
    { event_type: "incident.detected", sequence: 1 },
    { event_type: "agent.completed", actor: roleId, sequence: 2 },
    { event_type: "copilot.message", actor: "incident-copilot", sequence: 3, payload: { agent_id: roleId } },
  ];
  assert.equal(helpers(roleId), "COMPLETE");

  state.events = [
    { event_type: "incident.detected", sequence: 1 },
    { event_type: "workflow.blocked", actor: roleId, sequence: 2 },
    { event_type: "copilot.message", actor: "incident-copilot", sequence: 3, payload: { agent_id: roleId } },
  ];
  assert.equal(helpers(roleId), "DEGRADED");
});

test("persisted closed verification projects completed stages and non-empty history", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const helperStart = app.indexOf("  function roleEvents(id) {");
  const helperEnd = app.indexOf("  function agentState(id) {", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, "persisted lifecycle helpers are present");
  const state = {
    snapshot: {
      incident: { status: "CLOSED" },
      execution: { verified: true },
      approval: { history: [{ status: "CONSUMED" }] },
      advisory: { investigators: [] },
    },
    events: [{ event_type: "telemetry.observed", sequence: 1106 }],
  };
  const helpers = new Function(
    "state",
    "value",
    "eventType",
    "hasIncidentDetected",
    `${app.slice(helperStart, helperEnd)}; return { persistedLifecycleProjection, roleStatusFromLedger };`,
  )(
    state,
    (input) => input == null ? "" : String(input),
    (event) => String(event?.event_type || event?.event || ""),
    () => false,
  );
  const projection = helpers.persistedLifecycleProjection();
  assert.equal(projection.stagesComplete, true);
  assert.deepEqual(
    ["retryable_message_investigator", "short_shipment_investigator", "duplicate_posting_investigator"]
      .map((id) => helpers.roleStatusFromLedger(id)),
    ["COMPLETE", "COMPLETE", "COMPLETE"],
  );
  assert.match(app, /activityRows\.length\s*\? `\$\{activityRows\.length\} persisted events`/);
  assert.match(app, /: "Current stream"/);
  assert.match(app, /synthesisStatus\(\)[\s\S]*persisted\.stagesComplete/);
});

test("verified closed incident deep links select Recovery in the Scenario Lab", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const start = app.indexOf("  function scenarioForSnapshot(snapshot) {");
  const end = app.indexOf("  function liveSourceStatusClass", start);
  assert.ok(start >= 0 && end > start, "scenarioForSnapshot source is present");
  const snapshot = {
    incident_id: "closed-case",
    operational_state: "INCIDENT",
    incident: { status: "CLOSED" },
    execution: { verified: true },
  };
  const state = {
    snapshot,
    activeScenario: "incident",
    scenarioCatalog: { scenarios: [{ id: "incident", incident_id: "closed-case" }] },
    commandBusy: false,
    connection: "live",
    recoveryAvailable: true,
    goldenRunning: false,
    scenarioError: "",
  };
  const scenarioForSnapshot = new Function(
    "state",
    "window",
    "value",
    `${app.slice(start, end)}; return scenarioForSnapshot;`,
  )(
    state,
    { location: { search: "?scenario=incident&incident_id=closed-case" } },
    (input) => input == null ? "" : String(input),
  );
  assert.equal(scenarioForSnapshot(snapshot), "recovery");
  const elements = new Map();
  const createElement = () => ({
    attributes: {},
    classList: { toggle() {} },
    setAttribute(name, value) { this.attributes[name] = value; },
    disabled: false,
    textContent: "",
  });
  ["normal", "incident", "recovery"].forEach((scenario) => {
    elements.set(`scenario-${scenario}`, createElement());
  });
  elements.set("golden-incident", createElement());
  elements.set("scenario-error", createElement());
  const controlsStart = app.indexOf("  function renderScenarioControls() {");
  const controlsEnd = app.indexOf("  function sparklineValues", controlsStart);
  assert.ok(controlsStart >= 0 && controlsEnd > controlsStart, "renderScenarioControls source is present");
  const renderScenarioControls = new Function(
    "state",
    "scenarioForSnapshot",
    "$",
    "authoritativeScenarioState",
    `${app.slice(controlsStart, controlsEnd)}; return renderScenarioControls;`,
  )(state, scenarioForSnapshot, (id) => elements.get(id), () => ({
    activeIncident: null,
    incidentTransitionAllowed: false,
  }));
  renderScenarioControls();
  assert.match(html, /id="scenario-recovery"/);
  assert.equal(elements.get("scenario-recovery").attributes["aria-pressed"], "true");
  assert.equal(elements.get("scenario-incident").attributes["aria-pressed"], "false");
  assert.match(app, /const selectedScenario = state\.snapshot \? scenarioForSnapshot\(state\.snapshot\) : state\.activeScenario/);
  assert.match(app, /const selected = selectedScenario === scenario/);
  assert.match(app, /button\.setAttribute\("aria-pressed", String\(selected\)\)/);
});

test("refresh uses one authoritative snapshot for units and status", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /applySnapshot\(snapshot, snapshot\.units, false\)/);
  assert.doesNotMatch(app, /const units = await requestJSON\(`\/api\/v1\/incidents\/\$\{encodeURIComponent\(state\.incidentId\)\}\/units`\)/);
});

test("initial UI is quiet and stream loss pauses event-driven motion", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /<ol id="operation-feed"[^>]*><\/ol>/);
  assert.match(app, /No activity yet/);
  assert.match(app, /function pauseStream\(/);
  assert.match(app, /setConnection\("paused"/);
  assert.match(css, /body:not\(\[data-connection="live"\]\)/);
  assert.match(css, /animation-play-state:\s*paused/);
});

test("approval and forward controls fail closed until the live stream and quorum exist", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(app, /value\(approval\.status\) === "GRANTED"/);
  assert.match(app, /const approvedRoles = new Set\(/);
  assert.match(app, /value\(item\.intent_id\) === intent/);
  assert.match(app, /const quorumApproved = .*approvalCount === requiredRoles\.length/);
  assert.match(app, /const hasApproval = quorumApproved/);
  assert.match(app, /state\.commandBusy \|\| !canOperate\(\) \|\| !quorumApproved/);
  assert.match(app, /demoMode === "degraded" \|\| advisoryTerminallyDegraded\(\) \|\| state\.chatPending \|\| state\.replaying \|\| !streamIsLive\(\)/);
  assert.match(app, /button\.disabled = chatDisabled/);
  assert.match(css, /body:not\(\[data-connection="live"\]\) \.unit-density-cell\.is-moving/);
});

test("the live UI preserves truth and accessible targets", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const smoke = await readFile(new URL("../scripts/run_decision_workspace_smoke.py", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /Two-role approval/);
  assert.match(html, /Controlled recovery/);
  assert.doesNotMatch(html, /Chat cannot prepare, approve, or execute/);
  assert.match(app, /function renderUnitDetail\(/);
  assert.match(app, /data-evidence-id/);
  assert.match(app, /Enter a question about the incident/);
  assert.match(app, /window\.scrollTo\(0, 0\)/);
  assert.match(app, /ArrowLeft/);
  assert.match(smoke, /live_copilot_citations/);
  assert.match(smoke, /"copilot_citations": live_copilot_citations/);
  assert.match(app, /state\.replayTargetSequence > 0/);
  assert.match(app, /state\.lastSequence >= state\.replayTargetSequence/);
  assert.doesNotMatch(app, /state\.replaying && hasCompletedInvestigation\(\)/);
  assert.match(smoke, /replay_sequence_start = detected_sequence \+ 1[\s\S]*replay_sequence_end = replay_sequences\[-1\][\s\S]*expected_replay_sequences = list\(\s*range\(replay_sequence_start, replay_sequence_end \+ 1\)\s*\)/);
  assert.match(smoke, /open_replay_api_bytes_unchanged/);
  assert.match(app, /not proven/);
  assert.match(css, /\.unit-density-cell\s*\{[^}]*min-width:\s*2px/s);
  assert.match(app, /function renderScenarioControls\(\)/);
  assert.match(html, /SUPPLY CHAIN FLOW/);
  assert.match(app, /button\.hidden = normalScenario \|\| complete \|\| closed/);
  assert.match(app, /function renderLiveMetrics\(\)/);
  assert.match(app, /row\.hidden = normalScenario/);
  assert.match(app, /telemetry\.observed/);
  assert.match(app, /pulseTelemetry\(\)/);
  assert.match(app, /is-telemetry/);
  assert.match(app, /function reconciliationSeries\(snapshot\)/);
  assert.match(app, /point\.unit_counts\?\.total/);
  assert.match(app, /point\.unit_counts\?\.erp_recorded/);
  assert.match(app, /point\.unit_counts\?\.queue_failed/);
  assert.doesNotMatch(app, /recorded:\s*telemetry\.map\(\(point\) => telemetryRecordCount\(point\)\)/);
  assert.match(app, /visibilitychange/);
  assert.match(app, /document\.body\.dataset\.hidden = String\(document\.hidden\)/);
  assert.match(css, /prefers-reduced-motion: reduce/);
  assert.match(css, /body\[data-hidden="true"\][\s\S]*animation-play-state:\s*paused/);
  assert.doesNotMatch(html, /Synthetic facility simulator|Where the records are now|Agent mission control/);
  assert.match(app, /header-incident-state/);
  assert.doesNotMatch(app, /API · LIVE/);
  assert.doesNotMatch(html, /section-note/);
  assert.doesNotMatch(app, /The diagram moves only when/);
});

test("live source cards preserve disclosure and consume observation pulses once", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const smoke = await readFile(new URL("../scripts/run_decision_workspace_smoke.py", import.meta.url), "utf8");
  assert.match(app, /liveSourceRenderKey/);
  assert.match(app, /liveSourceAnimatedSequences/);
  assert.match(app, /function liveSourceDisclosureState\(host\)/);
  assert.match(app, /details\.open = disclosure\.get\(sourceId\) === true/);
  assert.match(app, /const animationKey = `\$\{sourceId\}:\$\{sequence\}`/);
  assert.match(app, /pulseBySource\.get\(sourceId\)/);
  assert.doesNotMatch(app, /function renderAll\(\) \{\s*renderLiveSources\(\);/);
  assert.doesNotMatch(app, /fetch\(\s*["'`]https?:\/\//);
  assert.match(smoke, /remote_resource_urls/);
  assert.match(smoke, /browser\.network_urls\(\)/);
  assert.match(smoke, /mobile live source cards/);
  assert.match(smoke, /window_size=\(390, 844\)/);
  assert.match(smoke, /live_source_client_width/);
  assert.match(smoke, /live_source_scroll_width/);
});

test("degraded mode removes advisory surfaces and preserves the deterministic gate", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /function applyModeVisibility\(\)/);
  assert.match(app, /\.live-panel/, "live investigation panel is mode-gated");
  assert.match(app, /\.agent-system-panel/, "agent graph and evidence are mode-gated");
  assert.match(app, /\.copilot-panel/, "Copilot is mode-gated");
  assert.match(app, /control\.disabled = degraded/);
  assert.match(app, /demoMode === "degraded"\s*\?\s*"dashboard"/);
  assert.match(app, /const noAction =/);
  assert.match(app, /VERIFIED · CLOSED/);
  assert.match(app, /currentDecision && !noAction/);
  assert.match(app, /executeButton\.hidden = Boolean\(noAction && !prepared && completedIntent\)/);
  assert.match(app, /function startInvestigation\(\)/);
  assert.match(app, /function replayInvestigation\(\)/);
  assert.match(app, /incidentStatus\(\) === "CLOSED"/);
  assert.match(app, /dashboard-start-investigation/);
  assert.match(app, /agent-start-investigation/);
  assert.match(app, /state\.replayTargetSequence/);
  assert.match(app, /MAX_EVENT_HISTORY = 2000/);
  assert.match(app, /state\.events\.length > MAX_EVENT_HISTORY/);
  assert.doesNotMatch(app, /if \(!deferStart/);
});

test("view tabs use a roving tabindex and the flow owns its narrow-screen scroll", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="tab-dashboard"[\s\S]*?tabindex="0"/);
  assert.match(html, /id="tab-agent"[\s\S]*?tabindex="-1"/);
  assert.match(app, /document\.querySelectorAll\("\[data-view\]"\)/);
  assert.match(app, /tab\.tabIndex = selected \? 0 : -1/);
  assert.match(css, /\.dashboard-grid\s*\{[^}]*min-height:/s);
  assert.match(css, /\.workspace-layout\s*\{[^}]*min-height:/s);
  assert.match(css, /\.dashboard-main\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.flow-map\s*\{[^}]*width:\s*100%/s);
  assert.match(css, /\.flow-map\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(css, /overflow-x:\s*auto/);
});

test("optional observability profile stays versioned and outside the native path", async () => {
  const compose = await readFile(new URL("../observability/docker-compose.yml", import.meta.url), "utf8");
  const prometheus = await readFile(new URL("../observability/prometheus.yml", import.meta.url), "utf8");
  const datasource = await readFile(new URL("../observability/grafana/provisioning/datasources/prometheus.yml", import.meta.url), "utf8");
  const provider = await readFile(new URL("../observability/grafana/provisioning/dashboards/provider.yml", import.meta.url), "utf8");
  const dashboard = await readFile(new URL("../observability/grafana/provisioning/dashboards/missing20.json", import.meta.url), "utf8");
  assert.match(compose, /prom\/prometheus:v2\.54\.1/);
  assert.match(compose, /grafana\/grafana:11\.2\.0/);
  assert.match(compose, /127\.0\.0\.1:9090:9090/);
  assert.match(compose, /127\.0\.0\.1:3000:3000/);
  assert.match(compose, /grafana\/provisioning\/datasources:\/etc\/grafana\/provisioning\/datasources/);
  assert.match(compose, /grafana\/provisioning\/dashboards:\/etc\/grafana\/provisioning\/dashboards/);
  assert.match(prometheus, /metrics_path:\s*\/metrics/);
  assert.match(prometheus, /host\.docker\.internal:8765/);
  assert.match(datasource, /type:\s*prometheus/);
  assert.match(provider, /path:\s*\/etc\/grafana\/provisioning\/dashboards/);
  assert.match(dashboard, /missing20_(recorded_units|queue_units|event_sequence)/);
});

test("agent workspace exposes one launch path and a live selected-role context", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.doesNotMatch(html, /dashboard-open-investigation|Open investigation/);
  assert.doesNotMatch(html, />View all agents</);
  assert.doesNotMatch(html, />View all</);
  assert.match(html, /id="agent-role-context"/);
  assert.match(html, /id="agent-role-tools"/);
  assert.match(html, /id="agent-role-evidence"/);
  assert.match(html, /id="orchestrator-node"[^>]*role="button"/);
  assert.match(app, /function selectAgent\(/);
  assert.match(app, /function renderRoleContext\(/);
  assert.match(app, /function drawGraphConnections\(/);
  assert.match(app, /data-graph-source/);
  assert.match(app, /is-selected-route/);
  assert.match(css, /.agent-link.is-event::after/);
  assert.match(css, /.agent-role-context/);
});

test("phase 2 workspace keeps chart focus, trace access, and evidence context honest", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  const smoke = await readFile(new URL("../scripts/run_decision_workspace_smoke.py", import.meta.url), "utf8");
  assert.match(html, /class="workspace-rail-tabs"/);
  assert.match(html, /data-rail-target="agent-role-context"/);
  assert.match(html, /data-rail-target="chat-log"/);
  assert.match(html, /data-rail-target="decision-panel"/);
  assert.match(html, /id="full-operation-feed"/);
  assert.match(html, /id="evidence-status"/);
  assert.match(app, /focusedChartId/);
  assert.match(app, /function restoreChartFocus\(/);
  assert.match(app, /filtered\.slice\(-8\)/);
  assert.match(app, /function stateAwareChatResponse\(/);
  assert.match(app, /agent_id: selectedRoleId/);
  assert.match(app, /function evidencePresentation\(/);
  assert.match(app, /const railTabList = document\.querySelector\("\.workspace-rail-tabs\[role=tablist\]"\)/);
  assert.match(app, /event\.stopPropagation\(\)/);
  assert.match(app, /event\.target\.closest\("\[role=tablist\]"\)/);
  assert.match(app, /chartCursor/);
  assert.match(app, /function syncFocusedChartCursor\(/);
  assert.match(app, /function applyEvidenceFocus\(/);
  assert.match(app, /\.evidence-record\[data-evidence-id\]/);
  assert.match(app, /scrollIntoView\(\{ behavior: "smooth", block: "nearest" \}\)/);
  assert.match(app, /Evidence .* is not admitted/);
  assert.match(css, /\.workspace-rail-tab/);
  assert.match(css, /\.workspace-route-ribbon/);
  assert.match(css, /\.evidence-record-fields/);
  assert.match(css, /\.evidence-record\.is-focused/);
  assert.match(smoke, /Input\.dispatchKeyEvent/);
  assert.match(smoke, /rail_keyboard_focus/);
  assert.match(smoke, /closed_citation_focus/);
  assert.match(smoke, /refresh-/);
  assert.match(smoke, /physical_chart_key_focus/);
});

test("agent graph route contract stays cubic, monotonic, and clear of node interiors", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  const start = app.indexOf("  function graphRouteContract() {");
  const end = app.indexOf("  function graphEventPathIds", start);
  assert.ok(start >= 0 && end > start, "graph route contract is present");
  const helpers = new Function(
    "number",
    `${app.slice(start, end)}; return { graphRouteContract, graphRouteSegments, graphRoutePoints, graphRoutePath };`,
  )((input, fallback) => Number.isFinite(Number(input)) ? Number(input) : fallback);
  const contract = helpers.graphRouteContract();
  assert.deepEqual(
    Object.keys(contract),
    ["incident", "source", "orchestrator", "investigator", "synthesis", "lifecycle", "return"],
  );
  assert.ok(Object.values(contract).every((route) => route.kind === "cubic-bezier"));
  assert.match(app, /function graphCubicPoint\(/);
  assert.match(app, /dataset\.routePoints/);
  assert.match(app, /dataset\.routePath/);
  assert.match(app, /routeContract: { \.\.\.contract\[route\.type\], lane: route\.lane }/);
  assert.match(css, /\.graph-route-path\s*\{/);
  assert.doesNotMatch(css, /\.graph-route-segment/);
  assert.doesNotMatch(css, /\.graph-route-arrow/);

  const metrics = {
    width: 1002,
    height: 680,
    sourceTop: 218,
    sourceBottom: 248,
    cardTop: 264,
    cardBottom: 340,
    lifecycleTop: 512,
    packetLeft: 442,
    packetRight: 560,
    orchestratorLeft: 438,
    orchestratorRight: 564,
    orchestratorTop: 112,
    orchestratorBottom: 190,
    incidentOuterLeft: 434,
    returnOuterLeft: 990,
    returnBottom: 548,
  };
  const rects = [
      ["receipt-retry", 190, 218, 266, 248],
      // The middle compact ERP evidence chip is an explicit obstacle, not a
      // decorative label; every unrelated route must clear this rectangle.
      ["erp-evidence-port", 463, 218, 539, 248],
      ["duplicate-posting", 736, 218, 812, 248],
    ["incident-packet", 442, 48, 560, 86],
    ["orchestrator", 438, 112, 564, 190],
    ["retryable_message_investigator", 110, 264, 345, 340],
    ["short_shipment_investigator", 383, 264, 619, 340],
    ["duplicate_posting_investigator", 657, 264, 892, 340],
    ["synthesis", 435, 394, 567, 452],
    ["safety", 70, 512, 271, 584],
    ["approval", 291, 512, 491, 584],
    ["execution", 511, 512, 711, 584],
    ["verification", 731, 512, 932, 584],
  ].map(([id, left, top, right, bottom]) => ({ id, left, top, right, bottom }));
  const edges = [
    ["incident", "incident-packet", "orchestrator", [501, 86], [501, 112], "incident-axis"],
      ["source", "receipt-retry", "retryable_message_investigator", [228, 248], [176, 264], "evidence-port-left"],
    ["orchestrator", "orchestrator", "retryable_message_investigator", [466, 190], [284, 264], "coord-left"],
    ["investigator", "retryable_message_investigator", "synthesis", [228, 340], [467, 394], "handoff-left"],
      ["source", "shipment-evidence", "short_shipment_investigator", [501, 248], [449, 264], "evidence-port-center"],
      ["orchestrator", "orchestrator", "short_shipment_investigator", [501, 190], [566, 264], "coord-middle"],
    ["investigator", "short_shipment_investigator", "synthesis", [501, 340], [501, 394], "handoff-center"],
      ["source", "duplicate-posting", "duplicate_posting_investigator", [774, 248], [826, 264], "evidence-port-right"],
    ["orchestrator", "orchestrator", "duplicate_posting_investigator", [536, 190], [718, 264], "coord-right"],
    ["investigator", "duplicate_posting_investigator", "synthesis", [774, 340], [535, 394], "handoff-right"],
    ["synthesis", "synthesis", "safety", [501, 452], [170, 512], "lifecycle-entry"],
    ["lifecycle", "safety", "approval", [271, 548], [291, 548], "lifecycle-chain"],
    ["lifecycle", "approval", "execution", [491, 548], [511, 548], "lifecycle-chain"],
    ["lifecycle", "execution", "verification", [711, 548], [731, 548], "lifecycle-chain"],
    ["return", "verification", "incident-packet", [932, 548], [560, 67], "outer-return"],
  ];
  const monotonic = (values) => {
    const increasing = values.every((value, index) => index === 0 || value >= values[index - 1] - .01);
    const decreasing = values.every((value, index) => index === 0 || value <= values[index - 1] + .01);
    return increasing || decreasing;
  };
  const segmentHitsRect = (a, b, rect, pad = 3) => {
    const left = rect.left + pad;
    const right = rect.right - pad;
    const top = rect.top + pad;
    const bottom = rect.bottom - pad;
    const inside = ([x, y]) => x > left && x < right && y > top && y < bottom;
    if (inside(a) || inside(b)) return true;
    const dx = b[0] - a[0];
    const dy = b[1] - a[1];
    let low = 0;
    let high = 1;
    for (const [p, q] of [[-dx, a[0] - left], [dx, right - a[0]], [-dy, a[1] - top], [dy, bottom - a[1]]]) {
      if (Math.abs(p) < 1e-9) {
        if (q < 0) return false;
        continue;
      }
      const ratio = q / p;
      if (p < 0) low = Math.max(low, ratio);
      else high = Math.min(high, ratio);
      if (low > high) return false;
    }
    return high > 0 && low < 1 && low <= high;
  };
  const routeIntersectsRect = (points, rect) => points.slice(1).some((point, index) => segmentHitsRect(points[index], point, rect));
  const segmentIntersection = (a, b, c, d) => {
    const denominator = (a[0] - b[0]) * (c[1] - d[1]) - (a[1] - b[1]) * (c[0] - d[0]);
    if (Math.abs(denominator) < 1e-9) return false;
    const t = ((a[0] - c[0]) * (c[1] - d[1]) - (a[1] - c[1]) * (c[0] - d[0])) / denominator;
    const u = -((a[0] - b[0]) * (a[1] - c[1]) - (a[1] - b[1]) * (a[0] - c[0])) / denominator;
    return t > .001 && t < .999 && u > .001 && u < .999;
  };
  const edgePoints = edges.map(([type, from, to, startPoint, endPoint, lane]) => {
    const route = { type, lane };
    const anchors = { x1: startPoint[0], y1: startPoint[1], x2: endPoint[0], y2: endPoint[1] };
    const segments = helpers.graphRouteSegments(route, anchors, metrics);
    assert.ok(segments.every((segment) => segment.length === 4), `${type} route must be cubic`);
    segments.forEach((segment) => {
      assert.ok(monotonic(segment.map((point) => point[0])), `${type} x direction must not reverse`);
      assert.ok(monotonic(segment.map((point) => point[1])), `${type} y direction must not reverse`);
    });
    const points = helpers.graphRoutePoints(route, anchors, metrics);
    assert.doesNotMatch(helpers.graphRoutePath(route, anchors, metrics), /\bL\b/);
    rects.filter((rect) => ![from, to].includes(rect.id)).forEach((rect) => {
      assert.equal(routeIntersectsRect(points, rect), false, `${type} route enters ${rect.id}`);
    });
    return { id: `${from}->${to}`, points };
  });
  const crossings = [];
  for (let first = 0; first < edgePoints.length; first += 1) {
    for (let second = first + 1; second < edgePoints.length; second += 1) {
      const a = edgePoints[first];
      const b = edgePoints[second];
      let crosses = false;
      for (let i = 1; i < a.points.length && !crosses; i += 1) {
        for (let j = 1; j < b.points.length && !crosses; j += 1) {
          crosses = segmentIntersection(a.points[i - 1], a.points[i], b.points[j - 1], b.points[j]);
        }
      }
      if (crosses) crossings.push([a.id, b.id]);
    }
  }
  assert.deepEqual(crossings, [], "graph routes must not cross outside a named port");
  assert.ok(rects.some((rect) => rect.id === "erp-evidence-port"), "ERP evidence chip is part of collision geometry");
  assert.ok(edgePoints.every(({ points }) => points.length >= 17));
  assert.deepEqual(
    [...new Set(edges.map(([, , , , , lane]) => lane))].sort(),
    ["coord-left", "coord-middle", "coord-right", "evidence-port-center", "evidence-port-left", "evidence-port-right", "handoff-center", "handoff-left", "handoff-right", "incident-axis", "lifecycle-chain", "lifecycle-entry", "outer-return"].sort(),
  );
  assert.equal(rects.some((rect) => rect.id === "operational-flow"), false);
});

test("copilot density exposes concise labels and available actions only", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.doesNotMatch(html, /chat-context-pill/);
  assert.doesNotMatch(html, /case-console-actions-heading|NEXT STEP/);
  assert.equal((html.match(/class="suggestion"/g) || []).length, 2);
  assert.match(app, /const actions = currentCaseActions\(\)\.filter\(\(action\) => action\.id !== "continue_investigation" && action\.enabled\)/);
  assert.match(app, /actionRail\.hidden = actions\.length === 0/);
  assert.match(app, /function evidenceChipLabel\(evidenceId\)/);
  assert.match(app, /setAttribute\("aria-label", `\$\{label\} evidence: \$\{evidenceId\}`\)/);
  assert.match(css, /\.case-action \{[^}]*min-height:\s*28px/s);
  assert.match(css, /\.suggestion \{[^}]*min-height:\s*25px/s);
  assert.match(css, /\.citation \{[^}]*min-height:\s*24px/s);
});

test("recovered and partial snapshots keep the UI state truthful", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /function isClosedOrRecovery\(\)/);
  assert.match(app, /if \(isClosedOrRecovery\(\)\)[\s\S]*label: isVerifiedClosedRecovery\(\) \? "VERIFIED" : "IDLE"/);
  assert.match(app, /function supplyChainStatus\(\)[\s\S]*label: isVerifiedClosedRecovery\(\) \? "RECOVERED" : "IDLE"/);
  assert.match(app, /task\.textContent = advisory\.partial[\s\S]*advisory\.warning \|\| "AI_CITATION_CLOSURE_INCOMPLETE"/);
  assert.match(app, /hypothesis\.textContent = advisory\.partial[\s\S]*\$\{advisory\.selectedHypothesis \|\| "UNKNOWN"\} · PARTIAL/);
  assert.match(app, /evidence\.textContent = advisory\.partial[\s\S]*"AI PARTIAL"/);
  assert.match(app, /setBadge\(badge, advisory\.partial \? "PARTIAL"/);
  assert.match(app, /status\.textContent = isVerifiedClosedRecovery\(\)[\s\S]*"Recovery verified · No further action"/);
  assert.doesNotMatch(app, /advisory\.partial[\s\S]*AI \$\{advisory\.coverage\}/);
});

test("dashboard flow links are continuous between components at every width", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(app, /column\.append\(node\);[\s\S]*column\.append\(link\);[\s\S]*map\.append\(column\);/);
  assert.match(app, /const nodes = \["warehouse", "message-queue", "erp", "invoice"\]/);
  assert.match(app, /const edge = edges\.find\(\(candidate\) => candidate\.from === item\.id && candidate\.to === next\.id\)/);
  assert.match(app, /const gapEdge = edge\.from === "message-queue" && edge\.to === "erp" && queueException > 0/);
  assert.equal((app.match(/const gapEdge = /g) || []).length, 1, "the queue anomaly branch is rendered once");
  assert.match(css, /\.flow-map\s*\{[^}]*overflow:\s*hidden;[^}]*overflow-x:\s*auto/s);
  assert.match(css, /\.flow-column\s*\{\s*display:\s*contents;\s*\}/);
  assert.match(css, /\.flow-node\s*\{[^}]*flex:\s*0 0 146px[^}]*margin:\s*0;/s);
  assert.match(css, /\.flow-link\s*\{[^}]*flex:\s*1 1 0[^}]*min-width:\s*30px/s);
  assert.match(css, /\.flow-node\s*\{\s*flex-basis:\s*103px;\s*min-width:\s*103px;/s);
  assert.match(css, /@media \(min-width: 768px\)[\s\S]*?\.flow-node \{[\s\S]*?flex: 1 1 0;/);
  assert.match(css, /@media \(min-width: 768px\)[\s\S]*?\.flow-link \{[\s\S]*?flex: 0 0 48px;/);
  assert.match(css, /\.flow-node-port-in \{[^}]*left: -5px/);
  assert.match(css, /\.flow-node-port-out \{[^}]*right: -5px/);
  assert.match(css, /\.flow-gap-branch \{/);
});

test("dashboard evidence ports and copy stay sparse and symmetric", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.doesNotMatch(html, /dashboard-open-investigation|Open investigation/);
  assert.doesNotMatch(html, /Select a node or data point to inspect the live flow/);
  assert.match(css, /\.graph-source-group \{[\s\S]*?justify-self: center;/);
  assert.doesNotMatch(css, /\.graph-source-group:nth-child/);
  assert.match(css, /\.agent-nodes \.agent-card:nth-child\(1\) \.graph-port-in \{ left: 28%;/);
  assert.match(css, /\.agent-nodes \.agent-card:nth-child\(2\) \.graph-port-in \{ left: 28%;/);
  assert.match(css, /\.agent-nodes \.agent-card:nth-child\(3\) \.graph-port-in \{ left: 72%;/);
  assert.match(css, /\.flow-node \{[\s\S]*?min-height: 96px;/);
});

test("dashboard agent rail projects the authoritative lifecycle label", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(html, /<aside id="agent-rail" class="agent-rail" aria-label="Agents investigating">/);
  assert.match(html, /<div id="agent-rail-title" class="rail-title">Agents<br \/>investigating<\/div>/);
  assert.match(app, /const agentRail = \$\("agent-rail"\);/);
  assert.match(app, /const agentRailTitle = \$\("agent-rail-title"\);/);
  assert.match(app, /const agentStatus = normalScenario \? "Agent status" : closedRecovery \? "Investigation complete" : "Agents investigating"/);
  assert.match(app, /agentRail\.setAttribute\("aria-label", agentStatus\)/);
  assert.match(app, /agentRailTitle\.textContent = agentStatus/);
  assert.match(app, /agentRailTitle\.setAttribute\("aria-label", agentStatus\)/);
});

test("final truth projection keeps advisory, closed state, and quantities honest", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(app, /Nova advisory: PARTIAL — cited \$\{cited\}\/\$\{total\} admitted records/);
  assert.match(app, /const total = catalog\.length \|\| 5/);
  assert.match(app, /Application validation: \$\{total\}\/\$\{total\} authoritative records/);
  assert.doesNotMatch(app, /const validation = source\.evaluator_source_coverage/);
  assert.match(app, /Recovery authority: deterministic controls only/);
  assert.match(app, /liveTitle\.textContent = normalScenario \? "System status" : closedRecovery \? "Incident history" : "Active incidents"/);
  assert.match(app, /closedRecovery\n      \? "Investigation complete"/);
  assert.match(app, /advisory\.selectedHypothesis\n          : isClosedOrRecovery\(\) \? "UNKNOWN" : "Team synthesis pending"/);
  assert.match(app, /state\.snapshot\?\.unit_counts/);
  assert.match(app, /const dispatched = total/);
  assert.match(app, /kind === "recorded"[\s\S]*point\.unit_counts\?\.erp_recorded/);
  assert.match(app, /metric === "erp"\) valueForMetric = number\(unitCounts\.erp_recorded\)/);
  assert.match(app, /roleQuestions = \{/);
  assert.match(app, /Which admitted evidence proves the receipt message is retryable/);
  assert.match(app, /button\.dataset\.question = roleQuestion\[1\]/);
  assert.match(css, /\.flow-column\s*\{\s*display:\s*contents/);
  assert.match(css, /\.flow-link\s*\{[^}]*flex:\s*1 1 0/);
});
