/* Read-only M5 renderer. It renders persisted values; it never creates a lifecycle fact. */
(function () {
  "use strict";

  const body = document.body;
  const requestedMode = new URLSearchParams(window.location.search).get("mode");
  const mode = requestedMode === "degraded" || requestedMode === "invalid" ? requestedMode : "complete";
  const $ = (id) => document.getElementById(id);
  const text = (value) => String(value == null ? "" : value);
  const replay = { artifact: null, stages: [], current: -1, started: false };

  function setStatus(node, value, className) {
    node.textContent = text(value);
    node.className = `status-chip ${className || "status-neutral"}`;
  }

  function evidenceClass(value) {
    if (value === "PROVEN") return "status-proven";
    if (value === "SCRIPTED SYNTHETIC PROOF") return "status-scripted";
    if (value === "NOT PROVEN") return "status-not-proven";
    return "status-neutral";
  }

  function chip(value) {
    const span = document.createElement("span");
    span.className = `status-chip ${evidenceClass(value)}`;
    span.textContent = text(value);
    return span;
  }

  function stageData(artifact) {
    const incident = artifact.case;
    const advisory = artifact.advisory;
    const human = artifact.human_control;
    const unit = incident.unit === "EA" ? "units" : incident.unit;
    const expected = `${incident.expected_quantity} ${unit}`;
    const recorded = `${incident.observed_quantity} ${unit}`;
    const missing = `${incident.missing_quantity} ${unit}`;
    const roles = new Set(human.approvals.map((item) => item.role)).size;
    const isComplete = artifact.mode === "complete";
    const citedEvidence = new Set(
      advisory.hypotheses.flatMap((item) => [
        ...item.supporting_evidence_ids,
        ...item.contradicting_evidence_ids,
      ])
    ).size;
    return [
      {
        title: "Detect the gap",
        outcome: expected + " expected. " + recorded + " recorded. " + missing + " missing.",
        impact: "The system records the problem before changing anything.",
      },
      {
        title: "Agents investigate",
        outcome: isComplete
          ? advisory.hypotheses.length + " AI investigators compare possible causes using " + citedEvidence + " persisted records."
          : "The AI service failed, so the system shows no made-up answer.",
        impact: isComplete
          ? "AI narrows the search; it does not make the decision."
          : "The safety rules still work when AI is unavailable.",
      },
      {
        title: "Safety decision",
        outcome: "The safety rules confirm that the missing record can be recovered without creating a duplicate.",
        impact: "Recovery is allowed, but nothing can happen before human approval.",
      },
      {
        title: "Two roles approve",
        outcome: roles + " required roles independently approve each controlled step.",
        impact: "Neither the AI nor one person can authorize a change alone.",
      },
      {
        title: "Recover and verify",
        outcome: "The missing records are recovered, verified, and the incident is closed.",
        impact: "Running the same recovery again makes no duplicate change.",
      },
    ];
  }

  function renderReplay(artifact) {
    replay.artifact = artifact;
    replay.stages = stageData(artifact);
    replay.current = -1;
    replay.started = false;
    const list = $("stage-list");
    list.replaceChildren();
    replay.stages.forEach((stage, index) => {
      const item = document.createElement("li");
      item.className = "stage-item";
      const control = document.createElement("input");
      control.type = "button";
      control.className = "stage-button";
      control.value = `${index + 1}. ${stage.title}`;
      control.dataset.stage = String(index);
      control.setAttribute("aria-label", `Replay stage ${index + 1}: ${stage.title}`);
      control.addEventListener("click", () => setStage(index));
      item.append(control);
      list.append(item);
    });

    const start = $("replay-start");
    const previous = $("replay-previous");
    const next = $("replay-next");
    const restart = $("replay-restart");
    const stagePanel = $("replay-stage");

    function update() {
      const active = replay.started ? replay.current : -1;
      [...list.querySelectorAll(".stage-item")].forEach((item, index) => {
        const control = item.querySelector(".stage-button");
        item.classList.toggle("is-active", index === active);
        item.classList.toggle("is-complete", active >= 0 && index < active);
        item.classList.toggle("is-upcoming", active < 0 || index > active);
        if (index === active) {
          control.setAttribute("aria-current", "step");
        } else {
          control.removeAttribute("aria-current");
        }
      });
      const progress = $("replay-progress").firstElementChild;
      progress.style.width = `${active < 0 ? 0 : ((active + 1) / replay.stages.length) * 100}%`;
      $("replay-progress").setAttribute("aria-valuenow", String(active < 0 ? 0 : active + 1));
      if (active < 0) {
        $("replay-step-label").textContent = "Ready to begin";
        $("replay-stage-title").textContent = "Start the replay";
        $("replay-stage-outcome").textContent = "Press Start to see how the system found and fixed the problem.";
        $("replay-stage-impact").textContent = "This is a read-only replay; nothing is changed.";
        $("replay-intro").textContent = "Start here. The replay explains the incident one step at a time.";
      } else {
        const stage = replay.stages[active];
        $("replay-step-label").textContent = `Step ${active + 1} of ${replay.stages.length}`;
        $("replay-stage-title").textContent = stage.title;
        $("replay-stage-outcome").textContent = stage.outcome;
        $("replay-stage-impact").textContent = stage.impact;
        $("replay-intro").textContent = "Follow the evidence in order. These controls only replay saved data.";
      }
      start.disabled = replay.started;
      previous.disabled = !replay.started || replay.current === 0;
      next.disabled = !replay.started || replay.current === replay.stages.length - 1;
      restart.disabled = !replay.started;
      start.hidden = replay.started;
      previous.hidden = !replay.started;
      next.hidden = !replay.started;
      restart.hidden = !replay.started;
    }

    function setStage(index) {
      if (index < 0 || index >= replay.stages.length) return;
      replay.started = true;
      replay.current = index;
      update();
      stagePanel.focus({ preventScroll: true });
    }

    start.addEventListener("click", () => setStage(0));
    previous.addEventListener("click", () => setStage(replay.current - 1));
    next.addEventListener("click", () => setStage(replay.current + 1));
    restart.addEventListener("click", () => {
      replay.started = false;
      replay.current = -1;
      update();
      start.focus();
    });
    update();
  }

  function render(artifact) {
    if (artifact.status === "UNAVAILABLE") {
      document.querySelectorAll("#case-header, #replay-section, .detail-disclosure").forEach((node) => { node.hidden = true; });
      $("unavailable").hidden = false;
      $("unavailable-status").textContent = text(artifact.status);
      $("unavailable-detail").textContent = `${artifact.reason_code}: ${artifact.detail}`;
      body.dataset.workspaceReady = "true";
      document.title = "The Missing 20 — Workspace unavailable";
      return;
    }
    const incident = artifact.case;
    const decision = artifact.deterministic_decision;
    const advisory = artifact.advisory;
    const execution = artifact.execution;
    const m6Proof = artifact.m6_aws_proof;
    const displayUnit = incident.unit === "EA" ? "units" : incident.unit;
    document.title = `The Missing 20 — ${incident.case_id}`;
    document.querySelectorAll("[data-mode-link]").forEach((link) => {
      link.removeAttribute("aria-current");
      if (link.dataset.modeLink === artifact.mode) link.setAttribute("aria-current", "page");
    });
    $("case-title").textContent = `${incident.missing_quantity} ${displayUnit} disappeared between two systems`;
    $("expected").textContent = `${incident.expected_quantity} ${displayUnit}`;
    $("observed").textContent = `${incident.observed_quantity} ${displayUnit}`;
    $("missing").textContent = `${incident.missing_quantity} ${displayUnit}`;
    renderReplay(artifact);

    $("mode-label").textContent = artifact.mode === "complete"
      ? "Complete scripted advisory trace · synthetic only"
      : "Real provider outcome · degraded; usefulness NOT PROVEN";

    const taxonomy = $("evidence-taxonomy");
    taxonomy.replaceChildren();
    artifact.evidence_taxonomy.forEach((item) => {
      const card = document.createElement("article");
      card.className = "taxonomy-card";
      card.append(chip(item.label));
      const heading = document.createElement("strong");
      heading.textContent = item.label;
      const count = document.createElement("span");
      count.className = "count";
      count.textContent = text(item.count);
      heading.append(count);
      card.append(heading);
      const detail = document.createElement("p");
      detail.textContent = item.detail;
      card.append(detail);
      taxonomy.append(card);
    });

    setStatus($("integration-status"), m6Proof.status, "status-proven");
    const integrationSummary = $("integration-summary");
    integrationSummary.replaceChildren();
    const stableUsefulness = m6Proof.capabilities.find((item) => item.capability_id === "stable_real_nova_usefulness");
    const agentCoreCount = m6Proof.capabilities.filter((item) => item.capability_id.startsWith("agentcore_")).length;
    [["Local lifecycle", m6Proof.lifecycle.status], ["Real integration", `${m6Proof.real_provider_integration.outcome_status} · CONNECTIVITY_AND_DEGRADATION_OBSERVABILITY`], ["Stable real AI", stableUsefulness ? stableUsefulness.status : "NOT PROVEN"]].forEach(([label, value]) => {
      const card = document.createElement("div"); card.className = "integration-stat";
      const span = document.createElement("span"); span.textContent = label;
      const strong = document.createElement("strong"); strong.textContent = text(value);
      card.append(span, strong); integrationSummary.append(card);
    });
    const capabilities = $("integration-capabilities");
    capabilities.replaceChildren();
    m6Proof.capabilities.forEach((item) => {
      const row = document.createElement("div"); row.className = "capability-row";
      const name = document.createElement("span"); name.className = "capability-name"; name.textContent = item.capability_id;
      const scope = document.createElement("span"); scope.className = "capability-scope"; scope.textContent = item.scope;
      row.append(name, scope, chip(item.evidence_class === "SCRIPTED_PROVEN" ? "SCRIPTED SYNTHETIC PROOF" : item.evidence_class));
      capabilities.append(row);
    });
    const coreNote = document.createElement("p"); coreNote.className = "muted"; coreNote.textContent = `${agentCoreCount} AgentCore capabilities remain NOT PROVEN.`;
    capabilities.append(coreNote);
    $("integration-digest").textContent = m6Proof.proof_digest;

    setStatus($("advisory-status"), `${advisory.status} · ${advisory.usefulness_status}`, advisory.mode === "complete" ? "status-scripted" : "status-not-proven");
    $("authority-label").textContent = advisory.authority_label;
    const meta = $("advisory-meta");
    meta.replaceChildren();
    [["Provider", advisory.provider || "—"], ["Model", advisory.model || "—"], ["Requests", advisory.usage.request_count], ["Latency", `${advisory.usage.latency_ms} ms`], ["Cost", `$${Number(advisory.usage.estimated_cost_usd).toFixed(6)}`]].forEach(([label, value]) => {
      const item = document.createElement("span");
      item.className = "meta-item";
      item.textContent = `${label}: ${value}`;
      meta.append(item);
    });
    const hypotheses = $("hypotheses");
    hypotheses.replaceChildren();
    if (!advisory.hypotheses.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No hypothesis was fabricated after the provider failure.";
      hypotheses.append(empty);
    } else {
      advisory.hypotheses.forEach((item) => {
        const card = document.createElement("article");
        card.className = "hypothesis-card";
        const top = document.createElement("div");
        top.className = "hypothesis-top";
        const heading = document.createElement("h3");
        heading.textContent = item.hypothesis_type;
        top.append(heading, chip(item.conclusion));
        card.append(top);
        const explanation = document.createElement("p");
        explanation.textContent = item.explanation;
        card.append(explanation);
        const evidence = document.createElement("small");
        evidence.textContent = `${item.supporting_evidence_ids.length} records support this; ${item.contradicting_evidence_ids.length} rule it out.`;
        card.append(evidence);
        hypotheses.append(card);
      });
    }
    $("advisory-report").textContent = advisory.incident_report || "Provider failure was persisted as degraded; no incident report was invented.";
    const warnings = $("advisory-warnings");
    warnings.replaceChildren();
    advisory.warnings.forEach((item) => { const span = document.createElement("span"); span.textContent = `Warning: ${item}`; warnings.append(span); });

    const detail = $("decision-details");
    detail.replaceChildren();
    [["Classification", decision.classification], ["Initial eligibility", decision.eligibility], ["Allowed action", decision.allowed_action || "NO ACTION"], ["Policy status", decision.policy_status], ["Authoritative sources", decision.authoritative_source_types.join(" · ")], ["Evidence IDs", `${decision.authoritative_evidence_ids.length} admitted records`], ["Lifecycle decisions", (artifact.deterministic_decisions || []).map((item) => `${item.classification} → ${item.allowed_action || "NO ACTION"}`).join(" · ")]].forEach(([label, value]) => {
      const dt = document.createElement("dt"); dt.textContent = label;
      const dd = document.createElement("dd"); dd.textContent = text(value);
      detail.append(dt, dd);
    });
    $("decision-digest").textContent = decision.decision_digest;
    const reasons = $("decision-reasons"); reasons.replaceChildren();
    decision.reason_codes.forEach((item) => { const span = document.createElement("span"); span.className = "reason-code"; span.textContent = item; reasons.append(span); });
    const invariants = $("decision-invariants"); invariants.replaceChildren();
    decision.invariants.forEach((item) => {
      const row = document.createElement("div"); row.className = "invariant";
      const name = document.createElement("span"); name.textContent = text(item.name);
      const result = document.createElement("strong"); result.className = "pass"; result.textContent = item.passed ? "PASS" : "FAIL";
      row.append(name, result); invariants.append(row);
    });

    setStatus($("quorum-status"), artifact.human_control.quorum_state, "status-proven");
    $("approval-boundary").textContent = artifact.human_control.approval_boundary;
    const roles = $("role-approvals"); roles.replaceChildren();
    artifact.human_control.approvals.forEach((item) => {
      const card = document.createElement("article"); card.className = "role-card";
      const role = document.createElement("span"); role.className = "role-name"; role.textContent = item.role; card.append(role);
      const principal = document.createElement("strong"); principal.textContent = item.principal_id; card.append(principal);
      const stage = document.createElement("p"); stage.textContent = `${item.action_id} · ${item.status}`; card.append(stage);
      roles.append(card);
    });

    setStatus($("replay-status"), `${execution.replay_status} · Δ effects ${execution.replay_effect_delta}`, "status-proven");
    const summary = $("execution-summary"); summary.replaceChildren();
    [["Fresh read", execution.fresh_read_status], ["Effects", execution.controlled_effects.length], ["Verification", execution.verification_status], ["Replay", execution.replay_status], ["Final state", execution.final_authoritative_state]].forEach(([label, value]) => { const card = document.createElement("div"); card.className = "execution-stat"; const span = document.createElement("span"); span.textContent = label; const strong = document.createElement("strong"); strong.textContent = text(value); card.append(span, strong); summary.append(card); });
    const effects = $("effects"); effects.replaceChildren(); execution.controlled_effects.forEach((item) => { const card = document.createElement("article"); card.className = "effect-card"; const strong = document.createElement("strong"); strong.textContent = item.effect_type; const span = document.createElement("span"); span.textContent = `${item.execution_id} · idempotency ${item.idempotency_key}`; card.append(strong, span); effects.append(card); });
    const checks = $("postconditions"); checks.replaceChildren(); execution.postconditions.forEach((item) => { const row = document.createElement("div"); row.className = "postcondition"; const check = document.createElement("span"); check.className = "check"; check.textContent = item.status === "PASS" ? "✓" : "!"; const label = document.createElement("span"); label.textContent = `${item.execution_id}: ${item.check}`; row.append(check, label); checks.append(row); });

    const timeline = $("audit-timeline"); timeline.replaceChildren(); $("timeline-count").textContent = `${artifact.audit_timeline.length} immutable records`;
    artifact.audit_timeline.forEach((item) => { const row = document.createElement("li"); row.className = "audit-item"; const number = document.createElement("span"); number.className = "audit-number"; number.textContent = String(item.sequence).padStart(2, "0"); const type = document.createElement("span"); type.className = "audit-type"; type.textContent = item.record_type; const label = document.createElement("span"); label.className = "audit-label"; label.textContent = item.label; const reference = document.createElement("code"); reference.textContent = item.reference; row.append(number, type, label, reference); timeline.append(row); });
    $("artifact-digest").textContent = artifact.artifact_digest;
    const claims = $("claims"); claims.replaceChildren(); artifact.claims.forEach((item) => { const row = document.createElement("article"); row.className = "claim-row"; const copy = document.createElement("div"); const p = document.createElement("p"); p.textContent = item.statement; const refs = document.createElement("small"); refs.textContent = item.source_refs.join(" · "); copy.append(p, refs); row.append(copy, chip(item.evidence_class)); claims.append(row); });
    body.dataset.workspaceReady = "true";
  }

  fetch(`/api/workspace?mode=${encodeURIComponent(mode)}`, { method: "GET", credentials: "same-origin" })
    .then((response) => { if (!response.ok) throw new Error(`artifact request returned ${response.status}`); return response.json(); })
    .then(render)
    .catch((error) => { $("unavailable").hidden = false; $("unavailable-detail").textContent = error.message; body.dataset.workspaceReady = "false"; });
})();
