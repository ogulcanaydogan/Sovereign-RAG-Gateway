# Huntr Bug Bounty Registration Guide

## Program Details

| Field | Value |
|---|---|
| **Platform** | Huntr (https://huntr.com) |
| **Project** | Sovereign RAG Gateway |
| **Repository** | https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway |
| **Language** | Python 3.12+ |
| **Current Version** | v1.1.0 (GA) |
| **License** | MIT |
| **Primary Contact** | Ogulcan Aydogan |

---

## 1. Program Description

Sovereign RAG Gateway is a policy-first, OpenAI-compatible governance gateway for regulated AI workloads. It enforces runtime policy evaluation (OPA/Rego), PHI/PII data redaction, retrieval authorization, and produces hash-chained audit trails for every request before traffic reaches upstream LLM providers.

The gateway operates in regulated environments (healthcare, financial services) where security failures have direct compliance and legal consequences. We welcome security research that identifies vulnerabilities in the governance enforcement pipeline, data protection mechanisms, and audit integrity guarantees.

---

## 2. Scope

### 2.1 In Scope: Core Modules

All source code under `app/` is in scope. The following components are prioritized by security criticality:

#### Tier 1: Critical Security Components

| Component | Path | Description | Why It Matters |
|---|---|---|---|
| **PII/PHI Redaction Engine** | `app/redaction/engine.py` | Regex-based detection and scrubbing of personally identifiable information and protected health information | A bypass means sensitive data reaches external LLM providers, a direct GDPR/HIPAA violation |
| **OPA Policy Client** | `app/policy/client.py` | HTTP client to OPA with fail-closed enforcement semantics | A bypass means requests can reach providers without policy evaluation, breaking the governance guarantee |
| **Policy Transforms** | `app/policy/transforms.py` | Policy-driven request/response mutations (model downgrade, parameter adjustment) | A bypass means policy-mandated restrictions can be circumvented |
| **Policy Models** | `app/policy/models.py` | PolicyDecision schema validation | Malformed policy responses could lead to incorrect allow/deny decisions |
| **Authentication Middleware** | `app/middleware/auth.py` | Bearer token validation, required header enforcement, tenant/user extraction | A bypass grants unauthorized access to the gateway |

#### Tier 2: High Security Components

| Component | Path | Description | Why It Matters |
|---|---|---|---|
| **Audit Writer** | `app/audit/writer.py` | Hash-chained JSON Lines audit event production with schema validation | Manipulation breaks tamper-evidence guarantees; missing events create audit gaps |
| **Retrieval Orchestrator** | `app/rag/retrieval.py` | Policy-aware retrieval coordination; enforces connector authorization from policy decisions | A bypass allows access to unauthorized data sources |
| **Connector Registry** | `app/rag/registry.py` | Connector registration and lookup | Registry manipulation could redirect retrieval to attacker-controlled sources |

#### Tier 3: RAG Connectors

| Component | Path | Description | Why It Matters |
|---|---|---|---|
| **Filesystem Connector** | `app/rag/connectors/filesystem.py` | JSON Lines index reader | Path traversal or injection could expose unauthorized files |
| **PostgreSQL pgvector Connector** | `app/rag/connectors/postgres.py` | Semantic retrieval via PostgreSQL | SQL injection could expose or modify data |
| **S3 Connector** | `app/rag/connectors/s3.py` | S3 JSONL index with local caching | SSRF, path traversal, or cache poisoning |
| **Confluence Connector** | `app/rag/connectors/confluence.py` | Confluence Cloud API with BM25 scoring | SSRF, credential leakage, authorization bypass |
| **Jira Connector** | `app/rag/connectors/jira.py` | Jira Cloud API with BM25 scoring | SSRF, credential leakage, authorization bypass |
| **SharePoint Connector** | `app/rag/connectors/sharepoint.py` | SharePoint connector | SSRF, credential leakage, authorization bypass |
| **Connector Base** | `app/rag/connectors/base.py` | Base connector interface | Interface-level vulnerabilities affecting all connectors |

#### Tier 4: Supporting Components

| Component | Path | Description | Why It Matters |
|---|---|---|---|
| **Chat Service** | `app/services/chat_service.py` | Full pipeline orchestration: auth, policy, retrieval, redact, egress | Logic errors could skip enforcement stages |
| **Inflight Guard** | `app/services/inflight_guard.py` | Request concurrency and overload protection | Bypass could enable DoS or resource exhaustion |
| **Provider Implementations** | `app/providers/http_openai.py`, `app/providers/azure_openai.py`, `app/providers/anthropic.py` | Upstream LLM provider adapters | SSRF, response injection, credential leakage |
| **Provider Registry** | `app/providers/registry.py` | Provider selection and fallback routing | Routing manipulation could direct traffic to attacker-controlled endpoints |
| **API Routes** | `app/api/routes.py` | FastAPI route definitions | Input validation, parameter injection |
| **Embeddings** | `app/rag/embeddings.py` | Hash-based and HTTP embedding generators | SSRF in HTTP embedding generator |
| **Request ID Middleware** | `app/middleware/request_id.py` | Unique request ID generation | Predictable IDs could enable replay or correlation attacks |
| **Webhook Dispatcher** | `app/webhooks/dispatcher.py` | Webhook event delivery | SSRF, injection in webhook payloads |
| **Dead Letter Store** | `app/webhooks/dead_letter_store.py` | Failed webhook storage | Data exposure, injection |
| **Configuration** | `app/config/settings.py` | Settings management (Pydantic BaseSettings) | Secrets exposure, injection through environment variables |
| **Metrics** | `app/metrics.py` | Prometheus metrics endpoint | Information disclosure, cardinality attacks |
| **Budget Tracker** | `app/budget/tracker.py` | Cost tracking | Manipulation could obscure actual spend |

### 2.2 In Scope: Infrastructure

| Component | Path | Description |
|---|---|---|
| **Rego Policies** | `policies/` (if present) or any `.rego` files | OPA policy definitions; logic errors could create unintended allow/deny paths |
| **Helm Chart** | `charts/` | Kubernetes deployment manifests; misconfigurations affecting security posture |
| **Dockerfile** | `Dockerfile` | Container build; image security, secrets in layers, privilege escalation |
| **Docker Compose** | `docker-compose.yml` | Local deployment; secrets exposure, network misconfigurations |
| **Terraform** | `deploy/` | Infrastructure-as-code; misconfigurations, secrets in state |

### 2.3 Out of Scope

The following are explicitly out of scope for bug bounty reports:

| Category | Path | Reason |
|---|---|---|
| **Examples** | `examples/` | Sample code, not deployed in production |
| **Documentation** | `docs/` | Markdown files, no executable code |
| **Deployment Scripts** | `deploy/` scripts (non-Terraform) | Operational scripts, not part of the runtime gateway |
| **Test Code** | `tests/` | Test fixtures and test utilities; not deployed |
| **Benchmarks** | `benchmarks/` | Performance test data and scripts |
| **Build Artifacts** | `artifacts/`, `sovereign_rag_gateway.egg-info/` | Generated output, not source |
| **CI Workflows** | `.github/workflows/` | CI/CD configuration (report supply chain issues through SECURITY.md instead) |
| **Scripts** | `scripts/` | Build, release, and utility scripts not part of runtime |
| **Virtual Environment** | `.venv/` | Dependency installation artifacts |

### 2.4 Out of Scope: Vulnerability Types

The following vulnerability types are out of scope regardless of where they occur:

- Social engineering attacks against maintainers
- Physical attacks
- Denial of service through volume (rate limiting is outside the gateway's scope)
- Vulnerabilities in upstream dependencies that are not exploitable through the gateway's code
- Vulnerabilities requiring local access to the host running the gateway
- Self-XSS or issues requiring the victim to paste code into their browser
- Issues in third-party services (OPA, PostgreSQL, S3) unless the gateway's integration code creates the vulnerability

---

## 3. Severity Classification

### 3.1 Critical (CVSS 9.0-10.0)

Vulnerabilities that break the core governance guarantee. Immediate response required.

| Category | Example |
|---|---|
| **PII/PHI Data Leak** | Bypass of the redaction engine that allows personally identifiable or protected health information to reach upstream LLM providers unredacted |
| **Policy Enforcement Bypass** | Any code path that allows a request to reach an upstream provider without OPA policy evaluation, including edge cases where fail-closed semantics are not enforced |
| **Complete Authentication Bypass** | Unauthenticated access to chat/completions, embeddings, or RAG retrieval endpoints |
| **Audit Trail Forgery** | Ability to inject, modify, or delete audit events, or break the hash chain such that tamper evidence is destroyed |

### 3.2 High (CVSS 7.0-8.9)

Vulnerabilities that undermine specific enforcement guarantees.

| Category | Example |
|---|---|
| **Partial Authentication Bypass** | Tenant isolation failure, accessing another tenant's data, policies, or retrieval results |
| **Retrieval Authorization Bypass** | Accessing retrieval connectors or data sources that the evaluated policy explicitly denies |
| **Audit Trail Manipulation** | Causing audit events to contain incorrect or misleading information (wrong policy hash, wrong redaction count, wrong provider route) without full forgery |
| **Policy Transform Bypass** | Circumventing policy-mandated transforms (model downgrade, parameter restrictions) while still receiving an allowed decision |
| **Credential Leakage** | Extraction of provider API keys, database credentials, or OPA credentials through the gateway's API surface |

### 3.3 Medium (CVSS 4.0-6.9)

Vulnerabilities with limited impact or requiring specific conditions.

| Category | Example |
|---|---|
| **Denial of Service** | Crafted input that causes the gateway to crash, hang, or consume excessive resources (CPU, memory, disk) |
| **Connector Injection** | SQL injection in PostgreSQL connector, path traversal in filesystem connector, or SSRF through S3/Confluence/Jira connectors, where the impact is limited by connector authorization |
| **Information Disclosure** | Leaking internal configuration, provider endpoints, or tenant metadata through error messages, metrics, or response headers |
| **Overload Shedding Bypass** | Circumventing the inflight guard to exceed concurrency limits |
| **Prompt Injection Affecting Governance** | Prompt content that influences policy evaluation, redaction decisions, or retrieval authorization (these should be decoupled from prompt content) |

### 3.4 Low (CVSS 0.1-3.9)

Hardening recommendations and minor issues.

| Category | Example |
|---|---|
| **Security Hardening** | Missing HTTP security headers, verbose error messages in production mode, timing side channels in authentication that leak information but don't enable bypass |
| **Configuration Weakness** | Default settings that are insecure if not changed, missing input validation on non-security-critical fields |
| **Informational** | Theoretical attack vectors that require unlikely preconditions, defense-in-depth recommendations |

---

## 4. Responsible Disclosure Policy

### 4.1 Reporting

1. **Do not** create a public GitHub issue for security vulnerabilities
2. Report through Huntr's platform for tracked vulnerabilities
3. For vulnerabilities outside Huntr's scope, email the security contact in SECURITY.md
4. Include:
   - Description of the vulnerability
   - Steps to reproduce (ideally with a proof of concept)
   - Affected component and file path
   - Estimated severity (Critical/High/Medium/Low)
   - Suggested fix (optional but appreciated)

### 4.2 Response Timeline

| Stage | Timeline |
|---|---|
| Initial acknowledgment | Within 48 hours |
| Severity assessment | Within 72 hours |
| Status update | Within 7 days |
| Fix for Critical | Within 14 days |
| Fix for High | Within 30 days |
| Fix for Medium | Within 60 days |
| Fix for Low | Next scheduled release |

### 4.3 Disclosure Timeline

- 90-day coordinated disclosure window from initial report
- If a fix is released before 90 days, disclosure can proceed after the fix is published
- Extensions can be negotiated for complex vulnerabilities

---

## 5. Testing Environment Setup

Researchers can set up a local testing environment:

```bash
# Clone the repository
git clone https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway.git
cd Sovereign-RAG-Gateway

# Install dependencies
pip install uv
uv sync --extra dev

# Start with Docker Compose (includes OPA and PostgreSQL)
docker compose up -d

# Run the gateway
uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8080

# Run tests to verify setup
uv run pytest
```

### 5.1 Key Endpoints to Test

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/chat/completions` | POST | Primary chat endpoint, full enforcement pipeline |
| `/v1/embeddings` | POST | Embedding generation endpoint |
| `/v1/models` | GET | Model listing |
| `/healthz` | GET | Liveness probe |
| `/readyz` | GET | Readiness probe |
| `/metrics` | GET | Prometheus metrics |

### 5.2 Environment Variables for Testing

| Variable | Purpose |
|---|---|
| `SRG_OPA_URL` | OPA server URL for policy evaluation |
| `SRG_OPA_SIMULATE_TIMEOUT` | Set to `true` to test fail-closed behavior |
| `SRG_RAG_ALLOWED_CONNECTORS` | Comma-separated list of enabled connectors |
| `SRG_RAG_POSTGRES_DSN` | PostgreSQL connection string for pgvector connector |

---

## 6. Attack Surface Priorities

For researchers looking to focus their efforts, these are the highest-value attack surfaces ordered by potential impact:

### Priority 1: Redaction Bypass

The redaction engine in `app/redaction/engine.py` is the last line of defense before data reaches external providers. Test:
- Unicode normalization bypass (e.g., fullwidth digits, homoglyphs)
- Encoding tricks (Base64-encoded PII in prompts)
- Context manipulation (PII split across multiple messages)
- Edge cases in regex patterns (boundary conditions, locale-specific formats)
- Classification-aware redaction bypass (manipulating the data classification to skip redaction)

### Priority 2: Policy Enforcement Gaps

The policy client in `app/policy/client.py` must enforce fail-closed semantics in all cases. Test:
- OPA timeout handling: does the gateway always deny on timeout?
- Malformed OPA responses: what happens with unexpected JSON structures?
- Race conditions between policy evaluation and request processing
- Observe mode to enforce mode transition: can observe-mode requests bypass enforcement?
- Empty or null policy decisions

### Priority 3: Authentication and Tenant Isolation

The auth middleware in `app/middleware/auth.py` extracts tenant and user identity. Test:
- Header injection to override tenant_id or user_id
- Token replay across tenants
- Missing or malformed authentication headers
- Extraction logic edge cases (empty strings, special characters, excessive length)

### Priority 4: Retrieval Authorization

The retrieval orchestrator in `app/rag/retrieval.py` enforces policy-scoped connector access. Test:
- Prompt content that attempts to override authorized connector list
- Connector name manipulation or injection
- Cross-tenant retrieval (accessing another tenant's retrieval results)
- Connector credential leakage through error messages

### Priority 5: Audit Trail Integrity

The audit writer in `app/audit/writer.py` produces hash-chained evidence. Test:
- Event injection or modification through the gateway's API
- Hash chain breakage through concurrent writes
- Schema validation bypass (events that pass validation but contain misleading data)
- Missing audit events for specific code paths (e.g., error paths, timeout paths)

---

## 7. Registration Steps

### 7.1 Register the Project on Huntr

1. Navigate to https://huntr.com
2. Sign in or create a maintainer account
3. Click "Add a Project" or navigate to the project registration page
4. Enter the repository URL: `https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway`
5. Fill in the program details:
   - **Project Name**: Sovereign RAG Gateway
   - **Description**: Policy-first OpenAI-compatible governance gateway for regulated AI workloads with runtime policy evaluation, PHI/PII redaction, and hash-chained audit trails
   - **Language**: Python
   - **License**: MIT
6. Define the scope using Sections 2.1 through 2.4 of this document
7. Define severity levels using Section 3 of this document
8. Set the response timeline from Section 4.2
9. Publish the program

### 7.2 Post-Registration

- [ ] Add a link to the Huntr program page in SECURITY.md
- [ ] Add a "Security" section to README.md referencing both SECURITY.md and the Huntr program
- [ ] Monitor Huntr for incoming reports and set up email notifications
- [ ] Establish an internal SLA for triaging reports within the timelines defined in Section 4.2

---

## 8. Triage Workflow

When a report arrives through Huntr:

```
Report received
    |
    v
Acknowledge within 48h
    |
    v
Reproduce the issue
    |
    +---> Cannot reproduce --> Request more info from researcher
    |
    v
Assess severity (Section 3)
    |
    v
Assign fix timeline (Section 4.2)
    |
    v
Develop fix on private branch
    |
    v
Verify fix resolves the issue
    |
    v
Add regression test to CI
    |
    v
Release fix (through normal release pipeline with Sigstore signing)
    |
    v
Publish security advisory (GitHub Security Advisories)
    |
    v
Credit researcher and close Huntr report
```

---

## 9. Legal Safe Harbor

Researchers acting in good faith and in compliance with this program's scope and disclosure policy won't face legal action from the project maintainers. This safe harbor applies to:

- Testing within the defined scope (Section 2)
- Reporting through Huntr or the security contact in SECURITY.md
- Not publicly disclosing vulnerabilities before the coordinated disclosure timeline (Section 4.3)
- Not accessing, modifying, or exfiltrating data belonging to other users in production deployments

This safe harbor doesn't extend to:
- Testing against production deployments operated by third parties without their consent
- Automated vulnerability scanning that causes service degradation
- Social engineering or physical attacks
