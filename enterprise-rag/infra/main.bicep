// Enterprise RAG — Azure Container Apps deployment.
//
// Resources: Container Apps Environment (api + qdrant), Azure Files (BM25 +
// Qdrant storage), Azure Database for PostgreSQL Flexible Server, Azure
// Static Web App (frontend). ACR is NOT created here — it's provisioned by
// a standalone `az acr create` before this template runs (see
// .github/workflows/deploy.yml), specifically to avoid a chicken-and-egg
// problem: this template needs a real, already-pushed image tag for the
// api app and migration job from the start (no placeholder image), and the
// registry has to exist before anything can be pushed to it.

@description('Short name used to derive resource names. Lowercase alphanumeric only.')
@minLength(3)
@maxLength(16)
param namePrefix string = 'ragapp'

param location string = resourceGroup().location

@description('Static Web Apps is only available in a handful of regions (centralus, eastus2, westus2, westeurope, eastasia) — independent of the main location, which may not be one of them.')
param staticWebAppLocation string = 'eastus2'

@description('Name of an already-existing ACR (see .github/workflows/deploy.yml, which creates it via `az acr create` before this template runs).')
param acrName string

@description('Full image reference already pushed to that ACR, e.g. myacr.azurecr.io/enterprise-rag-api:sha.')
param apiImage string

param postgresAdminLogin string = 'ragadmin'

@secure()
@description('Alphanumeric only — used unescaped inside a DATABASE_URL connection string.')
param postgresAdminPassword string

@secure()
param jwtSecretKey string

@secure()
param geminiApiKey string

param geminiModel string = 'gemini-2.5-flash'

@secure()
param groqApiKey string

param groqModel string = 'llama-3.1-8b-instant'

@secure()
param hfToken string

var postgresDbName = 'enterprise_rag'
var storageAccountName = take(replace('${namePrefix}st${uniqueString(resourceGroup().id)}', '-', ''), 24)

// ── Observability + Container Apps Environment ─────────────────────────

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${namePrefix}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── Persistent storage (Azure Files, SMB) ───────────────────────────────
//
// NOTE: Qdrant's storage engine relies on mmap and isn't officially
// validated against network filesystems (SMB Azure Files here). This is
// the cheap, simple option appropriate for a small/personal-scale
// deployment — for higher-traffic or data-integrity-critical use, prefer
// Qdrant Cloud (managed, no volume needed at all) or a Premium NFS file
// share instead. Same caveat applies to the per-workspace BM25 pickle
// files on the api container's volume.

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
}

resource qdrantShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 'qdrant-storage'
  properties: { shareQuota: 50 }
}

resource ragDataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-01-01' = {
  parent: fileServices
  name: 'rag-data'
  properties: { shareQuota: 20 }
}

resource qdrantEnvStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppsEnv
  name: 'qdrant-storage'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: qdrantShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource ragDataEnvStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerAppsEnv
  name: 'rag-data'
  properties: {
    azureFile: {
      accountName: storageAccount.name
      accountKey: storageAccount.listKeys().keys[0].value
      shareName: ragDataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

// ── Container Registry (pre-existing, see header note) + pull identity ──
//
// A user-assigned identity, created and role-assigned up front, rather
// than each container app/job's own system-assigned identity: with
// system-assigned identity, the role assignment can only be created AFTER
// the app exists (its principal ID isn't known until then) — but the
// app's very first revision tries to pull its image immediately on
// creation, using a permission that either doesn't exist yet or was
// granted moments ago and hasn't finished propagating through Azure AD.
// That race reliably fails first-time deployments. A pre-existing
// identity with the role already granted removes the race entirely.

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

resource acrPullIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${namePrefix}-acrpull-id'
  location: location
}

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource acrPullAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, acrPullIdentity.id, 'AcrPull')
  scope: acr
  properties: {
    principalId: acrPullIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleId
  }
}

// ── PostgreSQL ───────────────────────────────────────────────────────────

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2022-12-01' = {
  name: '${namePrefix}-psql'
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
  }
}

resource postgresDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2022-12-01' = {
  parent: postgres
  name: postgresDbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Special "0.0.0.0-0.0.0.0" range = allow connections that originate from
// other Azure resources (Container Apps consumption plan has no fixed
// egress IP to allowlist individually).
resource postgresFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2022-12-01' = {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

var databaseUrl = 'postgresql+psycopg://${postgresAdminLogin}:${postgresAdminPassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${postgresDbName}?sslmode=require'

// ── Qdrant container app (internal-only ingress) ────────────────────────

resource qdrantApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-qdrant'
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: false
        targetPort: 6333
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'qdrant'
          image: 'qdrant/qdrant:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          volumeMounts: [
            { volumeName: 'qdrant-storage', mountPath: '/qdrant/storage' }
          ]
        }
      ]
      volumes: [
        { name: 'qdrant-storage', storageType: 'AzureFile', storageName: qdrantEnvStorage.name }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

// ── API container app ────────────────────────────────────────────────────
//
// minReplicas/maxReplicas pinned to 1: the per-workspace BM25 index is a
// read-modify-write pickle file on the shared volume, which isn't safe
// under concurrent writers from multiple replicas. Scaling this out would
// need BM25 persistence moved off local/shared-file storage first.

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-api'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${acrPullIdentity.id}': {} }
  }
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        { server: acr.properties.loginServer, identity: acrPullIdentity.id }
      ]
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'jwt-secret-key', value: jwtSecretKey }
        { name: 'gemini-api-key', value: geminiApiKey }
        { name: 'groq-api-key', value: groqApiKey }
        { name: 'hf-token', value: hfToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret-key' }
            { name: 'JWT_ALGORITHM', value: 'HS256' }
            { name: 'JWT_ACCESS_TOKEN_EXPIRE_MINUTES', value: '1440' }
            { name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }
            { name: 'GEMINI_MODEL', value: geminiModel }
            { name: 'GROQ_API_KEY', secretRef: 'groq-api-key' }
            { name: 'GROQ_MODEL', value: groqModel }
            { name: 'HF_TOKEN', secretRef: 'hf-token' }
            { name: 'QDRANT_URL', value: 'http://${qdrantApp.properties.configuration.ingress.fqdn}' }
            { name: 'QDRANT_COLLECTION', value: 'enterprise_rag' }
            { name: 'EMBEDDING_MODEL', value: 'all-MiniLM-L6-v2' }
            { name: 'RERANKER_MODEL', value: 'cross-encoder/ms-marco-MiniLM-L-6-v2' }
            { name: 'BM25_DIR', value: 'data/bm25' }
            { name: 'CHUNK_SIZE', value: '512' }
            { name: 'CHUNK_OVERLAP', value: '64' }
            { name: 'DENSE_TOP_K', value: '20' }
            { name: 'SPARSE_TOP_K', value: '20' }
            { name: 'RERANK_TOP_K', value: '5' }
            { name: 'APP_ENV', value: 'production' }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'CORS_ORIGINS', value: 'https://${staticWebApp.properties.defaultHostname}' }
          ]
          volumeMounts: [
            { volumeName: 'rag-data', mountPath: '/app/data' }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        { name: 'rag-data', storageType: 'AzureFile', storageName: ragDataEnvStorage.name }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
  dependsOn: [acrPullAssignment]
}

// ── Migration job ─────────────────────────────────────────────────────────
//
// A Container Apps Job rather than `az containerapp exec` in CI: exec is
// built for interactive TTY debugging sessions and is known to hang/not
// report exit codes cleanly when driven from a non-interactive runner.
// Jobs give a real, pollable execution status instead.

resource migrateJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-migrate'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${acrPullIdentity.id}': {} }
  }
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 600
      replicaRetryLimit: 0
      manualTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        { server: acr.properties.loginServer, identity: acrPullIdentity.id }
      ]
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'jwt-secret-key', value: jwtSecretKey }
        { name: 'gemini-api-key', value: geminiApiKey }
        { name: 'groq-api-key', value: groqApiKey }
        { name: 'hf-token', value: hfToken }
      ]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: apiImage
          command: ['alembic']
          args: ['upgrade', 'head']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            // alembic/env.py calls get_settings(), which validates the
            // full Settings model — so this needs every required field,
            // not just DATABASE_URL, or Settings() raises before alembic
            // ever runs.
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'JWT_SECRET_KEY', secretRef: 'jwt-secret-key' }
            { name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }
            { name: 'GROQ_API_KEY', secretRef: 'groq-api-key' }
            { name: 'HF_TOKEN', secretRef: 'hf-token' }
          ]
        }
      ]
    }
  }
  dependsOn: [acrPullAssignment]
}

// ── Frontend (Static Web App) ────────────────────────────────────────────

resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: '${namePrefix}-web'
  location: staticWebAppLocation
  sku: { name: 'Free', tier: 'Free' }
  properties: {
    buildProperties: {
      skipGithubActionWorkflowGeneration: true
    }
  }
}

// ── Outputs ────────────────────────────────────────────────────────────

output acrLoginServer string = acr.properties.loginServer
output apiUrl string = 'https://${apiApp.properties.configuration.ingress.fqdn}'
output staticWebAppUrl string = 'https://${staticWebApp.properties.defaultHostname}'
@secure()
output staticWebAppDeploymentToken string = staticWebApp.listSecrets().properties.apiKey
