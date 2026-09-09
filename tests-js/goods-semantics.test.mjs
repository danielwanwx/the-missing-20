import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

const app = await readFile(new URL("../workspace/app.js", import.meta.url), "utf8");
const section = (name, next) => app.slice(app.indexOf(`  function ${name}(`), app.indexOf(`  function ${next}(`));
const number = (v, fallback = 0) => v == null || !Number.isFinite(Number(v)) ? fallback : Number(v);
test("an unposted receiving exception stays visible without fabricating a stock gap", () => {
  const context = {};
  vm.runInNewContext(section("receivingNeedsAttention", "platformFlowProjection"), context);
  for (const status of ["NEEDS_REVIEW", "NEEDS_PHOTO", "DRAFT_UNKNOWN", "SUBMIT_UNKNOWN", "UNAVAILABLE"]) {
    assert.equal(context.receivingNeedsAttention({receiving_work: {status: "CONFIGURED", arrivals: [{status}]}}), true);
  }
  for (const status of ["AWAITING_PHOTO", "COUNT_CANDIDATE", "RECEIPT_PREPARED", "RECEIPT_SUBMITTED"]) {
    assert.equal(context.receivingNeedsAttention({receiving_work: {status: "CONFIGURED", arrivals: [{status}]}}), false);
  }
  assert.match(app, /platform-confidence"\)\.hidden = receivingEvidenceOnly/);
  assert.match(app, /platform-guard"\)\.hidden = receivingEvidenceOnly/);
});

test("receiving does not draw fictional invoice to Slack routes", () => {
  const svg = {setAttribute() {}, replaceChildren() {this.cleared = true;}};
  const map = {dataset: {}, getBoundingClientRect: () => ({width: 800})};
  const stage = {offsetParent: {}, getBoundingClientRect: () => ({width: 800, height: 200})};
  const context = {state: {agentPlatform: {receiving_work: {status: "CONFIGURED"}}},
    document: {querySelector: () => stage}, $: id => id === "dashboard-evidence-map" ? map : svg};
  vm.runInNewContext(section("renderDashboardEvidenceLinks", "renderDashboardEvidence"), context);
  context.renderDashboardEvidenceLinks();
  assert.equal(svg.cleared, true);
  assert.equal(map.dataset.layout, "standalone");
});
test("live order headlines distinguish unreceived, partial, held and posted goods", () => {
  const context = { number };
  vm.runInNewContext(section("liveReceivingSummary", "renderHeader"), context);
  const base = { expected: 40, posted: 0, gap: 0, uom: "Box", invoiceHeld: false };
  assert.equal(context.liveReceivingSummary(base).title, "Awaiting receipt · 40 Box ordered");
  assert.equal(context.liveReceivingSummary({ ...base, posted: 1 }).title, "1 of 40 Box received");
  assert.equal(context.liveReceivingSummary({ ...base, posted: 1 }).detail, "39 Box still to receive");
  assert.equal(context.liveReceivingSummary({ ...base, posted: 40 }).title, "40 Box received");
  assert.equal(context.liveReceivingSummary({ ...base, posted: 40 }).detail, "Receipt posting complete");
  assert.equal(context.liveReceivingSummary({ ...base, posted: 41 }).title, "1 Box received above order quantity");
  assert.equal(context.liveReceivingSummary({ ...base, gap: 8 }).title, "8 Box need reconciliation");
  assert.equal(context.liveReceivingSummary({ ...base, invoiceHeld: true }).title, "Supplier invoice on hold");
  assert.equal(context.liveReceivingSummary({ ...base, expected: 0 }).title, "No ordered quantity recorded");
  for (const [posted, label] of [[0, "awaiting receipt"], [1, "partially received"], [40, "receipt posted in ERP"], [41, "over-receipt"]]) {
    assert.equal(context.liveReceivingSummary({ ...base, posted }).label, label);
  }
  assert.match(section("renderHeader", "renderScenarioControls"), /receivingSummary\?\.title/);
  assert.match(section("renderHeader", "renderScenarioControls"), /receivingSummary\?\.detail/);
});
test("fully issued receipts remain posted and invoice documents are not stock units", () => {
  const state = { agentPlatform: {
    case_projection: { provenance: "live-read", case: { uom: "Nos", quantities: {
      ordered: 20, available: 0, received_cumulative: 20, receipt_posted_quantity: 20,
      invoice_count: 1, quality_hold: 0, receipt_unresolved: 0,
    } } },
  } };
  const context = { state, number, value: (v) => String(v ?? "") };
  vm.runInNewContext(section("platformInvoiceStatus", "platformFlowProjection"), context);
  const result = vm.runInNewContext(`${section("platformFlowProjection", "businessImpactProjection")}\nplatformFlowProjection()`, context);
  assert.equal(result.recorded, 0);
  assert.equal(result.received, 20);
  assert.equal(result.posted, 20);
  assert.equal(result.invoiceCount, 1);
  assert.equal(result.gap, 0);
  assert.equal(result.uom, "Nos");
  assert.match(section("renderFlow", "selectUnit"), /\? platform\.posted/);
  assert.doesNotMatch(section("renderFlow", "selectUnit"), /invoiceHeld \? 0 : recorded/);
});

test("an absent live invoice is not open or released", () => {
  const context = {};
  vm.runInNewContext(section("platformInvoiceStatus", "platformFlowProjection"), context);
  const platform = {
    case_projection: { provenance: "live-read", case: { purchase_invoice: "", invoice_held: false, quantities: { invoice_count: 0 } } },
    document_lifecycle: { purchase_invoice: "AWAITING_INVOICE" },
    source_freshness: { status: "CURRENT" },
  };
  assert.equal(context.platformInvoiceStatus(platform), "NOT YET INVOICED");
  assert.equal(context.platformInvoiceStatus({ ...platform, document_lifecycle: {} }), "UNKNOWN");
  assert.equal(context.platformInvoiceStatus({ ...platform, source_freshness: { status: "UNAVAILABLE" } }), "UNKNOWN");
  platform.case_projection.case.purchase_invoice = "PI-1";
  platform.document_lifecycle.purchase_invoice = "PRESENT";
  assert.equal(context.platformInvoiceStatus(platform), "OPEN");
  platform.case_projection.case.invoice_held = true;
  assert.equal(context.platformInvoiceStatus(platform), "HELD");
  assert.match(app, /\["invoice", platformInvoiceStatus\(platform\)\.toLowerCase\(\)\]/);
  assert.match(app, /nodeStatus === "NOT YET INVOICED" \? "ph-bold ph-clock"/);
});

test("normal partial receiving does not require a recovery to be healthy", () => {
  const start = app.indexOf("    const allNodesHealthy = platform", app.indexOf("  function renderFlow("));
  const end = app.indexOf("    const projectedStatus", start);
  const expression = app.slice(start, end) + "\nallNodesHealthy";
  const platform = { sourceCurrent: true, gap: 0, invoiceHeld: false, posted: 1, expected: 40, verified: false };
  assert.equal(vm.runInNewContext(expression, { platform }), true);
  for (const change of [{ sourceCurrent: false }, { gap: 8 }, { invoiceHeld: true }, { posted: 41 }]) {
    assert.equal(vm.runInNewContext(expression, { platform: { ...platform, ...change } }), false);
  }
});
test("unknown monetary facts do not become zero dollar claims", () => {
  const start = app.indexOf("  function formatCurrency(");
  const source = app.slice(start, app.indexOf("\n  function ", start + 12));
  const context = { value: (v) => String(v ?? "") };
  vm.runInNewContext(source, context);
  assert.equal(context.formatCurrency(null), "—");
  assert.equal(context.formatCurrency(undefined), "—");
  assert.equal(context.formatCurrency(false), "—");
  assert.equal(context.formatCurrency(0), "$0");
});
test("the billed revenue card uses observed billing, not legacy value protected", () => {
  const start = app.indexOf("  function formatCurrency(");
  const format = app.slice(start, app.indexOf("\n  function ", start + 12));
  const assignment = app.match(/\["business-value-protected",[^\n]+/)[0].trim().replace(/,$/, "");
  const context = { value: (v) => String(v ?? ""), currency: "USD",
    impact: { value_protected: 999 }, proof: {}, observed: { billed_revenue: null } };
  vm.runInNewContext(format, context);
  assert.equal(vm.runInNewContext(assignment, context)[1], "—");
  context.observed.billed_revenue = 0;
  assert.equal(vm.runInNewContext(assignment, context)[1], "$0");
  context.observed.billed_revenue = 100;
  assert.equal(vm.runInNewContext(assignment, context)[1], "$100");
  context.proof = null;
  assert.equal(vm.runInNewContext(assignment, context)[1], "—");
});
test("ERP redirects use the current source document or the matching list, never an old case", () => {
  const context = { state: { erpEvidence: { documents: [
    { kind: "purchase_order", name: "PUR-ORD-2026-00012-1" },
    { kind: "purchase_receipt", name: "MAT-PRE-2026-00002" },
  ] } }, value: (v) => String(v ?? "") };
  vm.runInNewContext(section("liveERPDocument", "liveSaaSRecord"), context);
  const start = app.indexOf("  function erpDocumentLink(");
  vm.runInNewContext(app.slice(start, app.indexOf("  const MANAGER_ATTESTATIONS", start)), context);
  assert.equal(context.erpDocumentLink("purchase_order", "purchase-order").url,
    "https://missing20.v.frappe.cloud/app/purchase-order/PUR-ORD-2026-00012-1");
  assert.equal(context.erpDocumentLink("sales_invoice", "sales-invoice").url,
    "https://missing20.v.frappe.cloud/app/sales-invoice");
  context.state.erpEvidence.documents = [];
  assert.equal(context.erpDocumentLink("purchase_order", "purchase-order").url,
    "https://missing20.v.frappe.cloud/app/purchase-order");
  assert.doesNotMatch(app, /PUR-ORD-2026-00011|ACC-PINV-2026-00007/);
  assert.match(app, /window\.open\(erpDocumentLink\("purchase_order", "purchase-order"\)\.url/);
});
test("focus uses a native top-layer dialog, not a backdrop above the module", () => {
  const source = section("focusPlatformModule", "platformComponentContext");
  assert.match(source, /dialog\.showModal\(\)/);
  assert.match(source, /platformFocusAnchor\.replaceWith\(previous\)/);
  assert.match(source, /dialog\.addEventListener\("cancel"/);
  assert.doesNotMatch(source, /classList\.toggle\("platform-focus-open"/);
  assert.match(source, /platformFocusTrigger\?\.focus\(\)/);
});

test("finished effects use past tense and missing prestate is not fabricated", () => {
  assert.match(app, /units released · verified/);
  assert.match(app, /EARLIER STATE NOT RETAINED/);
  assert.doesNotMatch(app, /packetPreState\.invoice_status \|\| "PAYMENT_HOLD"/);
  assert.doesNotMatch(app, /parsed\.toISOString\(\)\.slice\(11, 19\)/);
});

test("missing resolution facts remain explicitly unknown and transitions are named", () => {
  assert.match(app, /itemValue == null \? "Unknown" : value\(itemValue\)/);
  assert.match(app, /Invoice state from \$\{priorInvoice\} to \$\{currentInvoice\}/);
});

test("history has single-selection keyboard controls and follows business impact", async () => {
  const html = await readFile(new URL("../workspace/index.html", import.meta.url), "utf8");
  const history = await readFile(new URL("../workspace/operations-history.js", import.meta.url), "utf8");
  assert.match(html, /id="history-metrics"[^>]+role="radiogroup"/);
  assert.ok(html.indexOf('class="business-impact"') < html.indexOf('id="operations-history"'));
  assert.match(history, /button\.setAttribute\("role", "radio"\)/);
  assert.match(history, /button\.setAttribute\("aria-checked"/);
  assert.match(history, /ArrowRight/);
  assert.match(history, /children\[next\]\.focus\(\)/);
});

test("photo dialog restores the actual invoking control, including rebuilt captures", async () => {
  const photo = await readFile(new URL("../workspace/photo-receiving.js", import.meta.url), "utf8");
  assert.match(photo, /returnFocus = trigger; returnCaptureId = id/);
  assert.match(photo, /returnFocus\?\.isConnected \? returnFocus : refreshedCapture \|\| opener/);
  assert.doesNotMatch(photo, /"close", \(\) => opener\.focus\(\)/);
});
