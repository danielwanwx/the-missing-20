# Supply Chain Exception Resolution Agent

An evidence-grounded Professional Agent for investigating and safely resolving synthetic supply-chain and ERP exceptions.

This repository is being created for the 2026 AWS Agents for Humans Hackathon. The current stage is foundation and design validation; it does not yet claim a deployed AgentCore implementation or a completed competition demo.

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

## Design

The independently reviewed design and implementation plan will be copied into `docs/` before the first public release.

## Provenance

This is a new competition repository. Conceptual influence and any later code reuse from the earlier FlowPulse project are disclosed in [docs/provenance.md](docs/provenance.md) before reuse occurs.

## License

[MIT](LICENSE)
