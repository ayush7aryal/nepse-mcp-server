#!/bin/bash

# Local development setup script for NEPSE MCP Server v2.0
# This script sets up PostgreSQL and Redis for local development

set -e

echo "🚀 Setting up NEPSE MCP Server v2.0 for local development..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
    echo "❌ Docker Compose is not available. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker is ready"

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    
    # Generate a secure admin API key
    ADMIN_KEY="admin_$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"
    
    # Update the .env file with the generated key
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/ADMIN_API_KEY=admin_your_secure_key_here/ADMIN_API_KEY=$ADMIN_KEY/" .env
    else
        # Linux
        sed -i "s/ADMIN_API_KEY=admin_your_secure_key_here/ADMIN_API_KEY=$ADMIN_KEY/" .env
    fi
    
    echo "🔑 Generated admin API key: $ADMIN_KEY"
    echo "📝 Updated .env file with secure credentials"
else
    echo "✅ .env file already exists"
fi

# Create docker-compose.yml for local development
echo "🐳 Creating Docker Compose configuration..."
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:14
    container_name: nepse-postgres
    environment:
      POSTGRES_DB: nepse_mcp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: nepse-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  adminer:
    image: adminer
    container_name: nepse-adminer
    ports:
      - "8080:8080"
    depends_on:
      - postgres

volumes:
  postgres_data:
  redis_data:
EOF

# Start the services
echo "🚀 Starting PostgreSQL and Redis..."
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check if services are running
if docker ps | grep -q nepse-postgres && docker ps | grep -q nepse-redis; then
    echo "✅ PostgreSQL and Redis are running"
else
    echo "❌ Failed to start services"
    exit 1
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
if command -v pip &> /dev/null; then
    pip install -r requirements.txt
else
    echo "⚠️  pip not found. Please install Python dependencies manually:"
    echo "   pip install -r requirements.txt"
fi

echo ""
echo "🎉 Local development environment setup completed!"
echo ""
echo "📋 Services Status:"
echo "=================="
echo "✅ PostgreSQL: localhost:5432 (user: postgres, password: password, db: nepse_mcp)"
echo "✅ Redis: localhost:6379"
echo "✅ Adminer (DB Admin): http://localhost:8080"
echo ""
echo "🚀 To start the NEPSE MCP Server:"
echo "================================"
echo "python server.py"
echo ""
echo "🔗 Server will be available at:"
echo "==============================="
echo "• API: http://localhost:8000"
echo "• Health: http://localhost:8000/health"
echo "• Docs: http://localhost:8000/docs"
echo ""
echo "🔑 Admin API Key (from .env file):"
echo "=================================="
grep "ADMIN_API_KEY=" .env | cut -d'=' -f2
echo ""
echo "🧪 Test commands:"
echo "================"
echo "# Health check"
echo "curl http://localhost:8000/health"
echo ""
echo "# Test with demo key"
echo "curl -H 'X-API-KEY: demo_key_123' http://localhost:8000/get_stock_price?symbol=NABIL"
echo ""
echo "🛑 To stop services:"
echo "==================="
if command -v docker-compose &> /dev/null; then
    echo "docker-compose down"
else
    echo "docker compose down"
fi
echo ""
echo "📚 For more information, check the README.md file"
