/* Durable observations, not an animation clock or generated benchmark. */
(() => {
  const measures = [
    { key: "received", label: "Received", color: "#087e9c" },
    { key: "recorded", label: "Case balance", color: "#536b16" },
    { key: "quality_hold", label: "Quality hold", color: "#c84630" },
    { key: "invoice_hold_value", label: "Invoice hold", color: "#7751c8", money: true },
    { key: "outstanding_order_quantity", label: "Still to receive", color: "#9b640b" },
    { key: "net_billed_sales", label: "Net billed sales", color: "#2364bc", money: true },
  ];
  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function benchmarkSummary(payload, key) {
    const baseline = payload.baseline || {};
    const metric = baseline.metrics?.[key] || {};
    if (baseline.status === "SOURCE_UNAVAILABLE" || metric.status === "UNAVAILABLE") return "Source unavailable";
    if (metric.status === "UNKNOWN_UNIT") return "Unit not confirmed";
    if (metric.status !== "AVAILABLE" || !finite(metric.previous_mean) || !finite(metric.change)) {
      return `Building baseline · ${metric.sample_count || 0}/${baseline.minimum_samples || 3} prior observations`;
    }
    const fmt = (number) => number.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return `Prior avg ${fmt(metric.previous_mean)} · ${metric.change > 0 ? "+" : ""}${fmt(metric.change)} vs ${metric.sample_count} observations`;
  }
  function visiblePoints(points, hours, now = Date.now()) {
    return (Array.isArray(points) ? points : []).filter((point) => {
      const time = Date.parse(point.observed_at);
      return Number.isFinite(time) && (!hours || time >= now - hours * 3600000);
    });
  }
  function series(points, key) {
    // Never connect different UOM/currency cohorts or gaps in source availability.
    let cohort = null;
    let segment = [];
    const segments = [];
    for (const point of points) {
      const next = JSON.stringify([point.case_id, point.source_id, point.currency, point.uom,
        point.item_code, point.metric_version, point.provenance, point.observation_kind]);
      const value = point.metrics?.[key];
      const time = Date.parse(point.observed_at);
      if (next !== cohort || !finite(value) || !Number.isFinite(time)) {
        if (segment.length) segments.push(segment);
        segment = [];
      }
      cohort = next;
      if (finite(value) && Number.isFinite(time)) segment.push({ time, value, point });
    }
    if (segment.length) segments.push(segment);
    return segments;
  }
  function stepPath(points, x, y) {
    return points.map((point, index) => index
      ? `H ${x(point.time)} V ${y(point.value)}`
      : `M ${x(point.time)} ${y(point.value)}`).join(" ");
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { visiblePoints, series, stepPath, finite, benchmarkSummary, measures };
  }
  if (typeof window !== "undefined") window.Missing20History = { visiblePoints, series, stepPath, finite, benchmarkSummary, measures };
  if (typeof document === "undefined") return;
  const root = document.getElementById("operations-history");
  if (!root) return;
  const $ = (id) => document.getElementById(id);
  const el = (tag, text = "", className = "") => {
    const result = document.createElement(tag); result.textContent = text;
    if (className) result.className = className;
    return result;
  };
  const svgEl = (tag, attributes) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  };
  const date = (value) => new Date(value).toLocaleString([], {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
  let payload = { points: [] };
  let selected = measures[0];
  let loading = false;
  let sourceKey = "";
  let generation = 0;
  let activeCase = "";
  let refreshPending = false;
  function inspect(point) {
    const definitions = $("history-record");
    const records = (point.documents || []).map((record) => (
      [record.kind, record.name || record.record_id, record.version || record.modified].filter(Boolean).join(" · ")
    ));
    const rows = [
      ["Observed", date(point.observed_at)],
      ["Source time", point.effective_at ? date(point.effective_at) : "Not supplied"],
      ["Value", finite(point.metrics?.[selected.key]) ? String(point.metrics[selected.key]) : "Unavailable"],
      ["Unit", selected.money ? point.currency || "Unknown currency" : point.uom || "Case units"],
      ["Source", point.source_id || "ERPNext"],
      ["Records", records.join("; ") || "No linked source records"],
      ["Baseline", point.id === payload.points?.at(-1)?.id && payload.baseline?.metrics?.[selected.key]?.status === "AVAILABLE"
        ? `Previous ${payload.baseline.metrics[selected.key].sample_count} comparable observations: mean ${payload.baseline.metrics[selected.key].previous_mean.toFixed(2)}. Observation average, not an industry benchmark.`
        : point.id !== payload.points?.at(-1)?.id ? "Baseline comparisons are shown for the latest observation."
          : "Still accumulating comparable observations."],
    ];
    const excluded = payload.excluded_observations || [];
    if (excluded.length) rows.push(["Excluded observations",
      `${excluded.length} transitional receipt snapshots; retained for audit, not used in this chart or baseline.`]);
    definitions.replaceChildren(...rows.flatMap(([label, value]) => [el("dt", label), el("dd", value)]));
  }
  function render() {
    const points = visiblePoints(payload.points, Number($("history-window").value));
    const latest = points.at(-1);
    $("history-status").textContent = payload.status === "SYNTHETIC_CASE"
      ? "Controlled scenario · connected business history is separate"
      : !points.length ? "No observations in this window. History begins with the first source read."
        : `${points.length} source observations · ${date(points[0].observed_at)} — ${date(latest.observed_at)}`;
    $("history-metrics").replaceChildren(...measures.map((measure, index) => {
      const button = el("button", "", "history-metric");
      button.type = "button"; button.setAttribute("role", "radio");
      button.setAttribute("aria-checked", String(measure === selected));
      button.tabIndex = measure === selected ? 0 : -1;
      button.style.setProperty("--measure-color", measure.color);
      const value = latest?.metrics?.[measure.key];
      button.append(el("span", measure.label), el("strong", finite(value)
        ? `${value.toLocaleString()} ${measure.money ? latest.currency || "" : latest.uom || ""}` : "—"));
      button.append(el("span", benchmarkSummary(payload, measure.key), "history-comparison"));
      const choose = (next) => {
        selected = measures[next]; render();
        $("history-metrics").children[next].focus();
      };
      button.addEventListener("click", () => choose(index));
      button.addEventListener("keydown", (event) => {
        const next = event.key === "Home" ? 0 : event.key === "End" ? measures.length - 1
          : ["ArrowRight", "ArrowDown"].includes(event.key) ? (index + 1) % measures.length
            : ["ArrowLeft", "ArrowUp"].includes(event.key) ? (index + measures.length - 1) % measures.length : null;
        if (next != null) { event.preventDefault(); choose(next); }
      });
      return button;
    }));
    const chart = $("history-chart");
    chart.replaceChildren();
    const segments = series(points, selected.key);
    const values = segments.flat();
    if (values.length === 1) {
      chart.append(el("p", "First available observation. A trend needs another comparable source change."));
    } else if (values.length) {
      const minTime = Math.min(...points.map((p) => Date.parse(p.observed_at)));
      const maxTime = Math.max(...points.map((p) => Date.parse(p.observed_at)));
      const min = Math.min(0, ...values.map((v) => v.value));
      const max = Math.max(1, ...values.map((v) => v.value));
      const x = (t) => 38 + (maxTime === minTime ? 0.5 : (t - minTime) / (maxTime - minTime)) * 824;
      const y = (v) => 164 - (v - min) / (max - min) * 136;
      const svg = svgEl("svg", { viewBox: "0 0 900 204", role: "img", "aria-label": `${selected.label}, source observations; use buttons below for exact values` });
      [min, max].forEach((value) => {
        svg.append(svgEl("line", { x1: 38, x2: 862, y1: y(value), y2: y(value), stroke: "#e0e5e9" }));
        const label = svgEl("text", { x: 38, y: y(value) - 8, fill: "#52616d", "font-size": 11 });
        label.textContent = value.toLocaleString(); svg.append(label);
      });
      segments.forEach((segment) => {
        svg.append(svgEl("path", { d: stepPath(segment, x, y), stroke: selected.color, "stroke-width": 2, fill: "none", "stroke-linejoin": "round" }));
        segment.forEach((point) => svg.append(svgEl("circle", { cx: x(point.time), cy: y(point.value), r: 3, fill: selected.color })));
      });
      chart.append(svg);
    } else chart.append(el("p", "This measure is not available from the connected records."));
    const samples = $("history-samples");
    samples.replaceChildren(...points.slice(-24).map((point) => {
      const button = el("button", `${date(point.observed_at)} · ${finite(point.metrics?.[selected.key]) ? point.metrics[selected.key] : "unavailable"}`);
      button.type = "button"; button.addEventListener("click", () => { inspect(point); $("history-detail").open = true; });
      return button;
    }));
    if (latest) inspect(latest);
    else $("history-record").replaceChildren();
  }
  async function refresh() {
    if (loading) { refreshPending = true; return; }
    loading = true; $("history-refresh").disabled = true;
    const requestGeneration = generation;
    try {
      const hours = Number($("history-window").value);
      const since = hours ? `&since=${encodeURIComponent(new Date(Date.now() - hours * 3600000).toISOString())}` : "";
      const response = await fetch(`/api/v1/agent-platform/history?limit=500${since}`);
      if (!response.ok) throw new Error("History could not be read. Retry the source connection.");
      const result = await response.json();
      if (requestGeneration !== generation) return;
      payload = result; render();
    } catch (error) {
      if (requestGeneration !== generation) return;
      payload = { points: [], baseline: { status: "SOURCE_UNAVAILABLE" } }; render();
      $("history-status").textContent = error.message;
    }
    finally {
      loading = false; $("history-refresh").disabled = false;
      if (refreshPending) { refreshPending = false; void refresh(); }
    }
  }
  $("history-refresh").addEventListener("click", refresh);
  $("history-window").addEventListener("change", () => { generation += 1; void refresh(); });
  window.addEventListener("missing20:projection", (event) => {
    const next = JSON.stringify(event.detail);
    if (next === sourceKey) return;
    if (activeCase !== event.detail.caseId) { activeCase = event.detail.caseId; generation += 1; payload = { points: [] }; render(); }
    sourceKey = next; void refresh();
  });
  window.addEventListener("missing20:receipt-changed", refresh);
  render();
  void refresh();
})();
