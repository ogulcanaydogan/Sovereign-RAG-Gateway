# OpenSSF Best Practices Badge Guide

## Pre-Submission Checklist for Sovereign RAG Gateway

This document maps Sovereign RAG Gateway's existing practices to OpenSSF Best Practices Badge criteria and identifies any gaps to address before submission.

**Badge Application URL**: https://www.bestpractices.dev/en/projects
**Repository**: https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway
**Current Version**: v1.1.0 (GA)

---

## 1. Basics

| Criterion | Status | Evidence |
|---|---|---|
| **OSS project URL** | PASS | https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway |
| **Project description** | PASS | README.md: "A policy-first, OpenAI-compatible governance gateway for regulated AI workloads" |
| **Interaction mechanisms** | PASS | GitHub Issues, Pull Requests |
| **Contribution guide** | CHECK | Verify CONTRIBUTING.md exists; if not, create one |
| **License** | PASS | MIT License (`LICENSE` file in repository root) |
| **License in standard location** | PASS | `LICENSE` file at root |
| **Documentation of basics** | PASS | README.md (problem statement, architecture, deployment), ARCHITECTURE.md (detailed module map, request lifecycle) |

### Action Items -- Basics

- [ ] Verify `CONTRIBUTING.md` exists. If missing, create a contribution guide covering development setup, code style (ruff, mypy), testing (pytest), and PR process.

---

## 2. Change Control

| Criterion | Status | Evidence |
|---|---|---|
| **Version control** | PASS | Git (GitHub) |
| **Unique version numbering** | PASS | Semantic versioning (v1.1.0), 19 releases. Tags validated in `release.yml` with regex `^v[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$` |
| **Release notes** | PASS | CHANGELOG.md with structured entries per release; `scripts/extract_release_notes.py` extracts notes per tag |
| **Version in accessible place** | PASS | `pyproject.toml` (`version = "1.1.0"`), checked by `scripts/check_version_sync.py` in CI |

---

## 3. Reporting

| Criterion | Status | Evidence |
|---|---|---|
| **Bug reporting process** | PASS | GitHub Issues |
| **Vulnerability reporting** | PASS | SECURITY.md with responsible disclosure instructions, 48-hour initial response SLA |
| **Vulnerability response process** | PASS | SECURITY.md: response within 48 hours, status update within 7 days, fix timeline based on severity |

### Action Items -- Reporting

- [ ] Consider adding a security contact email to SECURITY.md (currently marked as "to be added").
- [ ] Consider enabling GitHub Private Vulnerability Reporting for the repository.

---

## 4. Quality

### 4.1 Build and Test

| Criterion | Status | Evidence |
|---|---|---|
| **Working build system** | PASS | `pyproject.toml` with setuptools, `uv sync --extra dev` in CI |
| **Automated test suite** | PASS | pytest with unit, integration, contract, and benchmark tests; `ci.yml` runs tests on every push/PR |
| **Test coverage** | CHECK | pytest-cov is in dev dependencies; verify coverage reporting is enabled and meets threshold |
| **Tests added with new functionality** | PASS | CI includes schema validation, benchmark gates, citation eval gates, and pgvector ranking eval gates |

### 4.2 CI Workflows (11 workflows)

| Workflow | What It Validates | Badge Relevance |
|---|---|---|
| **ci.yml** | Lint (ruff), type check (mypy), schema validation, version sync, RAG fixture generation, citation eval gate (>=95%), pgvector ranking eval gate (>=80%), governance benchmark gates (leakage rate, latency p95, cost drift, citation presence), benchmark trend gate, reliability SLO gate, unit/integration tests (pytest) | Quality, Testing |
| **deploy-smoke.yml** | Kind cluster spin-up, Helm chart install, rollout validation, endpoint health check | Quality, Deployment |
| **slo-reliability.yml** | Governance benchmark, fault injection suite, soak testing, SLO compliance gates; runs on PR, weekly schedule, and manual dispatch | Quality, Reliability |
| **release.yml** | Semver tag validation, release notes extraction, GA release-verify gate, prerelease readiness gates (stabilization window), signed release evidence artifacts, Docker build/push to GHCR, Sigstore cosign (keyless), SPDX SBOM, provenance attestation, GitHub Release creation | Security, Supply Chain |
| **release-verify.yml** | Latest release asset/signature verification, historical integrity sweep (latest 10 releases), release evidence contract checks | Security, Supply Chain |
| **terraform-validate.yml** | Infrastructure-as-code validation for Terraform configurations | Quality |
| **evidence-replay-smoke.yml** | Audit trail forensic replay verification -- ensures evidence can be replayed and reconstructed | Quality, Auditability |
| **rollback-drill.yml** | Operational rollback procedure validation -- ensures the project can recover from failed deployments | Quality, Operations |
| **weekly-evidence-report.yml** | Automated reliability summary and release verification snapshots as operational baseline evidence | Quality, Operations |
| **ga-readiness.yml** | GA promotion gate enforcement -- validates that all promotion criteria are met before a GA release | Quality, Release Process |
| **scorecard.yml** | OpenSSF Scorecard analysis -- runs weekly on Monday and on push to main; uploads SARIF to GitHub Security | Security, Best Practices |
| **eks-reference-validate.yml** | EKS reference architecture validation | Quality, Deployment |

### 4.3 Static Analysis

| Criterion | Status | Evidence |
|---|---|---|
| **Compiler warnings addressed** | PASS | `ruff check .` in CI (`ci.yml` lint step); ruff configured with `select = ["E", "F", "I", "UP", "B"]` |
| **Static analysis** | PASS | mypy with strict settings (`disallow_untyped_defs = true`, `strict_equality = true`, `warn_return_any = true`); runs in CI on `app` and `scripts` packages |

### Action Items -- Quality

- [ ] Verify pytest-cov generates coverage reports in CI. If not, add `--cov=app --cov-report=xml` to pytest invocation and set a coverage threshold (recommend >=80%).
- [ ] Consider uploading coverage reports to Codecov or Coveralls for visibility.

---

## 5. Security

### 5.1 Secure Development

| Criterion | Status | Evidence |
|---|---|---|
| **Secure development knowledge** | PASS | SECURITY.md, fail-closed policy enforcement, PHI/PII redaction, hash-chained audit trails, Sigstore signing |
| **Use of cryptography** | PASS | Hash-chained audit events with policy version hashes; Sigstore cosign for release signing; OpenSSL for release evidence artifacts |
| **Secured delivery** | PASS | Container images signed with Sigstore cosign (keyless) and pushed to GHCR; SPDX SBOM attached to releases; provenance attestation |

### 5.2 Supply Chain Security

| Criterion | Status | Evidence |
|---|---|---|
| **Dependency management** | PASS | `pyproject.toml` with pinned version ranges; `uv.lock` for reproducible installs |
| **Known vulnerability scanning** | CHECK | Verify Dependabot or Trivy is configured |
| **Signed releases** | PASS | `release.yml` uses Sigstore cosign (keyless) for container signing |
| **SBOM generation** | PASS | `release.yml` generates SPDX SBOM for every release |
| **Provenance** | PASS | `release.yml` attaches provenance attestation to every release |
| **OpenSSF Scorecard** | PASS | `scorecard.yml` runs weekly and on push to main; results uploaded as SARIF to GitHub Security; uses pinned action hashes |

### 5.3 Security Practices in CI

| Practice | Implementation | File |
|---|---|---|
| **Pinned action versions** | Scorecard workflow uses full SHA hashes for all actions (`actions/checkout@34e11...`, `ossf/scorecard-action@4eaac...`) | `scorecard.yml` |
| **Minimal permissions** | Scorecard uses `permissions: read-all` at workflow level, with specific write permissions only for the analysis job | `scorecard.yml` |
| **Token scoping** | Release workflow scopes `id-token: write` for Sigstore OIDC, `packages: write` for GHCR, `attestations: write` for provenance | `release.yml` |
| **Persisted credentials** | Scorecard checkout uses `persist-credentials: false` | `scorecard.yml` |

### Action Items -- Security

- [ ] Verify Dependabot or a vulnerability scanning tool (Trivy, Snyk) is configured for dependency scanning. If not, enable Dependabot in `.github/dependabot.yml`.
- [ ] Consider pinning all action versions to full SHA hashes across all workflows (currently done in `scorecard.yml`, verify others).
- [ ] Add the security contact email to SECURITY.md.

---

## 6. Analysis

### 6.1 Strengths (Badge-Ready)

The following areas are strong and should pass badge review without changes:

1. **CI/CD maturity** -- 11 workflows covering lint, type check, testing, deployment validation, SLO reliability, release signing, operational drills, and evidence reporting. This exceeds typical badge requirements.

2. **Supply chain security** -- Sigstore cosign, SPDX SBOM, provenance attestation, and OpenSSF Scorecard are all in place. The release pipeline enforces stabilization windows and release-verify gates before publishing.

3. **Security-aware design** -- Fail-closed policy enforcement, PHI/PII redaction in the hot path, hash-chained audit trails, and deterministic deny semantics demonstrate security-first thinking throughout the architecture.

4. **Structured release process** -- 19 releases with semantic versioning, structured changelog, release notes extraction, alpha/RC/GA promotion gates, and stabilization window validation.

5. **Static analysis** -- Both ruff (linting) and mypy (type checking with strict settings) run in CI on every push and PR.

### 6.2 Gaps to Address

| Gap | Priority | Effort | Resolution |
|---|---|---|---|
| CONTRIBUTING.md | Medium | 1 hour | Create contribution guide covering dev setup, code style, testing, PR process |
| Security contact email in SECURITY.md | Medium | 5 minutes | Add email address to SECURITY.md |
| Coverage reporting visibility | Low | 30 minutes | Add coverage threshold to CI; optionally upload to Codecov |
| Dependabot configuration | Medium | 15 minutes | Create `.github/dependabot.yml` for Python, GitHub Actions, and Docker dependency updates |
| Pin all action hashes | Low | 1 hour | Update all workflow files to use full SHA hashes instead of version tags |

---

## 7. Badge Submission Steps

### 7.1 Before Submission

1. Address the gaps listed in Section 6.2 (priority Medium and above)
2. Run a final check:
   - `ruff check .` passes
   - `mypy app scripts` passes
   - `pytest` passes
   - All CI workflows are green on main branch

### 7.2 Submission Process

1. Navigate to https://www.bestpractices.dev/en/projects
2. Click "Get Your Badge"
3. Sign in with GitHub
4. Enter the repository URL: `https://github.com/ogulcanaydogan/Sovereign-RAG-Gateway`
5. The system will auto-detect some criteria from the repository
6. Work through each section, answering questions with "Met" and providing evidence links:
   - For CI evidence, link to the workflow files in `.github/workflows/`
   - For testing evidence, link to `ci.yml` which runs pytest
   - For static analysis, link to `ci.yml` (ruff and mypy steps)
   - For security, link to `SECURITY.md`, `release.yml` (Sigstore signing), and `scorecard.yml`
   - For change control, link to `CHANGELOG.md` and the releases page
7. Submit for review

### 7.3 After Submission

- Badge evaluation is automated for most criteria
- Some criteria may require manual review
- Once the badge is awarded, add the badge SVG to README.md:
  ```markdown
  [![OpenSSF Best Practices](https://www.bestpractices.dev/projects/XXXXX/badge)](https://www.bestpractices.dev/projects/XXXXX)
  ```

---

## 8. Passing vs Silver vs Gold

### Passing Badge (target now)

The project should qualify for the Passing badge with the minor gaps addressed in Section 6.2. The existing CI, supply chain, and security infrastructure significantly exceeds Passing requirements.

### Silver Badge (future target)

Additional requirements for Silver include:
- [ ] Code coverage reporting with a defined threshold (>=80% recommended)
- [ ] Assurance case documentation (threat model, security design rationale)
- [ ] Hardening guide for deployment
- [ ] At least one security audit (this is planned in the Sovereign Tech Fund and NLnet grant proposals)

### Gold Badge (future target)

Gold requires:
- [ ] Multiple contributors with commit access
- [ ] Formal security audit by an independent party
- [ ] Reproducible builds
- [ ] Hardware security module or equivalent for signing (Sigstore keyless may qualify)

The security audit planned in the grant proposals (Sovereign Tech Fund, NLnet NGI Zero) would directly contribute to Silver and Gold badge requirements.

---

## 9. Cross-Reference with Grant Proposals

The OpenSSF badge is referenced as supporting evidence in both grant applications:

- **Sovereign Tech Fund**: The badge demonstrates supply chain maturity and security-aware development practices, strengthening the case for the security audit investment.
- **NLnet NGI Zero**: The badge provides external validation of the project's quality and security posture, supporting the argument that the project is mature enough to benefit from hardening rather than needing fundamental rebuilding.

Achieving the Passing badge before grant submission strengthens both applications. The security audit funded by either grant would then enable progression to Silver/Gold.
