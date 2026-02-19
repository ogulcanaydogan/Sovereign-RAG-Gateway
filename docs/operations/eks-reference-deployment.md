# EKS Reference Deployment Guide

This guide provides a validated path to deploy Sovereign RAG Gateway on Amazon EKS with policy enforcement, structured audit logs, and observability-ready settings.

## 1. Prerequisites

- AWS account and IAM permissions for EKS, EC2, IAM, and ECR/GHCR image pull access.
- `kubectl`, `helm`, `aws`, and `eksctl` installed.
- Existing OPA endpoint and provider credentials.

## 2. Create Cluster

```bash
eksctl create cluster \
  --name srg-prod \
  --region us-east-1 \
  --version 1.30 \
  --nodes 3 \
  --node-type m6i.large \
  --managed
```

Validate access:

```bash
aws eks update-kubeconfig --name srg-prod --region us-east-1
kubectl get nodes
```

## 3. Namespace and Secrets

Create namespace:

```bash
kubectl create namespace srg-system
```

Create API key secret:

```bash
kubectl -n srg-system create secret generic srg-api-keys \
  --from-literal=api-keys="key-1,key-2"
```

If using External Secrets, apply:

```bash
kubectl apply -k deploy/secrets
```

## 4. Deploy Gateway

Use the EKS values profile:

```bash
helm upgrade --install srg charts/sovereign-rag-gateway \
  --namespace srg-system \
  --create-namespace \
  -f deploy/eks/values.example.yaml
```

Wait for rollout:

```bash
kubectl -n srg-system rollout status deployment/srg-sovereign-rag-gateway --timeout=180s
```

## 5. Post-Deploy Validation

Health checks:

```bash
kubectl -n srg-system port-forward svc/srg-sovereign-rag-gateway 18080:80
curl -s http://127.0.0.1:18080/healthz
curl -s http://127.0.0.1:18080/readyz
```

Chat smoke:

```bash
curl -s http://127.0.0.1:18080/v1/chat/completions \
  -H "Authorization: Bearer key-1" \
  -H "x-srg-tenant-id: tenant-a" \
  -H "x-srg-user-id: user-1" \
  -H "x-srg-classification: phi" \
  -H "content-type: application/json" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
```

Streaming smoke:

```bash
curl -N http://127.0.0.1:18080/v1/chat/completions \
  -H "Authorization: Bearer key-1" \
  -H "x-srg-tenant-id: tenant-a" \
  -H "x-srg-user-id: user-1" \
  -H "x-srg-classification: phi" \
  -H "content-type: application/json" \
  -d '{"model":"gpt-4o-mini","stream":true,"messages":[{"role":"user","content":"stream hello"}]}'
```

## 6. Recommended Production Hardening

- Enable IRSA for any AWS service integrations (S3 connector, external secrets).
- Restrict egress with NetworkPolicy to only approved model/provider endpoints.
- Keep `opaMode=enforce` and `redactionEnabled=true`.
- Set `providerFallbackEnabled=true` with at least two providers configured.
- Export `/metrics` to Prometheus and alert on `srg_provider_fallbacks_total` spikes.

## 7. Rollback

```bash
helm -n srg-system history srg
helm -n srg-system rollback srg <REVISION>
```

## 8. CI Validation

This guide and its EKS values profile are validated in CI by:

```bash
./scripts/eks_reference_validate.sh
```

The script lints the chart, renders with `deploy/eks/values.example.yaml`, and runs
`kubectl apply --dry-run=client` to catch invalid manifests before merge.
