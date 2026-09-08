#!/usr/bin/env node

/**
 * Creates the real ERPNext evidence layer for the Missing 20 demo.
 *
 * The script is deliberately idempotent: it only creates records whose
 * externally meaningful identifiers are absent.  It never deletes or edits
 * existing ERPNext records.
 */

import { readFile } from "node:fs/promises";

const env = Object.fromEntries(
  (await readFile(new URL("../.env", import.meta.url), "utf8"))
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const index = line.indexOf("=");
      return [line.slice(0, index), line.slice(index + 1)];
    }),
);

const required = ["ERPNEXT_BASE_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET"];
for (const key of required) {
  if (!env[key]) throw new Error(`Missing ${key} in .env`);
}

const baseUrl = env.ERPNEXT_BASE_URL.replace(/\/$/, "");
const headers = {
  Authorization: `token ${env.ERPNEXT_API_KEY}:${env.ERPNEXT_API_SECRET}`,
  "Content-Type": "application/json",
};

async function request(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, { headers, ...options });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(`${options.method ?? "GET"} ${path}: ${body.exc_type ?? response.status} ${body.exception ?? ""}`);
  }
  return body;
}

function resource(doctype, name = "") {
  return `/api/resource/${encodeURIComponent(doctype)}${name ? `/${encodeURIComponent(name)}` : ""}`;
}

async function findOne(doctype, filters) {
  const query = new URLSearchParams({
    fields: JSON.stringify(["name"]),
    filters: JSON.stringify(filters),
    limit_page_length: "1",
  });
  return (await request(`${resource(doctype)}?${query}`)).data?.[0] ?? null;
}

async function ensure(doctype, filters, payload) {
  const existing = await findOne(doctype, filters);
  if (existing) return { name: existing.name, created: false };
  const body = await request(resource(doctype), {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return { name: body.data.name, created: true, document: body.data };
}

async function submit(document) {
  const body = await request("/api/method/frappe.client.submit", {
    method: "POST",
    body: JSON.stringify({ doc: document }),
  });
  return body.message;
}

async function blockInvoice(name) {
  // ERPNext Cloud's current release exposes this as a document action rather
  // than the newer module-level helper. It executes the document's own
  // block_invoice method, which uses ERPNext's supported post-submit update.
  await request("/api/method/run_doc_method", {
    method: "POST",
    body: JSON.stringify({
      dt: "Purchase Invoice",
      dn: name,
      method: "block_invoice",
      args: {
        release_date: "2026-12-31",
        hold_comment: "M20 DEMO: payment hold pending three-way match. 8 ECU controllers are in Quality Hold after rejected incoming inspection.",
      },
    }),
  });
}

const company = "Missing 20 Automotive Demo";
const supplier = "M20 Controller Systems Ltd.";
const item = "M20-ECU-CTRL";
const stores = "Stores - M20";
const qualityHold = "M20 Quality Hold - M20";
const receiptDeliveryNote = "M20-DOCK-87421";
const vendorInvoice = "M20-VNDR-87421";
const date = "2026-09-01";

const result = {};

result.supplier = await ensure("Supplier", [["supplier_name", "=", supplier]], {
  doctype: "Supplier",
  supplier_name: supplier,
  supplier_type: "Company",
  supplier_group: "Demo Supplier Group",
  supplier_details: "M20 DEMO: external ECU controller supplier for the Missing 20 investigation.",
});

result.qualityWarehouse = await ensure("Warehouse", [["warehouse_name", "=", "M20 Quality Hold"]], {
  doctype: "Warehouse",
  warehouse_name: "M20 Quality Hold",
  company,
  parent_warehouse: "All Warehouses - M20",
  is_group: 0,
});

result.item = await ensure("Item", [["item_code", "=", item]], {
  doctype: "Item",
  item_code: item,
  item_name: "ECU Controller / Safety-Critical",
  item_group: "Demo Item Group",
  stock_uom: "Nos",
  is_stock_item: 1,
  is_purchase_item: 1,
  valuation_rate: 1200,
  inspection_required_before_purchase: 1,
  description: "M20 DEMO: safety-critical automotive electronic control unit.",
});

let purchaseOrder = await findOne("Purchase Order", [
  ["supplier", "=", supplier],
  ["transaction_date", "=", date],
]);
if (!purchaseOrder) {
  const created = await request(resource("Purchase Order"), {
    method: "POST",
    body: JSON.stringify({
      doctype: "Purchase Order",
      naming_series: "PUR-ORD-.YYYY.-",
      supplier,
      transaction_date: date,
      schedule_date: "2026-09-02",
      company,
      currency: "USD",
      conversion_rate: 1,
      set_warehouse: stores,
      items: [{
        doctype: "Purchase Order Item",
        item_code: item,
        item_name: "ECU Controller / Safety-Critical",
        schedule_date: "2026-09-02",
        qty: 20,
        uom: "Nos",
        stock_uom: "Nos",
        conversion_factor: 1,
        rate: 1200,
        warehouse: stores,
      }],
    }),
  });
  purchaseOrder = (await submit(created.data)).name ? await request(resource("Purchase Order", created.data.name)).then((body) => body.data) : created.data;
  result.purchaseOrder = { name: purchaseOrder.name, created: true };
} else {
  purchaseOrder = (await request(resource("Purchase Order", purchaseOrder.name))).data;
  result.purchaseOrder = { name: purchaseOrder.name, created: false };
}

let purchaseReceipt = await findOne("Purchase Receipt", [["supplier_delivery_note", "=", receiptDeliveryNote]]);
if (!purchaseReceipt) {
  const created = await request(resource("Purchase Receipt"), {
    method: "POST",
    body: JSON.stringify({
      doctype: "Purchase Receipt",
      naming_series: "MAT-PRE-.YYYY.-",
      supplier,
      supplier_delivery_note: receiptDeliveryNote,
      posting_date: date,
      posting_time: "10:17:00",
      company,
      currency: "USD",
      conversion_rate: 1,
      set_warehouse: stores,
      rejected_warehouse: qualityHold,
      items: [{
        doctype: "Purchase Receipt Item",
        item_code: item,
        item_name: "ECU Controller / Safety-Critical",
        received_qty: 20,
        qty: 12,
        rejected_qty: 8,
        uom: "Nos",
        stock_uom: "Nos",
        conversion_factor: 1,
        rate: 1200,
        warehouse: stores,
        rejected_warehouse: qualityHold,
        purchase_order: purchaseOrder.name,
        purchase_order_item: purchaseOrder.items[0].name,
      }],
    }),
  });
  purchaseReceipt = (await submit(created.data)).name ? await request(resource("Purchase Receipt", created.data.name)).then((body) => body.data) : created.data;
  result.purchaseReceipt = { name: purchaseReceipt.name, created: true };
} else {
  purchaseReceipt = (await request(resource("Purchase Receipt", purchaseReceipt.name))).data;
  result.purchaseReceipt = { name: purchaseReceipt.name, created: false };
}

let inspection = await findOne("Quality Inspection", [["reference_name", "=", purchaseReceipt.name]]);
if (!inspection) {
  try {
    const created = await request(resource("Quality Inspection"), {
      method: "POST",
      body: JSON.stringify({
        doctype: "Quality Inspection",
        naming_series: "MAT-QA-.YYYY.-",
        report_date: date,
        status: "Rejected",
        inspection_type: "Incoming",
        reference_type: "Purchase Receipt",
        reference_name: purchaseReceipt.name,
        child_row_reference: purchaseReceipt.items[0].name,
        item_code: item,
        sample_size: 8,
        manual_inspection: 1,
        inspected_by: env.ERPNEXT_API_USER,
        remarks: "M20 DEMO: 8 of 20 ECU controllers failed incoming safety inspection and remain in Quality Hold.",
      }),
    });
    inspection = await submit(created.data);
    result.qualityInspection = { name: inspection.name, created: true };
  } catch (error) {
    // The submitted receipt still records the 12/8 accepted/rejected split.
    // ERPNext only permits a linked Quality Inspection after an Item Manager
    // enables the item-level inspection requirement.
    if (!String(error).includes("Inspection Required before Purchase")) throw error;
    result.qualityInspection = {
      name: null,
      created: false,
      pendingItemConfiguration: true,
    };
  }
} else {
  result.qualityInspection = { name: inspection.name, created: false };
}

let invoice = await findOne("Purchase Invoice", [["bill_no", "=", vendorInvoice]]);
if (!invoice) {
  const created = await request(resource("Purchase Invoice"), {
    method: "POST",
    body: JSON.stringify({
      doctype: "Purchase Invoice",
      naming_series: "ACC-PINV-.YYYY.-",
      supplier,
      company,
      posting_date: date,
      bill_no: vendorInvoice,
      bill_date: date,
      currency: "USD",
      conversion_rate: 1,
      credit_to: "Creditors - M20",
      update_billed_amount_in_purchase_order: 0,
      update_billed_amount_in_purchase_receipt: 0,
      items: [{
        doctype: "Purchase Invoice Item",
        item_code: item,
        item_name: "ECU Controller / Safety-Critical",
        qty: 20,
        stock_qty: 20,
        uom: "Nos",
        stock_uom: "Nos",
        conversion_factor: 1,
        rate: 1200,
        warehouse: stores,
        purchase_order: purchaseOrder.name,
        purchase_receipt: purchaseReceipt.name,
      }],
    }),
  });
  invoice = await submit(created.data);
  await blockInvoice(invoice.name);
  result.purchaseInvoice = { name: invoice.name, created: true, onHold: true };
} else {
  invoice = (await request(resource("Purchase Invoice", invoice.name))).data;
  if (!invoice.on_hold) await blockInvoice(invoice.name);
  result.purchaseInvoice = { name: invoice.name, created: false, onHold: true };
}

console.log(JSON.stringify({ ok: true, result }, null, 2));
