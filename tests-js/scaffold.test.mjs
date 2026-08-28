import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("package is private during development", async () => {
  const raw = await readFile(new URL("../package.json", import.meta.url), "utf8");
  const pkg = JSON.parse(raw);
  assert.equal(pkg.private, true);
});

test("workspace exposes the two real-time views", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  assert.match(html, /data-view="dashboard"/);
  assert.match(html, /data-view="agent"/);
  assert.match(html, /id="flow-map"/);
  assert.match(html, /id="agent-graph"/);
  assert.match(html, /id="chat-form"/);
  assert.match(html, /id="dashboard-start-investigation"/);
  assert.match(html, /id="agent-start-investigation"/);
  assert.match(html, /Replay Investigation/);
});

test("client binds the API and ordered event ledger rather than timers", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /\/api\/v1\/incidents/);
  assert.match(app, /EventSource/);
  assert.match(app, /events\?after=/);
  assert.match(app, /replay=1/);
  assert.match(app, /tool\.started/);
  assert.match(app, /evidence\.returned/);
  assert.match(app, /dataset\.unitId/);
  assert.match(app, /\/chat/);
  assert.match(app, /\/decisions/);
  assert.doesNotMatch(app, /setInterval\s*\(/);
});

test("client recovers a reset stream from a fresh authoritative cursor", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /stream\.reset/);
  assert.match(app, /async function reconnectStream\(/);
  assert.match(app, /applySnapshot\(snapshot, snapshot\.units \|\| units\.units, true\)/);
  assert.match(app, /source\.onerror = \(\) =>/);
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
  assert.match(app, /No agent operations yet/);
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
  assert.match(app, /demoMode === "degraded" \|\| state\.chatPending \|\| state\.replaying \|\| !streamIsLive\(\)/);
  assert.match(app, /button\.disabled = chatDisabled/);
  assert.match(css, /body:not\(\[data-connection="live"\]\) \.unit-entity\.is-moving/);
});

test("the live UI preserves truth and accessible targets", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const smoke = await readFile(new URL("../scripts/run_decision_workspace_smoke.py", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /two simulated role principals/);
  assert.match(html, /Chat cannot prepare, approve, or execute/);
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
  assert.match(smoke, /expected_replay_sequences = list\(range\(2, int\(investigation_sequence\) \+ 1\)\)/);
  assert.match(smoke, /open_replay_api_bytes_unchanged/);
  assert.match(app, /not proven/);
  assert.match(css, /\.unit-entity\s*\{[^}]*min-width:\s*24px/s);
});

test("degraded mode removes advisory surfaces and preserves the deterministic gate", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /function applyModeVisibility\(\)/);
  assert.match(app, /\.live-panel/, "live investigation panel is mode-gated");
  assert.match(app, /\.agent-system-panel/, "agent graph and evidence are mode-gated");
  assert.match(app, /\.copilot-panel/, "Copilot is mode-gated");
  assert.match(app, /control\.disabled = degraded/);
  assert.match(app, /demoMode === "degraded" \? "dashboard"/);
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
  assert.doesNotMatch(app, /if \(!deferStart/);
});

test("view tabs use a roving tabindex and the flow owns its narrow-screen scroll", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  const css = await readFile(new URL("../workspace/style.css", import.meta.url), "utf8");
  assert.match(html, /id="tab-dashboard"[\s\S]*?tabindex="0"/);
  assert.match(html, /id="tab-agent"[\s\S]*?tabindex="-1"/);
  assert.match(app, /tab-dashboard"\)\.tabIndex = state\.view === "dashboard" \? 0 : -1/);
  assert.match(app, /tab-agent"\)\.tabIndex = state\.view === "agent" \? 0 : -1/);
  assert.match(css, /\.dashboard-layout > \*, \.workspace-layout > \*, \.agent-sidebar, \.flow-panel \{[^}]*min-width:\s*0/s);
  assert.match(css, /\.flow-map \{[^}]*max-width:\s*100%[^}]*overflow-x:\s*auto/s);
});
