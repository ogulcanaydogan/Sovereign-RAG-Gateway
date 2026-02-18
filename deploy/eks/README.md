# EKS Deployment Assets

This folder contains a reference Helm values file for deploying Sovereign RAG Gateway on Amazon EKS.

Files:
- `values.example.yaml`: production-oriented Helm overrides for EKS.

Use with:

```bash
helm upgrade --install srg charts/sovereign-rag-gateway \
  --namespace srg-system \
  --create-namespace \
  -f deploy/eks/values.example.yaml
```
