# Public receiving-photo development fixtures

These six original JPEGs are public Wikimedia photographs, **not pictures of our
demo warehouse**. File IDs intentionally do not contain counts or expected outcomes.
Only normalized JPEG bytes and the generic receiving prompt reach Strands; source
titles, filenames, license metadata and expected results never reach the model.

## Rights and provenance

These photographs are excluded from the repository's MIT license. The adjacent
[manifest](manifest.json) records the original page/download, author, exact image
license/link, any source-side modification and SHA-256 for each file. Redistribution
must retain those credits and the original applicable license. No local cropping,
compositing or label fabrication was performed. Intake applies EXIF orientation,
resizes to at most 1600 px, removes metadata and re-encodes JPEG; the original files
remain intact. See the [source research](../../../docs/research/2026-09-07-public-photo-fixture-sources.md).

## Predeclared cases

| ID | Input | Expected behavior |
| --- | --- | --- |
| p01 | Four separated batteries, different brands | Four visible pieces; no invented ERP SKU |
| p02 | One bearing assembly | One piece, not its internal steel balls |
| p03 | Overlapping batteries | Ask to separate them; no accepted receiving count |
| p04 | Cropped, blurred battery scene | Ask for a wider complete view |
| p05 | One open carton | One carton, not an inferred quantity of contents |
| p06 | Outdoor sky | Ask for actual receiving goods |

Counts and eligibility are manual visual annotations, not warehouse ground truth.
They were set before the matrix's first model run. The set is small, selected and
used during development; it is not a held-out accuracy benchmark. A photograph of
a product does not prove delivery, ownership, an ERP SKU or functional condition.

## Repeatable checks

From the repository root:

```sh
.venv/bin/python -m pytest tests/test_photo_receiving.py tests/test_public_photo_receiving.py
.venv/bin/python scripts/photo_receiving_eval.py --output artifacts/agent/photo-public-new-run.json
```

The first command is offline and uses **explicit test doubles** for the model; it
checks decode, metadata removal, states, duplicate uploads, retakes and no writes.
It is not a perception score. The second invokes actual AWS Bedrock via Strands
using the configured AWS profile; it incurs normal model usage and sends only these
public pictures. It runs the real durable intake service in fresh temporary storage
with **no ERP adapter** and records every success/failure, source/code hashes,
provider, usage, latency, state transitions and duplicate-upload behavior. Missing
AWS access fails rather than silently substituting a response.

Use `--repeats 3` for repeatability and `--case p04` for a bounded diagnostic run.
`--model-id` allows an explicit model comparison within the already authorized AWS
environment; it does not grant access, install a model or change the running app.
Old reports are never overwritten. Retake-text presence is checked automatically;
whether the words give a useful instruction still requires reading the output.

Final phone photos, SKU/lot extraction, batch identity, real ERP draft acceptance
and any stock posting remain separate acceptance tests. They do not block this
public-fixture development loop, and these tests do not waive those final gates.
