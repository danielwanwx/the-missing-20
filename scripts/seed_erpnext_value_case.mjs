#!/usr/bin/env node

/**
 * Seed the customer-side half of the live Missing 20 case in ERPNext.
 *
 * The external business event is a submitted fleet-service Sales Order placed
 * on hold while the safety-critical inventory discrepancy is investigated.
 * The script is idempotent and never deletes or cancels provider records.
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

for (const key of ["ERPNEXT_BASE_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET"]) {
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
    throw new Error(`${options.method ?? "GET"} ${path}: ${body.exc_type ?? response.status} ${body.exception ?? body.message ?? ""}`);
  }
  return body;
}

function resource(doctype, name = "") {
  return `/api/resource/${encodeURIComponent(doctype)}${name ? `/${encodeURIComponent(name)}` : ""}`;
}

async function findOne(doctype, filters, fields = ["name"]) {
  const query = new URLSearchParams({
    fields: JSON.stringify(fields),
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

const company = "Missing 20 Automotive Demo";
const customerName = "M20 Pacific Fleet Service";
const customerPo = "M20-FLEET-PO-2026-0907-A";
const itemCode = "M20-ECU-CTRL";
const warehouse = "Stores - M20";
const transactionDate = "2026-09-07";
const deliveryDate = "2026-09-08";
const quantity = 20;
const unitPrice = 2100;

let customer = await findOne("Customer", [["customer_name", "=", customerName]]);
if (!customer) {
  try {
    customer = await ensure("Customer", [["customer_name", "=", customerName]], {
      doctype: "Customer",
      customer_name: customerName,
      customer_type: "Company",
      customer_group: "Demo Customer Group",
      territory: "United States",
      default_currency: "USD",
      customer_details: "M20 DEMO: fleet service customer awaiting 20 safety-critical replacement ECU controllers.",
    });
  } catch (error) {
    if (!String(error).includes("PermissionError")) throw error;
    customer = await findOne("Customer", [], ["name", "customer_name"]);
    if (!customer) throw new Error("ERPNext API user cannot create or read a demo Customer");
  }
}

let order = await findOne("Sales Order", [["po_no", "=", customerPo]], ["name", "status", "docstatus"]);
let created = false;
if (!order) {
  const draft = await request(resource("Sales Order"), {
    method: "POST",
    body: JSON.stringify({
      doctype: "Sales Order",
      naming_series: "SAL-ORD-.YYYY.-",
      customer: customer.name,
      company,
      transaction_date: transactionDate,
      delivery_date: deliveryDate,
      po_no: customerPo,
      po_date: transactionDate,
      currency: "USD",
      conversion_rate: 1,
      selling_price_list: "Standard Selling",
      price_list_currency: "USD",
      plc_conversion_rate: 1,
      set_warehouse: warehouse,
      remarks: "M20 VALUE CASE: customer delivery waits for verified quality release and inventory reconciliation.",
      items: [{
        doctype: "Sales Order Item",
        item_code: itemCode,
        item_name: "ECU Controller / Safety-Critical",
        delivery_date: deliveryDate,
        qty: quantity,
        uom: "Nos",
        stock_uom: "Nos",
        conversion_factor: 1,
        rate: unitPrice,
        warehouse,
      }],
    }),
  });
  const submitted = await submit(draft.data);
  order = { name: submitted.name, status: submitted.status, docstatus: submitted.docstatus };
  created = true;
}

const current = (await request(resource("Sales Order", order.name))).data;
if (current.docstatus !== 1) throw new Error(`Sales Order ${current.name} is not submitted`);
if (current.status !== "On Hold" && current.per_delivered < 100 && current.per_billed < 100) {
  await request("/api/method/erpnext.selling.doctype.sales_order.sales_order.update_status", {
    method: "POST",
    body: JSON.stringify({ status: "On Hold", name: current.name }),
  });
}

const verified = (await request(resource("Sales Order", order.name))).data;
console.log(JSON.stringify({
  ok: true,
  customer: customer.name,
  sales_order: verified.name,
  customer_po: verified.po_no,
  status: verified.status,
  quantity: verified.total_qty,
  booked_value: verified.grand_total,
  currency: verified.currency,
  created,
}, null, 2));
