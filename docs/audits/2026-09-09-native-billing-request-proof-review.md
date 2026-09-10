# Native billing requests and response validation

Independently accepted as a pure adapter prerequisite. This change adds strict
insert-record restoration, complete acknowledged-draft and submitted-readback
values, and a full-document native submit request derived from the acknowledged
draft. It performs no ERP call and does not establish response provenance.

The response factories reuse the existing MAPPED, DRAFT and SUBMITTED invoice
validator with the same bill basis, PO and PR. They do not replace the later
coordinator's responsibility to supply its own actual insert response or to
verify fresh commercial facts and exact GL/SLE effects.

Independent review initially rejected the draft factory: an altered bill digest
or request bill number could be paired with the original valid draft. The
submitted factory similarly accepted a mismatched prior draft. Three regression
cases failed before correction and now reject those tuples. Shared validation
was reused; no new financial-rule copy or model-based validator was added.

The final native module has18 passing tests. The independent reviewer also ran
the37-test native/journal companion suite and reproduced rejection of all three
original counterexamples. Primary Ruff format/check and strict mypy passed for
the four companion files. The combined frozen candidate passed all1,853 Python
tests in63.79 seconds; this is a companion-candidate regression, not proof of a
real invoice, UI integration or full finalization. Four multiprocessing fork
deprecation warnings were retained; the tests completed normally.

Frozen native source SHA256:
`46bdf08a83aa060285a45c23731a3ca3ac8a3254d1cba933393b3eb0cbed7486`.
Native test SHA256:
`f74457bf07f443a55d7ec9affd35efdbaade82eb53e52b1391910cfe42954b3a`.
Full regression evidence is retained privately at
`/private/tmp/m20-billing-final-python-eyrundxh/`; before/after hashes agree.
The clean test checkout is based on `be226623`, with only the four reviewed
companion changes. The previous paused implementation remains archived; it was
not silently relabeled as accepted.

No new PI, DN, SI, payment, coordinator, HTTP route or model result is included.
