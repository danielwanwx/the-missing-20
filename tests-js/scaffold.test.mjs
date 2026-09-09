import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("package is private during development", async () => {
  const raw = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const pkg = JSON.parse(raw);
  assert.equal(pkg.private, true);
});

test("workspace exposes two primary views and presenter-only demo controls", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  assert.match(html, /data-view="dashboard"/);
  assert.match(html, /data-view="agent"/);
  assert.doesNotMatch(html, /data-view="scenario"/);
  assert.doesNotMatch(html, /id="tab-scenario"/);
  assert.match(html, /id="demo-controls-toggle"/);
  assert.match(html, /id="demo-controls-close"/);
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

test("flow-first dashboard keeps live truth visible and delegates reasoning", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="dashboard-event-feed"/);
  assert.match(html, /id="dashboard-event-now"/);
  assert.match(html, /id="dashboard-agent-status"/);
  assert.match(html, /id="dashboard-open-investigation"/);
  assert.match(html, /id="dashboard-evidence-map"/);
  assert.match(html, /id="dashboard-evidence-links"/);
  assert.match(app, /function renderDashboardEventRail\(/);
  assert.match(app, /function renderDashboardAgentStatus\(/);
  assert.match(app, /function renderDashboardEvidenceLinks\(/);
  assert.match(app, /legacyDashboard\.hidden = false/);
  assert.match(app, /newest-at-bottom/);
  assert.match(css, /\.dashboard-command-layout\s*\{[^}]*grid-template-columns:/s);
  assert.match(css, /\.dashboard-event-row\.is-new/);
  assert.match(css, /--command-muted:\s*#52616d/);
});

test("first paint gates the unhydrated dashboard behind one truthful loading state", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /data-boot-state="loading"/);
  assert.match(html, /id="workspace-boot"/);
  assert.match(html, /body\[data-boot-state="loading"\][\s\S]*\.topbar/s);
  assert.match(css, /body\[data-boot-state="ready"\][\s\S]*\.workspace-boot/s);
  assert.match(app, /document\.body\.dataset\.bootState = "ready"/);
  assert.match(app, /document\.body\.dataset\.bootState = "error"/);
});

test("dashboard has coordinated operational diagrams with honest empty states", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  for (const id of [
    "flow-map",
    "dashboard-chart",
    "queue-health-chart",
    "erp-health-chart",
    "invoice-health-chart",
    "business-impact-chart",
    "operations-history-chart",
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
  assert.match(app, /nodeId === "warehouse"[\s\S]*?"received"/);
  assert.match(app, /nodeId === "invoice"[\s\S]*?"matched"/);
  assert.match(css, /\.unit-density-strip\s*\{[^}]*repeat\(50,\s*minmax\(0,\s*1fr\)/s);
  assert.match(css, /\.flow-node-count\.is-stage-updated[\s\S]*animation:\s*none/);
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
  assert.equal((app.match(/createElementNS/g) || []).length, 3, "SVG is limited to topology paths and the no-canvas chart fallback");
  assert.match(app, /createElementNS\("http:" \+ "\/\/www\.w3\.org\/2000\/svg", "path"\)/);
});

test("dashboard rebaseline exposes one live incident control and stage projections", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="dashboard-inject-incident"[^>]*disabled/);
  assert.match(html, /Live[\s\S]*Inject incident/);
  assert.equal((html.match(/id="dashboard-open-investigation"/g) || []).length, 1);
  assert.match(html, /id="dashboard-component-graph"/);
  assert.match(html, /data-health-node="message-queue"/);
  assert.match(html, /id="dashboard-live-sources"[^>]*route-risk detector/);
  assert.match(app, /\$\("dashboard-inject-incident"\)\.addEventListener\("click", \(\) => \{/);
  assert.match(app, /liveFlow\?\.provenance === "live-read"[\s\S]*window\.open\(erpDocumentLink\("purchase_order", "purchase-order"\)\.url/);
  assert.match(app, /selectScenario\("incident"\)/);
  assert.match(app, /route-risk-detector/);
  assert.match(app, /function latestStageProjection\(snapshot\)/);
  assert.match(app, /flow-node-exception/);
  assert.doesNotMatch(app, /create\("span", "flow-node-port/);
  assert.doesNotMatch(app, /create\("span", "flow-particle/);
  assert.match(css, /\.component-graph\s*\{/);
  assert.match(css, /\.flow-node\.is-stage-updated/);
  assert.match(css, /\.flow-node-exception/);
});

test("client recovers a reset stream from a fresh authoritative cursor", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.equal((app.match(/new EventSource/g) || []).length, 1, "each tab owns only one permanent SSE connection");
  assert.doesNotMatch(app, /new EventSource\("\/api\/v1\/agent-platform\/events/);
  assert.match(app, /stream\.reset/);
  assert.match(app, /async function reconnectStream\(/);
  assert.match(app, /function incidentSnapshotPath\(incidentId\)/);
  assert.match(app, /projection=browser/);
  assert.match(app, /applySnapshot\(snapshot, snapshot\.units, true\)/);
  assert.match(app, /source\.onerror = \(\) =>/);
});

test("scenario controls fail closed on an explicit deep-linked run", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /const requestedIncidentIsExplicit = Boolean\(/);
  assert.match(app, /\["incident", "recovery"\]\.includes\(requestedScenario\)/);
  assert.match(app, /requestedIncidentIsExplicit[\s\S]*incident_id: requestedIncidentId/);
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

test("dashboard motion is labeled as source-triggered rather than a fake timer", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /external\.source\.changed/);
  assert.match(app, /external\.source\.changed/);
  assert.match(app, /Source-triggered observation/);
  assert.doesNotMatch(app, /Flow batch/);
  assert.doesNotMatch(html, /new \/ 60s/i);
  assert.match(html, /changed records/);
});

test("live ERP projection owns KPIs, charts, and the external trigger path", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /platform\.case_projection/);
  assert.match(app, /const liveAuthority = value\(caseProjection\?\.provenance\).*=== "live-read"/);
  assert.match(app, /if \(!liveAuthority && !syntheticAuthority\) return null/);
  assert.match(app, /platformMetricEvents[\s\S]*latestPlatformMetric\.change_count/);
  assert.match(app, /authoritative: platform\.provenance === "live-read"/);
  assert.match(app, /scheduleAgentPlatformProjectionRefresh\(\)/);
  assert.match(app, /Open ERPNext; this dashboard advances only after the external records change/);
  assert.match(app, /control\.dataset\.sourceAuthority = liveSourceMode \? "external" : "scenario"/);
  assert.match(app, /liveAuthority && value\(raw\.provenance\).*includes\("synthetic"\).*return null/);
  assert.match(app, /if \(section\) section\.hidden = !operations/);
  assert.match(app, /if \(historyPanel\) historyPanel\.hidden = !operations/);
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

test("replay dashboard charts append the authoritative verified close", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const helperStart = app.indexOf("  function verifiedClosedSnapshot(snapshot) {");
  const helperEnd = app.indexOf("  function reconciliationPoints(snapshot)", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, "chart reconciliation helpers are present");
  const state = {
    replaying: false,
    telemetry: [
      {
        sequence: 120,
        observed_at: "2026-08-28T00:01:00.000Z",
        unit_counts: { total: 100, erp_recorded: 80, queue_failed: 20 },
        queue_depth: 20,
      },
    ],
  };
  const snapshot = {
    projection_sequence: 140,
    incident: { status: "CLOSED" },
    execution: { verified: true },
    unit_counts: { total: 100, erp_recorded: 100, queue_failed: 0 },
    telemetry: { latest: { observed_at: "2026-08-28T00:02:00.000Z" } },
  };
  const helpers = new Function(
    "state",
    "value",
    "number",
    `${app.slice(helperStart, helperEnd)}; return { chartTelemetryPoints, reconciliationSeries };`,
  )(
    state,
    (input) => input == null ? "" : String(input),
    (input, fallback = 0) => Number.isFinite(Number(input)) ? Number(input) : fallback,
  );
  const series = helpers.reconciliationSeries(snapshot);
  assert.deepEqual(series.expected, [100, 100]);
  assert.deepEqual(series.recorded, [80, 100]);
  assert.deepEqual(series.gap, [20, 0]);
  assert.equal(state.telemetry.length, 1, "historical telemetry remains unchanged");
  state.replaying = true;
  assert.equal(helpers.chartTelemetryPoints(snapshot).length, 1, "replay does not preempt history");
});

test("live stage chart stays scoped to the current flow run", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const helperStart = app.indexOf("  function verifiedClosedSnapshot(snapshot) {");
  const helperEnd = app.indexOf("  function telemetryPoints(snapshot, metric)", helperStart);
  assert.ok(helperStart >= 0 && helperEnd > helperStart, "stage chart helpers are present");
  const state = {
    replaying: false,
    transitionBaseline: null,
    telemetry: [
      {
        sequence: 1,
        flow_run_id: "flow-1",
        stage_counts: { warehouse: 100, message_queue: 100, erp: 100, invoice: 100 },
        unit_counts: { total: 100, erp_recorded: 100, queue_failed: 0 },
      },
      {
        sequence: 2,
        flow_run_id: "flow-2",
        stage_counts: { warehouse: 20, message_queue: 0, erp: 0, invoice: 0 },
        unit_counts: { total: 100, erp_recorded: 100, queue_failed: 0 },
      },
      {
        sequence: 3,
        flow_run_id: "flow-2",
        stage_counts: { warehouse: 40, message_queue: 20, erp: 0, invoice: 0 },
        unit_counts: { total: 100, erp_recorded: 100, queue_failed: 0 },
      },
    ],
  };
  const helpers = new Function(
    "state",
    "value",
    "number",
    `${app.slice(helperStart, helperEnd)}; return { reconciliationSeries, reconciliationPoints };`,
  )(
    state,
    (input) => input == null ? "" : String(input),
    (input, fallback = 0) => Number.isFinite(Number(input)) ? Number(input) : fallback,
  );
  const snapshot = { incident: { status: "OPEN" }, execution: { verified: false }, unit_counts: {} };
  assert.deepEqual(helpers.reconciliationSeries(snapshot).expected, [20, 40]);
  assert.deepEqual(helpers.reconciliationPoints(snapshot).map((point) => point.expected), [20, 40]);
  assert.match(app, /function renderSvgLineChart\(canvas, series, tones, options = \{\}\)/);
  assert.match(app, /if \(!surface\) return renderSvgLineChart\(canvas, series, tones, options\)/);
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
  assert.match(html, /Manager approval/);
  assert.match(html, /Controlled recovery/);
  assert.match(app, /Approve as \$\{definition\.name\}/);
  assert.match(app, /recordManagerApproval/);
  assert.match(app, /MANAGER_ATTESTATIONS/);
  assert.match(app, /activityDrawer\.open = true/);
  assert.match(app, /isLatest \? " is-new"/);
  assert.match(css, /@keyframes activity-enter/);
  assert.match(smoke, /data-approval-principal="manager"/);
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
  assert.match(app, /latestStageProjection/);
  assert.match(app, /function reconciliationSeries\(snapshot\)/);
  assert.match(app, /point\.stage_counts\?\.warehouse/);
  assert.match(app, /point\.stage_counts\?\.erp/);
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

test("browser smoke waits for settled Copilot turns before chaining chat", async () => {
  const smoke = await readFile(new URL("../scripts/run_decision_workspace_smoke.py", import.meta.url), "utf8");
  assert.match(smoke, /chat-message\.chat-pending/);
  assert.match(smoke, /COPILOT_IDLE/);
  assert.match(smoke, /Case Console free-form chat submit/);
  assert.match(smoke, /copilot_before = browser\.evaluate/);
  assert.match(smoke, /_copilot_response_expression/);
  assert.match(smoke, /RETRYABLE_MESSAGE/);
  assert.match(smoke, /failed-message/);
  assert.match(smoke, /erp-receipt/);
  assert.match(smoke, /warehouse/);
  assert.match(smoke, /getAttribute\('aria-label'\)/);
  assert.doesNotMatch(smoke, /textContent \|\| ''\)\.trim\(\)[\s\S]*=== id/);
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
  assert.equal((html.match(/id="dashboard-open-investigation"/g) || []).length, 1);
  assert.doesNotMatch(html, />View all agents</);
  assert.doesNotMatch(html, />View all</);
  assert.match(html, /id="agent-role-context"/);
  assert.match(html, /id="agent-role-tools"/);
  assert.match(html, /id="agent-role-evidence"/);
  assert.match(html, /id="orchestrator-node"[^>]*role="button"/);
  assert.match(app, /function selectAgent\(/);
  assert.match(app, /function renderRoleContext\(/);
  assert.match(app, /function drawGraphConnections\(/);
  assert.match(app, /data-supply-node/);
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

test("agent graph route contract stays contextual, centered, and clear of node interiors", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
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
    ["supply", "boundary", "incident", "source", "orchestrator", "investigator", "synthesis", "lifecycle", "return"],
  );
  assert.ok(Object.values(contract).every((route) => route.kind === "cubic-bezier"));
  assert.match(app, /function graphCubicPoint\(/);
  assert.match(app, /dataset\.routePoints/);
  assert.match(app, /dataset\.routePath/);
  assert.match(app, /routeContract: { \.\.\.contract\[route\.type\], lane: route\.lane }/);
  assert.match(css, /\.graph-route-path\s*\{/);
  assert.doesNotMatch(css, /\.graph-route-segment/);
  assert.doesNotMatch(css, /\.graph-route-arrow/);
  assert.match(css, /\.operations-map\.agent-system-panel \.graph-port\s*\{[\s\S]*?width:\s*5px;[\s\S]*?min-width:\s*5px;[\s\S]*?height:\s*5px;[\s\S]*?background:\s*rgba\(92, 222, 234, \.86\)/);
  assert.match(css, /\.graph-supply-node \.graph-port-flow-out\s*\{[\s\S]*?right:\s*-5px;/);
  assert.match(css, /\.workspace-timeline\s*\{\s*position:\s*relative;\s*\}/);
  assert.match(css, /\.orchestrator-node \.graph-port-in\s*\{[\s\S]*?left:\s*50%;/);
  assert.match(css, /\.synthesis-node \.graph-port-in\s*\{[\s\S]*?left:\s*50%;/);
  assert.match(css, /\.graph-step\[data-graph-node="safety"\] \.graph-port-in\s*\{[\s\S]*?left:\s*50%;/);
  assert.match(html, /DETERMINISTIC SUPPLY CHAIN/);
  assert.doesNotMatch(html, /READ-ONLY INVESTIGATION BOUNDARY|AGENT INVESTIGATION|DETERMINISTIC CONTROL/);
  assert.match(html, /<strong>Evidence API<\/strong>/);
  assert.doesNotMatch(html, /Authoritative synthetic state|Advisory only|Policy · human quorum · bounded effects|<small>READ ONLY<\/small>/);
  assert.doesNotMatch(html, /graph-port-coordination-(left|middle|right)/);
  assert.doesNotMatch(html, /graph-port-synthesis-(left|middle|right)/);

  const metrics = {
    width: 1002,
    height: 680,
    sourceTop: 64,
    sourceBottom: 106,
    cardTop: 290,
    cardBottom: 366,
    lifecycleTop: 542,
    packetLeft: 551,
    packetRight: 671,
    orchestratorLeft: 451,
    orchestratorRight: 551,
    orchestratorTop: 158,
    orchestratorBottom: 236,
    incidentOuterLeft: 543,
    returnOuterLeft: 990,
    returnBottom: 578,
  };
  const rects = [
    ["warehouse", 80, 64, 265, 106],
    ["queue", 299, 64, 484, 106],
    ["erp", 518, 64, 703, 106],
    ["invoice", 737, 64, 922, 106],
    ["incident-packet", 550, 122, 670, 160],
    ["evidence-api", 582, 178, 640, 216],
    ["orchestrator", 451, 158, 551, 236],
    ["retryable_message_investigator", 110, 290, 345, 366],
    ["short_shipment_investigator", 383, 290, 619, 366],
    ["duplicate_posting_investigator", 657, 290, 892, 366],
    ["synthesis", 435, 412, 567, 470],
    ["safety", 70, 542, 271, 614],
    ["approval", 291, 542, 491, 614],
    ["execution", 511, 542, 711, 614],
    ["verification", 731, 542, 932, 614],
  ].map(([id, left, top, right, bottom]) => ({ id, left, top, right, bottom }));
  const edges = [
    ["supply", "warehouse", "queue", [265, 85], [299, 85], "supply-chain"],
    ["supply", "queue", "erp", [484, 85], [518, 85], "supply-chain"],
    ["supply", "erp", "invoice", [703, 85], [737, 85], "supply-chain"],
    ["boundary", "erp", "incident-packet", [610, 106], [610, 122], "supply-incident"],
    ["boundary", "incident-packet", "evidence-api", [610, 160], [610, 178], "incident-evidence"],
    ["boundary", "evidence-api", "orchestrator", [581, 197], [551, 197], "evidence-orchestrator"],
    ["orchestrator", "orchestrator", "retryable_message_investigator", [501, 236], [228, 290], "coord-left"],
    ["investigator", "retryable_message_investigator", "synthesis", [228, 366], [501, 412], "handoff-left"],
    ["orchestrator", "orchestrator", "short_shipment_investigator", [501, 236], [501, 290], "coord-middle"],
    ["investigator", "short_shipment_investigator", "synthesis", [501, 366], [501, 412], "handoff-middle"],
    ["orchestrator", "orchestrator", "duplicate_posting_investigator", [501, 236], [774, 290], "coord-right"],
    ["investigator", "duplicate_posting_investigator", "synthesis", [774, 366], [501, 412], "handoff-right"],
    ["synthesis", "synthesis", "safety", [501, 470], [170, 542], "lifecycle-entry"],
    ["lifecycle", "safety", "approval", [271, 578], [291, 578], "lifecycle-chain"],
    ["lifecycle", "approval", "execution", [491, 578], [511, 578], "lifecycle-chain"],
    ["lifecycle", "execution", "verification", [711, 578], [731, 578], "lifecycle-chain"],
    ["return", "verification", "invoice", [932, 578], [830, 64], "outer-return"],
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
    if (type !== "lifecycle") segments.forEach((segment) => {
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
  assert.ok(rects.some((rect) => rect.id === "evidence-api"), "read-only evidence boundary is part of collision geometry");
  assert.ok(edgePoints.every(({ points }) => points.length >= 17));
  assert.deepEqual(
    [...new Set(edges.map(([, , , , , lane]) => lane))].sort(),
    ["coord-left", "coord-middle", "coord-right", "evidence-orchestrator", "handoff-left", "handoff-middle", "handoff-right", "incident-evidence", "lifecycle-chain", "lifecycle-entry", "outer-return", "supply-chain", "supply-incident"].sort(),
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

test("case console presents one judge-readable evidence-to-outcome workflow", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /class="platform-command-canvas"/);
  assert.match(html, />Inventory</);
  assert.match(html, />Investigation</);
  assert.match(html, />Manager decision</);
  assert.match(html, /id="platform-source-receipts"/);
  assert.match(html, /id="platform-hypotheses"/);
  assert.match(html, /id="platform-runtime-trace"/);
  assert.match(html, />SDK flight recorder</);
  assert.match(html, /id="platform-outcome"/);
  assert.match(html, /Inspect Resolution Packet/);
  assert.doesNotMatch(html, /80 AVAILABLE|100 VERIFIED/);
  assert.doesNotMatch(html, /id="platform-constellation"|id="platform-plan"/);
  assert.match(app, /const selectedTools = new Set\(Array\.isArray\(strands\.tool_calls\)/);
  assert.match(app, /strandsStatus === "COMPLETE"\s*\? \[\.\.\.selectedTools\]/);
  assert.match(app, /const toolState = strandsStatus === "COMPLETE"\s*\? "READ"/);
  assert.doesNotMatch(app, /selectedTools\.has\(toolName\) \? "READ" : "NOT NEEDED"/);
  assert.match(app, /Array\.isArray\(strands\.runtime_events\)/);
  assert.match(app, /rawName === "LiveAdvisoryResult"\s*\? "Typed result"/);
  assert.match(app, /const verifiedPostState = executionStatus === "VERIFIED"/);
  assert.match(app, /\["Delivery note", packetEffects\.delivery_note\]/);
  assert.match(app, /\["Sales invoice", packetEffects\.sales_invoice\]/);
  assert.match(app, /findings\.join_keys && findings\.join_keys\.integration_business_key/);
  assert.match(app, /tuple\.supplier_lot/);
  assert.match(app, /\$\{supplierLot\} · CLEARED/);
  assert.match(app, /transition\.hidden = executionStatus !== "VERIFIED"/);
  assert.match(app, /AGENT_UNAVAILABLE: "Retry the real Strands investigation — no plan released"/);
  assert.match(app, /PHYSICAL_SHORTAGE_CONFIRMED: "Escalate 20-unit supplier shortage — preserve hold"/);
  assert.match(app, /reviewAction === "RETRY_INVESTIGATION"/);
  assert.match(app, /reviewAction === "AUTHORIZE_DIAGNOSIS"/);
  assert.match(app, /operator_id: "M20 Demo Operator"/);
  assert.match(app, /makeKey\("m20-platform-execute"\)/);
  assert.doesNotMatch(app, /void runPlatformDiagnosis\(\)/);
  assert.match(app, /executionStatus\)\s*\? \[/);
  assert.doesNotMatch(html, />HUMAN START REQUIRED</);
  assert.match(app, /platform\.latest_sequence/);
  assert.match(css, /\.platform-command-canvas \{[^}]*grid-template-columns:/s);
  assert.match(css, /\.platform-outcome-rail\[data-status="verified"\]/);
  assert.match(css, /\.platform-runtime-span\.is-model/);
  assert.match(css, /\.platform-runtime-span\.is-tool/);
});

test("case console is a borderless, movable command canvas with atomic live nodes", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /class="platform-command-toolbar"/);
  assert.match(html, /id="platform-arrange-mode"/);
  assert.match(html, /id="platform-reset-layout"/);
  assert.match(html, /data-canvas-module="signals"/);
  assert.match(html, /data-canvas-module="investigation"/);
  assert.match(html, /data-canvas-module="agent-console"/);
  assert.match(html, /data-canvas-module="conversation"/);
  assert.match(html, />Ask the agent</);
  assert.match(html, /id="platform-investigation-links"/);
  assert.match(html, /data-investigation-node="erpnext"/);
  assert.match(html, /data-investigation-node="airtable"/);
  assert.match(html, /data-investigation-node="celigo"/);
  assert.match(html, /data-investigation-node="jira"/);
  assert.match(html, /data-investigation-node="slack"/);
  assert.match(html, /data-investigation-node="agent"/);
  assert.match(html, /data-investigation-node="manager"/);
  assert.match(html, /id="platform-node-popover"/);
  assert.doesNotMatch(html, /class="platform-section-divider"/);
  assert.match(css, /@font-face\s*\{[^}]*font-family:\s*"Geist"/s);
  assert.match(css, /@font-face\s*\{[^}]*font-family:\s*"Geist Mono"/s);
  assert.match(css, /\.platform-canvas-module\s*\{[^}]*border:\s*0;/s);
  assert.match(css, /\.platform-investigation-link\s*\{[^}]*stroke-width:\s*1\.15;/s);
  assert.match(css, /body\[data-agent-platform="ready"\]\s*\{[^}]*--ink:\s*#17212b;/s);
  assert.match(css, /data-investigation-node="erpnext"[^}]*background:\s*#008ca0;/s);
  assert.match(css, /data-investigation-node="airtable"[^}]*background:\s*#256cd3;/s);
  assert.match(css, /data-investigation-node="celigo"[^}]*background:\s*#7550bd;/s);
  assert.match(css, /data-investigation-node="jira"[^}]*background:\s*#d76416;/s);
  assert.match(css, /data-investigation-node="slack"[^}]*background:\s*#719000;/s);
  assert.match(app, /const PLATFORM_LAYOUT_KEY = "missing20-command-canvas-v1"/);
  assert.match(app, /function setPlatformArrangeMode\(/);
  assert.match(app, /function bindPlatformCanvasInteractions\(/);
  assert.match(app, /function renderPlatformInvestigationLinks\(/);
  assert.match(app, /function platformLinkPath\(/);
  assert.match(app, /function platformNodeAnchor\(/);
  assert.match(app, /localStorage\.setItem\(PLATFORM_LAYOUT_KEY/);
  assert.doesNotMatch(app, /setInterval\([^)]*platform/i);
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

test("dashboard flow nodes are independent live instruments without throughput lines", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(app, /const nodes = \["warehouse", "message-queue", "erp", "invoice"\]/);
  const renderStart = app.indexOf("function renderFlow()");
  const renderEnd = app.indexOf("function selectUnit", renderStart);
  const renderFlow = app.slice(renderStart, renderEnd);
  assert.match(renderFlow, /latestStageProjection\(snapshot\)/);
  assert.match(renderFlow, /dataset\.stageCount/);
  assert.match(renderFlow, /flow-node-exception/);
  assert.doesNotMatch(renderFlow, /flow-link/);
  assert.doesNotMatch(renderFlow, /flow-node-port/);
  assert.match(css, /\.flow-map\s*\{[^}]*overflow:\s*hidden;[^}]*overflow-x:\s*auto/s);
  assert.match(css, /body\[data-agent-platform="ready"\] \.flow-map\s*\{[^}]*gap:/s);
  assert.match(css, /\.flow-node\s*\{\s*flex-basis:\s*103px;\s*min-width:\s*103px;/s);
  assert.match(css, /@media \(min-width: 768px\)[\s\S]*?\.flow-node \{[\s\S]*?flex: 1 1 0;/);
  assert.match(css, /\.flow-node\.is-stage-updated/);
  assert.match(css, /\.flow-node-count\.is-stage-updated/);
  assert.match(css, /font-variant-numeric:\s*tabular-nums/);
});

test("dashboard evidence ports and copy stay sparse and symmetric", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="dashboard-open-investigation"/);
  assert.equal((html.match(/id="dashboard-open-investigation"/g) || []).length, 1);
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
  assert.match(app, /metric === "erp"\) valueForMetric = number\(point\.stage_counts\?\.erp/);
  assert.match(app, /roleQuestions = \{/);
  assert.match(app, /Which admitted evidence proves the receipt message is retryable/);
  assert.match(app, /button\.dataset\.question = roleQuestion\[1\]/);
  assert.match(css, /\.flow-column\s*\{\s*display:\s*contents/);
  assert.match(css, /body\[data-agent-platform="ready"\] \.flow-link \{ display:\s*none;/);
});

test("live console reveals only reached states and refreshes metrics from SSE", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="flow-window-count">—<\/b><small>changed records<\/small>/);
  assert.match(html, /id="flow-ledger-sequence">—<\/b><small>ledger seq<\/small>/);
  assert.doesNotMatch(html, /Duplicate posting prevention/);
  assert.doesNotMatch(html, /ERP sync delay/);
  assert.match(html, /id="synthesis-status"[^>]*hidden/);
  assert.equal((html.match(/data-graph-step-status hidden/g) || []).length, 4);
  assert.match(html, /class="graph-loop-label" hidden/);
  assert.match(app, /scheduleAgentPlatformProjectionRefresh\(\)/);
  assert.match(app, /statusNode\.hidden = !reached/);
  assert.match(app, /loopVerified\.hidden = !lifecycleDone\.verification/);
  assert.match(app, /telemetryRecordCount\(latestTelemetry\)/);
  assert.match(css, /@keyframes live-metric-arrival/);
  assert.match(app, /const liveAuthority = hasLiveSourceAuthority\(\)/);
  assert.match(app, /liveAuthority\s*\? platformEvents\s*:\s*\[\.\.\.ledgerEvents, \.\.\.platformEvents, \.\.\.erpReadEvents, \.\.\.saasReadEvents\]/);
  assert.match(app, /const authoritativeSequence = platform\?\.latestSequence/);
  assert.match(app, /const visibleEventTotal = liveFlow\s*\? platformActivity\.length/);
  assert.match(app, /const platformMetrics = liveFlow && Array\.isArray\(state\.agentPlatform\?\.activity\)/);
  assert.match(app, /inventoryReconciled && liveFlow\.invoiceHeld[\s\S]*"Invoice payment hold"/);
  assert.match(app, /"Inventory reconciled · invoice payment hold awaits agent diagnosis"/);
  assert.doesNotMatch(app, /inventory reconciliation \$\{\["ACKNOWLEDGED", "VERIFIED"\]/);
  assert.match(app, /consoleNode\.dataset\.phase =/);
  assert.match(css, /\.agent-platform-console\[data-phase="idle"\][\s\S]*\.platform-chat-card/s);
  assert.match(html, /HISTORICAL OPERATING WINDOW/);
  assert.doesNotMatch(html, /90-DAY OPERATING WINDOW[\s\S]{0,220}>LIVE</);
});

test("manager can reject a prepared plan without executing it", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(html, /id="platform-reject-plan"/);
  assert.match(app, /runPlatformAction\("reject"/);
  assert.match(app, /\/api\/v1\/agent-platform\/\$\{path\}/);
  assert.doesNotMatch(app, /case_matrix_size, 14/);
  assert.match(html, /<dt>Scenario set<\/dt><dd id="platform-metric-cases">—<\/dd>/);
});

test("dashboard projects source-derived operating economics and event-time exposure", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");

  for (const id of [
    "business-availability",
    "business-reconciliation",
    "business-working-capital",
    "business-invoice-hold",
    "business-unit-cost",
    "business-price-variance",
    "business-quality-hold",
    "business-value-protected",
    "business-impact-chart",
  ]) assert.match(html, new RegExp(`id="${id}"`));

  assert.match(app, /state\.agentPlatform\?\.business_impact/);
  assert.match(app, /business_metrics:\s*\{/);
  assert.match(app, /source: "agent-platform-event-ledger"/);
  assert.match(app, /function renderBusinessImpact\(\)/);
  assert.match(app, /function drawBusinessImpactChart\(snapshot\)/);
  assert.match(css, /\.business-metric-grid/);
  assert.match(css, /grid-area: impact/);
  assert.doesNotMatch(html, /\$1,000|\$5,000|80\.0%/);
});

test("dashboard exposes connected plant risk from backend history instead of static report values", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");

  for (const id of [
    "operations-risk-score",
    "operations-oee",
    "operations-schedule",
    "operations-units-risk",
    "operations-revenue-risk",
    "operations-margin-risk",
    "operations-days-supply",
    "operations-inbound-otif",
    "operations-supplier-ppm",
    "operations-history-chart",
  ]) assert.match(html, new RegExp(`id="${id}"`));

  assert.match(app, /state\.agentPlatform\?\.connected_operations/);
  assert.match(app, /function renderConnectedOperations\(\)/);
  assert.match(app, /function drawConnectedOperationsChart\(\)/);
  assert.match(app, /source: "synthetic-mes-demand-ledger"/);
  assert.match(css, /\.operations-risk-signal/);
  assert.match(css, /\.operations-metric-grid/);
  assert.doesNotMatch(html, /900,000|130,000|83\.3%|94\.4%/);
});

test("dashboard and investigation components expose live parameters on click without framework tag noise", async () => {
  const [html, app, css] = await Promise.all([
    readFile(new URL("../workspace/index.html", import.meta.url), "utf8"),
    readFile(new URL("../workspace/app.js", import.meta.url), "utf8"),
    readFile(new URL("../workspace/style.css", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(html, /Adaptive reads|Typed output|Hook telemetry|Policy gate|Verified effects/);
  assert.match(html, /id="platform-node-popover-metrics"/);
  assert.match(html, /id="platform-evidence-details"/);
  assert.match(html, /id="platform-node-popover-action"/);
  assert.match(html, /id="platform-node-popover-external"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.match(html, /id="dashboard-component-inspector"/);
  assert.match(html, /id="dashboard-component-inspector-metrics"/);
  assert.match(html, /id="dashboard-component-inspector-external"[^>]*target="_blank"[^>]*rel="noopener noreferrer"/);
  assert.match(app, /const EXTERNAL_SERVICE_LINKS = Object\.freeze/);
  for (const host of ["missing20.v.frappe.cloud", "airtable.com", "integrator.io", "shrikisgood.atlassian.net", "app.slack.com"]) {
    assert.match(app, new RegExp(host.replaceAll(".", "\\.")));
  }
  assert.match(app, /function platformComponentContext\(/);
  assert.match(app, /receipt\.dataset\.platformSource = systemId/);
  assert.match(app, /function openDashboardComponentInspector\(/);
  assert.match(app, /function bindDashboardMetricInspectors\(/);
  assert.match(app, /openDashboardComponentInspector\(flowComponentContext\(item\)\)/);
  assert.match(app, /Stock Ledger Entry/);
  assert.match(app, /General Ledger/);
  assert.match(app, /Difference \$\{formatCurrency/);
  assert.match(app, /Case balance \$\{currentAvailable\} → \$\{targetAvailable\} · verified readback/);
  assert.match(html, /id="platform-findings-history"[^>]*hidden><summary>Findings at diagnosis/);
  assert.doesNotMatch(app, /AFTER EXECUTION · \$\{status\}/);
  assert.match(css, /\.dashboard-component-inspector\s*\{/);
  assert.match(css, /component-problem-pulse/);
  assert.match(css, /\.platform-investigation-node\.is-problem/);
});

test("connected source inspectors use fetched record ids and never link to the retired fake ERP document", async () => {
  const [html, app] = await Promise.all([
    readFile(new URL("../workspace/index.html", import.meta.url), "utf8"),
    readFile(new URL("../workspace/app.js", import.meta.url), "utf8"),
  ]);
  assert.doesNotMatch(app, /PO-4817|INV-4817/);
  assert.match(app, /function liveERPDocument\(kind\)/);
  assert.match(app, /function liveSaaSRecord\(componentId\)/);
  assert.match(app, /liveRecord\?\.record_id/);
  assert.match(app, /state\.erpEvidence\.activity/);
  assert.match(app, /state\.saasEvidence\.activity/);
  assert.match(html, /source-driven-final-v32/);
});
