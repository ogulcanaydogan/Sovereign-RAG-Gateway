# Sovereign RAG Gateway Differentiation Strategy

## Goal
Define an honest, technical differentiation stance for a Kubernetes-deployable governance gateway in front of LLM providers and RAG connectors.

## Scope and Assumptions
- First vertical: healthcare-style PHI controls on synthetic data.
- Deployment model: self-hosted Kubernetes (kind first, cloud second).
- API posture: OpenAI-compatible endpoints for low adoption friction.

## Competitor and Adjacent Landscape (Top 10)

| Tool | What it does well | What it misses for this target |
|---|---|---|
| LiteLLM Proxy | Broad provider abstraction, routing/fallback, budget controls | Not opinionated around regulated runtime governance and tamper-evident decision provenance |
| Portkey Gateway | Mature gateway features, guardrails, observability | Strong platform, but less centered on self-hosted compliance evidence chains |
| Kong AI Gateway | Enterprise-grade policy plugins and traffic controls | Generic governance posture; less healthcare-first PHI workflow and audit lineage defaults |
| Gloo AI Gateway | Kubernetes-native gateway plus guardrail integration | Less opinionated about end-to-end compliance narrative and policy-to-audit linkage |
| Envoy AI Gateway | Open source, K8s-native traffic/routing/security controls | Earlier maturity; regulated controls need extra assembly |
| Helicone AI Gateway | Fast OSS setup, routing/cache/failover ergonomics | Reliability/cost oriented; weaker regulator-facing provenance story |
| OpenRouter | Multi-provider routing and fallback | Primarily provider orchestration, not tenant governance control plane |
| Azure APIM GenAI Gateway | Enterprise limits, quotas, semantic cache integration | Platform-centric and cloud-tied; less sovereign multi-cloud portability |
| NVIDIA NeMo Guardrails | Strong guardrail model for I/O and retrieval rails | Guardrails are not a complete OpenAI-compatible governance gateway |
| Guardrails AI | Rich validator ecosystem and structured output checks | Library-level safety, not cluster-level in-path governance and audit system |

## Honest Gap Assessment (What We Must Execute Well)
- OPA decision quality can become policy sprawl without strong conventions and test discipline.
- Regex-first PHI redaction has false positives/negatives; benchmark transparency is mandatory.
- Full OpenAI API parity is expensive; scope should remain explicit by version.
- Compliance claims require operational evidence, not architecture diagrams.

## Unique Wedge (3 Pillars)
1. In-path governance, fail-closed by default.
2. Evidence-grade traceability with immutable audit hash chain.
3. Regulated RAG control plane with connector policy checks and citations.

## Differentiation by Buyer Role
- CISO/Security: deterministic policy enforcement and tamper-evident auditability.
- SRE/Platform: one API edge for limits, routing, observability, and incident replay.
- Compliance/Privacy: measurable leakage reduction with reproducible tests.

## Positioning Statement
Sovereign RAG Gateway is the runtime governance control plane for regulated LLM and RAG traffic: enforce policy before data leaves, prove every decision after the fact, and operate it with standard Kubernetes/SRE workflows.

## Proof Requirements for Credibility
- Public benchmark runs with raw outputs, not only summary charts.
- Versioned policy/audit schemas and deterministic failure behavior.
- Reproducible deploy + demo steps that external teams can rerun.
