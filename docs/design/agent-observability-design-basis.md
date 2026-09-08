# Agent Observability Design Basis

The interface is designed as an **agent observability console**, not a generic analytics dashboard. Its visual hierarchy follows what a judge must verify in one pass:

1. A real cross-system discrepancy exists.
2. Strands selected and called tools autonomously.
3. Evidence from independent systems was reconciled into competing hypotheses.
4. Deterministic policy retained write authority.
5. A manager intervened only at the bounded decision.
6. The resulting effect was independently reread and verified.

## External design and workflow references

- [Anthropic frontend-design skill](https://github.com/anthropics/skills): commit to one intentional aesthetic direction, preserve production behavior, and avoid generic AI-dashboard decoration.
- [Linear UI redesign](https://linear.app/now/how-we-redesigned-the-linear-ui): reduce visual noise, preserve alignment, and make navigation and hierarchy predictable as the product grows.
- [Vercel Geist typography](https://vercel.com/geist/typography): use explicit type roles and tabular/monospace treatment for dense operational values.
- [Vercel Geist colors](https://vercel.com/geist/colors): separate backgrounds, borders, high-contrast controls, and text roles instead of distributing accent color everywhere.
- [AWS Strands architecture and observability](https://aws.amazon.com/blogs/machine-learning/strands-agents-sdk-a-technical-deep-dive-into-agent-architectures-and-observability/): expose the model-driven loop, tool trajectory, OpenTelemetry-compatible evidence, and human control boundary.
- [AWS Strands evaluation workflow](https://aws.amazon.com/blogs/machine-learning/observing-and-evaluating-ai-agentic-workflows-with-strands-agents-sdk-and-arize-ax/): make latency, tokens, tool correctness, trace path, and continuous evaluation visible as first-class proof.
- [LangSmith trace views](https://docs.langchain.com/langsmith/view-traces): separate scan-level thread context from run-level inputs, outputs, timing, tokens, errors, and metadata.
- [LangSmith dashboards](https://docs.langchain.com/langsmith/dashboards): keep trace volume, latency, errors, token usage, cost, and tool behavior directly inspectable.

## Applied visual direction

- **Structure:** silver control canvas, white evidence surfaces, one dark current-run strip.
- **Color:** cyan, violet, orange, and lime identify independent authorities; coral is reserved for unresolved operational risk.
- **Typography:** Geist Sans for decisions and hierarchy; Geist Mono for machine-verifiable facts.
- **Motion:** only fresh ledger events, active stages, and live source changes move.
- **Density:** summary proof is visible immediately; raw evidence and Resolution Packets remain expandable.
- **Authority:** the Agent owns investigation, while the Manager gate is visually and behaviorally distinct from autonomous work.
