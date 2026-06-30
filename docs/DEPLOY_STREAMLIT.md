# Deploy the demo on Streamlit Community Cloud

The repo is ready to deploy as a public demo over **synthetic data** with zero secrets.

## Steps
1. Go to <https://share.streamlit.io> and sign in with GitHub.
2. **New app** → pick the repo `ignacioviola1984-spec/nexo-os`, branch `main`,
   **Main file path:** `streamlit_app.py`.
3. Deploy. First start takes ~1 minute (it installs deps and generates the synthetic
   dataset once); after that it's fast.

That's it. On first start the app:
- generates the synthetic dataset if missing, and
- runs one analysis cycle so the approval inbox is populated.

## Access
The public demo (`NEXO_DEMO_MODE=1`, the default for `streamlit_app.py`) has **open
access** — no login, so any visitor (e.g. a recruiter) lands directly on the dashboard
over synthetic data. The full authentication + RBAC path stays in the code and is used
for a real deployment (set `NEXO_DEMO_MODE=0` and provide admin credentials).

## Optional secrets (Settings → Secrets)
All optional — the demo works without them:
```toml
ANTHROPIC_API_KEY = "sk-ant-..."        # enables model-written Spanish prose
NEXO_ADMIN_USERNAME = "demo"
NEXO_ADMIN_PASSWORD = "choose-your-own"
NEXO_AUTH_COOKIE_KEY = "a-random-string"
```
Without `ANTHROPIC_API_KEY` the recommendations use the deterministic grounded text
(the numbers are identical either way — the model only rewrites the prose).

## Notes
- The data source stays synthetic on the public demo (PII / client-confidentiality).
  The BigQuery path is not used here.
- Streamlit Cloud's filesystem is ephemeral: approvals and the audit log persist for
  the life of the container and reset on redeploy — appropriate for a demo.
