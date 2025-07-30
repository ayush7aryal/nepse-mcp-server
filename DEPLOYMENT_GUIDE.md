# NEPSE MCP Server - Azure Deployment Guide

This guide will help you deploy your NEPSE MCP Server to Azure and configure it for use with Claude Desktop.

## 🚀 Quick Deployment

### Prerequisites

1. **Azure CLI**: Install from [here](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
2. **Docker**: Install from [here](https://docs.docker.com/get-docker/)
3. **Azure Subscription**: You need an active Azure subscription

### Step 1: Login to Azure

```bash
az login
```

### Step 2: Make deployment script executable

```bash
chmod +x deploy-azure.sh
```

### Step 3: Run deployment

```bash
./deploy-azure.sh
```

The script will:

- Create a resource group
- Set up Azure Container Registry
- Build and push your Docker image
- Deploy to Azure Container Apps
- Generate a secure admin API key
- Provide you with the deployment URL

## 📋 Manual Deployment (Alternative)

If you prefer manual deployment or need more control:

### 1. Create Resource Group

```bash
az group create --name nepse-mcp-rg --location eastus
```

### 2. Create Container Registry

```bash
az acr create --resource-group nepse-mcp-rg --name nepsemcpregistry --sku Basic --admin-enabled true
```

### 3. Build and Push Image

```bash
# Build image
docker build -t nepsemcpregistry.azurecr.io/nepse-mcp-server:latest .

# Login to registry
az acr login --name nepsemcpregistry

# Push image
docker push nepsemcpregistry.azurecr.io/nepse-mcp-server:latest
```

### 4. Create Container App Environment

```bash
az containerapp env create \
  --name nepse-mcp-env \
  --resource-group nepse-mcp-rg \
  --location eastus
```

### 5. Deploy Container App

```bash
az containerapp create \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --environment nepse-mcp-env \
  --image nepsemcpregistry.azurecr.io/nepse-mcp-server:latest \
  --target-port 8000 \
  --ingress 'external' \
  --registry-server nepsemcpregistry.azurecr.io \
  --registry-username nepsemcpregistry \
  --registry-password $(az acr credential show --name nepsemcpregistry --query passwords[0].value --output tsv) \
  --env-vars "PORT=8000" "HOST=0.0.0.0" "LOG_LEVEL=INFO" "ADMIN_API_KEY=your-secure-admin-key" \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3
```

## 🔧 Claude Desktop Configuration

After deployment, you'll need to configure Claude Desktop to use your MCP server.

### 1. Get Your Server URL

After deployment, you'll receive a URL like: `https://nepse-mcp-server--abc123.eastus.azurecontainerapps.io`

### 2. Configure Claude Desktop

Create or edit your Claude Desktop MCP configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add your server configuration:

```json
{
  "mcpServers": {
    "nepse-stock-server": {
      "command": "npx",
      "args": [
        "@modelcontextprotocol/server-fetch",
        "https://your-deployed-url.azurecontainerapps.io"
      ],
      "env": {
        "X-API-KEY": "demo_key_123"
      }
    }
  }
}
```

### 3. Alternative: Direct HTTP Configuration

If the above doesn't work, you can use a direct HTTP configuration:

```json
{
  "mcpServers": {
    "nepse-stock-server": {
      "command": "curl",
      "args": [
        "-X",
        "POST",
        "-H",
        "Content-Type: application/json",
        "-H",
        "X-API-KEY: demo_key_123",
        "https://your-deployed-url.azurecontainerapps.io"
      ]
    }
  }
}
```

## 🔑 API Key Management

### Default API Keys

Your server comes with these default API keys:

- `demo_key_123` - Demo client (rate limit: 100 requests)
- Admin key - Generated during deployment (rate limit: 1000 requests)

### Generate New API Keys

Use the admin API key to generate new keys:

```bash
curl -X POST \
  -H "X-API-KEY: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "New Client", "rate_limit": 200}' \
  https://your-url.azurecontainerapps.io/generate_new_key
```

### Check Usage Statistics

```bash
curl -H "X-API-KEY: your-admin-key" \
  https://your-url.azurecontainerapps.io/get_usage_stats
```

## 🧪 Testing Your Deployment

### 1. Health Check

```bash
curl https://your-url.azurecontainerapps.io/health
```

### 2. Test Stock Price API

```bash
curl -H "X-API-KEY: demo_key_123" \
  "https://your-url.azurecontainerapps.io/get_stock_price?symbol=NABIL"
```

### 3. Test Technical Analysis

```bash
curl -H "X-API-KEY: demo_key_123" \
  "https://your-url.azurecontainerapps.io/get_prediction?symbol=NABIL"
```

## 🔒 Security Considerations

### Production Recommendations

1. **Replace Demo Key**: Remove or change the demo API key
2. **Use Azure Key Vault**: Store API keys in Azure Key Vault
3. **Enable HTTPS Only**: Ensure all traffic is encrypted
4. **Set Up Monitoring**: Use Azure Monitor for logging and alerts
5. **Configure CORS**: Restrict CORS to specific domains
6. **Rate Limiting**: Implement proper rate limiting per client
7. **Database Storage**: Replace in-memory storage with Azure Database

### Environment Variables

Set these environment variables for production:

```bash
ADMIN_API_KEY=your-secure-admin-key
LOG_LEVEL=INFO
PORT=8000
HOST=0.0.0.0
```

## 📊 Monitoring and Scaling

### View Logs

```bash
az containerapp logs show \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --follow
```

### Scale Application

```bash
az containerapp update \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --min-replicas 2 \
  --max-replicas 5
```

### Update Application

```bash
# Build new image
docker build -t nepsemcpregistry.azurecr.io/nepse-mcp-server:v2 .

# Push new image
docker push nepsemcpregistry.azurecr.io/nepse-mcp-server:v2

# Update container app
az containerapp update \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --image nepsemcpregistry.azurecr.io/nepse-mcp-server:v2
```

## 🛠️ Troubleshooting

### Common Issues

1. **Authentication Errors**: Ensure X-API-KEY header is included
2. **CORS Issues**: Check CORS configuration in server.py
3. **Rate Limiting**: Check if you've exceeded your rate limit
4. **Network Issues**: Verify Azure networking and firewall rules

### Debug Commands

```bash
# Check container app status
az containerapp show --name nepse-mcp-server --resource-group nepse-mcp-rg

# View recent logs
az containerapp logs show --name nepse-mcp-server --resource-group nepse-mcp-rg --tail 100

# Check resource usage
az monitor metrics list --resource /subscriptions/your-sub/resourceGroups/nepse-mcp-rg/providers/Microsoft.App/containerApps/nepse-mcp-server
```

## 💰 Cost Optimization

### Azure Container Apps Pricing

- **Consumption Plan**: Pay per request (recommended for low traffic)
- **Dedicated Plan**: Fixed monthly cost (better for high traffic)

### Cost-Saving Tips

1. Set appropriate min/max replicas
2. Use consumption-based pricing for development
3. Monitor and optimize resource usage
4. Set up budget alerts

## 🔄 CI/CD Pipeline

For automated deployments, consider setting up GitHub Actions:

```yaml
name: Deploy to Azure
on:
  push:
    branches: [main]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Login to Azure
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Build and deploy
        run: |
          az acr build --registry nepsemcpregistry --image nepse-mcp-server:${{ github.sha }} .
          az containerapp update --name nepse-mcp-server --resource-group nepse-mcp-rg --image nepsemcpregistry.azurecr.io/nepse-mcp-server:${{ github.sha }}
```

## 📞 Support

If you encounter issues:

1. Check the troubleshooting section above
2. Review Azure Container Apps documentation
3. Check server logs for error messages
4. Verify API key configuration

## 🎉 Success!

Once deployed, your NEPSE MCP Server will be accessible from any Claude Desktop instance worldwide with proper API key authentication. The server provides real-time NEPSE stock data, technical analysis, and portfolio management features.
