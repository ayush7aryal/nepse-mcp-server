# NEPSE MCP Server v2.0

A Model Context Protocol (MCP) server that provides real-time NEPSE (Nepal Stock Exchange) stock data, technical analysis, and portfolio management features. This server features database-backed user management, Redis caching, and can be deployed to Azure with auto-scaling capabilities.

## 🚀 Features

### Core Features

- **Real-time Stock Data**: Get current prices, historical data, and market information
- **Technical Analysis**: RSI, MACD, Moving Averages, Bollinger Bands
- **User-Specific Watchlists**: Each user has their own isolated watchlist
- **Company Reports**: Financial reports and bonus/dividend information
- **Redis Caching**: High-performance caching for frequently accessed data
- **Request Analytics**: Comprehensive logging and usage tracking

### Security & Performance

- **Database-Backed Authentication**: PostgreSQL-based user and API key management
- **Rate Limiting**: Configurable rate limits per user
- **Auto-Scaling**: Horizontal scaling from 2-10 replicas based on load
- **Request Logging**: Detailed analytics for monitoring and debugging
- **Secure Secrets Management**: Azure Key Vault integration

### Deployment Ready

- **Azure Optimized**: Full Azure Container Apps deployment with PostgreSQL and Redis
- **Docker Containerized**: Production-ready containerization
- **Health Monitoring**: Comprehensive health checks and monitoring
- **Local Development**: Easy local setup with Docker Compose

## 📊 Available Tools

### Stock Data Tools

- `get_stock_price(symbol)` - Get latest stock price and OHLCV data (cached)
- `get_bonus_info(symbol)` - Get bonus/dividend information (cached)
- `get_company_report(symbol)` - Get detailed financial reports (cached)

### Portfolio Tools (User-Specific)

- `add_to_watchlist(symbol)` - Add stock to your personal watchlist
- `remove_from_watchlist(symbol)` - Remove stock from your watchlist
- `get_watchlist()` - Get your current watchlist

### Technical Analysis

- `get_prediction(symbol)` - Get technical analysis with indicators and signals (cached)

### Admin Tools (Admin API key required)

- `generate_new_key(client_name, rate_limit)` - Generate new API keys
- `get_usage_stats()` - Get comprehensive usage statistics and analytics

## 🔧 Quick Start

### Local Development

1. **Setup Local Environment**

   ```bash
   # Clone the repository
   git clone <repository-url>
   cd nepse-mcp-server

   # Run the setup script (sets up PostgreSQL, Redis, and dependencies)
   ./setup-local.sh
   ```

2. **Start the Server**

   ```bash
   python server.py
   ```

3. **Test the API**

   ```bash
   curl -H "X-API-KEY: demo_key_123" http://localhost:8000/health
   ```

4. **Access Services**
   - **API**: http://localhost:8000
   - **API Docs**: http://localhost:8000/docs
   - **Database Admin**: http://localhost:8080 (Adminer)

### Azure Deployment

1. **Prerequisites**

   - Azure CLI installed and logged in
   - Docker installed
   - Active Azure subscription

2. **Deploy**

   ```bash
   chmod +x deploy-azure.sh
   ./deploy-azure.sh
   ```

3. **Configure Claude Desktop**
   - Copy your deployment URL from the script output
   - Update your Claude Desktop configuration
   - Use the provided admin API key

## 🏗️ Architecture

### Database Schema

- **API Keys**: User authentication and rate limiting
- **Watchlists**: User-specific stock watchlists
- **Request Logs**: Analytics and monitoring data

### Caching Strategy

- **Stock Prices**: 5 minutes TTL
- **Bonus Info**: 1 hour TTL
- **Company Reports**: 2 hours TTL
- **Technical Analysis**: 10 minutes TTL

### Scaling Configuration

- **Min Replicas**: 2
- **Max Replicas**: 10
- **CPU Threshold**: 70%
- **Memory Threshold**: 80%

## 🔑 Authentication

The server uses database-backed API key authentication via the `X-API-KEY` header.

### Default API Keys

- `demo_key_123` - Demo client (100 requests limit)
- Admin key - Generated during deployment (1000 requests limit)

### Generate New Keys

```bash
curl -X POST \
  -H "X-API-KEY: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "New Client", "rate_limit": 200}' \
  https://your-url.azurecontainerapps.io/generate_new_key
```

## 📁 Project Structure

```
nepse-mcp-server/
├── server.py                          # Main MCP server implementation
├── database.py                        # Database models and operations
├── cache.py                          # Redis caching implementation
├── requirements.txt                   # Python dependencies
├── Dockerfile                         # Optimized Docker configuration
├── deploy-azure.sh                    # Azure deployment script
├── setup-local.sh                     # Local development setup
├── .env.example                       # Environment variables template
├── azure-container-app.yaml           # Kubernetes deployment config
├── DEPLOYMENT_GUIDE.md               # Detailed deployment guide
├── claude_desktop_config_simple.json  # Simple Claude Desktop config
├── claude_desktop_config.json         # Advanced Claude Desktop config
└── README.md                          # This file
```

## 🛠️ Configuration

### Environment Variables

#### Server Configuration

- `PORT` - Server port (default: 8000)
- `HOST` - Server host (default: 0.0.0.0)
- `LOG_LEVEL` - Logging level (default: INFO)
- `ADMIN_API_KEY` - Admin API key (auto-generated if not set)

#### Database Configuration

- `DATABASE_URL` - PostgreSQL connection string
- `SQL_DEBUG` - Enable SQL query logging (default: false)

#### Cache Configuration

- `REDIS_URL` - Redis connection string
- `REDIS_ENABLED` - Enable/disable Redis caching (default: true)
- `CACHE_TTL` - Default cache TTL in seconds (default: 300)

### Claude Desktop Configuration

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

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

## 🧪 Testing

### Health Check

```bash
curl https://your-url.azurecontainerapps.io/health
```

### Stock Data

```bash
# Get stock price
curl -H "X-API-KEY: demo_key_123" \
  "https://your-url.azurecontainerapps.io/get_stock_price?symbol=NABIL"

# Add to watchlist
curl -H "X-API-KEY: demo_key_123" -X POST \
  "https://your-url.azurecontainerapps.io/add_to_watchlist?symbol=NABIL"

# Get watchlist
curl -H "X-API-KEY: demo_key_123" \
  "https://your-url.azurecontainerapps.io/get_watchlist"
```

### Technical Analysis

```bash
curl -H "X-API-KEY: demo_key_123" \
  "https://your-url.azurecontainerapps.io/get_prediction?symbol=NABIL"
```

### Admin Functions

```bash
# Get usage statistics
curl -H "X-API-KEY: your-admin-key" \
  "https://your-url.azurecontainerapps.io/get_usage_stats"

# Generate new API key
curl -X POST \
  -H "X-API-KEY: your-admin-key" \
  -H "Content-Type: application/json" \
  -d '{"client_name": "Test Client", "rate_limit": 150}' \
  "https://your-url.azurecontainerapps.io/generate_new_key"
```

## 🔒 Security Features

- **Database-Backed Authentication**: Secure PostgreSQL-based user management
- **Rate Limiting**: Per-user configurable rate limits
- **Request Logging**: Comprehensive audit trail
- **Secrets Management**: Azure Key Vault integration
- **HTTPS Only**: All traffic encrypted in production
- **Input Validation**: Comprehensive input validation and sanitization
- **Error Handling**: Secure error handling without information leakage

## 📊 Monitoring & Analytics

### View Logs

```bash
az containerapp logs show \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --follow
```

### Usage Statistics

The admin endpoint provides comprehensive analytics:

- Total requests per client
- Active vs inactive clients
- Recent request patterns (24h)
- Cache hit/miss ratios
- Database connection status

### Performance Metrics

- Response times per endpoint
- Cache performance statistics
- Database query performance
- Auto-scaling events

## 🚀 Scaling & Performance

### Auto-Scaling Configuration

- **CPU-based scaling**: Scales up when CPU > 70%
- **Memory-based scaling**: Scales up when memory > 80%
- **Min replicas**: 2 (high availability)
- **Max replicas**: 10 (cost control)

### Performance Optimizations

- **Redis caching**: Reduces API calls by 80%+
- **Database connection pooling**: Efficient connection management
- **Async operations**: Non-blocking I/O for better concurrency
- **Request batching**: Optimized database operations

### Manual Scaling

```bash
az containerapp update \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --min-replicas 3 \
  --max-replicas 15
```

## 🔄 Updates & Maintenance

### Update Deployment

```bash
# Build new version
docker build -t nepsemcpregistry.azurecr.io/nepse-mcp-server:v2.1 .

# Push to registry
docker push nepsemcpregistry.azurecr.io/nepse-mcp-server:v2.1

# Update container app
az containerapp update \
  --name nepse-mcp-server \
  --resource-group nepse-mcp-rg \
  --image nepsemcpregistry.azurecr.io/nepse-mcp-server:v2.1
```

### Database Migrations

The server automatically creates and updates database tables on startup.

### Cache Management

```bash
# Clear cache for a specific stock
curl -X DELETE -H "X-API-KEY: your-admin-key" \
  "https://your-url.azurecontainerapps.io/cache/clear?pattern=stock:NABIL:*"
```

## 🛠️ Troubleshooting

### Common Issues

1. **Database Connection Issues**

   - Check PostgreSQL server status
   - Verify connection string format
   - Check firewall rules

2. **Cache Performance Issues**

   - Monitor Redis memory usage
   - Check cache hit ratios
   - Verify Redis connectivity

3. **Authentication Errors**

   - Ensure `X-API-KEY` header is included
   - Check API key exists in database
   - Verify rate limits not exceeded

4. **Claude Desktop Integration**
   - Verify config file location and syntax
   - Check API key permissions
   - Test MCP connection manually

### Debug Commands

```bash
# Check app status
az containerapp show --name nepse-mcp-server --resource-group nepse-mcp-rg

# View recent logs
az containerapp logs show --name nepse-mcp-server --resource-group nepse-mcp-rg --tail 100

# Test database connectivity
curl -H "X-API-KEY: your-admin-key" \
  "https://your-url.azurecontainerapps.io/get_usage_stats"

# Test cache connectivity
curl "https://your-url.azurecontainerapps.io/health"
```

## 💰 Cost Optimization

### Azure Resources

- **Container Apps**: Consumption-based pricing
- **PostgreSQL**: Burstable tier for cost efficiency
- **Redis**: Basic tier for development, Standard for production
- **Container Registry**: Basic tier sufficient for most use cases

### Cost-Saving Tips

- Use appropriate min/max replicas based on usage patterns
- Monitor resource utilization and adjust accordingly
- Consider Azure Reserved Instances for predictable workloads
- Set up budget alerts and cost monitoring

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Update documentation
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:

1. Check the troubleshooting section
2. Review Azure Container Apps documentation
3. Check server logs for error messages
4. Verify configuration and credentials

## 🎯 What's New in v2.0

### ✨ Major Features

- **Database Integration**: PostgreSQL-backed user management and data persistence
- **Redis Caching**: High-performance caching layer for improved response times
- **User Isolation**: Each user has their own watchlist and data
- **Request Analytics**: Comprehensive logging and usage tracking
- **Auto-Scaling**: Intelligent scaling based on CPU and memory usage

### 🔧 Technical Improvements

- **Async Operations**: Full async/await implementation for better performance
- **Connection Pooling**: Efficient database connection management
- **Error Handling**: Enhanced error handling and logging
- **Security**: Improved authentication and authorization
- **Monitoring**: Better health checks and monitoring capabilities

### 🚀 Deployment Enhancements

- **One-Click Setup**: Automated local development environment setup
- **Azure Integration**: Full Azure services integration (PostgreSQL, Redis, Container Apps)
- **Secrets Management**: Secure credential handling
- **Environment Configuration**: Flexible environment-based configuration

---

**Made with ❤️ for the NEPSE trading community**

_Empowering traders with real-time data, advanced analytics, and seamless integration._
