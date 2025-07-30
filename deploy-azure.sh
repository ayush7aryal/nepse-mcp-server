#!/bin/bash

# Azure deployment script for NEPSE MCP Server v2.0
# Make sure you have Azure CLI installed and are logged in

set -e

# Configuration
RESOURCE_GROUP="nepse-mcp-rg"
LOCATION="eastus"
ACR_NAME="nepsemcpregistry"
APP_NAME="nepse-mcp-server"
CONTAINER_APP_ENV="nepse-mcp-env"
POSTGRES_SERVER="nepse-postgres-server"
REDIS_NAME="nepse-redis-cache"

echo "🚀 Starting Azure deployment for NEPSE MCP Server v2.0..."

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    echo "❌ Azure CLI is not installed. Please install it first."
    exit 1
fi

# Check if logged in to Azure
if ! az account show &> /dev/null; then
    echo "❌ Not logged in to Azure. Please run 'az login' first."
    exit 1
fi

echo "✅ Azure CLI is ready"

# Create resource group
echo "📦 Creating resource group..."
az group create --name $RESOURCE_GROUP --location $LOCATION

# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-24)
ADMIN_API_KEY="admin_$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"

echo "🔑 Generated secure credentials"

# Create PostgreSQL server
echo "🗄️ Creating PostgreSQL server..."
az postgres flexible-server create \
  --resource-group $RESOURCE_GROUP \
  --name $POSTGRES_SERVER \
  --location $LOCATION \
  --admin-user nepseadmin \
  --admin-password $POSTGRES_PASSWORD \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --storage-size 32 \
  --version 14 \
  --public-access 0.0.0.0 \
  --yes

# Create database
echo "📊 Creating database..."
az postgres flexible-server db create \
  --resource-group $RESOURCE_GROUP \
  --server-name $POSTGRES_SERVER \
  --database-name nepse_mcp

# # Create Redis cache
# echo "🔄 Creating Redis cache..."
# az redis create \
#   --resource-group $RESOURCE_GROUP \
#   --name $REDIS_NAME \
#   --location $LOCATION \
#   --sku Basic \
#   --vm-size c0 \
#   --enable-non-ssl-port

# # Get Redis connection details
# REDIS_KEY=$(az redis list-keys --resource-group $RESOURCE_GROUP --name $REDIS_NAME --query primaryKey --output tsv)
# REDIS_HOST=$(az redis show --resource-group $RESOURCE_GROUP --name $REDIS_NAME --query hostName --output tsv)

# Create Azure Container Registry
echo "🏗️ Creating Azure Container Registry..."
az acr create --resource-group $RESOURCE_GROUP --name $ACR_NAME --sku Basic --admin-enabled true

# Get ACR login server
ACR_LOGIN_SERVER=$(az acr show --name $ACR_NAME --resource-group $RESOURCE_GROUP --query loginServer --output tsv)
echo "📝 ACR Login Server: $ACR_LOGIN_SERVER"

# Build and push Docker image
echo "🔨 Building Docker image..."
docker build -t $ACR_LOGIN_SERVER/nepse-mcp-server:latest .

echo "🔐 Logging in to ACR..."
az acr login --name $ACR_NAME

echo "📤 Pushing image to ACR..."
docker push $ACR_LOGIN_SERVER/nepse-mcp-server:latest

# Create Container Apps environment
echo "🌍 Creating Container Apps environment..."
az containerapp env create \
  --name $CONTAINER_APP_ENV \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# Prepare connection strings
DATABASE_URL="postgresql+asyncpg://nepseadmin:$POSTGRES_PASSWORD@$POSTGRES_SERVER.postgres.database.azure.com:5432/nepse_mcp"
REDIS_URL="redis://:$REDIS_KEY@$REDIS_HOST:6379/0"

# Create the container app
echo "🚢 Creating Container App..."
az containerapp create \
  --name $APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --environment $CONTAINER_APP_ENV \
  --image $ACR_LOGIN_SERVER/nepse-mcp-server:latest \
  --target-port 8000 \
  --ingress 'external' \
  --registry-server $ACR_LOGIN_SERVER \
  --registry-username $ACR_NAME \
  --registry-password $(az acr credential show --name $ACR_NAME --query passwords[0].value --output tsv) \
  --secrets "admin-api-key=$ADMIN_API_KEY" "database-url=$DATABASE_URL" \
  --env-vars "PORT=8000" "HOST=0.0.0.0" "LOG_LEVEL=INFO" "ADMIN_API_KEY=secretref:admin-api-key" "DATABASE_URL=secretref:database-url" \
  --cpu 1.0 \
  --memory 2Gi \
  --min-replicas 2 \
  --max-replicas 10

# Get the app URL
APP_URL=$(az containerapp show --name $APP_NAME --resource-group $RESOURCE_GROUP --query properties.configuration.ingress.fqdn --output tsv)

echo "🎉 Deployment completed successfully!"
echo ""
echo "📋 Deployment Summary:"
echo "====================="
echo "Resource Group: $RESOURCE_GROUP"
echo "Container Registry: $ACR_NAME"
echo "PostgreSQL Server: $POSTGRES_SERVER"
# echo "Redis Cache: $REDIS_NAME"
echo "App Name: $APP_NAME"
echo "App URL: https://$APP_URL"
echo ""
echo "🔑 Credentials (SAVE THESE SECURELY!):"
echo "======================================"
echo "Admin API Key: $ADMIN_API_KEY"
echo "PostgreSQL Password: $POSTGRES_PASSWORD"
# echo "Redis Key: $REDIS_KEY"
echo ""
echo "🔗 Access your MCP server at: https://$APP_URL"
echo "📊 Health check: https://$APP_URL/health"
echo "📚 API docs: https://$APP_URL/docs"
echo ""
echo "✨ New Features in v2.0:"
echo "========================"
echo "✅ Database-backed user management"
echo "✅ User-specific watchlists"
echo "✅ Request logging and analytics"
echo "✅ Auto-scaling (2-10 replicas)"
echo "✅ Enhanced security"
echo ""
echo "🧪 Test your deployment:"
echo "curl -H 'X-API-KEY: demo_key_123' https://$APP_URL/health"
echo ""
echo "⚠️  IMPORTANT: Save all credentials securely!"
echo "   You'll need them for database access and admin functions."
