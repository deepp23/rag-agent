# Deploying to Azure

Architecture: Azure Container Apps (API + Qdrant, internal-only ingress for
Qdrant), Azure Database for PostgreSQL Flexible Server, Azure Files (BM25 +
Qdrant persistent storage), Azure Container Registry, Azure Static Web Apps
(frontend). Defined in [`main.bicep`](./main.bicep); rolled out by
[`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) on every
push to `main`.

## Known limitations (read before relying on this in production)

- **Single replica only.** Both the API and Qdrant apps are pinned to
  `minReplicas: 1, maxReplicas: 1`. The per-workspace BM25 index is a
  read-modify-write pickle file on a shared volume — concurrent writers
  from multiple replicas would race. Scaling out needs BM25 persistence
  moved off local/shared-file storage first.
- **Qdrant on network storage.** Qdrant's storage engine uses mmap and
  isn't officially validated against network filesystems (this uses
  Standard SMB Azure Files — cheap, appropriate for a small/personal-scale
  deployment). If you hit odd storage errors under real load, either
  switch to a Premium NFS file share or move to
  [Qdrant Cloud](https://qdrant.tech/cloud/) (managed — just a URL + API
  key, no volume at all).
- **DB migrations run via `az containerapp exec`** against the already-updated
  API revision, after it starts accepting traffic. For this project's scale
  that's an acceptable tradeoff, not zero-downtime-safe for breaking schema
  changes.

## One-time setup

You need your own `az login` session with Owner/Contributor on the
subscription for this part — none of it runs from CI.

**1. Resource group**

```bash
az group create --name rag-app-rg --location eastus
```

**2. Azure AD app registration + GitHub OIDC federation** (no client secret
stored anywhere — GitHub Actions authenticates via short-lived OIDC tokens)

```bash
APP_ID=$(az ad app create --display-name enterprise-rag-deploy --query appId -o tsv)
az ad sp create-for-rbac --id "$APP_ID" 2>/dev/null || az ad sp create --id "$APP_ID"

az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-main-branch",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<your-org>/<your-repo>:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

az role assignment create \
  --assignee "$APP_ID" \
  --role Contributor \
  --scope "$(az group show -n rag-app-rg --query id -o tsv)"

echo "AZURE_CLIENT_ID=$APP_ID"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID=$(az account show --query id -o tsv)"
```

**3. GitHub repo configuration** (Settings → Secrets and variables → Actions)

Variables:
| Name | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | `rag-app-rg` |
| `AZURE_NAME_PREFIX` | e.g. `ragapp` (optional, defaults to `ragapp`) |
| `AZURE_ACR_NAME` | **required** — any globally-unique 5-50 char alphanumeric name, e.g. `ragappacr123`. Created on first deploy if it doesn't exist yet; if it already exists (e.g. you're reusing one from an earlier deployment attempt), it's adopted and updated in place — existing images aren't touched. |

Secrets:
| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | from step 2 |
| `AZURE_TENANT_ID` | from step 2 |
| `AZURE_SUBSCRIPTION_ID` | from step 2 |
| `POSTGRES_ADMIN_PASSWORD` | strong password, **alphanumeric only** (embedded unescaped in a connection string) |
| `JWT_SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GEMINI_API_KEY` | your Gemini key |
| `GROQ_API_KEY` | your Groq key |
| `HF_TOKEN` | your HuggingFace token |

**4. Push to `main`.** The workflow provisions everything and deploys both
the API and frontend. First run takes longer (~15-20 min, mostly Postgres
Flexible Server + first image build); later runs are much faster.

## Manual deploy (no GitHub Actions)

```bash
ACR_NAME=ragappacr123   # must already exist, or be creatable fresh here
az acr create --resource-group rag-app-rg --name "$ACR_NAME" --sku Basic --admin-enabled false

az acr build --registry "$ACR_NAME" --image enterprise-rag-api:manual .

az deployment group create \
  --resource-group rag-app-rg --name main \
  --template-file infra/main.bicep \
  --parameters namePrefix=ragapp acrName="$ACR_NAME" \
    apiImage="$ACR_NAME.azurecr.io/enterprise-rag-api:manual" \
    postgresAdminPassword='<...>' jwtSecretKey='<...>' \
    geminiApiKey='<...>' groqApiKey='<...>' hfToken='<...>'

# Migrations run as a Container Apps Job, not `containerapp exec` (exec is
# built for interactive debugging, not reliable one-off batch commands).
EXEC=$(az containerapp job start -g rag-app-rg -n ragapp-migrate --query name -o tsv)
az containerapp job execution show -g rag-app-rg -n ragapp-migrate --job-execution-name "$EXEC" --query properties.status
```

Then build the frontend with `VITE_API_BASE_URL=<apiUrl>/api/v1 npm run build`
in `frontend/` and deploy `frontend/dist` to the Static Web App via
`swa deploy` or the portal's manual upload.
