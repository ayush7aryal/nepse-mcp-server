import os
import logging
import secrets
import datetime
from typing import Dict, Any, Optional
import asyncio
import time

from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import requests
import pandas as pd
from dotenv import load_dotenv

from mcp.server.fastmcp import FastMCP
from database import db_manager, init_default_data, APIKey
from cache import cache_manager, get_cached_stock_data, cache_stock_data, start_cache_maintenance

# Load environment variables
load_dotenv()

# ======================
# Configuration
# ======================

# Environment variables with defaults
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "admin_" + secrets.token_urlsafe(32))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Print admin key on startup (only for demo - remove in production)
logger.info(f"Admin API Key: {ADMIN_API_KEY}")

# ======================
# Authentication Setup
# ======================

API_KEY_NAME = "X-API-KEY"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

class AuthenticationError(Exception):
    pass

async def get_api_key(api_key: Optional[str] = Depends(api_key_header)) -> str:
    """Dependency to validate API keys"""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required. Include X-API-KEY header."
        )
    
    # Get API key from database
    db_api_key = await db_manager.get_api_key(api_key)
    if not db_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key"
        )
    
    # Check rate limiting
    if db_api_key.requests_made >= db_api_key.rate_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded"
        )
    
    # Update usage stats
    await db_manager.update_api_key_usage(api_key)
    
    return api_key

async def get_admin_api_key(api_key: str = Depends(get_api_key)) -> str:
    """Dependency to validate admin API keys"""
    db_api_key = await db_manager.get_api_key(api_key)
    if not db_api_key or not db_api_key.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return api_key

def generate_api_key(client_name: str, rate_limit: int = 100, is_admin: bool = False) -> str:
    """Generate new API key"""
    return f"{client_name.lower().replace(' ', '_')}_{secrets.token_urlsafe(16)}"

# ======================
# FastAPI App Setup
# ======================

# Create FastAPI app first
app = FastAPI(
    title="NEPSE Stock Server",
    description="NEPSE Stock Analysis Server with Technical Indicators",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MCP server
mcp = FastMCP("NEPSE Stock Server")

# ======================
# Request Logging Middleware
# ======================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests for analytics"""
    start_time = time.time()
    
    # Get API key from header
    api_key = request.headers.get("X-API-KEY")
    
    try:
        response = await call_next(request)
        process_time = int((time.time() - start_time) * 1000)
        
        # Log request if API key is present
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
        
        # Log error if API key is present
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
# Core Tools using Chukul APIs with Caching
# ======================

@mcp.tool()
async def get_stock_price(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """
    Get the latest closing price for a NEPSE stock from chukul.com.
    Requires valid API key in X-API-KEY header.
    """
    try:
        logger.info(f"Fetching stock price for {symbol}")
        
        # Check cache first
        cached_data = await get_cached_stock_data(symbol, "price")
        if cached_data:
            logger.info(f"Returning cached price data for {symbol}")
            return cached_data
        
        # Fetch from API
        url = f"https://chukul.com/api/data/historydata/?symbol={symbol}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        if not data:
            raise ValueError("No price data found.")
        
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
        
        # Cache the result
        await cache_stock_data(symbol, "price", result, ttl=300)  # 5 minutes
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"Network error fetching stock price for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to fetch stock data: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error fetching stock price for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching stock price: {str(e)}"
        )

@mcp.tool()
async def get_bonus_info(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """
    Get bonus/dividend data for a NEPSE stock.
    Requires valid API key in X-API-KEY header.
    """
    try:
        logger.info(f"Fetching bonus info for {symbol}")
        
        # Check cache first
        cached_data = await get_cached_stock_data(symbol, "bonus")
        if cached_data:
            logger.info(f"Returning cached bonus data for {symbol}")
            return cached_data
        
        url = f"https://chukul.com/api/bonus/?symbol={symbol}"
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        result = {
            "symbol": symbol.upper(),
            "bonus_data": data,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Cache the result
        await cache_stock_data(symbol, "bonus", result, ttl=3600)  # 1 hour
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"Network error fetching bonus info for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to fetch bonus data: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error fetching bonus info for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching bonus info: {str(e)}"
        )

@mcp.tool()
async def get_company_report(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """
    Get financial report data using company ID from Chukul.
    Requires valid API key in X-API-KEY header.
    """
    try:
        logger.info(f"Fetching company report for {symbol}")
        
        # Check cache first
        cached_data = await get_cached_stock_data(symbol, "report")
        if cached_data:
            logger.info(f"Returning cached report data for {symbol}")
            return cached_data
        
        # First get company ID
        search_url = f"https://chukul.com/api/stock/?search={symbol}"
        res = requests.get(search_url, timeout=10)
        res.raise_for_status()
        companies = res.json()
        
        if not companies:
            raise ValueError(f"No company found for symbol {symbol}")
        
        company = companies[0]
        company_id = company['id']

        # Get company report
        report_url = f"https://chukul.com/api/stock/{company_id}/report/"
        report_res = requests.get(report_url, timeout=10)
        report_res.raise_for_status()
        report = report_res.json()
        
        result = {
            "symbol": symbol.upper(),
            "company_info": company,
            "financial_report": report,
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Cache the result
        await cache_stock_data(symbol, "report", result, ttl=7200)  # 2 hours
        
        return result
        
    except requests.RequestException as e:
        logger.error(f"Network error fetching company report for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to fetch company report: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error fetching company report for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching company report: {str(e)}"
        )

# ======================
# Database-backed Watchlist Tools
# ======================

@mcp.tool()
async def add_to_watchlist(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """Add stock to user's watchlist. Requires API key."""
    symbol = symbol.upper()
    success = await db_manager.add_to_watchlist(api_key, symbol)
    
    if success:
        # Get updated watchlist count
        watchlist = await db_manager.get_watchlist(api_key)
        return {
            "message": f"Added {symbol} to watchlist",
            "symbol": symbol,
            "watchlist_size": len(watchlist)
        }
    else:
        return {
            "message": f"{symbol} already in watchlist",
            "symbol": symbol,
            "watchlist_size": len(await db_manager.get_watchlist(api_key))
        }

@mcp.tool()
async def remove_from_watchlist(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """Remove stock from user's watchlist. Requires API key."""
    symbol = symbol.upper()
    success = await db_manager.remove_from_watchlist(api_key, symbol)
    
    watchlist = await db_manager.get_watchlist(api_key)
    
    if success:
        return {
            "message": f"Removed {symbol} from watchlist",
            "symbol": symbol,
            "watchlist_size": len(watchlist)
        }
    else:
        return {
            "message": f"{symbol} not in watchlist",
            "symbol": symbol,
            "watchlist_size": len(watchlist)
        }

@mcp.tool()
async def get_watchlist(api_key: str = Depends(get_api_key)) -> dict:
    """Get user's current watchlist. Requires API key."""
    watchlist = await db_manager.get_watchlist(api_key)
    return {
        "watchlist": sorted(watchlist),
        "count": len(watchlist),
        "timestamp": datetime.datetime.now().isoformat()
    }

# ======================
# Technical Analysis Tools
# ======================

def get_stock_df(symbol: str) -> pd.DataFrame:
    """Helper function to get stock data as DataFrame"""
    today = int(time.time())
    url = f"https://chukul.com/api/data/adjhistorydata/data/?symbol={symbol}&from=1280080358&to={today}"

    try:
        res = requests.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()

        df = pd.DataFrame({
            'timestamp': data['t'],
            'open': data['o'],
            'close': data['c'],
            'high': data['h'],
            'low': data['l'],
            'volume': data['vol'],
        })
        
        df['date'] = pd.to_datetime(df['timestamp'], unit='s')
        df = df.iloc[::-1].reset_index(drop=True)
        df.set_index('date', inplace=True)
        
        return df
    except Exception as e:
        logger.error(f"Error fetching stock data for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error fetching stock data: {str(e)}"
        )

def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to DataFrame"""
    try:
        # Moving Averages
        df['SMA20'] = df['close'].rolling(window=20, min_periods=20).mean()
        df['SMA50'] = df['close'].rolling(window=50, min_periods=50).mean()
        
        # MACD
        df['EMA12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['EMA26'] = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = df['EMA12'] - df['EMA26']
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # Bollinger Bands
        bb_period = 20
        df['BB_Middle'] = df['close'].rolling(window=bb_period, min_periods=bb_period).mean()
        bb_std = df['close'].rolling(window=bb_period, min_periods=bb_period).std()
        df['BB_Upper'] = df['BB_Middle'] + (2 * bb_std)
        df['BB_Lower'] = df['BB_Middle'] - (2 * bb_std)
        df['BB_Position'] = (df['close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower']) * 100
        
        return df
    except Exception as e:
        logger.error(f"Error calculating technical indicators: {str(e)}")
        raise




@mcp.tool()
async def get_prediction(symbol: str, api_key: str = Depends(get_api_key)) -> dict:
    """
    Get technical analysis prediction for a stock.
    Requires API key.
    """
    try:
        logger.info(f"Generating prediction for {symbol}")
        
        # Check cache first
        cached_data = await get_cached_stock_data(symbol, "prediction")
        if cached_data:
            logger.info(f"Returning cached prediction for {symbol}")
            return cached_data
        
        df = get_stock_df(symbol)
        df = add_technical_indicators(df)
        
        latest = df.iloc[-1]
        previous = df.iloc[-2] if len(df) > 1 else latest
        
        # Generate analysis
        analysis = {
            "symbol": symbol.upper(),
            "current_price": float(latest['close']),
            "technical_indicators": {
                "RSI": float(latest['RSI']) if not pd.isna(latest['RSI']) else None,
                "MACD": float(latest['MACD']) if not pd.isna(latest['MACD']) else None,
                "MACD_Signal": float(latest['MACD_Signal']) if not pd.isna(latest['MACD_Signal']) else None,
                "SMA20": float(latest['SMA20']) if not pd.isna(latest['SMA20']) else None,
                "SMA50": float(latest['SMA50']) if not pd.isna(latest['SMA50']) else None,
                "BB_Position": float(latest['BB_Position']) if not pd.isna(latest['BB_Position']) else None
            },
            "signals": [],
            "timestamp": datetime.datetime.now().isoformat()
        }
        
        # Generate signals
        if not pd.isna(latest['RSI']):
            if latest['RSI'] > 70:
                analysis["signals"].append("RSI indicates overbought condition")
            elif latest['RSI'] < 30:
                analysis["signals"].append("RSI indicates oversold condition")
        
        if not pd.isna(latest['MACD']) and not pd.isna(latest['MACD_Signal']):
            if latest['MACD'] > latest['MACD_Signal']:
                analysis["signals"].append("MACD shows bullish momentum")
            else:
                analysis["signals"].append("MACD shows bearish momentum")
        
        # Cache the result
        await cache_stock_data(symbol, "prediction", analysis, ttl=600)  # 10 minutes
        
        return analysis
        
    except Exception as e:
        logger.error(f"Error generating prediction for {symbol}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error generating prediction: {str(e)}"
        )

# ======================
# Authentication Endpoint
# ======================

@mcp.tool()
async def authenticate_user(client_id: str, username: str, password: str) -> dict:
    """
    Authenticate user with credentials and return session info.
    This endpoint accepts clientID, username, and password for authentication.
    """
    try:
        # Here you can implement your authentication logic
        # For now, this is a placeholder that accepts any credentials
        
        # You can add your actual authentication logic here:
        # - Validate against your user database
        # - Check credentials with external service
        # - Generate session tokens, etc.
        
        logger.info(f"Authentication attempt for client_id: {client_id}, username: {username}")
        
        # Placeholder authentication - replace with your actual logic
        if client_id and username and password:
            return {
                "success": True,
                "message": "Authentication successful",
                "client_id": client_id,
                "username": username,
                "session_token": f"session_{secrets.token_urlsafe(16)}",
                "timestamp": datetime.datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "message": "Invalid credentials",
                "timestamp": datetime.datetime.now().isoformat()
            }
            
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return {
            "success": False,
            "message": f"Authentication failed: {str(e)}",
            "timestamp": datetime.datetime.now().isoformat()
        }

# ======================
# Admin Tools
# ======================

@mcp.tool()
async def generate_new_key(client_name: str, rate_limit: int = 100, admin_api_key: str = Depends(get_admin_api_key)) -> dict:
    """Generate new API key (admin only)"""
    try:
        new_key = generate_api_key(client_name, rate_limit, is_admin=False)
        
        # Create in database
        await db_manager.create_api_key(
            api_key=new_key,
            client_name=client_name,
            rate_limit=rate_limit,
            is_admin=False
        )
        
        logger.info(f"Generated new API key for {client_name}")
        return {
            "message": "New API key generated successfully",
            "api_key": new_key,
            "client_name": client_name,
            "rate_limit": rate_limit,
            "created_at": datetime.datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error generating new API key: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating API key: {str(e)}"
        )

@mcp.tool()
async def get_usage_stats(admin_api_key: str = Depends(get_admin_api_key)) -> dict:
    """Get usage statistics (admin only)"""
    try:
        stats = await db_manager.get_usage_stats()
        
        # Add cache stats
        cache_stats = await cache_manager.get_stats()
        stats["cache"] = cache_stats
        
        return stats
    except Exception as e:
        logger.error(f"Error getting usage stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting usage stats: {str(e)}"
        )

# ======================
# Health Check Endpoints
# ======================

@app.get("/health")
async def health_check():
    """Health check endpoint for Azure"""
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "2.0.0",
        "database": "connected",
        "cache": "enabled" if cache_manager.enabled else "disabled"
    }

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "NEPSE Stock Analysis Server",
        "version": "2.0.0",
        "description": "MCP server for NEPSE stock data with technical analysis",
        "features": [
            "Database-backed user management",
            "Redis caching for performance",
            "User-specific watchlists",
            "Request logging and analytics",
            "Rate limiting per user"
        ],
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "mcp": "Use MCP client to connect"
        },
        "authentication": "Required - use X-API-KEY header"
    }

# Mount MCP server
mcp.mount(app)

# ======================
# Startup and Shutdown Events
# ======================

@app.on_event("startup")
async def startup_event():
    """Initialize database and cache on startup"""
    try:
        # Initialize database
        await db_manager.init_database()
        await init_default_data()
        
        # Initialize cache
        await cache_manager.init_redis()
        await start_cache_maintenance()
        
        logger.info("Server startup completed successfully")
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    try:
        await cache_manager.close()
        logger.info("Server shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# ======================
# Server Startup
# ======================

if __name__ == "__main__":
    logger.info(f"Starting NEPSE MCP Server v2.0 on {HOST}:{PORT}")
    logger.info(f"Admin API Key: {ADMIN_API_KEY}")
    
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        log_level=LOG_LEVEL.lower(),
        reload=False
    )
