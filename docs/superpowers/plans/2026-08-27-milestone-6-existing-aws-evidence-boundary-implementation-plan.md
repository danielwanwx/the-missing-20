# Milestone 6 Existing AWS Evidence Boundary Implementation Plan

**Design:** [`2026-08-27-milestone-6-existing-aws-evidence-boundary-design.md`](../specs/2026-08-27-milestone-6-existing-aws-evidence-boundary-design.md)
**Status:** `APPROVE_M6_EXISTING_EVIDENCE_BOUNDARY`; M7 authorized

1. Add strict M6 proof contracts and fixed raw-byte source anchors in
   `authority_b/aws_proof.py`.
2. Validate lifecycle, Golden, preflight, and redacted Authority-B relations; compose
   the canonical proof bundle and expose fail-closed load/write helpers.
3. Add `scripts/build_m6_aws_proof.py` and generate
   `artifacts/aws/m6-proof-bundle-v1.json` without network or AWS imports/clients.
4. Add unit mutation/claim-scan coverage, then minimally expose the proof in the
   read-only Decision Workspace and local browser smoke.
5. Update README/Makefile only to disclose the existing-evidence boundary and provide
   the offline build target.
6. Run focused M6 tests, full offline checks, Golden v1/v2, workspace/browser smoke,
   provenance/secret/remote-resource scans, and `git diff --check`.

## Gate record

- Design gate: independent Chief Architect approval is required before implementation.
- Implementation gate: independent review checks the spec, source anchors, fail-closed
  mutation matrix, and the absence of provider/cloud side effects.
- One focused material correction is allowed. A second reproducible integrity defect
  stops M6 and is reported as a root-cause-level blocker.

## Explicit non-goals

No AWS/provider/network call, new spend, AgentCore SDK/deployment/IaC, credentials,
write authority, authentication, public release, commit, push, video, Devpost, or
resume/LinkedIn work.

## Final implementation gate

- Initial independent review found one material provenance defect: a rehashed proof
  could substitute the lifecycle case and trace identity while retaining its digest.
- The sole focused correction binds lifecycle `case_id`, `trace_id`, and bundle digest
  to the independently validated authoritative lifecycle source; coordinated rehash
  mutation tests cover both identities.
- Final gates: Ruff PASS; mypy PASS across 105 source files; 517 Python tests PASS with
  1 managed-sandbox loopback skip; 1 JavaScript test PASS; Golden v1 16/16 with all five
  safety counters zero; Golden v2 `PASS_WITH_DISCLOSED_AI_DEGRADATION`; M6 proof PASS
  with digest `f1f8af784ef8c7c1d5f40ceb7d228a2a0b82ae68a392dd03d845a084179143b6`, zero
  provider calls, and zero new cost; lifecycle/workspace builds PASS;
  complete/degraded/invalid browser smoke PASS; `git diff --check` PASS.
- Final independent verdict: `APPROVE_M6_EXISTING_EVIDENCE_BOUNDARY`.
