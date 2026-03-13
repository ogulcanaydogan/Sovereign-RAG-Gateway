# NLnet NGI Zero Commons Fund Proposal

## Application Details

| Field | Value |
|---|---|
| **Fund** | NGI Zero Commons Fund |
| **URL** | https://nlnet.nl/propose/ |
| **Requested Amount** | EUR 42,000 |
| **Deadline** | 2026-04-01 |
| **Applicant** | Ogulcan Aydogan |
| **Project** | Sovereign RAG Gateway |
| **Repository** | https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway |
| **License** | MIT |
| **Language** | Python 3.12+ |

---

## 1. Abstract (200 words)

Sovereign RAG Gateway is an open source, policy-first governance gateway for AI workloads in regulated sectors. It sits between applications and LLM providers, enforcing runtime policy evaluation through Open Policy Agent, PHI/PII data redaction, retrieval authorization across five data connectors, and tamper-evident hash-chained audit trail generation -- all before any data leaves the organizational boundary.

Current enterprise AI deployments scatter governance controls across disconnected services, making it impossible to prove that data protection was applied at the point of egress. Sovereign RAG Gateway unifies these controls in a single deterministic enforcement pipeline with fail-closed semantics: if policy evaluation is unavailable, the request is denied, not silently permitted.

This proposal seeks EUR 42,000 to harden the gateway for production deployment in healthcare and financial services: professional security audit of the PII redaction engine and policy enforcement layer, expanded redaction coverage for European PII patterns (BSN, IBAN, national ID formats), EU AI Act compliance documentation, and a GDPR Article 30 operational guide. The project is fully self-hosted with zero cloud dependencies, supporting data residency requirements and organizational sovereignty over AI governance. It has 19 releases, 11 CI workflows, Sigstore-signed containers, and OpenSSF Scorecard integration.

---

## 2. Description of Work

### 2.1 Problem Statement

Organizations in healthcare, financial services, and public administration are adopting AI systems that process sensitive personal data -- patient health records, financial transactions, citizen information. The EU AI Act, GDPR, and sector-specific regulations (HIPAA for cross-border healthcare, DORA for financial services) require demonstrable governance controls: provable data protection at the point of processing, audit trails for regulatory inspection, and policy enforcement that cannot be silently bypassed.

Existing approaches bolt governance on after the fact. Redaction runs in a separate service with eventual consistency. Policy evaluation is asynchronous. Audit logs are scattered across systems with no causal linkage. During incidents or regulatory audits, no single system can reconstruct the complete decision path for a given AI request.

### 2.2 Proposed Solution

Sovereign RAG Gateway moves governance into the critical path. Every request passes through a deterministic pipeline: identity verification, OPA policy evaluation (fail-closed), PHI/PII redaction, policy-scoped retrieval authorization, provider egress, and hash-chained audit event production. The gateway produces tamper-evident decision records that enable forensic replay of any request.

The project is already functional (v1.1.0 GA) with 5 RAG connectors, 3 upstream LLM providers, Prometheus observability, and Kubernetes deployment support. This proposal funds the security hardening and compliance work needed to make it production-ready for regulated European organizations.

### 2.3 Technical Architecture

- **Runtime**: Python 3.12, FastAPI, uvicorn
- **Policy Engine**: Open Policy Agent (OPA) with Rego policy language, fail-closed enforcement
- **Data Protection**: Regex-based PHI/PII detection with classification-aware redaction
- **RAG Connectors**: Filesystem (JSON Lines), PostgreSQL pgvector, S3, Confluence, Jira
- **Audit**: Hash-chained JSON Lines with schema validation and forensic replay support
- **Providers**: OpenAI, Azure OpenAI, Anthropic with cost-aware fallback routing
- **Deployment**: Docker, Helm/Kubernetes, Argo CD GitOps, External Secrets Operator
- **Supply Chain**: Sigstore cosign, SPDX SBOM, provenance attestation, OpenSSF Scorecard

---

## 3. Budget

| Milestone | Amount (EUR) | Duration |
|---|---|---|
| **M1: Security Audit** | 18,000 | Weeks 1-6 |
| Professional code audit and penetration testing of PII redaction engine (`app/redaction/engine.py`), OPA policy client (`app/policy/client.py`), authentication middleware (`app/middleware/auth.py`), and audit trail integrity (`app/audit/writer.py`). Includes threat model documentation and remediation report. | | |
| **M2: European PII Pattern Expansion** | 8,000 | Weeks 7-9 |
| Expand redaction engine to cover European PII formats: Dutch BSN, German Steuer-ID, French INSEE, IBAN (all EU formats), European phone number formats, national health ID numbers. Add adversarial evasion test suite (Unicode normalization, encoding bypass, prompt injection to circumvent redaction). Benchmark false-positive rates. | | |
| **M3: OPA Policy Hardening** | 7,000 | Weeks 10-11 |
| Formal verification of all fail-closed enforcement paths. Harden policy transform pipeline against injection. Expand Rego policy test suite with regulatory scenario coverage (GDPR data subject requests, cross-border transfer restrictions, classification-based access control). Document observe-to-enforce migration path. | | |
| **M4: EU AI Act Compliance Documentation** | 5,000 | Weeks 12-13 |
| Map gateway capabilities to EU AI Act articles (risk management, transparency, human oversight, technical documentation). Produce GDPR Article 30 record-keeping guide for gateway audit trails. Write deployment security hardening guide for regulated environments. | | |
| **M5: Hardened Release and Publication** | 4,000 | Weeks 14-16 |
| Implement audit remediation for critical and high findings. Re-test remediated components. Release hardened version with security advisory. Publish audit summary and compliance documentation. Update OpenSSF Scorecard posture. | | |
| **Total** | **42,000** | **16 weeks** |

---

## 4. Milestones and Deliverables

### Milestone 1: Security Audit (EUR 18,000)

**Deliverables:**
- Threat model document covering all security-critical components
- Professional audit report with vulnerability classification (Critical/High/Medium/Low)
- Penetration test results for PII redaction bypass, OPA policy bypass, authentication bypass, RAG connector injection, and audit trail manipulation
- Remediation plan with priority ranking

**Acceptance criteria:**
- Audit conducted by a firm with recognized security credentials
- Report covers all five attack surface areas listed above
- All Critical and High findings have documented remediation paths

### Milestone 2: European PII Pattern Expansion (EUR 8,000)

**Deliverables:**
- Expanded redaction engine with 10+ European PII pattern categories
- Adversarial test suite with 50+ evasion test cases
- False-positive rate benchmark report
- Updated pattern documentation

**Acceptance criteria:**
- Detection rate above 95% for standard-format European PII in test corpus
- Adversarial evasion test suite passes in CI
- False-positive rate below 2% on non-PII text corpus

### Milestone 3: OPA Policy Hardening (EUR 7,000)

**Deliverables:**
- Formal path analysis documenting all code paths from request ingress to provider egress, verifying fail-closed enforcement at each
- Expanded Rego policy test suite with 20+ regulatory scenarios
- Policy transform injection resistance tests
- Observe-to-enforce migration guide

**Acceptance criteria:**
- Zero code paths permit request processing without policy evaluation (verified by path analysis)
- All regulatory scenario tests pass in CI
- Migration guide reviewed and validated

### Milestone 4: EU AI Act Compliance Documentation (EUR 5,000)

**Deliverables:**
- EU AI Act capability mapping document (gateway features to specific articles)
- GDPR Article 30 record-keeping guide using gateway audit trails
- Deployment security hardening guide for regulated environments
- Threat model summary suitable for procurement review

**Acceptance criteria:**
- Documents reviewed by at least one domain expert
- Mapping covers Articles 9, 11, 12, 13, 14, 15, and 17 of the EU AI Act
- Guides are actionable (step-by-step, not aspirational)

### Milestone 5: Hardened Release and Publication (EUR 4,000)

**Deliverables:**
- Hardened release addressing all Critical and High audit findings
- Security advisory published through GitHub Security Advisories
- Audit summary published (non-confidential portions)
- Updated OpenSSF Scorecard with improved posture

**Acceptance criteria:**
- All Critical findings remediated and re-tested
- All High findings remediated or documented with mitigation timeline
- Release signed with Sigstore and includes SPDX SBOM

---

## 5. NGI Relevance

### 5.1 Open Internet and Trust

Sovereign RAG Gateway contributes to a trustworthy internet by ensuring that AI systems processing personal data operate under provable governance controls. As AI becomes embedded in internet services, the gap between "AI is deployed" and "AI is governed" becomes a trust deficit. The gateway provides the enforcement infrastructure that closes this gap.

### 5.2 Privacy by Design

The gateway implements privacy by design through deterministic PII/PHI redaction in the enforcement path. Data protection is not a feature flag or an optional plugin -- it is a mandatory stage in the request pipeline that cannot be bypassed. This aligns with GDPR Article 25 (Data Protection by Design and by Default).

### 5.3 Sovereignty and Self-Determination

Organizations using the gateway retain complete control over:
- **Policy definitions** -- authored in Rego, version-controlled, reviewed by the organization
- **Data residency** -- self-hosted, no external data egress beyond the chosen LLM provider
- **Audit evidence** -- stored locally, hash-chained, available for regulatory inspection without third-party involvement
- **Deployment** -- Kubernetes, Docker, or bare-metal; no vendor lock-in

### 5.4 Healthcare Use Case

A hospital deploying AI for clinical note summarization can use Sovereign RAG Gateway to:
- Enforce that PHI is redacted before any text reaches the LLM provider
- Restrict RAG retrieval to authorized medical knowledge bases (not all indexed data)
- Produce audit trails proving that governance was enforced for every request
- Demonstrate compliance to health data regulators with hash-chained evidence

### 5.5 Financial Services Use Case

A bank deploying AI for customer service can use Sovereign RAG Gateway to:
- Enforce PII redaction for account numbers, transaction details, and personal identifiers
- Apply tenant-scoped policies that restrict which models and data sources each department can access
- Generate audit evidence for FCA/BaFin/ECB regulatory inspections
- Operate with fail-closed semantics that satisfy DORA operational resilience requirements

---

## 6. Existing Work and Project Status

### 6.1 Current State

- **Version**: v1.1.0 (GA), promoted through alpha, RC, and GA stages with stabilization window validation
- **Releases**: 19 releases following semantic versioning with structured release notes
- **CI**: 11 workflows covering lint, type check, testing, deployment smoke, SLO reliability, release signing, Terraform validation, evidence replay, rollback drills, and operational evidence reporting
- **Supply Chain**: Sigstore cosign on every release, SPDX SBOM generation, provenance attestation, OpenSSF Scorecard (weekly)
- **Deployment**: Helm chart with values schema validation, RBAC, network policies; Argo CD ApplicationSet; External Secrets Operator integration
- **Observability**: Prometheus metrics (7 metric families), Grafana dashboard (10 panels)

### 6.2 What This Grant Adds

The project is architecturally complete and operationally mature. What it lacks is the security depth and compliance documentation that European regulated organizations require before production adoption:

- **No professional security audit** -- the PII redaction engine, OPA integration, and authentication layer have not been reviewed by an independent security firm
- **Limited European PII coverage** -- current patterns focus on US formats; European national ID, tax ID, and health ID patterns are missing
- **No EU AI Act mapping** -- organizations cannot yet map gateway capabilities to specific regulatory requirements
- **No GDPR operational guide** -- there is no step-by-step guide for using audit trails to satisfy Article 30 record-keeping

---

## 7. Comparable Projects and Differentiation

| Project | Approach | Limitation |
|---|---|---|
| LiteLLM | Proxy/gateway for multiple LLM providers | No policy enforcement, no redaction, no audit trails |
| Guardrails AI | Validation framework for LLM outputs | Post-hoc validation, not inline enforcement; no RAG governance |
| Portkey | AI gateway with observability | Cloud-hosted, no self-hosted option; no policy engine; no data redaction |
| LangChain/LlamaIndex | RAG frameworks | No governance layer; no policy enforcement; no audit evidence |

Sovereign RAG Gateway is the only open source project that combines inline policy enforcement (OPA), data redaction (PHI/PII), retrieval authorization, and hash-chained audit trails in a single deterministic enforcement pipeline with fail-closed semantics.

---

## 8. Submission Checklist

- [ ] Navigate to https://nlnet.nl/propose/
- [ ] Select "NGI Zero Commons Fund" as the fund
- [ ] Fill in project name: "Sovereign RAG Gateway"
- [ ] Paste abstract from Section 1 (200 words)
- [ ] For "Describe the work" use Sections 2 and 3
- [ ] For "Relevance to NGI" use Section 5
- [ ] For "Comparable projects" use Section 7
- [ ] Budget: EUR 42,000 with milestone breakdown from Section 3
- [ ] Include repository URL and architecture documentation link
- [ ] Submit before 2026-04-01 deadline
- [ ] NLnet typically responds within 2-3 months; monitor email for review questions
- [ ] If selected, NLnet will request a detailed milestone plan (use Section 4)

---

## 9. Additional Notes for NLnet Reviewers

**On project scope**: This is not a "build a new thing" proposal. The gateway exists, works, and has 19 releases. This proposal funds the security and compliance hardening that transforms working open source software into infrastructure that European regulated organizations can actually adopt.

**On sustainability**: The gateway has zero runtime costs (self-hosted, MIT license). Post-grant sustainability comes from organizational adoption driving community contribution, not from commercial licensing. The compliance documentation and security audit report are permanent assets that compound in value as the regulatory environment matures.

**On the maintainer**: Ogulcan Aydogan is the sole maintainer with a background in ML engineering and infrastructure. The project demonstrates sustained engineering discipline (19 releases, 11 CI workflows, GA promotion gates) rather than a one-time code dump.
