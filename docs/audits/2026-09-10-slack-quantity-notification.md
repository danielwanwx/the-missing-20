# Distributor Slack quantity notification — scoped acceptance

The v2 notification shows received, held, missing, dispatched, and recorded
delivery-confirmation quantities with the source UOM and case/PO identity.
A missing current selection is labelled as no new selection in this event.
Legacy partial payloads show unavailable fields rather than invented zeros.

Independent Terra review initially rejected the expanded payload because the
old milestone key omitted some displayed fields. The corrected v2 key includes
all five displayed quantities and a versioned notification namespace. Changed
quantities therefore create a meaningful new snapshot; exact same-event replay
keeps its key and does not send again. Twelve focused tests passed under the
primary runner, including changed quantities under an otherwise unchanged
exception, replay identity, and legacy partial-payload rendering. Ruff format,
lint and diff checks passed. Independent re-review returned scoped GO.

Migration limit: the first post-upgrade sync of a legacy case can emit one v2
summary because the namespace changes; subsequent v2 replays are stable. No old
journal was rewritten. The prepared PO19 runtime has no legacy notification keys.
No external notification was sent during this code acceptance. Its actual
provider presentation/readback remains part of the fresh business rehearsal.
This slice is not model-semantic or whole-system recording acceptance.
