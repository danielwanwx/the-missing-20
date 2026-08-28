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
});

test("client binds the API and ordered event ledger rather than timers", async () => {
  const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
  assert.match(app, /\/api\/v1\/incidents/);
  assert.match(app, /EventSource/);
  assert.match(app, /events\?after=/);
  assert.match(app, /tool\.started/);
  assert.match(app, /evidence\.returned/);
  assert.match(app, /dataset\.unitId/);
  assert.match(app, /\/chat/);
  assert.match(app, /\/decisions/);
  assert.doesNotMatch(app, /setInterval\s*\(/);
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
  assert.match(app, /state\.commandBusy \|\| !streamIsLive\(\) \|\| !quorumApproved/);
  assert.match(app, /state\.chatPending \|\| !streamIsLive\(\)/);
  assert.match(app, /button\.disabled = chatDisabled/);
  assert.match(css, /body:not\(\[data-connection="live"\]\) \.unit-entity\.is-moving/);
});
