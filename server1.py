import os
import logging
import secrets
import datetime
import time
import json
from typing import Dict, Any, Optional, List
import asyncio

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import pandas as pd
from dotenv import load_dotenv
from meroshare import MeroShare  # Make sure to implement this or use your existing implementation

from database import db_manager, init_default_data, APIKey
from fastapi.mcp import FastMCP

# Load environment variables
load_dotenv()

# ======================
# Configuration
# ======================
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin_" + secrets.token_urlsafe(32))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
CONFIG_FILE = os.getenv("CONFIG_FILE", "claude_config.json")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Track server start time
server_start_time = time.time()

# ======================
# Authentication Setup
# ======================
API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Initialize FastAPI app
app = FastAPI(
    title="NEPSE Stock Server",
    description="Advanced NEPSE Stock Analysis with Portfolio Tracking",
    version="3.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MCP server
mcp = FastMCP("NEPSE Stock Server")

# ======================
# Helper Functions
# ======================
def load_claude_config() -> Dict[str, Any]:
    """Load Claude configuration file"""
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading config: {str(e)}")
        return {}

async def validate_api_key(api_key: str) -> APIKey:
    """Validate API key and return key object"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required"
        )
    
    db_api_key = await db_manager.get_api_key(api_key)
    if not db_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    
    if db_api_key.requests_made >= db_api_key.rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )
    
    await db_manager.update_api_key_usage(api_key)
    return db_api_key

# ======================
# Authentication Dependencies
# ======================
async def get_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    """Dependency to validate API keys"""
    db_api_key = await validate_api_key(api_key)
    return api_key

async def get_admin_api_key(api_key: str = Depends(get_api_key)) -> str:
    """Dependency to validate admin API keys"""
    db_api_key = await validate_api_key(api_key)
    if not db_api_key.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return api_key

# ======================
# Middleware
# ======================
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests for analytics"""
    start_time = time.time()
    api_key = request.headers.get("X-API-KEY")
    
    try:
        response = await call_next(request)
        process_time = int((time.time() - start_time) * 1000)
        
        if api_key:
            await db_manager.log_request(
                api_key=api_key,
                endpoint=str(request.url.path),
                method=request.method,
                status_code=response.status_code,
                response_time_ms=process_time
            )
        
        return response
    except Exception as e:
        process_time = int((time.time() - start_time) * 1000)
        if api_key:
            await db_manager.log_request(
                api_key=api_key,
                endpoint=str(request.url.path),
                method=request.method,
                status_code=500,
                response_time_ms=process_time,
                error_message=str(e)
            )
        raise

# ======================
# Core Tools
# ======================
@mcp.tool()
async def get_stock_price(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """Get current stock price with caching"""
    try:
        
        url = f"https://chukul.com/api/data/historydata/?symbol={symbol}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        if not data:
            raise ValueError("No price data found")
        
        latest_data = data[0]
        result = {
            "symbol": symbol.upper(),
            "price": float(latest_data['close']),
            "open": float(latest_data['open']),
            "high": float(latest_data['high']),
            "low": float(latest_data['low']),
            "volume": int(latest_data['volume']),
            "date": latest_data['date'],
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        return result
        
    except Exception as e:
        logger.error(f"Error fetching stock price: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# [Include all your existing tools like get_bonus_info, get_company_report, etc.]

# ======================
# Portfolio Tools
# ======================
@mcp.tool()
async def get_portfolio(
    meroshare_username: str,
    meroshare_password: str,
    demat: str,
    api_key: str = Depends(get_api_key)
) -> dict:
    """Get complete portfolio with current valuation"""
    try:
        # Initialize MeroShare client
        ms = MeroShare(
            username=meroshare_username,
            password=meroshare_password,
            demat=demat
        )
        
        portfolio = ms.get_portfolio()
        total_investment = 0
        current_value = 0
        detailed_holdings = []
        
        for holding in portfolio:
            symbol = holding["symbol"]
            try:
                price_data = await get_stock_price(symbol, api_key)
                current_price = price_data["price"]
                current_val = current_price * holding["quantity"]
                
                detailed_holdings.append({
                    "symbol": symbol,
                    "quantity": holding["quantity"],
                    "average_price": holding["average_price"],
                    "total_cost": holding["total_cost"],
                    "current_price": current_price,
                    "current_value": current_val,
                    "profit_loss": current_val - holding["total_cost"],
                    "profit_loss_pct": ((current_val - holding["total_cost"]) / holding["total_cost"]) * 100
                })
                
                total_investment += holding["total_cost"]
                current_value += current_val
                
            except Exception as e:
                logger.warning(f"Skipping {symbol}: {str(e)}")
                detailed_holdings.append({
                    "symbol": symbol,
                    "error": str(e)
                })
        
        return {
            "holdings": detailed_holdings,
            "summary": {
                "total_investment": total_investment,
                "current_value": current_value,
                "total_profit_loss": current_value - total_investment,
                "total_profit_loss_pct": ((current_value - total_investment) / total_investment) * 100
            },
            "timestamp": datetime.datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Portfolio error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

# ======================
# Admin Tools
# ======================
@mcp.tool()
async def create_user(
    client_name: str,
    rate_limit: int = 100,
    is_admin: bool = False,
    admin_api_key: str = Depends(get_admin_api_key)
) -> dict:
    """Create new API user"""
    new_key = f"{client_name.lower().replace(' ', '_')}_{secrets.token_urlsafe(16)}"
    
    await db_manager.create_api_key(
        api_key=new_key,
        client_name=client_name,
        rate_limit=rate_limit,
        is_admin=is_admin
    )
    
    return {
        "message": "User created",
        "api_key": new_key,
        "client_name": client_name,
        "rate_limit": rate_limit,
        "is_admin": is_admin
    }

@mcp.tool()
async def list_users(admin_api_key: str = Depends(get_admin_api_key)) -> dict:
    """List all API users"""
    users = await db_manager.list_api_keys()
    return {"users": users}

@mcp.tool()
async def revoke_key(
    api_key: str,
    admin_api_key: str = Depends(get_admin_api_key)
) -> dict:
    """Revoke an API key"""
    await db_manager.revoke_api_key(api_key)
    return {"message": "Key revoked"}

# ======================
# System Endpoints
# ======================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "3.0.0",
        "uptime_seconds": int(time.time() - server_start_time),
        "database": "connected" if db_manager.is_connected() else "disconnected"
    }

# Mount MCP server
mcp.mount(app)

# ======================
# Startup/Shutdown
# ======================
@app.on_event("startup")
async def startup_event():
    """Initialize services"""
    try:
        await db_manager.init_database()
        await init_default_data(ADMIN_API_KEY)
        logger.info("Server started successfully")
    except Exception as e:
        logger.error(f"Startup failed: {str(e)}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources"""
    await db_manager.close()
    logger.info("Server shutdown complete")

# ======================
# Main Execution
# ======================
if __name__ == "__main__":
    logger.info(f"Starting NEPSE Server v3.0 on {HOST}:{PORT}")
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False
    )