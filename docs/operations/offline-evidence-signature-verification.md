# Offline Evidence Signature Verification

This runbook verifies release evidence artifacts without network access.

## Required Files

Obtain these files from a release artifact set and place them in one directory:

- `bundle.json`
- `bundle.sha256`
- `bundle.sig`
- `release-evidence-public.pem`

## 1) Verify SHA-256 Digest

```bash
sha256sum bundle.json
cat bundle.sha256
```

Compare the digest values.

Expected outcome:
- Exact hash match.

If digest does not match, treat the bundle as tampered or incomplete.

## 2) Verify Detached Signature

```bash
openssl dgst -sha256 \
  -verify release-evidence-public.pem \
  -signature bundle.sig \
  bundle.json
```

Expected output:

```text
Verified OK
```

If output is not `Verified OK`, treat the evidence bundle as untrusted.

## Legacy Note (Older Releases)

Some older bundles used legacy digest behavior where `bundle.sha256` was calculated without a trailing newline in `bundle.json`.

For those bundles, repository tooling (`scripts/check_release_assets.py`) can verify in legacy compatibility mode and reports that mode explicitly.

## Failure Handling

- `sha256 mismatch`: stop, reacquire artifacts from release assets.
- `signature verification failed`: stop, reacquire `release-evidence-public.pem` and `bundle.sig` from the same release.
- `missing files`: do not proceed with manual trust assumptions.

## Recommended Command (Automated Offline-Style Verification)

If `gh` access is available in a controlled environment, run:

```bash
GH_TOKEN="$(gh auth token)" \
python scripts/check_release_assets.py \
  --repo ogulcanaydogan/Sovereign-RAG-Gateway \
  --tag v0.7.0-alpha.1 \
  --verify-bundle-integrity \
  --verify-signature \
  --require-public-key
```

This performs the same checks and provides deterministic pass/fail output.
