# Sovereign RAG Gateway Differentiation Strategy

Claim date: 2026-02-17  
Last revalidated: 2026-02-17

## Goal
Define a technically defensible differentiation stance for a Kubernetes-deployable, OpenAI-compatible gateway that enforces regulated runtime controls for LLM and RAG traffic.

## Scope and Assumptions
- Primary buyer: security engineering, SRE, and platform teams operating regulated workloads.
- Deployment posture: self-hosted Kubernetes first, cloud-managed variants second.
- Product boundary: runtime policy enforcement + audit evidence, not a full GRC platform.

## Top 10 Competitor and Adjacent Tools

| Tool | What it does well | What it misses for this target |
|---|---|---|
| LiteLLM Proxy | Broad model/provider abstraction, retries, fallback, and budget controls | Limited default posture for fail-closed governance and regulator-facing evidence lineage |
| Portkey | Mature AI gateway controls (routing, guardrails, observability) | Compliance evidence model is less opinionated for self-hosted sovereign operations |
| Kong AI Gateway | Enterprise API gateway maturity, policy plugins, traffic controls | AI governance is extensible but not purpose-built for LLM-specific audit chain semantics |
| Gloo AI Gateway | Kubernetes-native gateway and guardrail integrations | Requires additional composition for end-to-end runtime compliance evidence |
| Envoy AI Gateway | Open-source, policy/routing foundation at edge and mesh layers | Earlier ecosystem maturity for regulated LLM governance workflows |
| Cloudflare AI Gateway | Strong edge reliability, analytics, and request controls | Cloud-tied posture can be a blocker for strict sovereign hosting constraints |
| Azure APIM GenAI Gateway | Enterprise controls, quotas, safety and governance integration | Platform coupling and less portability for multi-cloud sovereign deployments |
| NVIDIA NeMo Guardrails | Strong guardrail patterns for dialog and retrieval rails | Guardrails are not a full in-path governance gateway with tenant audit lineage |
| Guardrails AI | Flexible validator ecosystem and structured output checks | Library-centric control model, not a centralized runtime enforcement plane |
| OpenRouter (adjacent) | Multi-provider routing and fallback ergonomics | Focused on provider orchestration, not regulated policy enforcement and evidence trails |

## Source Mapping
All competitor claims above map to primary references in `/Users/ogulcanaydogan/Desktop/Projects/YaPAY/Sovereign-RAG-Gateway/docs/research/landscape-sources.md`.

## Honest Gap Assessment (Execution Risks)
- Policy quality risk: OPA policies can drift into inconsistent behavior without strict fixture coverage and review gates.
- Redaction accuracy risk: regex-first redaction has measurable false positives and false negatives.
- API parity risk: OpenAI compatibility beyond core endpoints can expand scope quickly.
- Evidence risk: audit credibility depends on reproducible artifacts, not narrative claims.

## Unique Wedge (3 Pillars)
1. Fail-closed, in-path governance.
   - Every request is evaluated before retrieval and provider egress.
   - Policy backend unavailability defaults to deterministic deny behavior.
2. Tamper-evident decision lineage.
   - Each request produces decision artifacts linked by request ID and policy hash.
   - Forensic replay can reconstruct auth, policy, transform, and provider route path.
3. Regulated RAG control boundary.
   - Source authorization, classification-aware redaction, and citation constraints are enforced in one runtime boundary.

## Positioning by Buyer
- Security leadership: deterministic controls and replayable evidence for incident and audit scrutiny.
- SRE/platform: one enforcement plane for auth, routing, budget, and policy outcomes.
- Compliance/privacy: measurable reduction of leakage risk with explicit false-positive/false-negative reporting.

## Publishable Benchmark Angle
### Theme
Governance Yield vs Performance Overhead.

### Research Question
How much leakage/authorization risk reduction can in-path governance deliver relative to the latency and cost overhead it introduces?

### Experimental Design
- Control: direct provider calls.
- Treatment A: gateway observe mode.
- Treatment B: gateway enforce + redaction.
- Treatment C: gateway enforce + redaction + policy-scoped RAG.

### Publishability Requirements
- Release raw CSV/JSON outputs and reproducibility manifest for each run.
- Report confidence intervals for key rates (leakage, deny precision/recall).
- Publish failure cases and benchmark limitations, not score-only summaries.

## Non-Claims
- No claim of perfect PHI detection accuracy.
- No claim of full provider API parity in early versions.
- No claim that gateway controls replace secure SDLC or data governance programs.
