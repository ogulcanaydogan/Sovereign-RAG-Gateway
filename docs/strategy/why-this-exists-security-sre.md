# Why Sovereign RAG Gateway Exists (Security and SRE Narrative)

Regulated AI systems fail in predictable ways when governance is bolted on after runtime traffic leaves the boundary. One component handles redaction, another handles policy checks, another handles routing, and logs are scattered across services. During incidents, teams cannot prove whether controls were actually enforced at decision time or only observed later.

Sovereign RAG Gateway exists to move governance into the hot path and make the decision trail inspectable.

For every request, identity and classification context are attached early, policy is evaluated before retrieval/provider egress, and transform decisions are recorded with request-linked evidence. This changes security posture from best-effort controls to deterministic control points.

For security teams, the practical benefit is not abstract "AI safety" language. The benefit is concrete: fewer unknowns in incident response and fewer unprovable controls in audits. You can answer who requested what, which policy version evaluated it, what transformations were applied, what route was selected, and why the decision was allow or deny.

For SRE teams, this consolidates operational behavior that is usually spread across application code and ad hoc middleware. A single gateway path can enforce auth context requirements, runtime policy decisions, budget/rate constraints, and policy-scoped retrieval behavior while preserving OpenAI-compatible request surfaces for application teams.

The project is intentionally opinionated about failure behavior. If policy evaluation is unavailable, fail closed. In regulated environments, silent fallback to permissive behavior creates larger incident and audit risk than explicit denial.

This project also makes a narrow promise: measurable governance outcomes under realistic performance budgets. Benchmarking is designed to publish raw artifacts and methodology, not only aggregate scores, so teams can inspect leakage rates, policy precision/recall, and latency impact directly.

## What this does not claim
- It does not claim perfect redaction or perfect policy authoring.
- It does not claim to replace broader data governance, IAM, or secure SDLC controls.
- It does not claim full API parity with every provider-specific extension.

The core claim is narrower and testable: enforce policy before egress, preserve evidence for replay, and keep overhead within explicit SRE budgets.
