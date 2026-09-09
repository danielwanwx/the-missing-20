import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const source = await readFile(new URL("../workspace/photo-receiving.js", import.meta.url), "utf8");
const start = source.indexOf("  function refreshOpenCapture(");
const end = source.indexOf("  async function refreshGallery(", start);

test("Jira receiving actions are never labelled as Airtable", () => {
  const scope = {};
  vm.createContext(scope);
  vm.runInContext(source.slice(source.indexOf("  function handoffLabel("), source.indexOf("  function render(")), scope);
  for (const [operation, text] of Object.entries({create: "review opened", comment: "evidence updated", resolve: "review resolved"})) {
    assert.equal(scope.handoffLabel({route: `jira-receiving:QRC:${operation}`, status: "VERIFIED", evidence: {operation}}), `Jira · ${text} ↗`);
  }
  assert.equal(scope.handoffLabel({route: "jira-receiving:QRC:create", status: "UNKNOWN"}), "Jira · checking delivery");
  assert.equal(scope.handoffLabel({route: "airtable-receiving:base:table", status: "VERIFIED"}), "Airtable · synced ↗");
});

test("background draft results advance the open dialog without another click", () => {
  assert.ok(start >= 0, "background draft refresh is missing");
  const rendered = [];
  const context = { dialog: { open: true }, busy: false,
    session: { id: "capture-a", version: 3 }, render: state => rendered.push(state) };
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  context.refreshOpenCapture([{ id: "capture-a", version: 5, status: "DRAFT_VERIFIED" }]);
  assert.equal(rendered.length, 1);
  assert.equal(rendered[0].status, "DRAFT_VERIFIED");
  context.refreshOpenCapture([{ id: "capture-a", version: 2 }]);
  context.refreshOpenCapture([{ id: "capture-b", version: 9 }]);
  context.busy = true;
  context.refreshOpenCapture([{ id: "capture-a", version: 8 }]);
  context.busy = false;
  context.dialog.open = false;
  context.refreshOpenCapture([{ id: "capture-a", version: 8 }]);
  assert.equal(rendered.length, 1, "stale/other/busy/closed views must not be overwritten");
});

test("visible gallery polls actual state, not a timer that invents events", () => {
  assert.doesNotMatch(source, /The ERP response was interrupted/);
  assert.match(source, /document\.visibilityState === "visible" && !busy/);
  assert.match(source, /refreshOpenCapture\(captures\)/);
  assert.match(source, /clearInterval\(galleryTimer\)/);
});

test("destination readback updates an unchanged receipt version", () => {
  const rendered = [];
  const context = { dialog: { open: true }, busy: false,
    session: { id: "capture-a", version: 5, handoffs: [{ status: "UNKNOWN" }] },
    render: state => rendered.push(state) };
  vm.createContext(context);
  vm.runInContext(source.slice(start, end), context);
  context.refreshOpenCapture([{ id: "capture-a", version: 5, handoffs: [{ status: "VERIFIED" }] }]);
  assert.equal(rendered.length, 1);
  assert.equal(rendered[0].handoffs[0].status, "VERIFIED");
  context.refreshOpenCapture([{ id: "capture-a", version: 4, handoffs: [] }]);
  assert.equal(rendered.length, 1);
  assert.match(source, /Open posted ERP receipt/);
});
