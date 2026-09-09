/* The model selects a metric. All values below come from the recorded tool result. */
(() => {
  const initialQuestions = ["What needs my attention?", "Show the receiving trend and its historical baseline.", "Which source records support the current quantities?"];
  function questionsFor(turns) {
    const proposed = turns?.at(-1)?.follow_up_questions;
    return Array.isArray(proposed) && proposed.length ? proposed.filter((q) => typeof q === "string" && q.trim()).slice(0, 3)
      : initialQuestions;
  }
  function retainedChartState(points, metric, api) {
    const unitKey = api.measures.find((item) => item.key === metric)?.money ? "currency" : "uom";
    const candidates = points.filter((point) => api.finite(point.metrics?.[metric]) && Number.isFinite(Date.parse(point.observed_at)));
    const latest = candidates.findLast((point) => typeof point[unitKey] === "string" && point[unitKey].trim());
    const keys = ["case_id", "source_id", "currency", "uom", "item_code", "metric_version", "provenance", "observation_kind"];
    // Split first: removing outages or other cohorts first would bridge missing evidence.
    const segments = latest ? api.series(points, metric).filter((segment) => keys.every((key) => segment[0].point[key] === latest[key])) : [];
    return { segments, unit: latest?.[unitKey], emptyMessage: !candidates.length
      ? "No retained values for this metric." : !latest ? "Unit not confirmed; comparison unavailable." : "" };
  }
  function comparableSegments(points, metric, api) {
    return retainedChartState(points, metric, api).segments;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { questionsFor, comparableSegments, retainedChartState };
  if (typeof document === "undefined") return;
  const el = (tag, text, className = "") => {
    const node = document.createElement(tag); node.textContent = text; node.className = className; return node;
  };
  const svgEl = (tag, attrs) => {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value)); return node;
  };
  function renderAttachment(attachment) {
    const api = window.Missing20History;
    const metric = api?.measures.find((item) => item.key === attachment?.metric);
    if (attachment?.kind !== "history" || !metric || !attachment.history) return null;
    const history = attachment.history;
    const points = Array.isArray(history.points) ? history.points : [];
    const figure = el("figure", "", "conversation-chart");
    const { segments, unit, emptyMessage } = retainedChartState(points, metric.key, api);
    figure.append(el("figcaption", `${metric.label}${unit ? ` · ${unit}` : ""}`));
    figure.append(el("p", api.benchmarkSummary(history, metric.key)));
    // Only compare one explicit cohort. Other observations remain inspectable below.
    const values = segments.flat();
    if (emptyMessage || values.length < 2) figure.append(el("p", emptyMessage || "Not enough source changes for a trend."));
    else {
      const start = Math.min(...values.map((p) => p.time)); const end = Math.max(...values.map((p) => p.time));
      const low = Math.min(0, ...values.map((p) => p.value)); const high = Math.max(1, ...values.map((p) => p.value));
      const x = (time) => 32 + (time - start) / (end - start || 1) * 496;
      const y = (value) => 122 - (value - low) / (high - low) * 96;
      const svg = svgEl("svg", {viewBox: "0 0 560 150", role: "img", "aria-label": `${metric.label} by observed time; exact values in source observations`});
      for (const value of [low, high]) {
        const label = svgEl("text", {x: 4, y: y(value), fill: "#344759", "font-size": 11}); label.textContent = String(value); svg.append(label);
      }
      for (const segment of segments) {
        svg.append(svgEl("path", {d: api.stepPath(segment, x, y), fill: "none", stroke: metric.color, "stroke-width": 2}));
        for (const point of segment) svg.append(svgEl("circle", {cx: x(point.time), cy: y(point.value), r: 2, fill: metric.color}));
      }
      figure.append(svg);
    }
    const details = el("details", ""); details.append(el("summary", `Source observations (${points.length})`));
    const list = el("ol", "");
    points.forEach((point) => {
      const value = point.metrics?.[metric.key];
      const item = el("li", `${new Date(point.observed_at).toLocaleString()} · ${api.finite(value) ? value : "unavailable"} ${metric.money ? point.currency || "" : point.uom || ""}`);
      item.append(el("span", point.evidence_id || `${point.case_id} · ${point.id}`));
      (point.documents || []).forEach((doc) => item.append(el("span", `${doc.kind} · ${doc.name} · ${doc.version || "version not supplied"}`)));
      list.append(item);
    });
    details.append(list); figure.append(details);
    return figure;
  }
  window.Missing20Conversation = { questionsFor, renderAttachment };
})();
