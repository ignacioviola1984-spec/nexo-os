# Deployment pipeline and rollback

The deploy pipeline is a visible, gated promotion: the same lint -> test -> eval gate as
CI, then the enterprise gates (`security-review`, `controls-check`), then a release
manifest, then promotion. Rollback is guarded by a schema-compatibility check so a
service can never be rolled back across a schema change without a down-migration.

## Pipeline stages (`.github/workflows/deploy.yml`)

1. **Gate** - install, lint, seed synthetic data, tests, eval harness. A red gate stops
   the deploy.
2. **Security gate** - `nexo security-review` (fails on HIGH/CRITICAL) and
   `nexo controls-check` (fails on any FAIL), run with `NEXO_ENV=production` so the
   production-tightened checks apply.
3. **Manifest** - `nexo release-manifest --write release.json` records version, git sha,
   environment, tenant, and the schema fingerprint. This artifact is what a rollback
   targets.
4. **Deploy** - environment-scoped job (GitHub Environments: `staging`, then
   `production` with required reviewers). The actual host command is deployment-specific;
   the seam is the `deploy` job.

## Environments and secrets

- Set per-environment secrets in the platform (never in the repo): `ANTHROPIC_API_KEY`,
  `NEXO_AUTH_COOKIE_KEY`, backend credentials, and OIDC/IAM config.
- `NEXO_GIT_SHA` is set by CI to the deployed commit, so `/healthz` and the release
  manifest report exactly what is running.
- Production requires `NEXO_ENV=production`, which turns weak secrets and open-access
  flags into hard failures in the security gate.

## Rollback

A release manifest pins the schema fingerprint (`enterprise/release.py`), a hash of the
canonical schema. Before flipping traffic back:

```bash
python -m nexo_os rollback-check path/to/previous-release.json
```

- **SAFE** - same schema fingerprint, tenant, and environment. Proceed.
- **BLOCKED** - the fingerprint differs (a schema change shipped since that release).
  Rolling the service back without a down-migration would mismatch code and data. Run the
  down-migration first, or roll forward with a fix instead.

Keep the last few release manifests as build artifacts so any of them can be a rollback
target.

## Local dry run of the gates

```bash
NEXO_ENV=production python -m nexo_os security-review
NEXO_ENV=production python -m nexo_os controls-check
python -m nexo_os release-manifest --write release.json
```
