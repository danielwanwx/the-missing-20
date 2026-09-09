import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
function source(name) {
  const start = app.indexOf(`  function ${name}(`);
  return app.slice(start, app.indexOf("\n  function ", start + 12));
}
function geometry(visible = true) {
  const bounds = { left: 20, top: 100, width: 800, height: 300, bottom: 400 };
  const target = {
    getBoundingClientRect: () => visible
      ? { left: 60, top: 120, width: 120, height: 80, bottom: 200 }
      : { left: 0, top: 0, width: 0, height: 0, bottom: 0 },
  };
  const nodes = Array.from({ length: 4 }, () => ({
    style: { left: "0px" }, getBoundingClientRect: () => bounds,
  }));
  const map = { dataset: {}, getBoundingClientRect: () => bounds,
    querySelector: (selector) => nodes[["jira", "celigo", "airtable", "slack"].findIndex((id) => selector.includes(id))],
    querySelectorAll: () => nodes,
  };
  const svg = { children: ["stale-path"], setAttribute() {},
    replaceChildren() { this.children = []; }, append(path) { this.children.push(path); },
  };
  const context = {
    state: {agentPlatform: null},
    document: { querySelector: () => ({ offsetParent: {}, getBoundingClientRect: () => bounds }) },
    $: (id) => ({ "dashboard-evidence-map": map, "dashboard-evidence-links": svg,
      "flow-map": { querySelector: () => target } })[id],
    createSvgPath: () => ({ setAttribute() {} }), platformLinkPath: () => "path",
  };
  vm.runInNewContext(source("renderDashboardEvidenceLinks"), context);
  return { context, map, svg };
}

test("hidden flow targets do not collapse four source buttons onto one point", () => {
  const { context, map, svg } = geometry(false);
  context.renderDashboardEvidenceLinks();
  assert.equal(map.dataset.layout, "standalone");
  assert.equal(svg.children.length, 0, "no dangling paths to invisible targets");
  assert.match(css, /\.dashboard-evidence-map\[data-layout="standalone"\]\s*\{[^}]*display:\s*grid/s);
  assert.match(css, /\.dashboard-evidence-map\[data-layout="standalone"\] \.dashboard-evidence-node\s*\{[^}]*position:\s*relative/s);
});

test("visible flow targets retain their existing connected layout", () => {
  const { context, map, svg } = geometry();
  map.dataset.layout = "standalone";
  context.renderDashboardEvidenceLinks();
  assert.equal(map.dataset.layout, "connected");
  assert.equal(svg.children.length, 4);
});

test("persistent source outage does not close a read-only inspector on every poll", () => {
  let closed = 0;
  const element = { dataset: {}, querySelectorAll: () => [], replaceChildren() {} };
  const context = {
    state: { agentPlatform: { source_freshness: { status: "UNAVAILABLE" } } },
    document: { body: { dataset: { sourceFreshness: "unavailable" } }, querySelectorAll: () => [] },
    $: () => element, setBadge() {}, closeDashboardComponentInspector: () => { closed += 1; },
  };
  vm.runInNewContext(source("renderSourceFreshness"), context);
  context.renderSourceFreshness();
  context.renderSourceFreshness();
  assert.equal(closed, 0);
  context.document.body.dataset.sourceFreshness = "current";
  context.renderSourceFreshness();
  assert.equal(closed, 1, "an old current-state inspector is dismissed when its evidence becomes unavailable");
});

test("inspecting a source cannot relabel historical charts as live during an outage", () => {
  const nodes = {};
  const context = {
    state: { connection: "live" },
    document: { body: { dataset: { sourceFreshness: "unavailable" } } },
    $: (id) => nodes[id] ||= {}, pointTime: () => "", value: (v) => String(v ?? ""),
  };
  vm.runInNewContext(source("renderDiagramCursorLabels"), context);
  context.renderDiagramCursorLabels();
  assert.equal(nodes["trend-time"].textContent, "HISTORY");
  assert.equal(nodes["business-trend-time"].textContent, "HISTORY");
});

test("retained events show their actual last timestamp rather than a static NOW", () => {
  const nodes = { "dashboard-event-now": { firstElementChild: { textContent: "NOW" } } };
  const node = () => ({ dataset: {}, classList: { add() {} }, append() {}, replaceChildren() {} });
  const context = {
    state: { agentPlatform: { activity: [
      { sequence: 1, source_id: "erp", label: "Receipt read", occurred_at: "2026-09-07T12:00:00Z" },
    ] }, events: [
      { sequence: 9, source_id: "erp", label: "Other scenario", occurred_at: "2026-09-09T12:00:00Z" },
    ], dashboardLatestRenderedSequence: 0 },
    $: (id) => nodes[id] ||= { ...node(), firstElementChild: { textContent: "NOW" } },
    create: node, number: (v) => Number(v || 0), value: (v) => String(v ?? ""), slug: (v) => v,
    platformFlowProjection: () => ({}), dashboardEventSource: () => "ERPNext",
    operatorEventTime: (date) => date.toISOString(), eventDetail: () => "",
  };
  vm.runInNewContext(source("renderDashboardEventRail"), context);
  context.renderDashboardEventRail();
  assert.equal(nodes["dashboard-event-now"].firstElementChild.textContent,
    "Latest · 2026-09-07T12:00:00.000Z");
  context.state.agentPlatform.activity = [];
  context.renderDashboardEventRail();
  assert.equal(nodes["dashboard-event-now"].firstElementChild.textContent, "Waiting for events");
  context.platformFlowProjection = () => null;
  context.renderDashboardEventRail();
  assert.equal(nodes["dashboard-event-now"].firstElementChild.textContent,
    "Latest · 2026-09-09T12:00:00.000Z");
});

test("Investigation counts retained events, not the lifetime ledger sequence", () => {
  const node = {};
  const context = { $: () => node, value: String,
    platform: { latest_sequence: 111, activity: Array.from({ length: 80 }, () => ({})) } };
  const assignment = app.match(/\$\("platform-event-count"\)\.textContent =[^;]+;/)[0];
  vm.runInNewContext(assignment, context);
  assert.equal(node.textContent, "80 events");
});

test("normal monitoring does not inherit a selected case's failed investigation", () => {
  const nodes = {};
  const node = () => ({ dataset: {}, querySelector: () => nodes.facts ||= {} });
  const context = {
    state: { events: [], agentPlatform: { latest_sequence: 47,
      agent_run: {state: "BLOCKED"}, diagnosis: {finding: "AGENT_VALIDATION_FAILED"},
      activity: [{sequence: 47, label: "Other case failure"}] } },
    $: id => nodes[id] ||= node(), platformFlowProjection: () => null,
    receivingNeedsAttention: () => false, isNormalScenario: () => true,
    number: (v, fallback = 0) => v == null ? fallback : Number(v),
    value: v => String(v ?? ""), slug: v => v,
  };
  vm.runInNewContext(source("renderDashboardAgentStatus"), context);
  context.renderDashboardAgentStatus();
  assert.equal(nodes["dashboard-agent-stage"].textContent, "Monitoring");
  assert.equal(nodes["dashboard-agent-event-count"].textContent, "0");
  assert.equal(nodes["dashboard-open-investigation"].hidden, true);
});

test("receiving conflicts remain visible beside an existing agent answer", () => {
  const nodes = {};
  const node = () => ({ dataset: {}, children: [], classList: { add() {} },
    append(...items) { this.children.push(...items); }, replaceChildren() { this.children = []; } });
  const context = {
    state: { agentPlatform: { activity: [
      { sequence: 1, source_id: "agent-platform", label: "Agent answer", occurred_at: "2026-09-08T10:00:00Z" },
      { sequence: 2, source_id: "receiving-scan", status: "CONFLICT", label: "Scan conflict needs review", occurred_at: "2026-09-08T10:01:00Z" },
    ] }, dashboardLatestRenderedSequence: 0 },
    $: (id) => nodes[id] ||= node(),
    create: node, number: (v) => Number(v || 0), value: (v) => String(v ?? ""), slug: (v) => v,
    platformFlowProjection: () => ({}), operatorEventTime: () => "10:01:00", eventDetail: () => "",
  };
  vm.runInNewContext(source("dashboardEventSource") + source("renderDashboardEventRail"), context);
  context.renderDashboardEventRail();
  const rows = nodes["dashboard-event-feed"].children;
  assert.equal(rows.length, 2);
  assert.equal(rows[1].dataset.source, "Receiving");
  assert.equal(context.dashboardEventSource({ source_id: "receiving-photo", detail: "ERP receipt prepared" }), "Receiving");
});

test("case coverage is unknown without proof, never a hard-coded demo case count", () => {
  let observed;
  const context = { proof: {}, number: (v, fallback = 0) => Number.isFinite(Number(v)) ? Number(v) : fallback,
    metricText: (id, text) => { observed = text; } };
  const assignment = app.match(/metricText\("platform-metric-cases"[^;]+;/)[0];
  vm.runInNewContext(assignment, context);
  assert.equal(observed, "—");
  context.proof.case_matrix_size = 0;
  vm.runInNewContext(assignment, context);
  assert.equal(observed, "0");
  context.proof.case_matrix_size = 3;
  vm.runInNewContext(assignment, context);
  assert.equal(observed, "3");
});
