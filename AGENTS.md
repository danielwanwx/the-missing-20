# Project delivery requirements

- After each completed optimization, run the relevant verification, commit the
  completed changes, and push to the project's intended Git remote. The user has
  authorized this routine delivery step; do not ask for approval each time.
- Verify the push result. Report the commit and any push failure accurately;
  a local commit alone does not satisfy delivery.
- Stage only reviewed, task-relevant changes. Preserve unrelated work. Never
  include credentials, local runtime databases, private session data, or sensitive
  artifacts merely because they appear in the working tree.
- Do not force-push, rewrite shared history, or claim incomplete work is verified.

# Research-led agent improvements

- For a repeated agent reasoning or workflow failure, preserve the failing case
  and pause expansion of that candidate. Investigate the failure mechanism and
  current SDK capabilities before adding another prompt, validator or state layer.
- Compare a small set of materially different approaches against the same task:
  the retained baseline, a native/existing-component approach, and another
  plausible alternative when evidence supports one. Prefer official source code,
  maintained repositories and maintainer discussions. Record versions, licenses,
  integration requirements and what each component does not solve.
- Freeze inputs, expected outcomes, model/configuration, budgets and stop rules
  before a comparison. Keep expected outcomes and review rubrics outside model
  inputs. Keep memory, answer quality, workflow recovery and real ERP
  effects as separate acceptance dimensions. A historical baseline is not a fresh
  paired measurement; scripted or fake-service results are not real-model or ERP
  acceptance. Preserve every failed attempt and the held-out set.
- If a mechanism fails the agreed stop rule, return to research and choose a
  different supported approach. Do not keep layering exceptions to fit that case.
  Ordinary implementation defects still receive a bounded fix and regression;
  a new framework is not required for every bug.
- Terra Max implements coupled/core work; Luna Max implements narrow changes with
  stable interfaces. The primary agent owns hypotheses, selection, coordination,
  verification and release. Existing authorized independent review remains required.
- Run candidates in isolated experiments before changing the product. Promote
  only independently reviewed improvements with demonstrated task benefit and
  acceptable integration cost. Continue the original commit/push verification
  requirements for each accepted deliverable.
