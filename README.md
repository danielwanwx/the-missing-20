# The Missing 20

**Find the gap. Prove the cause. Close it safely.**

An agentic supply-chain exception resolution system that investigates cross-system discrepancies and carries approved recovery actions through verified closure.

This repository is being created for the 2026 AWS Agents for Humans Hackathon. Its current deterministic vertical slice proves the synthetic supply-chain case through real local persistence, authorization, execution, verification, and replay. It does not yet claim a deployed AgentCore implementation or an agent-driven competition demo.

## Product boundary

- Deterministic code detects mismatches and enforces every safety-critical condition.
- Strands agents will compare hypotheses, gather cited evidence, and recommend a recovery plan.
- Separate human roles approve receipt-message restart and invoice release.
- A deterministic executor will fresh-read authoritative state before and after each mutation.
- The system will contain no payment tool.

All enterprise APIs, records, incidents, runbooks, and business data in this repository are synthetic. No employer or customer material may be added.

## Development

Prerequisites:

- Python 3.12+
- Node.js 20+

Run the local quality gate:

```bash
python3.12 -m venv .venv
make bootstrap PYTHON=.venv/bin/python
make check PYTHON=.venv/bin/python
```

Run the offline deterministic case:

```bash
make demo
```

The command seeds two temporary SQLite databases from the versioned JSON scenario, runs the complete `100 / 80 / 100` resolution path, and writes the auditable result to [`artifacts/demo/main-case.json`](artifacts/demo/main-case.json). It makes no AWS or model calls.

## Design

The independently reviewed design is available in [`docs/superpowers/specs/2026-08-25-the-missing-20-design.md`](docs/superpowers/specs/2026-08-25-the-missing-20-design.md), with its explorable [Architecture v4.2](docs/architecture/the-missing-20-architecture-v4.2.html). See the [implementation plan](docs/superpowers/plans/2026-08-25-the-missing-20-implementation-plan.md), the [Milestone 2 execution contract](docs/superpowers/specs/2026-08-25-milestone-2-deterministic-vertical-slice-design.md), and the accepted [Milestone 3 Golden v1 contract](docs/superpowers/specs/2026-08-25-milestone-3-golden-v1-design.md) for the current build.

## Provenance

This is a new competition repository. Conceptual influence and any later code reuse from the earlier FlowPulse project are disclosed in [docs/provenance.md](docs/provenance.md) before reuse occurs.

## License

[MIT](LICENSE)
