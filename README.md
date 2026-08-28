# The Missing 20

**Find the gap. Prove the cause. Close it safely.**

The Missing 20 is a guided supply-chain incident replay. It starts with a simple
problem: the warehouse expects 100 units, the ERP records 80, and nobody knows where
the other 20 went. Specialized agents compare possible causes and surface evidence,
while deterministic policy, two independent human roles, controlled execution, and
verification keep AI output from directly changing operational state.

![Guided incident replay](artifacts/workspace/screenshots/complete.png)

## Try the guided replay

Prerequisites: Python 3.12+ and Node.js 20+.

```bash
python3.12 -m venv .venv
make bootstrap PYTHON=.venv/bin/python
make workspace
PYTHONPATH=src .venv/bin/python scripts/decision_workspace_server.py
```

Open the local URL printed by the server and choose **Start replay**. The product leads
the viewer through five stages:

1. Detect the 20-unit gap.
2. Compare competing agent hypotheses.
3. Apply deterministic safety rules.
4. Require approval from two distinct roles.
5. Recover, verify, and prove replay creates no duplicate effect.

The workspace also exposes two explicit failure views:

- `?mode=degraded`: the provider failed, no hypothesis is invented, and deterministic
  protection remains available.
- `?mode=invalid`: authoritative lifecycle evidence is incomplete, so the workspace
  fails closed and hides operational claims.

## Why this is different

Most agent demos stop at a plausible answer. The Missing 20 separates investigation
from authority:

- Strands agents may propose hypotheses, retrieve synthetic knowledge, identify gaps,
  and prepare an incident explanation.
- Deterministic code alone owns evidence integrity, state classification, action
  eligibility, policy, execution, verification, and replay.
- Every controlled action requires an exact two-role quorum.
- The executor rereads authoritative state, applies a bounded idempotent effect,
  verifies postconditions, and records a zero-effect replay.

The browser is a read-only projection of persisted synthetic evidence. It never grants
approval or executes an action.

## Evidence boundary

| Capability | Current evidence |
| --- | --- |
| Detection, policy, per-action quorum, execution, verification, replay | **Proven locally** with synthetic data |
| Strands multi-agent investigation | **Scripted synthetic proof** |
| Amazon Bedrock Nova Pro | Connectivity and degraded-outcome observability only |
| Stable useful real-provider investigation | **Not proven** |
| AgentCore Runtime, Gateway, Policy, Observability, deployment | **Not implemented and not claimed** |

The consumed Nova attempt remains preserved as a visible degraded result. It is not
relabelled as a successful AI run. All records, runbooks, incidents, and business data
in this repository are synthetic; no employer or customer material is admitted.

## Architecture

See the truthful [as-built architecture](docs/architecture/as-built-architecture.md).
The older v4.2 document is a historical target design and is not evidence of the
current implementation.

## Verification

Run the complete local quality and competition-package gates:

```bash
make check
make golden
make golden-v2
make workspace-smoke
make judge-demo
```

`make judge-demo` regenerates the lifecycle, workspaces, and package audit in a clean
temporary state. It does not make an AWS or model call. The current package preserves
the cumulative prior provider estimate of `$0.1250496` under the approved `$0.60` cap.

## Competition materials

- [Five-minute demo card](docs/demo/five-minute-demo.md)
- [Judging map](docs/submission/judging-map.md)
- [Evidence matrix](docs/submission/evidence-matrix.md)
- [Known limitations](docs/submission/known-limitations.md)
- [Competitive benchmark](docs/submission/competitive-benchmark.md)
- [Provenance](docs/provenance.md)

The repository is prepared for development review. Public video upload and Devpost
submission remain separate human-controlled release actions.

## License

[MIT](LICENSE)
