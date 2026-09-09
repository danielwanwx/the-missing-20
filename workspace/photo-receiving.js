/* Photo intake is source-driven. No timer invents counts or workflow events. */
(() => {
  const opener = document.getElementById("photo-receiving-open");
  if (!opener) return;
  let returnFocus = opener;
  let returnCaptureId = "";
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  const dialog = node("dialog", "", "photo-receiving-dialog");
  dialog.setAttribute("aria-labelledby", "photo-receiving-title");
  const heading = node("header");
  const title = node("h2", "Photo-assisted receiving");
  title.id = "photo-receiving-title";
  const close = node("button", "Close", "button button-quiet");
  close.type = "button";
  heading.append(title, close);
  const body = node("div", "", "photo-receiving-body");
  const left = node("section");
  const instruction = node("p", "Photograph the complete delivery, up to 20 separate receiving units. Keep cartons and readable labels in frame; hidden contents are not counted.");
  const input = node("input");
  input.type = "file";
  input.accept = "image/jpeg,image/png";
  input.setAttribute("capture", "environment");
  input.setAttribute("aria-label", "Take or choose receiving photo");
  input.hidden = true;
  const choosePhoto = node("button", "Choose receiving photo", "button button-quiet");
  choosePhoto.type = "button";
  choosePhoto.addEventListener("click", () => input.click());
  const arrivalLabel = node("label", "Receiving batch");
  const arrivalSelect = node("select");
  arrivalSelect.setAttribute("aria-label", "Receiving batch");
  arrivalLabel.append(arrivalSelect);
  arrivalLabel.hidden = true;
  let arrivals = null;
  const fileSummary = node("p");
  fileSummary.hidden = true;
  const imageStage = node("div", "", "photo-receiving-image");
  const image = node("img");
  image.alt = "Receiving photo with numbered model observations";
  image.hidden = true;
  imageStage.append(image);
  const privacy = node("p", "Photos are stored in this demo and sent to AWS for analysis. Upload only demo goods.", "photo-receiving-privacy");
  left.append(arrivalLabel, instruction, input, choosePhoto, fileSummary, privacy, imageStage);
  const right = node("section");
  const status = node("strong", "Ready for a photo", "photo-receiving-status");
  status.setAttribute("role", "status");
  const count = node("h3");
  const details = node("p");
  const metrics = node("p", "", "photo-receiving-metrics");
  const notice = node("p", "Count candidates do not change inventory. ERP drafts are not posted stock.");
  const draft = node("button", "Create ERP draft", "button button-primary");
  draft.hidden = true;
  const identity = node("fieldset", "", "photo-identity");
  identity.hidden = true;
  identity.append(node("legend", "Confirm the item"));
  const identityOptions = node("select");
  identityOptions.setAttribute("aria-label", "Item from the configured purchase order");
  const identityNotice = node("p", "The photo did not identify a SKU. Select only if you can confirm the actual goods match this order.");
  const identityButton = node("button", "Confirm item match", "button button-quiet");
  identityButton.type = "button";
  identity.append(identityNotice, identityOptions, identityButton);
  const confirmLabel = node("label", "", "photo-receiving-confirm");
  const confirmReceived = node("input");
  confirmReceived.type = "checkbox";
  confirmLabel.append(confirmReceived, node("span", "I confirm these goods were received and match this ERP draft."));
  confirmLabel.hidden = true;
  const submit = node("button", "Post confirmed receipt", "button button-primary");
  submit.hidden = true;
  const external = node("a", "Open ERP draft ↗");
  external.target = "_blank";
  external.rel = "noopener noreferrer";
  external.hidden = true;
  const handoffList = node("ul", "", "photo-receiving-handoffs");
  handoffList.hidden = true;
  const events = node("ol", "", "photo-receiving-events");
  const technical = node("details", "", "operator-details");
  technical.append(node("summary", "Analysis details"), metrics, events);
  const photoVersions = node("details", "", "operator-details");
  const versionList = node("div", "", "goods-photo-versions");
  photoVersions.append(node("summary", "Earlier photos"), versionList);
  photoVersions.hidden = true;
  const fresh = node("button", "New receiving session", "button button-quiet");
  right.append(status, count, details, notice, identity, draft, external, handoffList, confirmLabel, submit, photoVersions, technical, fresh);
  body.append(left, right);
  dialog.append(heading, body);
  document.body.append(dialog);
  let session = null;
  let busy = false;
  let timer = null;
  let renderedEvents = "";
  let generation = 0;
  let pollController = null;
  let currentFilename = "";
  let identityKey = "";
  let historyKey = "";
  const labels = {
    AWAITING_PHOTO: "Ready for a photo", ANALYZING: "Inspecting your photo…",
    NEEDS_PHOTO: "Another view needed", NEEDS_REVIEW: "Review needed",
    COUNT_CANDIDATE: "Count ready · not received", RECEIPT_PREPARED: "Ready to prepare a receipt",
    UNAVAILABLE: "Analysis unavailable", DRAFT_UNKNOWN: "ERP outcome needs reconciliation",
    DRAFT_VERIFIED: "ERP draft verified",
    SUBMIT_UNKNOWN: "Posting outcome needs reconciliation",
    RECEIPT_SUBMITTED: "Receipt posted and verified",
    DUPLICATE_EVIDENCE: "Already recorded · no second receipt",
  };
  async function request(path, payload, signal) {
    const response = await fetch(`/api/v1/photo-receiving${path}`, payload === undefined ? { signal } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload), signal,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.detail || result.detail || "Photo request failed.");
    return result;
  }
  const scanPanel = node("details", "", "operator-details receiving-scan");
  scanPanel.append(node("summary", "Scan goods"));
  const scanControls = node("div", "", "receiving-scan-controls");
  const scanCode = node("input");
  scanCode.type = "text"; scanCode.maxLength = 100;
  scanCode.placeholder = "Item barcode or carton ID";
  scanCode.setAttribute("aria-label", "Item barcode or carton ID");
  const identify = node("button", "Identify", "button button-quiet");
  const camera = node("button", "Start camera", "button button-quiet");
  const chooseVideo = node("button", "Choose video", "button button-quiet");
  const stopScan = node("button", "Stop scanning", "button button-quiet");
  [identify, camera, chooseVideo, stopScan].forEach((button) => { button.type = "button"; });
  [identify, camera, chooseVideo].forEach((button) => { button.disabled = true; });
  const videoFile = node("input"); videoFile.type = "file"; videoFile.accept = "video/*"; videoFile.hidden = true;
  const video = node("video"); video.muted = true; video.playsInline = true; video.hidden = true;
  const scanStatus = node("p", "A product barcode identifies the item, not the number of cartons.");
  scanStatus.setAttribute("role", "status");
  const scanResult = node("div", "", "receiving-scan-result");
  scanControls.append(scanCode, identify, camera, chooseVideo, stopScan);
  scanPanel.append(scanControls, videoFile, video, scanStatus, scanResult);
  left.insertBefore(scanPanel, imageStage);
  let scanGeneration = 0;
  let scanRequest = null;
  let identifying = false;
  let selectedBarcode = null;
  function haltScan() {
    scanGeneration += 1; scanRequest?.abort(); scanRequest = null;
    capture.stop(); video.hidden = true;
    identifying = false; identify.disabled = false;
  }
  async function identifyCode(code, format, observationMethod = "manual") {
    if (!arrivals || !arrivalSelect.value || busy || identifying) return;
    const activeGeneration = scanGeneration;
    const arrivalId = arrivalSelect.value;
    identifying = true; identify.disabled = true;
    scanRequest = new AbortController();
    const signal = scanRequest.signal;
    scanStatus.textContent = "Looking up the current ERP item and order…";
    try {
      const match = await request("/barcode", { arrival_id: arrivalId, code, format }, signal);
      if (activeGeneration !== scanGeneration) return;
      selectedBarcode = match;
      scanResult.replaceChildren(node("strong", match.item_name), node("p", `${match.item_code} · ${match.item_group || "Item"} · ${match.unit_price} ${match.currency} / ${match.uom}`));
      for (const [label, href] of [["ERP item ↗", match.item_url], ["Purchase order ↗", match.order_url]]) {
        const url = new URL(href);
        if (url.protocol !== "https:") continue;
        const link = node("a", label); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
        scanResult.append(link);
      }
      const alreadyReceived = arrivals.find((arrival) => arrival.arrival_id === arrivalId)?.receipt;
      if (match.kind === "handling_unit" && !alreadyReceived) {
        const response = await request("/scan", { source_event_id: crypto.randomUUID(), arrival_id: arrivalId,
          handling_unit_id: code, occurred_at: new Date().toISOString(),
          observation_method: observationMethod, barcode_format: format }, signal);
        if (activeGeneration !== scanGeneration) return;
        scanStatus.textContent = response.status === "CONFLICT" ? "Conflicting carton evidence · review needed. Stock unchanged."
          : "Carton observation recorded · repeated views do not add stock. Continue with a receiving photo.";
      } else if (alreadyReceived) {
        scanStatus.textContent = "This batch is already received. Identity checked; no second receipt or carton observation created.";
      } else {
        scanStatus.textContent = "Item and order price verified. Photograph the delivery to establish its quantity. Stock unchanged.";
      }
      window.dispatchEvent(new CustomEvent("missing20:receipt-changed"));
    } catch (error) {
      if (activeGeneration === scanGeneration && error.name !== "AbortError") {
        scanResult.replaceChildren(); scanStatus.textContent = error.message;
      }
    } finally {
      if (activeGeneration === scanGeneration) { identifying = false; identify.disabled = false; }
    }
  }
  const capture = new window.M20Barcode.BarcodeCapture({ video, onCode: identifyCode,
    onState: (message) => { scanStatus.textContent = message; } });
  identify.addEventListener("click", () => identifyCode(scanCode.value.trim(), "manual"));
  scanCode.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); identify.click(); } });
  camera.addEventListener("click", () => { haltScan(); video.hidden = false; void capture.start(); });
  chooseVideo.addEventListener("click", () => videoFile.click());
  videoFile.addEventListener("change", () => { const file = videoFile.files[0]; if (file) { haltScan(); video.hidden = false; void capture.start(file); } videoFile.value = ""; });
  stopScan.addEventListener("click", () => { haltScan(); scanStatus.textContent = "Scanning stopped"; });
  scanPanel.addEventListener("toggle", () => { if (!scanPanel.open) haltScan(); });
  window.addEventListener("pagehide", haltScan);
  function handoffLabel(handoff) {
    const jira = handoff.route.startsWith("jira-receiving:");
    const provider = jira ? "Jira" : handoff.route.startsWith("celigo-slack:")
      ? "Slack via Celigo" : handoff.route.startsWith("airtable-receiving:") ? "Airtable" : "External service";
    if (handoff.status !== "VERIFIED") return `${provider} · ${handoff.status === "UNKNOWN" ? "checking delivery" : "waiting to sync"}`;
    const action = jira ? ({ create: "review opened", comment: "evidence updated", resolve: "review resolved" }[handoff.evidence?.operation] || "review synced") : "synced";
    return `${provider} · ${action} ↗`;
  }
  function render(state) {
    // A slow status GET must not overwrite the newer upload response.
    if (session?.id === state.id && (session.events?.length || 0) > (state.events?.length || 0)) return;
    session = state;
    identify.disabled = busy || identifying || !arrivals;
    camera.disabled = chooseVideo.disabled = busy || !arrivals;
    status.textContent = labels[state.status] || state.status;
    dialog.dataset.status = state.status;
    count.textContent = state.count == null ? "" : `${state.count} visible ${state.analysis?.assessment?.receiving_unit || "object"}${state.count === 1 ? "" : "s"}`;
    count.hidden = state.count == null;
    const assessment = state.analysis?.assessment;
    identity.hidden = !(assessment?.countable && assessment?.visibility === "clear"
      && !assessment.item_code && !state.identity_confirmation
      && ["COUNT_CANDIDATE", "NEEDS_REVIEW"].includes(state.status));
    identityButton.disabled = busy;
    if (!identity.hidden && identityKey !== `${state.id}:${state.version}`) {
      identityKey = `${state.id}:${state.version}`;
      void loadIdentity(identityKey);
    }
    identityButton.disabled = busy || !identityOptions.options.length;
    photoVersions.hidden = !(state.image_version > 1);
    if (!photoVersions.hidden && historyKey !== `${state.id}:${state.image_version}`) {
      historyKey = `${state.id}:${state.image_version}`;
      void loadPhotoVersions(state.id, historyKey);
    }
    const guidance = {
      COUNT_CANDIDATE: "The count is not linked to an eligible purchase order. Retake one photo with both the full carton and a readable item label visible.",
      NEEDS_PHOTO: "Take another photo with every item fully visible, separated and in frame.",
      NEEDS_REVIEW: "The item or purchase order could not be verified. Check the label and order before receiving.",
      RECEIPT_PREPARED: "The item and purchase order match. A draft receipt can be prepared; stock remains unchanged.",
      DRAFT_VERIFIED: "Your draft was found in ERPNext. Open it to review; inventory has not been posted.",
      DRAFT_UNKNOWN: "The ERP draft has not been verified. Reconcile the original request; do not create another receipt.",
      UNAVAILABLE: "Photo analysis could not complete. Try again; no stock has changed.",
      SUBMIT_UNKNOWN: "The posting outcome is uncertain. Reconcile the existing receipt; do not receive these goods again.",
      RECEIPT_SUBMITTED: "ERPNext confirms the submitted receipt and stock ledger entries.",
      DUPLICATE_EVIDENCE: "This photo is already recorded. Open the original observation instead of receiving it again.",
    };
    details.textContent = [state.identity_confirmation?.item_code
      ? `${state.identity_confirmation.item_code} · confirmed by operator` : assessment?.item_code, assessment?.supplier_lot,
      guidance[state.status] || ""].filter(Boolean).join(" · ");
    metrics.textContent = state.analysis
      ? `${state.analysis.model} · ${(state.analysis.latency_ms / 1000).toFixed(1)}s · ${state.analysis.usage?.totalTokens ?? "—"} tokens`
      : "";
    if (state.digest) {
      const url = `/api/v1/photo-receiving/image?id=${encodeURIComponent(state.id)}&v=${state.digest}`;
      if (image.getAttribute("src") !== url) image.src = url;
      image.hidden = false;
    } else { image.hidden = true; image.removeAttribute("src"); }
    fileSummary.hidden = !state.digest;
    fileSummary.textContent = state.digest ? `Uploaded: ${currentFilename || "receiving photo"}` : "";
    choosePhoto.textContent = state.digest ? "Take another view" : "Choose receiving photo";
    choosePhoto.disabled = busy || Boolean(state.draft_attempted);
    if (state.work_item) {
      arrivalSelect.value = state.work_item.arrival_id;
      instruction.textContent = `${state.work_item.arrival_id} · ${state.purchase_order} · ${state.work_item.item_code}. Photograph this batch; another view does not create another receipt.`;
      fresh.textContent = "Reopen selected batch";
    }
    imageStage.querySelectorAll(".photo-object-marker").forEach((marker) => marker.remove());
    (assessment?.objects || []).forEach((item, index) => {
      const marker = node("span", String(index + 1), "photo-object-marker");
      marker.style.left = `${item.x * 100}%`;
      marker.style.top = `${item.y * 100}%`;
      marker.title = item.description;
      imageStage.append(marker);
    });
    draft.hidden = !state.drafts_enabled || !["RECEIPT_PREPARED", "DRAFT_UNKNOWN"].includes(state.status);
    draft.textContent = state.status === "DRAFT_UNKNOWN" ? "Reconcile ERP draft" : "Create ERP draft";
    draft.disabled = busy;
    const canSubmit = ["DRAFT_VERIFIED", "SUBMIT_UNKNOWN"].includes(state.status);
    confirmLabel.hidden = !canSubmit || state.status === "SUBMIT_UNKNOWN";
    submit.hidden = !canSubmit;
    submit.textContent = state.status === "SUBMIT_UNKNOWN" ? "Reconcile posted receipt" : "Post confirmed receipt";
    submit.disabled = busy || (state.status !== "SUBMIT_UNKNOWN" && !confirmReceived.checked);
    notice.textContent = state.status === "RECEIPT_SUBMITTED"
      ? "Received stock is verified. Billing and physical dispatch remain separate steps."
      : "Count candidates do not change inventory. ERP drafts are not posted stock.";
    external.hidden = !state.draft?.url;
    external.textContent = state.status === "RECEIPT_SUBMITTED" ? "Open posted ERP receipt ↗" : "Open ERP draft ↗";
    if (state.draft?.url && new URL(state.draft.url).protocol === "https:") external.href = state.draft.url;
    handoffList.hidden = !(state.handoffs || []).length;
    handoffList.replaceChildren(...(state.handoffs || []).map((handoff) => {
      const row = node("li");
      const verified = handoff.status === "VERIFIED";
      const label = handoffLabel(handoff);
      let safeUrl = null;
      try { const url = new URL(handoff.evidence?.url); if (url.protocol === "https:") safeUrl = url.href; } catch (_) { /* No verified external link yet. */ }
      const content = node(verified && safeUrl ? "a" : "span", label);
      if (verified && safeUrl) { content.href = safeUrl; content.target = "_blank"; content.rel = "noopener noreferrer"; }
      row.append(content); return row;
    }));
    const signature = JSON.stringify(state.events);
    if (signature !== renderedEvents) {
      const atBottom = events.scrollHeight - events.scrollTop - events.clientHeight < 30;
      events.replaceChildren(...(state.events || []).map((event) => {
        const row = node("li");
        row.append(node("time", new Date(event.at).toLocaleTimeString()), node("span", event.detail));
        return row;
      }));
      if (atBottom) events.scrollTop = events.scrollHeight;
      renderedEvents = signature;
    }
    input.disabled = busy || Boolean(state.draft_attempted);
    fresh.disabled = busy;
    void refreshGallery();
  }
  function report(error) { status.textContent = error.message; dialog.dataset.status = "UNAVAILABLE"; }
  async function start() {
    if (busy) return;
    haltScan(); scanResult.replaceChildren(); selectedBarcode = null;
    busy = true; input.disabled = fresh.disabled = true;
    const currentGeneration = ++generation;
    clearInterval(timer); pollController?.abort();
    try {
      const state = await request("", arrivals ? { arrival_id: arrivalSelect.value } : {});
      if (currentGeneration === generation) { currentFilename = ""; confirmReceived.checked = false; render(state); input.value = ""; }
    } finally { busy = false; if (session) render(session); fresh.disabled = false; }
  }
  async function loadArrivals() {
    const result = await request("/arrivals");
    arrivals = result.status === "CONFIGURED" ? result.arrivals : null;
    scanPanel.hidden = !arrivals;
    arrivalLabel.hidden = !arrivals;
    if (arrivals) arrivalSelect.replaceChildren(...arrivals.map((arrival) => {
      const option = node("option", `${arrival.arrival_id} · ${arrival.expected_quantity} ${arrival.uom} planned${arrival.receipt ? " · received" : ""}`);
      option.value = arrival.arrival_id; return option;
    }));
  }
  async function openReceiving(trigger) {
    returnFocus = trigger; returnCaptureId = "";
    dialog.showModal();
    try { await loadArrivals(); if (!session) await start(); else render(session); } catch (error) { report(error); }
  }
  opener.addEventListener("click", () => openReceiving(opener));
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", () => {
    haltScan();
    const refreshedCapture = Array.from(document.querySelectorAll("[data-capture-id]"))
      .find((item) => item.dataset.captureId === returnCaptureId);
    (returnFocus?.isConnected ? returnFocus : refreshedCapture || opener).focus();
  });
  fresh.addEventListener("click", () => start().catch(report));
  arrivalSelect.addEventListener("change", () => start().catch(report));
  input.addEventListener("change", async () => {
    const file = input.files[0];
    if (!file || !session || busy) return;
    if (file.size > 5 * 1024 * 1024) { report(new Error("Choose a photo smaller than 5 MB.")); return; }
    currentFilename = file.name;
    busy = true;
    input.disabled = fresh.disabled = true;
    status.textContent = "Uploading photo…";
    const uploadGeneration = generation;
    const uploadSessionId = session.id;
    pollController = new AbortController();
    let polling = false;
    timer = setInterval(async () => {
      if (polling) return;
      polling = true;
      try {
        const state = await request(`?id=${encodeURIComponent(uploadSessionId)}`, undefined, pollController.signal);
        if (generation === uploadGeneration && session?.id === uploadSessionId) render(state);
      } catch { /* POST reports errors. */ }
      finally { polling = false; }
    }, 1500);
    try {
      const encoded = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1]);
        reader.onerror = () => reject(new Error("Could not read this photo."));
        reader.readAsDataURL(file);
      });
      const state = await request("/upload", { id: uploadSessionId, image: encoded });
      if (generation === uploadGeneration) render(state);
    } catch (error) { report(error); }
    finally {
      clearInterval(timer); pollController.abort(); busy = false;
      input.disabled = Boolean(session?.draft_attempted); fresh.disabled = draft.disabled = false;
      input.value = "";
      if (session) render(session);
    }
  });
  draft.addEventListener("click", async () => {
    if (busy || !session) return;
    busy = true; draft.disabled = input.disabled = fresh.disabled = true;
    try { render(await request("/draft", { id: session.id })); } catch (error) { report(error); }
    finally { busy = false; draft.disabled = fresh.disabled = false; input.disabled = Boolean(session?.draft_attempted); }
  });
  async function loadIdentity(key) {
    identityButton.disabled = true;
    identityOptions.replaceChildren();
    try {
      const result = await request("/identity");
      if (identityKey !== key) return;
      identityOptions.replaceChildren(...(result.items || []).map((item) => {
        const option = node("option", `${item.item_code} · ${item.remaining_quantity} ${item.uom} remaining`);
        option.value = item.item_code; return option;
      }));
      identityNotice.textContent = identityOptions.options.length
        ? `Order ${result.purchase_order}. Confirm only if the physical goods match this item.`
        : "No receivable lines remain on the configured order.";
      identityButton.disabled = !identityOptions.options.length;
    } catch { identityNotice.textContent = "A receivable demo purchase order must be configured before matching goods."; }
  }
  async function loadPhotoVersions(id, key) {
    versionList.textContent = "Loading retained photos…";
    try {
      const result = await request(`/history?id=${encodeURIComponent(id)}`);
      if (historyKey !== key) return;
      versionList.replaceChildren(...(result.versions || []).map((version) => {
        const link = node("a", `Photo ${version.image_version} · ${labels[version.status] || version.status} ↗`);
        link.href = `/api/v1/photo-receiving/image?id=${encodeURIComponent(id)}&image_version=${version.image_version}`;
        link.target = "_blank"; link.rel = "noopener noreferrer";
        return link;
      }));
    } catch { versionList.textContent = "Retained photos could not be loaded."; }
  }
  identityButton.addEventListener("click", async () => {
    if (busy || !session || !identityOptions.value) return;
    busy = true; identityButton.disabled = true;
    try {
      const result = await request("/confirm-identity", { id: session.id,
        item_code: identityOptions.value, expected_version: session.version, confirm_match: true,
        ...(selectedBarcode?.arrival_id === arrivalSelect.value
          && selectedBarcode?.item_code === identityOptions.value
          ? { barcode_evidence_id: selectedBarcode.evidence_id } : {}) });
      busy = false; render(result);
    } catch (error) { report(error); }
    finally { busy = false; identityButton.disabled = false; }
  });
  confirmReceived.addEventListener("change", () => { submit.disabled = busy || !confirmReceived.checked; });
  submit.addEventListener("click", async () => {
    if (busy || !session || (session.status !== "SUBMIT_UNKNOWN" && !confirmReceived.checked)) return;
    busy = true; submit.disabled = fresh.disabled = true;
    try {
      render(await request("/submit", {
        id: session.id, receipt_name: session.draft?.name,
        expected_version: session.version, confirm_received: true,
      }));
      window.dispatchEvent(new CustomEvent("missing20:receipt-changed"));
    } catch (error) { report(error); }
    finally { busy = false; fresh.disabled = false; if (session) render(session); }
  });
  const gallery = document.getElementById("goods-gallery-items");
  const galleryStatus = document.getElementById("goods-gallery-status");
  let galleryBusy = false;
  let gallerySignature = "";
  async function reopen(id, trigger) {
    if (busy) return;
    returnFocus = trigger; returnCaptureId = id;
    busy = true; clearInterval(timer); pollController?.abort(); generation += 1;
    try {
      await loadArrivals(); currentFilename = ""; confirmReceived.checked = false;
      const state = await request(`?id=${encodeURIComponent(id)}`);
      busy = false; render(state); dialog.showModal();
    } catch (error) { dialog.showModal(); report(error); }
    finally { busy = false; }
  }
  function refreshOpenCapture(captures) {
    if (!dialog.open || busy || !session) return;
    const latest = captures.find((capture) => capture.id === session.id);
    if (latest && (latest.version > session.version || (latest.version === session.version
      && JSON.stringify(latest.handoffs) !== JSON.stringify(session.handoffs)))) render(latest);
  }
  async function refreshGallery() {
    if (!gallery || galleryBusy) return;
    galleryBusy = true;
    try {
      const result = await request("/list?limit=50");
      const captures = (result.captures || []).filter((capture) => capture.digest);
      refreshOpenCapture(captures);
      const signature = JSON.stringify(captures.map((capture) => [capture.id, capture.version, capture.digest]));
      galleryStatus.textContent = captures.length ? `${captures.length} receiving observations` : "Photograph a delivery to identify it and prepare receiving.";
      if (signature === gallerySignature) return;
      gallerySignature = signature;
      gallery.replaceChildren(...captures.map((capture) => {
        const button = node("button", "", "goods-capture");
        button.type = "button";
        button.dataset.captureId = capture.id;
        const thumbnail = node("img");
        thumbnail.src = `/api/v1/photo-receiving/image?id=${encodeURIComponent(capture.id)}&v=${encodeURIComponent(capture.digest)}`;
        thumbnail.alt = capture.analysis?.assessment?.item_code || "Receiving observation";
        thumbnail.loading = "lazy";
        const text = node("span");
        text.append(node("strong", capture.analysis?.assessment?.item_code || "Goods photo"), node("span", labels[capture.status] || capture.status));
        button.append(thumbnail, text);
        button.addEventListener("click", () => reopen(capture.id, button));
        return button;
      }));
    } catch { galleryStatus.textContent = "Photo history unavailable. Open receiving to retry."; }
    finally { galleryBusy = false; }
  }
  document.getElementById("goods-gallery-add")?.addEventListener("click", (event) => openReceiving(event.currentTarget));
  // Background preparation can finish after the upload/identity POST. Read
  // persisted local state; never synthesize a receipt or a progress event.
  const galleryTimer = setInterval(() => {
    if (document.visibilityState === "visible" && !busy) void refreshGallery();
  }, 3000);
  window.addEventListener("pagehide", () => clearInterval(galleryTimer), { once: true });
  void refreshGallery();
})();
