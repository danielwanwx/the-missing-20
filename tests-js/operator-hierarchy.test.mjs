import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
const photo = await readFile(new URL("../workspace/photo-receiving.js", import.meta.url), "utf8");

test("operator overview has four primary business metrics and retains all twelve hooks", () => {
  const overview = html.split('<div class="business-metric-grid">')[1].split("</div>")[0];
  assert.equal([...overview.matchAll(/data-business-metric=/g)].length, 4);
  assert.equal([...html.matchAll(/data-business-metric=/g)].length, 12);
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
  assert.equal(new Set(ids).size, ids.length, "no duplicate data hooks");
  assert.match(html, /id="business-all-metrics"><summary>/);
  assert.match(html, /id="business-detail-alert" hidden/);
});

test("runtime and historical investigation facts are disclosed on demand", () => {
  assert.match(html, /<details class="operator-details platform-run-details"><summary>Run details/);
  assert.match(html, /<details class="operator-details" id="platform-technical-details"><summary>/);
  assert.match(html, /id="platform-findings-history"[^>]*hidden><summary>Findings at diagnosis/);
  assert.doesNotMatch(html, />STRANDS AGENT LOOP<|>HUMAN ↔ AGENT</);
  assert.ok(html.indexOf('id="platform-activity"') < html.indexOf('id="platform-tool-calls"'));
  assert.match(app, /actions.hidden =[\s\S]{0,200}AWAITING_MANAGER_APPROVAL/);
});

test("updates preserve conversation and do not animate unchanged business values", () => {
  assert.match(app, /conversationHost.renderedConversation !== conversationSignature/);
  assert.match(app, /sourceDetails.open = expandedSources.has/);
  assert.match(app, /const changed = node.textContent !== text/);
  assert.match(app, /if \(advanced && changed\)/);
});

test("photo intake explains cloud handling and never claims a count posted stock", () => {
  assert.match(photo, /Photos are stored in this demo and sent to AWS/);
  assert.match(photo, /Count ready · not received/);
  assert.match(photo, /inventory has not been posted/);
  assert.match(photo, /technical.append\(node\("summary", "Analysis details"\), metrics, events\)/);
});

test("an unavailable ERP read cannot render zero inventory or a current recovery verdict", () => {
  const source = app.slice(app.indexOf("  function renderSourceFreshness()"), app.indexOf("  function bodyReady()"));
  const elements = new Map();
  const node = (id) => {
    if (!elements.has(id)) elements.set(id, { textContent: "0", hidden: false, querySelectorAll: () => [], replaceChildren() {} });
    return elements.get(id);
  };
  const state = { agentPlatform: { source_freshness: { status: "UNAVAILABLE" }, conversation: [{ answer: "An earlier answer" }] }, agentPlatformError: "" };
  const document = { body: { dataset: {} }, querySelectorAll: () => [] };
  const sandbox = { state, document, $: node, setBadge: (target, label) => { target.textContent = label; }, closeDashboardComponentInspector() {} };
  vm.runInNewContext(`${source}\nrenderSourceFreshness();`, sandbox);
  assert.equal(node("source-unavailable").hidden, false);
  assert.equal(node("expected-count").textContent, "—");
  assert.equal(node("recorded-count").textContent, "—");
  assert.equal(node("path-status").textContent, "UNKNOWN");
  assert.equal(node("platform-execution-actions").hidden, true);
  assert.equal(node("platform-outcome-status").textContent, "HISTORICAL RESULT");
  assert.equal(node("platform-answer-status").textContent, "HISTORY");
  assert.equal(node("platform-diagnosis-summary").textContent, "Waiting for current source evidence.");
  assert.equal(document.body.dataset.sourceFreshness, "unavailable");
  state.agentPlatform.source_freshness.error_code = "RATE_LIMITED";
  vm.runInNewContext("renderSourceFreshness();", sandbox);
  assert.match(node("source-unavailable-title").textContent, /rate-limiting/);
  state.agentPlatform.source_freshness.status = "CURRENT";
  vm.runInNewContext("renderSourceFreshness();", sandbox);
  assert.equal(node("source-unavailable").hidden, true);
  assert.equal(document.body.dataset.sourceFreshness, "current");
});

test("failed chat retains the current question and cannot reuse an older successful answer", async () => {
  const source = app.slice(app.indexOf("  async function askPlatformQuestion("), app.indexOf("  async function runPlatformAction("));
  const state = { agentPlatformQuestionBusy: false, agentPlatformAnswer: "Old successful answer" };
  const sandbox = {
    state, value: (value) => String(value ?? ""), scheduleRender() {},
    setAgentPlatformProjection() {},
    requestJSON: async () => { throw new Error("Provider request unavailable"); },
  };
  await vm.runInNewContext(`${source}\naskPlatformQuestion('Check the current stock');`, sandbox);
  assert.equal(state.agentPlatformQuestionAttempt.question, "Check the current stock");
  assert.equal(state.agentPlatformQuestionAttempt.status, "AGENT_UNAVAILABLE");
  assert.equal(state.agentPlatformQuestionBusy, false);
  assert.notEqual(state.agentPlatformAnswer, "Old successful answer");
  assert.equal(state.agentPlatformReadError, undefined, "chat failure is not an ERP read failure");
  sandbox.requestJSON = async () => ({ answer: "Withheld by validation", agent_advisory: { status: "VALIDATION_FAILED" } });
  await vm.runInNewContext("askPlatformQuestion('Check again');", sandbox);
  assert.equal(state.agentPlatformQuestionAttempt.status, "VALIDATION_FAILED");
  assert.equal(state.agentPlatformQuestionAttempt.detail, "Withheld by validation");
  const views = [{ kind: "history", metric: "received", history: { points: [] } }];
  sandbox.requestJSON = async () => ({ answer: "Current source unavailable", agent_advisory: {
    status: "SOURCE_UNAVAILABLE", mode: "not_invoked", retained_views: views,
  } });
  await vm.runInNewContext("askPlatformQuestion('Show the receiving trend');", sandbox);
  assert.equal(state.agentPlatformQuestionAttempt.retainedViews, views);
  assert.equal(state.agentPlatformQuestionAttempt.status, "SOURCE_UNAVAILABLE");
  assert.match(app, /attempt\.retainedViews[\s\S]{0,250}renderAttachment/);
});
