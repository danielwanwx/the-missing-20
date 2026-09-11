# The Missing 20 — submission film storyboard

Status: first reviewable script framework; not recorded or rendered.
Target: 4:50, English narration and captions, 16:9, 1920×1080 delivery, 30 fps.
Audience: Agents for Humans judges and a parts distributor's warehouse/operations manager.
Core message: Turn fragmented receiving evidence into a reviewable customer-fulfillment outcome across systems.

## Creative direction

Open on the manager's dilemma, then let the product provide the evidence. The recurring visual motif is a customer commitment of 40 parts: 20 + 18 received, a quality exception, a separate replacement of 2, and customer fulfillment of 25 + 15. This is an editorial diagram of recorded events, not a fabricated live UI state.

Use the application's existing dark interface, restrained lime accents for verified state and amber for the observed exception. Typography: existing Geist family. Use clean cuts, slow targeted crops, and short match cuts between matching record IDs. No stock warehouse montage, decorative 3D dashboards, invented measurements, or simulated typing of model answers. Keep the product visible for most of the film.

Split-screen convention: product decision or evidence on the left, its actual source record on the right. At 1080p, crop each side to one legible record detail; alternate to full screen for tables. Never show four unreadable applications simultaneously. Keep a small PO19 case badge through the main story. Separate historical demonstrations carry a different badge throughout.

All shot timings below include transitions. Exact timing will be locked after a scratch voice read. This framework deliberately stops before capture, paid speech synthesis, installation, or rendering.

## Evidence lanes

- **Main business story:** completed PO19, `M20-DIST-COMPONENT-RECORDING-20260910`. Actual isolated-demo ERP and external records; counts, inspections, and delivery confirmations are synthetic inputs. Repaired continuation; no new events during capture.
- **Separate feature inserts:** dashboard/investigation and photo receiving may use retained earlier cases only after their runtime and source are checked. Label `Separate feature demonstration` with the actual case. Never attribute their stock or invoice numbers to PO19.
- **Model evaluation insert:** previously captured real Opus English answers about PO18. Label `Prior model evaluation · PO18 · recorded answer`. Do not stage these answers inside the empty PO19 chat. Q1–Q4 are available; show one answer plus a brief real follow-up excerpt if readable. No new paid inference.
- **Editorial graphics:** diagrams and callouts derived from source records are labelled `Recorded sequence` or `Architecture`. They are presentation graphics, not application functionality or a performance benchmark.

## Shot-by-shot framework and voiceover

### 01 · 0:00–0:18 · A human problem

**Picture:** Tight crop of the recorded 20 + 18 receipt evidence. A restrained overlay reads `40 promised. 38 initially counted.` Cut to the product name and a glimpse of the full operations workspace.

**Voiceover:** “The cartons arrived. But can we fulfill the customer orders? For a parts distributor, that answer is scattered across receipt counts, quality checks, customer contracts, and several business systems. The Missing 20 brings that work into one operational flow.”

**On-screen footer:** `Isolated demo tenant · Simulated operational inputs · Completed-case walkthrough`.

### 02 · 0:18–0:38 · Orient the judge

**Picture:** Full PO19 operations view, then a deliberate left-to-right crop: quantities and process diagram, customer commitments, evidence/history. Brief dashboard navigation insert only if its different case badge remains visible; no old revenue figures.

**Voiceover:** “The manager starts with a readable view of the order: what was received, what is held, what can ship, and which commitments remain. This walkthrough follows a completed demo case, with real records in isolated ERP and collaboration systems.”

**Proof:** Main PO19 badge and source status. Dashboard insert is a feature overview, not the PO19 source.

### 03 · 0:38–0:58 · Capture once, retain evidence

**Picture:** Separate photo-receiving feature insert: existing image, extracted fields and record preview. Show scanner/barcode control and English dictation control as interface features, without processing a new event or claiming an untested recognition result. Match cut back to PO19's recorded event form/history.

**Voiceover:** “Receiving begins with evidence. The interface supports photo and barcode capture, while the operations view records counts, lots, and inspection events. Each input stays identifiable, so the manager can inspect the evidence behind the resulting state.”

**Capture gate:** Show a real retained extraction only if available. Otherwise show the capture controls and say “capture interface,” not “successful extraction.” Do not imply one-box receiving is the 40-part case.

### 04 · 0:58–1:23 · Cartons are not parts

**Picture:** Left: LOT-A 20 and LOT-B 18 activity rows. Right: matching Purchase Receipts. Editorial sequence reveals `20 + 18 = 38`, then `2 missing`. Open resolved shortage history; highlight the actual history row, not a fake active alert.

**Voiceover:** “Four cartons did not mean forty parts. The first two lots contained twenty and eighteen. The system preserves that two-part shortage rather than confusing package count with inventory. A later replacement is recorded separately, so the final total still has an explainable history.”

**Proof:** PO19 receipt links; replacement LOT-C has 2 parts and one extra carton. Current carton total is five.

### 05 · 1:23–1:48 · Quality changes what can ship

**Picture:** Left: recorded failed sample and resolved hold. Right: rejected Quality Inspection, then accepted whole-lot reinspection. Annotate the source value 10.3 against 9.9–10.1 only when visible in the verified record. Amber highlight follows the evidence, then release state.

**Voiceover:** “Quantity is only half the decision. A failed sample placed the second lot on hold. A later whole-lot reinspection supported release. A failed sample is not proof that every part was defective, and the system keeps the original failure alongside the later result.”

**Proof:** Inspection scope, actual document IDs, recorded measurements. Do not animate the current zero-alert page into a false live failure.

### 06 · 1:48–2:15 · Contracts make the decision practical

**Picture:** Contract policy on left, customer orders on right. Emphasize promised date, partial-shipment permission and minimum/remainder terms. Animate source-derived shipment sequence A20 → A5 / B13 → B2, ending A25 / B15. Show retained agent selection with its original Nova attribution.

**Voiceover:** “The allocation decision follows written customer terms: promised date first, permitted partial shipments, minimum quantities, and a final remainder rule. Customer A receives twenty, then five. Customer B receives thirteen, then the final two. The agent selects within the feasible contract plan; the application applies and verifies the business effects.”

**Proof:** Do not label historical Nova allocations as Opus decisions. Current plan has zero additional allocation; the sequence is historical evidence.

### 07 · 2:15–2:38 · Show actual ERP effects

**Picture:** Match-cut from fulfillment row to actual ERPNext Pick List, Delivery Note and Shipment. Final remainder: Pick `STO-PICK-2026-00015`, Delivery Note `MAT-DN-2026-00017`, Shipment `SHIPMENT-00015`, quantity 2. Fullscreen one useful document crop, not a list of API responses.

**Voiceover:** “The result is visible in native ERP documents: pick lists, delivery notes, and shipments. The final two-part remainder has its own records. We verify the source state after the action, rather than treating an agent's explanation as proof that inventory moved.”

### 08 · 2:38–3:14 · Cross-app proof, not logos

**Picture:** Three 9-second match-cut pairs plus a 6-second Celigo segment, with 3 seconds reserved for transitions within this 36-second shot. Left stays on the PO19 handoff card; right opens the actual linked application. Airtable `recWHcDEadZrLyRBI`; Jira `QRC-4`; Slack message `1789088499.513429`. Celigo: show its matching integration execution if directly available; otherwise retain the accurate `Slack via Celigo` route and journal evidence, with an on-screen `Retained route verification · execution screen not shown` label, not an unrelated run.

**Voiceover:** “The same operation also leaves evidence where people already work. Airtable holds the linked operating record. Jira carries the exception and its resolution evidence. Slack receives the coordinated update through Celigo. We can follow each link back to the same case, connecting the warehouse outcome with the team's existing tools.”

**Capture gate:** Every external screen must match PO19. Pre-open tabs and hide account menus. An unavailable Celigo execution UI remains an explicitly pending capture item; a logo alone is not proof of a run.

### 09 · 3:14–3:29 · Commercial clarity

**Picture:** Fullscreen commercial panel, then crop purchase order USD160 and customer order values USD150 / USD90. Hold the visible missing-invoice state briefly.

**Voiceover:** “Commercial records stay precise: a hundred and sixty dollars in purchase-order value, and two customer orders totaling two hundred and forty. Invoices are missing in this case. Order value is not revenue.”

### 10 · 3:29–3:59 · Show the agent's judgment

**Picture:** Distinct title `Prior model evaluation · PO18`. Show verbatim readable excerpts from actual English Q1 and Q4 reports, with question, answer, model and recorded status. Emphasize the answer separating recorded confirmations from physical receipt. Brief return to the current English voice controls as an interface insert, without synthesized audio pretending to be a live agent response.

**Voiceover:** “In a separate recorded model evaluation, we asked the agent to explain the receipt history and what delivery confirmations actually prove. The English answers distinguish recorded events from independently verified physical receipt. These are captured Bedrock answers, not a live query in this take. That distinction matters when people act on an answer.”

**Editing rule:** Use original answer text, visually excerpted with an ellipsis where cut. Never rewrite an answer and present it as model output. Exclude the failed Q5 timeline enumeration and out-of-scope Chinese stress question.

### 11 · 3:59–4:23 · Make the engineering inspectable

**Picture:** Planned separate investigation-workspace capture, pending runtime/source verification: left source rail and highlighted graph node; center findings/timeline; right selected context, tools/execution log and manager decision panel. Then a compact accurate architecture card: `Strands + Bedrock → evidence + contract decision → application execution → ERP readback + external handoffs`.

**Voiceover:** “Behind the interface, Strands coordinates evidence tools and Bedrock reasoning. The investigation workspace exposes sources, findings, and execution history. Contract-constrained fulfillment and manager-gated recovery are distinct paths. The important boundary is visible: a proposed answer is separate from an applied action and its verified result.”

**Capture gate:** The older manager-gated recovery workspace is a separate feature demonstration. Do not imply the PO19 allocation required that manager approval, or show AgentCore deployment as the current direct Bedrock runtime.

### 12 · 4:23–4:40 · Close the business loop

**Picture:** Return to PO19 full-screen; emphasize 40 received, 40 dispatched, A25/B15, no current hold/shortage, and current-case completion bars. Keep `Synthetic delivery confirmations` visible. Show resolved evidence history, not a claim that no exception ever occurred.

**Voiceover:** “Back in our case: forty received, forty dispatched, customer commitments fulfilled in the recorded workflow, and no remaining stock hold or shortage. The complete history stays available, including the exception and recovery. Delivery confirmations here are simulated evidence.”

### 13 · 4:40–4:50 · A memorable promise

**Picture:** Product mark, readable repository address, three restrained verbs: `Receive. Resolve. Fulfill.` Keep the live product as the background instead of a generic technology animation.

**Voiceover:** “The Missing 20 helps parts distributors turn scattered operational evidence into a clear, reviewable fulfillment outcome. Receive. Resolve. Fulfill.”

## Complete frontend and app coverage map

Coverage means each user-facing capability has a deliberate visual slot, not every button is exercised or every capability is certified. Details can live in submission screenshots and the repository without extending the required film beyond five minutes.

| Surface / capability | Shot | Evidence mode / capture requirement |
| --- | --- | --- |
| Dashboard, supply-chain flow, system health, exception node highlight | 02, 11 | Separate feature demo; inspect actual state; do not synthesize healthy/red states |
| Left source rail / inventory / source cards | 02, 11 | Visible source and case labels |
| Center investigation map, findings and lifecycle | 11 | Retained case; capture pending runtime/source check; highlight only an actual selected node |
| Right context, conversation, activity/tools and decision panels | 10, 11 | Real retained context/trace; no new investigation |
| Reconciliation timeline, graphs and evidence history | 04, 11 | Recorded sequence; earlier case distinctly labelled |
| Operations quantity grid and stage flow | 02, 04, 12 | Current PO19 |
| Current-case benchmark diagram / completion bars | 12 | 40/40 source-backed; never industry/savings benchmark |
| Photo receiving / image evidence / preview | 03 | Separate retained case; actual extraction if available |
| Barcode/scanner and English voice controls | 03, 10 | Interface demonstration; recognition/playback not yet capture-verified |
| Arrival/inspection/event form | 03, 04, 05 | Existing form/history only; never resubmit events |
| Lot quality, hold/release, manager alerts and resolved alerts | 04, 05, 12 | Real history, no invented active alert |
| Written contracts, partial allocation, final remainder | 06 | PO19 contracts + original historical selection |
| Pick/dispatch/delivery and native source documents | 07, 12 | Same-case actual ERPNext screens |
| Invoice/order-value panel | 09 | Missing is shown as missing |
| Airtable | 08 | Actual case record UI |
| Jira | 08 | Actual QRC-4 UI and resolution evidence |
| Slack | 08 | Actual same-case message UI |
| Celigo | 08 | Matching execution UI if accessible; otherwise explicit route/evidence only |
| Public route/weather/port context, if visible | 02 | Secondary optional insert; do not imply it caused this shortage |
| Demo controls, settings, metrics, resize/focus utilities | 02, 11 | Brief navigation/focus visible; not independent business claims |

## Production workflow after script review

1. Freeze source case/revision; complete a screen-by-screen capture sheet. Mark every shot captured, blocked, or substituted. Do not spend model credit to improve a transition.
2. Capture clean UI footage in short segments. Wait for source loading before each take. Record raw segments before adding editorial graphics. Preserve originals and shot-to-file provenance privately.
3. Time the script using a scratch read. Trim repeated narration before accelerating speech. The 4:50 total already leaves ten seconds under the official 5:00 limit; all cuts and transitions must fit inside the listed scene durations.
4. Generate ElevenLabs English voiceover per approved scene, using the user's API credential server-side. Choose a clear, calm business narrator; audition only a short sample before the full script. Voice ID and pronunciation are still to be selected. No API key is requested in chat or written to Git.
5. Assemble with HyperFrames for deterministic titles, crops, split screens and captions; use FFmpeg for final encoding/muxing if needed. Install the required workflow only when composition work begins. No editor installation is necessary for this script deliverable.
6. Add English captions from final audio, subtle transitions and optional properly licensed low-level music. As creative targets, keep narration intelligible, avoid crowded captions, and leave records readable for several seconds.
7. Review the actual rendered video: duration, English text/audio, legibility, matching case IDs, factual narration, source labels, no exposed credentials, no invented live responses. Then preview the final public version before upload/submission.

## Capture gaps to resolve before calling the film complete

- PO19 live operations view is verified; initial load can be slow.
- External record identifiers/readbacks are verified, but every native-app shot must be framed and captured.
- Matching Celigo execution screen has not been capture-verified.
- Earlier dashboard/investigation and photo-receiving inserts need a clean runtime/case check before filming.
- English voice-control activation and playback are not yet verified in the final footage; interface visibility alone does not establish them.
- No actual film, ElevenLabs audio, captions, public upload, or final submission exists from this script step.

## Reference and review boundary

See [reference research](../2026-09-10-video-reference-research.md) for verified award sources, accessible video material and transcript-access limitations. Presentation choices in this storyboard are our synthesis, not a claim that a particular editing style caused an award.

The official [competition rules](https://agentsforhumans.devpost.com/rules) require a working-project demonstration and a pitch covering the problem, audience and importance in a public video of at most five minutes. The project must function as depicted. Professional production quality is the creative target; production deployment, comprehensive accuracy and winning are not established by a polished edit.
