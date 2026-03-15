# Sovereign Tech Fund Application

## Application Details

| Field | Value |
|---|---|
| **Program** | Sovereign Tech Fund |
| **URL** | https://www.sovereign.tech/programs/fund |
| **Requested Amount** | EUR 55,000 |
| **Deadline** | 2026-03-25 |
| **Applicant** | Ogulcan Aydogan |
| **Project** | Sovereign RAG Gateway |
| **Repository** | https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway |
| **License** | MIT |
| **Language** | Python 3.12+ |
| **Current Version** | v1.1.0 (GA) |

---

## 1. Executive Summary

Sovereign RAG Gateway is open source infrastructure for digital sovereignty in AI. It is a policy-first, OpenAI-compatible governance gateway that enforces runtime policy evaluation, PHI/PII data redaction, retrieval authorization, and hash-chained audit trail generation for every LLM and RAG request before traffic leaves the organizational boundary.

European organizations deploying AI in regulated sectors (healthcare, financial services, public administration) face a structural gap: governance controls are bolted on after the fact, audit logs are scattered across systems, and no single enforcement point can prove that data protection was applied before sensitive information reached an external provider. Sovereign RAG Gateway closes this gap by moving policy enforcement, data redaction, and evidence production into the critical request path.

The gateway is fully self-hosted, requires no cloud dependencies, and supports on-premises deployment with air-gapped operation capabilities. Organizations retain complete control over their RAG pipelines, policy definitions, data residency, and audit evidence. This aligns directly with the Sovereign Tech Fund's mission to strengthen the digital infrastructure that European society depends on.

This proposal requests EUR 55,000 over 16 weeks to fund a professional security audit of the gateway's core enforcement mechanisms, harden the PII redaction engine against adversarial evasion, achieve formal OPA policy certification, and produce compliance documentation for EU AI Act alignment.

---

## 2. Relevance to Digital Sovereignty

Sovereign RAG Gateway directly addresses multiple dimensions of digital sovereignty for European organizations:

### 2.1 Self-Hosted, Zero Cloud Dependency

The gateway runs entirely on infrastructure controlled by the deploying organization. There's no SaaS dependency, no telemetry phone-home, and no external service required for core operation. Policy evaluation uses Open Policy Agent (OPA), which runs as a local sidecar. Retrieval connectors (filesystem, PostgreSQL pgvector, S3, Confluence, Jira) connect to organization-owned data stores. The gateway can operate in air-gapped environments using hash-based local embeddings.

### 2.2 Policy Sovereignty Through OPA/Rego

Policy definitions are written in Rego, a declarative language that is version-controlled, peer-reviewed, and deployed independently of gateway code. Organizations define their own governance rules: which tenants can access which models, which data classifications require redaction, and which retrieval sources are authorized for which users. Policy is authored and owned by the organization, not by a vendor.

### 2.3 Data Protection at the Enforcement Point

PHI/PII redaction happens in the gateway's hot path, before any data leaves the organizational boundary. This isn't post-hoc logging or best-effort filtering. It's deterministic enforcement. If redaction fails or policy evaluation is unavailable, the gateway defaults to deterministic deny (fail-closed). European organizations processing health data (GDPR Article 9), financial records, or citizen data can demonstrate that protection was applied at the point of egress.

### 2.4 Tamper-Evident Audit Trails

Every request produces a hash-chained audit event that records the policy version hash, redaction count, retrieval sources, provider routing decision, and timing. Given a request ID, an investigator can reconstruct the complete decision path. This supports GDPR Article 30 record-keeping obligations and provides the forensic evidence base required by EU AI Act transparency requirements.

### 2.5 Supply Chain Integrity

The release pipeline (19 releases to date) uses Sigstore cosign for keyless container signing, generates SPDX SBOMs, and attaches provenance attestations to every release. The OpenSSF Scorecard workflow runs weekly. This supply chain posture ensures European organizations can verify the integrity of every artifact they deploy.

---

## 3. Technical Description

### 3.1 Architecture Overview

Sovereign RAG Gateway is a Python 3.12+ application built on FastAPI and uvicorn. It exposes an OpenAI-compatible API surface (`/v1/chat/completions`, `/v1/embeddings`, `/v1/models`) and processes every request through a deterministic enforcement pipeline:

1. **Ingress Layer**: Request ID assignment, Bearer token validation, tenant/user/classification extraction
2. **Policy Evaluation**: OPA/Rego policy evaluation with fail-closed semantics; observe and enforce modes for progressive adoption
3. **Policy Transforms**: model downgrade, parameter adjustment based on policy decision
4. **Data Redaction**: PHI/PII regex detection with classification-aware application
5. **Retrieval Authorization**: policy-scoped connector access; prompt injection can't override source authorization
6. **Provider Egress**: multi-provider routing with cost-aware selection and automatic failover (OpenAI, Azure OpenAI, Anthropic)
7. **Citation Integrity**: verification that response citations reference authorized sources
8. **Audit Evidence**: hash-chained JSON Lines audit events with schema validation

### 3.2 RAG Connectors (5 production connectors)

| Connector | Backend | Use Case |
|---|---|---|
| `FilesystemConnector` | JSON Lines index | Air-gapped, small-scale, testing |
| `PostgresPgvectorConnector` | PostgreSQL + pgvector | Semantic retrieval, production |
| `S3Connector` | S3 JSONL with local caching | Cloud-native deployments |
| `ConfluenceConnector` | Confluence Cloud API + BM25 | Enterprise knowledge bases |
| `JiraConnector` | Jira Cloud API + BM25 | Project/issue retrieval |

### 3.3 CI/CD and Quality Infrastructure

The project maintains 11 CI workflows (plus 1 scheduled scorecard):

| Workflow | Purpose |
|---|---|
| `ci.yml` | Lint (ruff), type check (mypy), unit/integration tests (pytest), schema validation, benchmark gates |
| `deploy-smoke.yml` | Kind cluster deployment, Helm install, rollout validation, health checks |
| `slo-reliability.yml` | Fault injection suite, soak testing, SLO compliance gates |
| `release.yml` | Container build, GHCR push, Sigstore signing, SPDX SBOM, provenance attestation |
| `release-verify.yml` | Release asset/signature verification, historical integrity sweep |
| `terraform-validate.yml` | Infrastructure-as-code validation |
| `evidence-replay-smoke.yml` | Audit trail forensic replay verification |
| `rollback-drill.yml` | Operational rollback procedure validation |
| `weekly-evidence-report.yml` | Automated reliability and release evidence snapshots |
| `ga-readiness.yml` | GA promotion gate enforcement |
| `scorecard.yml` | OpenSSF Scorecard analysis (weekly) |
| `eks-reference-validate.yml` | EKS reference architecture validation |

### 3.4 Deployment

- **Container**: `python:3.12-slim` base, non-root process, minimal attack surface
- **Kubernetes**: Helm chart with namespace isolation, RBAC, network policies, health probes
- **GitOps**: Argo CD ApplicationSet with per-environment values, External Secrets Operator integration
- **Observability**: Prometheus metrics endpoint (7 metric families), pre-built Grafana dashboard

---

## 4. Security Audit Need

The gateway enforces security-critical decisions in the hot path of every AI request. Three components require professional security audit to provide European organizations with the confidence to deploy in production regulated environments:

### 4.1 PII/PHI Redaction Engine (`app/redaction/engine.py`)

The redaction engine uses regex-based pattern detection to identify and scrub personally identifiable information and protected health information before data leaves the organizational boundary. A professional audit would:

- Evaluate pattern coverage against GDPR personal data categories and HIPAA PHI identifiers
- Test adversarial evasion techniques (encoding, Unicode normalization, prompt injection to bypass redaction)
- Assess false-positive rates and their impact on utility
- Recommend hardening measures and pattern expansion

### 4.2 OPA Integration and Fail-Closed Enforcement (`app/policy/client.py`, `app/policy/transforms.py`)

The policy engine implements fail-closed semantics: if OPA is unreachable, the gateway denies the request. A professional audit would:

- Verify that no code path permits request processing without policy evaluation
- Test timeout handling, partial response scenarios, and malformed OPA responses
- Evaluate the policy transform pipeline for injection or bypass vectors
- Assess the observe-to-enforce mode transition for security implications

### 4.3 Authentication and Authorization Layer (`app/middleware/auth.py`, `app/rag/retrieval.py`)

Bearer token validation and tenant-scoped retrieval authorization control access to data and models. A professional audit would:

- Test token validation for timing attacks, replay attacks, and header injection
- Verify retrieval authorization cannot be bypassed through prompt content
- Evaluate multi-tenant isolation guarantees
- Assess connector credential handling and injection resistance

---

## 5. Budget

| Category | Amount (EUR) | Description |
|---|---|---|
| **Security Audit** | 35,000 | Professional penetration testing and code audit of PII redaction engine, OPA integration, authentication layer, and audit trail integrity by a recognized European security firm |
| **PII Redaction Hardening** | 8,000 | Implementation of audit recommendations: expanded pattern coverage, Unicode normalization, adversarial test suite, false-positive rate benchmarking |
| **OPA Policy Certification** | 7,000 | Formal verification of fail-closed enforcement paths, policy transform pipeline hardening, Rego policy test suite expansion, observe/enforce mode security review |
| **Compliance Documentation** | 5,000 | EU AI Act alignment documentation, GDPR Article 30 compliance guide, deployment security hardening guide, threat model documentation |
| **Total** | **55,000** | |

---

## 6. Timeline

| Week | Milestone | Deliverable |
|---|---|---|
| 1-2 | **Audit Preparation** | Threat model documentation, attack surface inventory, security audit scope definition with selected firm |
| 3-8 | **Security Audit Execution** | Professional audit of PII redaction engine, OPA integration, authentication layer; interim findings review at week 5 |
| 9-10 | **Audit Report and Prioritization** | Final audit report, vulnerability classification, remediation plan with priority ranking |
| 11-13 | **Hardening Implementation** | PII redaction hardening, OPA enforcement path fixes, authentication layer improvements, adversarial test suite |
| 14-15 | **Compliance Documentation** | EU AI Act alignment guide, GDPR compliance documentation, deployment security guide |
| 16 | **Verification and Publication** | Re-test of critical findings, publish audit summary, release hardened version with security advisory |

---

## 7. Impact for European Organizations

### 7.1 Healthcare

European healthcare organizations deploying AI for clinical decision support, patient communication, or medical records processing need provable PHI protection. Sovereign RAG Gateway provides deterministic redaction enforcement with audit evidence that can be presented to DPAs (Data Protection Authorities) and health regulators.

### 7.2 Financial Services

Banks, insurers, and fintechs operating under FCA, BaFin, or ECB supervision need demonstrable controls over AI systems that process customer financial data. The gateway's policy enforcement, audit trails, and fail-closed semantics align with the operational resilience requirements of DORA (Digital Operational Resilience Act).

### 7.3 Public Administration

European government agencies evaluating AI adoption need infrastructure that guarantees data residency, policy control, and audit transparency. The gateway's self-hosted architecture and policy sovereignty model enable adoption without creating dependencies on non-European cloud providers.

### 7.4 EU AI Act Compliance

The EU AI Act requires risk management, transparency, and human oversight for high-risk AI systems. Sovereign RAG Gateway's policy evaluation, audit trails, and retrieval authorization provide technical building blocks for these requirements. The compliance documentation produced through this grant will map gateway capabilities to specific EU AI Act articles.

---

## 8. Supporting Materials

### 8.1 Project Maturity Evidence

- **19 releases** following semver with structured release notes extracted from CHANGELOG.md
- **11 CI workflows** covering lint, type check, testing, deployment smoke, SLO reliability, release signing, and operational drills
- **GA release (v1.1.0)** with stabilization window validation, release-verify gates, and evidence artifacts
- **OpenSSF Scorecard** integrated with weekly automated runs and SARIF upload to GitHub Security
- **Sigstore signing** on every release with SPDX SBOM and provenance attestation
- **Helm chart** with values schema validation, RBAC, and network policies

### 8.2 Repository Links

- Repository: https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway
- Architecture documentation: `ARCHITECTURE.md` (detailed module map, request lifecycle, design decisions)
- Security policy: `SECURITY.md`
- Changelog: `CHANGELOG.md`

### 8.3 Maintainer

Ogulcan Aydogan, sole maintainer and author. Background in ML engineering and infrastructure, with focus on governance and compliance tooling for regulated AI workloads.

---

## 9. Submission Steps

1. Navigate to https://www.sovereign.tech/programs/fund
2. Click "Apply" or "Submit a Project"
3. Fill in the application form with the information above, adapting section lengths to form field requirements
4. Attach or link the repository URL and architecture documentation
5. For the "How does this project contribute to digital sovereignty?" question, use Section 2 above
6. For the budget breakdown, use the table in Section 5
7. For the timeline, use the milestones in Section 6
8. Submit before the 2026-03-25 deadline
9. Monitor email for reviewer questions (typical response time is 4-6 weeks)

---

## 10. Key Talking Points for Reviewers

When discussing this application with Sovereign Tech Fund reviewers, emphasize:

1. **Name alignment isn't coincidental.** The project was built from first principles around the concept of sovereign control over AI governance. Every design decision (fail-closed, self-hosted, OPA policy sovereignty, hash-chained audit) serves organizational sovereignty.

2. **This is infrastructure, not a product.** The gateway is a building block that European organizations compose into their AI architectures. It doesn't compete with LLM providers; it governs the interface between organizations and providers.

3. **The security audit is the highest-value investment.** A professional audit transforms the project from "promising open source tool" to "audited infrastructure that procurement teams can approve." This unlocks adoption in exactly the organizations that need sovereignty most.

4. **Supply chain maturity is already high.** Sigstore signing, SPDX SBOMs, provenance attestations, and OpenSSF Scorecard are already in place. The grant funds the security depth that complements this supply chain breadth.

5. **EU AI Act timing is strategic.** Organizations are actively seeking technical infrastructure to comply with EU AI Act requirements. A security-audited governance gateway with compliance documentation arrives exactly when demand peaks.
