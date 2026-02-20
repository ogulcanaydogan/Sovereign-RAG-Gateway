# Sovereign RAG Gateway

**A policy-first, OpenAI-compatible governance gateway for regulated AI workloads.**

![Version](https://img.shields.io/badge/version-0.4.0-blue)
![Python](https://img.shields.io/badge/python-3.12+-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/license-see%20LICENSE-green)
![CI](https://img.shields.io/badge/CI-passing-brightgreen)

Sovereign RAG Gateway enforces runtime governance — identity verification, policy evaluation, data redaction, and retrieval authorization — in the critical path of every LLM and RAG request, before traffic reaches upstream providers. It produces tamper-evident, hash-chained decision trails that enable forensic replay during incident response and regulatory audits.

Built for security engineering teams, platform teams, and SREs operating AI systems in healthcare, financial services, and other regulated domains where post-hoc controls are insufficient.

---

## The Problem

Enterprise AI deployments in regulated industries face a structural gap: governance controls are bolted on after the fact — one service handles redaction, another handles policy, another handles routing, and audit logs are scattered across systems with no causal linkage. During incidents, no single system can reconstruct the complete decision path for a given request.

In healthcare (HIPAA), financial services (FCA, PRA), and other regulated domains, auditors require demonstrable proof that controls were enforced at decision time — not aspirational documentation that controls exist somewhere in the architecture. The fundamental question is: *what exact policy version evaluated this request, what transformations were applied to the data, and can you cryptographically prove it?*

Post-hoc logging cannot answer this question. If redaction runs in a separate service with eventual consistency, you cannot prove that PHI was scrubbed before it left the boundary. If policy evaluation is asynchronous, you cannot prove the request was governed before reaching the provider. Observability without enforcement is monitoring, not governance.

## How It Works

Sovereign RAG Gateway moves governance into the hot path. Every request passes through a deterministic enforcement pipeline before any data leaves the boundary:

```mermaid
flowchart TD
    A["Client Request"] --> B["Identity & Classification\n(tenant, user, data class)"]
    B --> C{"Policy Evaluation\n(OPA)"}
    C -- "OPA Unavailable" --> DENY["Deterministic Deny\n(fail-closed)"]
    C -- "Deny" --> DENY
    C -- "Allow" --> D["Data Redaction\n(PHI/PII, classification-aware)"]
    D --> E{"RAG Enabled?"}
    E -- "Yes" --> F["Retrieval Authorization\n(policy-scoped connectors)"]
    F --> G["Citation Integrity\nEnforcement"]
    G --> H["Provider Egress\n(upstream LLM)"]
    E -- "No" --> H
    H --> I["Response to Client"]

    B -.-> AUD["Audit Artifact\n(request-linked, hash-chained)"]
    C -.-> AUD
    D -.-> AUD
    F -.-> AUD
    H -.-> AUD

    style DENY fill:#d32f2f,color:#fff,stroke:#b71c1c
    style AUD fill:#1565c0,color:#fff,stroke:#0d47a1
    style C fill:#f57f17,color:#fff,stroke:#e65100
    style A fill:#2e7d32,color:#fff,stroke:#1b5e20
    style I fill:#2e7d32,color:#fff,stroke:#1b5e20
```

The gateway is intentionally opinionated about failure behaviour: if policy evaluation is unavailable, it defaults to **deterministic deny**. In regulated environments, silent fallback to permissive behaviour creates larger incident and audit risk than explicit denial.

### The Problem This Solves — Before vs After

```mermaid
flowchart LR
    subgraph BEFORE["Typical Enterprise AI (Scattered Controls)"]
        direction TB
        APP1["App Code"] --> LLM1["LLM Provider"]
        APP1 -.-> LOG1["Logger A"]
        APP1 -.-> RED1["Redaction Svc"]
        APP1 -.-> POL1["Policy Svc"]
        APP1 -.-> AUD1["Audit DB"]
        LOG1 ~~~ RED1
        RED1 ~~~ POL1
        POL1 ~~~ AUD1
    end

    subgraph AFTER["Sovereign RAG Gateway (Unified Control Plane)"]
        direction TB
        APP2["App Code\n(unchanged)"] --> GW["Gateway\n(policy + redact + audit + RAG)"]
        GW --> LLM2["LLM Provider"]
    end

    style BEFORE fill:#fff3e0,stroke:#e65100
    style AFTER fill:#e8f5e9,stroke:#2e7d32
    style GW fill:#1565c0,color:#fff,stroke:#0d47a1
```

## Architecture

The gateway is structured as five cooperating layers. Each layer has a single responsibility, and data flows through them in a fixed, deterministic sequence:

```mermaid
graph TB
    subgraph GATEWAY["Sovereign RAG Gateway"]
        direction TB
        subgraph INGRESS["Ingress Layer"]
            AUTH["Auth Middleware\n(Bearer + headers)"]
            REQID["Request ID\nMiddleware"]
        end

        subgraph ENFORCEMENT["Enforcement Layer"]
            POLICY["Policy Engine"]
            REDACT["Redaction Engine\n(PHI/PII)"]
            TRANSFORM["Policy Transforms"]
        end

        subgraph RETRIEVAL["RAG Layer"]
            ORCH["Retrieval\nOrchestrator"]
            REG["Connector Registry"]
            FS["Filesystem\nConnector"]
            PG["PostgreSQL\npgvector"]
            S3C["S3\nConnector"]
            CONFL["Confluence\nConnector"]
            JIRAC["Jira\nConnector"]
        end

        subgraph EVIDENCE["Evidence Layer"]
            AUDIT["Audit Writer\n(JSON Lines, hash-chained)"]
        end

        EGRESS["Provider Egress\n(OpenAI-compatible)"]
    end

    CLIENT["Client\n(OpenAI SDK)"] --> AUTH
    AUTH --> REQID
    REQID --> POLICY
    POLICY --> TRANSFORM
    TRANSFORM --> REDACT
    REDACT --> ORCH
    ORCH --> REG
    REG --> FS
    REG --> PG
    REG --> S3C
    REG --> CONFL
    REG --> JIRAC
    ORCH --> EGRESS
    EGRESS --> LLM["Upstream LLM\nProvider"]

    POLICY <--> OPA["OPA Server\n(policy bundles)"]

    AUTH -.-> AUDIT
    POLICY -.-> AUDIT
    REDACT -.-> AUDIT
    ORCH -.-> AUDIT
    EGRESS -.-> AUDIT

    style GATEWAY fill:#f5f5f5,stroke:#424242,stroke-width:2px
    style INGRESS fill:#e3f2fd,stroke:#1565c0
    style ENFORCEMENT fill:#fff3e0,stroke:#e65100
    style RETRIEVAL fill:#e8f5e9,stroke:#2e7d32
    style EVIDENCE fill:#ede7f6,stroke:#4527a0
    style OPA fill:#f57f17,color:#fff,stroke:#e65100
    style LLM fill:#78909c,color:#fff,stroke:#455a64
    style CLIENT fill:#2e7d32,color:#fff,stroke:#1b5e20
```

### Module Map

| Layer | Modules | Responsibility |
|---|---|---|
| Ingress | `middleware/auth.py`, `middleware/request_id.py` | Identity extraction, classification headers, request tracing |
| Enforcement | `policy/client.py`, `policy/transforms.py`, `redaction/engine.py` | OPA evaluation, fail-closed contract, PHI/PII scrubbing |
| Retrieval | `rag/retrieval.py`, `rag/registry.py`, `rag/connectors/` | Policy-scoped dispatch across 5 connectors (filesystem, pgvector, S3, Confluence, Jira) |
| Egress | `providers/registry.py`, `providers/http_openai.py`, `providers/azure_openai.py`, `providers/anthropic.py` | Multi-provider routing with streaming, cost-aware fallback |
| Evidence | `audit/writer.py` | Hash-chained JSON Lines, schema-validated audit events |

Full architecture reference: [`ARCHITECTURE.md`](ARCHITECTURE.md)

## Core Capabilities

### In-Path Policy Enforcement

```mermaid
flowchart TD
    REQ["Request Context\n(tenant, user, classification,\nmodel, RAG config)"] --> PC["PolicyClient"]
    PC -->|"HTTP POST"| OPA["OPA Server"]

    OPA --> ALLOW["Allow\n+ transforms\n+ policy_hash"]
    OPA --> DENY["Deny\n+ reason code\n+ policy_hash"]

    PC -->|"timeout / error"| CLOSED["Fail-Closed Deny\n(OPA unavailable)"]

    ALLOW --> AUDIT["Audit Event"]
    DENY --> AUDIT
    CLOSED --> AUDIT

    style DENY fill:#d32f2f,color:#fff,stroke:#b71c1c
    style CLOSED fill:#d32f2f,color:#fff,stroke:#b71c1c
    style ALLOW fill:#2e7d32,color:#fff,stroke:#1b5e20
    style OPA fill:#f57f17,color:#fff,stroke:#e65100
    style AUDIT fill:#1565c0,color:#fff,stroke:#0d47a1
```

Every request is evaluated by OPA before retrieval or provider egress. Policy decisions are deterministic, machine-readable, and recorded with the policy version hash. Supports `enforce` mode (blocks requests) and `observe` mode (logs without blocking) for progressive rollout.

### Data Protection Flow

```mermaid
flowchart LR
    CLIENT["Client Request\n(may contain PHI)"] --> CLASS{"Classification\nHeader"}
    CLASS -- "phi / pii" --> SCAN["Regex Pattern\nScanner"]
    CLASS -- "public" --> PASS["Unchanged\nPayload"]

    SCAN --> MRN["MRN Pattern\n→ [MRN_REDACTED]"]
    SCAN --> DOB["DOB Pattern\n→ [DOB_REDACTED]"]
    SCAN --> PHONE["Phone Pattern\n→ [PHONE_REDACTED]"]

    MRN --> OUT["Redacted\nPayload"]
    DOB --> OUT
    PHONE --> OUT

    OUT --> PROVIDER["To Provider\n(PHI removed)"]
    PASS --> PROVIDER

    OUT -.-> AUDIT["Audit Event\n(redaction_count)"]

    style CLIENT fill:#fff3e0,stroke:#e65100
    style SCAN fill:#fce4ec,stroke:#c62828
    style PROVIDER fill:#2e7d32,color:#fff,stroke:#1b5e20
    style AUDIT fill:#1565c0,color:#fff,stroke:#0d47a1
    style MRN fill:#fce4ec,stroke:#c62828
    style DOB fill:#fce4ec,stroke:#c62828
    style PHONE fill:#fce4ec,stroke:#c62828
```

Classification-aware redaction activates only when the request's data classification header indicates PHI or PII. Redaction events are counted, logged, and included in the audit artifact. The system makes no claim of perfect detection — false-positive and false-negative rates are explicitly measured and published.

### Policy-Scoped Retrieval (RAG)

```mermaid
graph TB
    POLICY["Policy Decision\n(allowed connectors)"] --> AUTH_CHECK["Authorization\nCheck"]
    AUTH_CHECK -- "authorized" --> REG["Connector\nRegistry"]
    AUTH_CHECK -- "denied" --> BLOCK["Blocked\n(regardless of prompt)"]

    REG --> FS["Filesystem\nConnector"]
    REG --> PG["PostgreSQL\npgvector"]
    REG --> S3["S3\nConnector"]
    REG --> CONFL["Confluence\n(read-only)"]
    REG --> JIRA["Jira\n(read-only)"]

    FS --> MERGE["Merge & Rank\nResults"]
    PG --> MERGE
    S3 --> MERGE
    CONFL --> MERGE
    JIRA --> MERGE

    MERGE --> CIT["Citation\nMetadata"]
    CIT --> VERIFY["Citation Integrity\nVerification"]

    style BLOCK fill:#d32f2f,color:#fff,stroke:#b71c1c
    style POLICY fill:#f57f17,color:#fff,stroke:#e65100
    style VERIFY fill:#2e7d32,color:#fff,stroke:#1b5e20
```

Connector access is authorized per-tenant and per-policy. Source partitions are enforced regardless of prompt content — prompt injection attempts to override source scope are ineffective because authorization is decoupled from prompt content. Citations in responses must reference only authorized sources.

### Tamper-Evident Audit Trail

```mermaid
flowchart LR
    subgraph CHAIN["SHA-256 Hash Chain (append-only JSON Lines)"]
        direction LR
        E1["Event N-1\npayload_hash: abc12"]
        E2["Event N\nprev_hash: abc12\npayload_hash: def45"]
        E3["Event N+1\nprev_hash: def45\npayload_hash: 78gh9"]

        E1 --> E2
        E2 --> E3
    end

    subgraph FIELDS["Each Audit Event Contains"]
        direction TB
        F1["request_id"]
        F2["tenant_id + user_id"]
        F3["policy_decision + policy_hash"]
        F4["redaction_count"]
        F5["provider_route + latency"]
        F6["payload_hash + prev_hash"]
    end

    E2 -.-> REPLAY["Forensic Replay\n(by request_id)"]

    style CHAIN fill:#ede7f6,stroke:#4527a0
    style FIELDS fill:#e3f2fd,stroke:#1565c0
    style REPLAY fill:#2e7d32,color:#fff,stroke:#1b5e20
```

Each audit event is hash-chained using SHA-256 — every event records the `payload_hash` of the previous event as its `prev_hash`, creating a tamper-evident chain. Given a `request_id`, an investigator can reconstruct the complete execution path: auth context, policy evaluation, transforms applied, redaction operations, retrieval sources, and provider routing decision.

### Multi-Provider Routing with Cost-Aware Fallback

```mermaid
flowchart TD
    REQ["Chat / Embeddings /\nStream Request"] --> REG["Provider Registry\n(eligible_chain)"]

    REG --> CAP{"Capability\nCheck"}
    CAP -->|"chat / embeddings\n/ streaming"| SELECT{"Select\nPrimary"}

    SELECT --> P1["OpenAI\n(priority: 10)"]
    P1 -->|"success"| OK["Return Response\nor SSE Stream"]
    P1 -->|"429 / 502 / 503"| FB{"Fallback?"}

    FB -->|"next in chain"| P2["Azure OpenAI\n(priority: 50)"]
    P2 -->|"success"| OK
    P2 -->|"429 / 502 / 503"| P3["Anthropic\n(priority: 100)"]
    P3 --> OK

    FB -->|"no more providers"| ERR["ProviderError"]

    REG --> COST["cheapest_for_tokens()\n(cost-aware selection)"]
    COST -.-> SELECT

    style REG fill:#e3f2fd,stroke:#1565c0
    style OK fill:#2e7d32,color:#fff,stroke:#1b5e20
    style ERR fill:#d32f2f,color:#fff,stroke:#b71c1c
    style COST fill:#fff3e0,stroke:#e65100
    style CAP fill:#fff3e0,stroke:#e65100
```

Capability-aware provider routing with `eligible_chain()` filters providers by operation type (chat, embeddings, streaming) and model support before attempting fallback. Priority-ordered fallback chain with automatic failover on retryable errors (429, 502, 503). Cost-per-token selection via `cheapest_for_tokens()` enables budget-aware routing across OpenAI, Azure OpenAI, and Anthropic. Routing decisions — provider name, attempts, and full fallback chain — are recorded in audit events for forensic analysis.

### Observability Stack

```mermaid
flowchart LR
    GW["Gateway\n(/metrics endpoint)"] --> PROM["Prometheus\n(scrape every 10s)"]
    PROM --> GRAF["Grafana\n(10 pre-built panels)"]

    GRAF --> R1["Request Overview\n(rate, latency p50/p95/p99,\nstatus distribution)"]
    GRAF --> R2["Policy Decisions\n(allow/deny rate,\ndeny ratio gauge)"]
    GRAF --> R3["Provider & Cost\n(token throughput,\nhourly cost, fallback rate)"]
    GRAF --> R4["Data Protection\n(redaction rate,\nprovider distribution)"]

    style GW fill:#e3f2fd,stroke:#1565c0
    style PROM fill:#fff3e0,stroke:#e65100
    style GRAF fill:#e8f5e9,stroke:#2e7d32
```

Custom in-process Prometheus collector with zero external dependencies — 6 counters and 1 histogram exposed at `/metrics` in standard text format. Pre-built Grafana dashboard ConfigMap with 10 panels across four operational domains, deployable alongside the gateway Helm chart.

### OpenAI API Compatibility

Drop-in compatible with OpenAI's chat completions, embeddings, and model listing endpoints. Application teams use standard OpenAI client SDKs without modification — governance is transparent at the transport layer.

## Security Trust Boundaries

```mermaid
flowchart TD
    subgraph UNTRUSTED["Untrusted Zone"]
        CLIENT["Client Application\n(may send PHI/PII)"]
        LLM["External LLM Provider\n(data leaves boundary)"]
    end

    subgraph BOUNDARY["Gateway Enforcement Boundary"]
        direction TB
        AUTH["Auth Middleware\n(identity verification)"]
        POLICY["Policy Engine\n(OPA evaluation)"]
        REDACT["Redaction Engine\n(PHI/PII removal)"]
        AUDIT["Audit Writer\n(tamper-evident trail)"]
    end

    subgraph CONTROLLED["Controlled Zone"]
        OPA["OPA Server\n(policy bundles)"]
        PG["PostgreSQL\n(pgvector)"]
        FS["Filesystem Index\n(JSON Lines)"]
    end

    CLIENT -->|"raw request\n(may contain PHI)"| AUTH
    AUTH --> POLICY
    POLICY --> REDACT
    REDACT -->|"redacted +\npolicy-evaluated"| LLM

    POLICY <-->|"mTLS / internal"| OPA
    REDACT -.-> PG
    REDACT -.-> FS

    AUTH -.-> AUDIT
    POLICY -.-> AUDIT
    REDACT -.-> AUDIT

    style UNTRUSTED fill:#ffebee,stroke:#c62828,stroke-width:2px
    style BOUNDARY fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    style CONTROLLED fill:#e3f2fd,stroke:#1565c0,stroke-width:2px
    style CLIENT fill:#fff3e0,stroke:#e65100
    style LLM fill:#78909c,color:#fff,stroke:#455a64
    style AUDIT fill:#1565c0,color:#fff,stroke:#0d47a1
```

The gateway is the sole enforcement point between untrusted client traffic and untrusted provider egress. All governance — authentication, policy evaluation, data redaction, and evidence production — executes within this boundary. The controlled zone (OPA, PostgreSQL, filesystem index) is reachable only from the gateway over internal networking. No client traffic bypasses the enforcement layer, and no unredacted data leaves the boundary toward external providers.

## Key Architecture Decisions

| Decision | Alternative Considered | Trade-off | Why This Choice |
|---|---|---|---|
| Fail-closed on OPA unavailability | Fail-open with logging | Availability impact during policy outages | Explicit denial is safer than implicit permission in regulated workloads |
| Regex-first PHI/PII redaction | NER/ML model pipeline | Lower accuracy on context-dependent entities | Deterministic, no model dependency, measurable false-positive rate. ML upgrade path planned |
| Synchronous policy evaluation | Async / eventual consistency | Adds latency to every request | Async would break the "enforce before egress" guarantee |
| Single gateway binary | Microservice mesh | Cannot scale concerns independently | Reduces operational complexity; policy, redaction, and audit are tightly coupled |
| OpenAI-compatible surface only | Multi-protocol support | No native Anthropic/Google endpoints | Reduces scope; most providers offer OpenAI-compatible modes |
| Hash-based local embeddings | Always use remote embeddings | Lower semantic quality for retrieval | Deterministic, no network calls, enables air-gapped and test deployments |
| Custom Prometheus collector | `prometheus_client` library | More code to maintain | Zero external dependency; thread-safe in-process implementation with no transitive risk |

## Governance Modes

The gateway supports progressive adoption through two operational modes, allowing teams to validate policy behaviour against production traffic before enabling enforcement:

```mermaid
flowchart LR
    subgraph OBSERVE["Observe Mode"]
        direction TB
        R1["Request"] --> P1["Policy\nEvaluation"]
        P1 --> L1["Log Decision\n(allow/deny)"]
        L1 --> E1["Forward to\nProvider"]
        P1 -.->|"never blocks"| E1
    end

    subgraph ENFORCE["Enforce Mode"]
        direction TB
        R2["Request"] --> P2["Policy\nEvaluation"]
        P2 -- "Allow" --> E2["Forward to\nProvider"]
        P2 -- "Deny" --> D2["403 Structured\nDenial"]
    end

    OBSERVE -->|"confidence\ngained"| ENFORCE

    style OBSERVE fill:#fff3e0,stroke:#e65100
    style ENFORCE fill:#e8f5e9,stroke:#2e7d32
    style D2 fill:#d32f2f,color:#fff,stroke:#b71c1c
```

Teams start in observe mode to baseline policy decisions against real traffic patterns. Once false-positive rates are acceptable and policy coverage is validated, switching to enforce mode makes policy decisions binding.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | FastAPI 0.115+ (async, OpenAI-compatible) |
| Policy Engine | Open Policy Agent (OPA) 0.67+ |
| Vector Store | PostgreSQL 16+ with pgvector |
| Containerisation | Docker (Python 3.12-slim) |
| Orchestration | Kubernetes, Helm v3 |
| Observability | Prometheus metrics, Grafana dashboards, OpenTelemetry collector |
| CI/CD | GitHub Actions (test, deploy-smoke, release) |
| GitOps | Argo CD ApplicationSet, External Secrets Operator |
| Supply Chain | Cosign (keyless signing), SPDX SBOM, provenance attestation |
| Package Management | uv |
| Quality | pytest, ruff, mypy (strict mode) |

## Benchmark Methodology

The project follows a publish-methodology-not-just-scores approach to evaluation:

```mermaid
flowchart LR
    CORPUS["Synthetic Corpus\n+ Adversarial\nInputs"] --> CONDITIONS["4 Test\nConditions"]
    CONDITIONS --> METRICS["Metrics\nCollection"]
    METRICS --> GATES["CI Quality\nGates"]
    GATES --> ARTIFACTS["Published\nArtifacts"]

    CONDITIONS -.-> C1["Baseline\n(no gateway)"]
    CONDITIONS -.-> C2["Observe\n(log only)"]
    CONDITIONS -.-> C3["Enforce\n(policy + redact)"]
    CONDITIONS -.-> C4["Enforce + RAG\n(full pipeline)"]

    ARTIFACTS -.-> A1["CSV / JSON\nraw data"]
    ARTIFACTS -.-> A2["Provenance\nmanifest"]
    ARTIFACTS -.-> A3["Reproduction\nscripts"]

    style CORPUS fill:#e3f2fd,stroke:#1565c0
    style GATES fill:#fff3e0,stroke:#e65100
    style ARTIFACTS fill:#e8f5e9,stroke:#2e7d32
```

**Governance Yield vs Performance Overhead** — the primary benchmark track quantifies the tradeoff between governance effectiveness and runtime overhead:

| Condition | Description |
|---|---|
| Baseline | Direct provider calls, no gateway |
| Observe | Gateway decisions logged, not enforced |
| Enforce | Policy evaluation + data redaction |
| Enforce + RAG | Policy + redaction + connector-scoped retrieval |

**Key Metrics and v0.2 Targets:**
| Metric | Target |
|---|---|
| Leakage rate (sensitive data reaching provider) | < 0.5% |
| Redaction false-positive rate | < 8% |
| Policy deny F1 score | >= 0.90 |
| Citation integrity (authorised sources only) | >= 99% |
| p95 latency overhead (chat) | < 250 ms |
| p95 latency overhead (RAG) | < 600 ms |

CI-enforced quality gates: citation presence rate >= 0.95, pgvector Recall@3 >= 0.80. All benchmark artifacts (raw CSV/JSON, provenance manifests, reproduction scripts) are published alongside summary reports.

Full methodology: [`docs/benchmarks/governance-yield-vs-performance-overhead.md`](docs/benchmarks/governance-yield-vs-performance-overhead.md)

## Release and Supply Chain Pipeline

Every tagged release goes through a signed, auditable pipeline:

```mermaid
flowchart LR
    TAG["Git Tag\n(v*)"] --> BUILD["Container\nBuild"]
    BUILD --> PUSH["Push to\nGHCR"]
    PUSH --> SIGN["Cosign\n(keyless)"]
    SIGN --> SBOM["SPDX SBOM\nGeneration"]
    SBOM --> PROV["Provenance\nAttestation"]
    PROV --> REL["GitHub\nRelease"]

    TAG --> NOTES["Extract Notes\nfrom CHANGELOG"]
    NOTES --> REL

    style TAG fill:#2e7d32,color:#fff,stroke:#1b5e20
    style SIGN fill:#1565c0,color:#fff,stroke:#0d47a1
    style SBOM fill:#4527a0,color:#fff,stroke:#311b92
    style PROV fill:#4527a0,color:#fff,stroke:#311b92
    style REL fill:#2e7d32,color:#fff,stroke:#1b5e20
```

## CI/CD Pipeline

```mermaid
flowchart LR
    subgraph CI["ci.yml (every push / PR)"]
        direction TB
        LINT["ruff\nlint"] --> TYPE["mypy\ntypecheck"]
        TYPE --> TEST["pytest\n(unit + integration)"]
        TEST --> SCHEMA["schema\nvalidation"]
    end

    subgraph SMOKE["deploy-smoke.yml"]
        direction TB
        KIND["Spin up\nkind cluster"] --> HELM["Install\nHelm chart"]
        HELM --> ROLL["Validate\nrollout"]
        ROLL --> HEALTH["Endpoint\nhealth check"]
    end

    subgraph RELEASE["release.yml (v* tag)"]
        direction TB
        BUILD["Container\nbuild"] --> GHCR["Push to\nGHCR"]
        GHCR --> COSIGN["Cosign\n(keyless)"]
        COSIGN --> SBOM_R["SPDX\nSBOM"]
        SBOM_R --> ATTEST["Provenance\nattestation"]
        ATTEST --> GH_REL["GitHub\nRelease"]
    end

    PUSH["git push"] --> CI
    PUSH --> SMOKE
    TAG_R["git tag v*"] --> RELEASE

    style CI fill:#e3f2fd,stroke:#1565c0
    style SMOKE fill:#e8f5e9,stroke:#2e7d32
    style RELEASE fill:#ede7f6,stroke:#4527a0
    style PUSH fill:#2e7d32,color:#fff,stroke:#1b5e20
    style TAG_R fill:#4527a0,color:#fff,stroke:#311b92
```

- **ci.yml** — lint (ruff), type check (mypy strict), test (pytest), and JSON Schema validation on every push and pull request
- **deploy-smoke.yml** — spins up a kind cluster, installs the Helm chart, validates rollout, and runs endpoint health checks
- **release.yml** — triggered by `v*` tags: builds container, pushes to GHCR, signs with cosign (keyless), generates SPDX SBOM, attaches provenance attestation, publishes release notes from CHANGELOG

## GitOps and Secret Management

```mermaid
flowchart LR
    subgraph REPO["Git Repository"]
        direction TB
        CHART["Helm Chart\n(charts/)"]
        DEV_V["dev/values.yaml"]
        STG_V["staging/values.yaml"]
        PROD_V["prod/values.yaml"]
    end

    subgraph ARGOCD["Argo CD"]
        direction TB
        APPSET["ApplicationSet\n(env generator)"]
    end

    subgraph K8S["Kubernetes"]
        direction TB
        DEV_NS["srg-system\n(dev)"]
        STG_NS["srg-staging\n(staging)"]
        PROD_NS["srg-prod\n(prod)"]
    end

    subgraph ESO["External Secrets"]
        direction TB
        AWS["AWS Secrets\nManager"]
        SYNC["ESO Controller\n(1h refresh)"]
    end

    REPO --> APPSET
    APPSET --> DEV_NS
    APPSET --> STG_NS
    APPSET --> PROD_NS

    AWS --> SYNC
    SYNC --> DEV_NS
    SYNC --> STG_NS
    SYNC --> PROD_NS

    style REPO fill:#e3f2fd,stroke:#1565c0
    style ARGOCD fill:#fff3e0,stroke:#e65100
    style K8S fill:#e8f5e9,stroke:#2e7d32
    style ESO fill:#ede7f6,stroke:#4527a0
```

Argo CD ApplicationSet generates one Application per environment from a list generator. Dev and staging auto-sync on commit; prod requires manual sync approval. External Secrets Operator syncs API keys and provider credentials from AWS Secrets Manager into Kubernetes Secrets with automatic 1-hour refresh. Rotation runbook covers standard rotation, emergency revocation, and sync monitoring.

## Competitive Landscape

Evaluated against 10 adjacent tools in the AI gateway and governance space:

| Category | Tools Evaluated |
|---|---|
| AI Gateway / Proxy | LiteLLM Proxy, Portkey, OpenRouter |
| API Gateway + AI | Kong AI Gateway, Gloo AI Gateway, Envoy AI Gateway |
| Cloud-Native AI Gateway | Cloudflare AI Gateway, Azure APIM GenAI Gateway |
| Guardrails / Safety | NVIDIA NeMo Guardrails, Guardrails AI |

**Differentiation — three capabilities no single competitor combines:**

- **Fail-closed in-path policy enforcement** — deterministic deny when OPA is unavailable, not silent fallback to permissive behaviour
- **Tamper-evident decision lineage** — SHA-256 hash-chained audit events with policy version hashes, enabling forensic reconstruction of any request
- **Policy-scoped RAG with citation integrity** — retrieval authorization decoupled from prompt content, citations verified against allowed sources

Full analysis with source references: [`docs/strategy/differentiation-strategy.md`](docs/strategy/differentiation-strategy.md)

## Engineering Metrics

### Codebase Scale

| Metric | Value |
|---|---|
| Application code | ~4,970 lines across 44 modules |
| Test code | ~3,090 lines across 46 test files |
| Test-to-code ratio | 59% |
| Test functions | 122 (unit, integration, contract, benchmark) |
| Support scripts | ~1,830 lines across 13 scripts |
| Documentation | ~1,150 lines across 22 documents |
| Current version | 0.5.0 |

### Quality and Contracts

| Metric | Value |
|---|---|
| Type checking | mypy strict mode (zero errors on 44 source files) |
| Linting | ruff (zero warnings) |
| JSON Schema contracts | 4 (policy decision, audit event, citations, evidence bundle) |
| Test coverage scope | Unit, integration, contract, benchmark validation |
| Benchmark eval gates | 2 (citation integrity, pgvector ranking) |

### Deployment and Operations

| Metric | Value |
|---|---|
| Kubernetes manifests | 25 YAML files |
| Helm chart templates | 12 templates with values schema validation |
| CI/CD pipelines | 7 (test, provider parity matrix, deploy-smoke, signed release, EKS validation, evidence replay, weekly evidence automation) |
| GitOps environments | 3 (dev, staging, prod via Argo CD) |
| Prometheus metrics | 10 counters + 2 histograms |
| Grafana dashboard panels | 10 panels across 4 operational domains |

## Quick Start

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for containerised deployment)
- kind (for local Kubernetes)

### Development
```bash
make dev            # Start dev server with hot reload
make test           # Run full test suite
make lint           # Ruff linting
make typecheck      # mypy strict type checking
```

### Kubernetes Deployment
```bash
make helm-lint      # Validate Helm chart
make helm-template  # Generate manifests
make demo-up        # Deploy to kind + smoke test
```

### API Usage

PHI-classified request with automatic redaction:
```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello DOB 01/01/1990"}]}'
```

RAG-enabled request with citation tracking:
```bash
curl -s http://127.0.0.1:8000/v1/chat/completions \
  -H 'Authorization: Bearer dev-key' \
  -H 'x-srg-tenant-id: tenant-a' \
  -H 'x-srg-user-id: user-1' \
  -H 'x-srg-classification: phi' \
  -H 'content-type: application/json' \
  -d '{
    "model":"gpt-4o-mini",
    "messages":[{"role":"user","content":"give triage policy summary"}],
    "rag":{"enabled":true,"connector":"filesystem","top_k":2}
  }'
```

Generate an evidence bundle for incident replay:
```bash
python scripts/audit_replay_bundle.py \
  --request-id <request_id> \
  --audit-log artifacts/audit/events.jsonl \
  --out-dir artifacts/evidence \
  --include-chain-verify
```

Replay failed webhook deliveries from dead-letter storage:
```bash
python scripts/replay_webhook_dead_letter.py \
  --dead-letter artifacts/audit/webhook_dead_letter.db \
  --dead-letter-backend sqlite \
  --event-types policy_denied,budget_exceeded \
  --max-events 50 \
  --report-out artifacts/audit/webhook_replay_report.json
```

### v0.4 Runtime Control Environment Flags

```bash
# Budget controls
SRG_BUDGET_ENABLED=true
SRG_BUDGET_DEFAULT_CEILING=100000
SRG_BUDGET_WINDOW_SECONDS=3600
SRG_BUDGET_TENANT_CEILINGS="tenant-a:50000,tenant-b:250000"
SRG_BUDGET_BACKEND=memory # memory|redis
SRG_BUDGET_REDIS_URL=redis://redis:6379/0
SRG_BUDGET_REDIS_PREFIX=srg:budget
SRG_BUDGET_REDIS_TTL_SECONDS=7200

# Webhook notifications
SRG_WEBHOOK_ENABLED=true
SRG_WEBHOOK_ENDPOINTS='[{"url":"https://hooks.example.com/srg","secret":"replace_me","event_types":["policy_denied","budget_exceeded","redaction_hit","provider_fallback","provider_error"]}]'
SRG_WEBHOOK_TIMEOUT_S=5.0
SRG_WEBHOOK_MAX_RETRIES=1
SRG_WEBHOOK_BACKOFF_BASE_S=0.2
SRG_WEBHOOK_BACKOFF_MAX_S=2.0
SRG_WEBHOOK_DEAD_LETTER_BACKEND=sqlite # sqlite|jsonl
SRG_WEBHOOK_DEAD_LETTER_PATH=artifacts/audit/webhook_dead_letter.db
SRG_WEBHOOK_DEAD_LETTER_RETENTION_DAYS=30

# Tracing diagnostics + OTLP export
SRG_TRACING_ENABLED=true
SRG_TRACING_MAX_TRACES=1000
SRG_TRACING_OTLP_ENABLED=true
SRG_TRACING_OTLP_ENDPOINT=http://otel-collector:4318/v1/traces
SRG_TRACING_OTLP_TIMEOUT_S=2.0
SRG_TRACING_OTLP_HEADERS='{"Authorization":"Bearer replace_me"}'
SRG_TRACING_SERVICE_NAME=sovereign-rag-gateway

# SharePoint connector (optional)
SRG_RAG_SHAREPOINT_BASE_URL=https://graph.microsoft.com/v1.0
SRG_RAG_SHAREPOINT_SITE_ID=<site-id>
SRG_RAG_SHAREPOINT_DRIVE_ID=<drive-id>
SRG_RAG_SHAREPOINT_BEARER_TOKEN=<token>
SRG_RAG_SHAREPOINT_ALLOWED_PATH_PREFIXES=/drives/<drive-id>/root:/Ops
```

## Documentation

| Document | Description |
|---|---|
| [`docs/strategy/differentiation-strategy.md`](docs/strategy/differentiation-strategy.md) | Competitive analysis and positioning |
| [`docs/strategy/why-this-exists-security-sre.md`](docs/strategy/why-this-exists-security-sre.md) | Security and SRE problem narrative |
| [`docs/strategy/killer-demo-stories.md`](docs/strategy/killer-demo-stories.md) | 5 measurable demo scenarios |
| [`docs/benchmarks/governance-yield-vs-performance-overhead.md`](docs/benchmarks/governance-yield-vs-performance-overhead.md) | Full benchmark methodology |
| [`docs/architecture/threat-model.md`](docs/architecture/threat-model.md) | Threat matrix, controls, and residual risk |
| [`docs/operations/helm-kind-runbook.md`](docs/operations/helm-kind-runbook.md) | Local Kubernetes deployment guide |
| [`docs/operations/confluence-connector.md`](docs/operations/confluence-connector.md) | Confluence read-only connector setup |
| [`docs/operations/jira-connector.md`](docs/operations/jira-connector.md) | Jira read-only connector setup |
| [`docs/operations/sharepoint-connector.md`](docs/operations/sharepoint-connector.md) | SharePoint read-only connector setup |
| [`docs/operations/compliance-control-mapping.md`](docs/operations/compliance-control-mapping.md) | Technical control-to-evidence mapping |
| [`docs/operations/incident-replay-runbook.md`](docs/operations/incident-replay-runbook.md) | Request-level replay and signed evidence procedure |
| [`docs/operations/secrets-rotation-runbook.md`](docs/operations/secrets-rotation-runbook.md) | Secret rotation and emergency revocation |
| [`docs/operations/runtime-controls-v050.md`](docs/operations/runtime-controls-v050.md) | Redis budgets, OTLP tracing export, and webhook delivery hardening |
| [`docs/benchmarks/reports/provider-parity-latest.md`](docs/benchmarks/reports/provider-parity-latest.md) | Cross-provider compatibility matrix snapshot |
| [`docs/benchmarks/reports/index.md`](docs/benchmarks/reports/index.md) | Weekly benchmark/evidence report index |
| [`docs/contracts/v1/`](docs/contracts/v1/) | JSON Schema contracts (policy, audit, citations, evidence bundle) |
| [`docs/releases/v0.5.0.md`](docs/releases/v0.5.0.md) | Current stable release notes (v0.5.0) |
| [`docs/releases/v0.5.0-alpha.1.md`](docs/releases/v0.5.0-alpha.1.md) | Latest prerelease notes (v0.5.0-alpha.1) |
| [`docs/releases/v0.4.0-rc1.md`](docs/releases/v0.4.0-rc1.md) | Previous release candidate notes (v0.4.0-rc1) |
| [`deploy/terraform/README.md`](deploy/terraform/README.md) | Terraform EKS module usage and secure defaults |
| [`docs/releases/v0.3.0.md`](docs/releases/v0.3.0.md) | Previous release notes (v0.3.0) |
| [`docs/releases/v0.2.0.md`](docs/releases/v0.2.0.md) | Previous release notes (v0.2.0) |

## Honest Gap Assessment

This project makes narrow, testable claims — not aspirational ones:

- **No claim of perfect PHI detection.** Regex-first redaction has measurable false positives and false negatives. Rates are benchmarked and published.
- **No claim of full provider API parity.** OpenAI compatibility covers core endpoints (chat, embeddings, models). Provider-specific extensions are out of scope in early versions.
- **No claim that this replaces broader controls.** Gateway enforcement does not substitute for secure SDLC, IAM, or data governance programmes.
- **Policy quality depends on fixture coverage.** OPA policies can drift without strict test gates and review processes.

## Roadmap

- [x] Multi-provider routing with cost-aware fallback
- [x] Baseline Grafana dashboards for request/policy/cost telemetry
- [x] External secrets integration and rotation runbook
- [x] GitOps manifests (Argo CD) for declarative promotion
- [x] Streaming support for chat completions
- [x] Azure/Anthropic provider adapters
- [x] S3 connector for document retrieval
- [x] EKS reference deployment with validated guide
- [x] Evidence replay bundle export and schema
- [x] Confluence read-only connector
- [x] Jira read-only connector
- [x] SharePoint read-only connector
- [x] Signed evidence bundle output (detached signature + verification)

### Next (v0.4.0)
- [x] Response redaction — scan LLM output for PHI/PII before returning to clients
- [x] Token budget enforcement — per-tenant sliding window quotas with policy integration
- [x] OpenTelemetry distributed tracing across gateway → OPA → providers
- [x] Webhook notifications on policy denials, redaction triggers, and cost threshold breaches
- [x] Terraform/Pulumi IaC module for production AWS deployment (EKS + RDS + S3)

### Next (v0.5.0 Foundation)
- [x] Redis-backed distributed budget tracking for multi-replica deployments
- [x] OTLP HTTP trace exporter with configurable endpoint, timeout, and headers
- [x] Webhook retry/backoff/idempotency + dead-letter queue output
- [x] Dead-letter replay CLI with deterministic summary/report output
- [x] Benchmark trend regression gate (current vs checked-in baseline)
- [x] SharePoint read-only connector (Graph API, policy-scoped retrieval)
- [x] Promote v0.5.0-alpha.1 release notes and tagged prerelease ([tag/release](https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway/releases/tag/v0.5.0-alpha.1), [release workflow run](https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway/actions/runs/22216373015))
- [x] Validate runtime-controls stack in kind smoke environment and publish weekly report ([deploy-smoke run](https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway/actions/runs/22207623171), [weekly report](docs/benchmarks/reports/weekly-2026-02-20.md))

### Next (v0.6.0)
- [ ] Promote provider parity matrix as a release gate with persisted CI artifacts (`http_openai`, `azure_openai`, `anthropic`)
- [ ] Harden webhook dead-letter durability defaults (`sqlite` backend + retention pruning + replay compatibility)
- [ ] Publish webhook replay/retention metric panels in operations dashboards
- [ ] Automate weekly evidence report generation via scheduled GitHub Actions workflow
- [ ] Auto-maintain `docs/benchmarks/reports/index.md` from weekly report artifacts
- [ ] Add SharePoint managed-identity authentication mode (tokenless runtime credential path)
- [ ] Ship `v0.6.0` release dossier with migration notes from `v0.5.x`

## Licence

See [LICENSE](LICENSE) for details.
