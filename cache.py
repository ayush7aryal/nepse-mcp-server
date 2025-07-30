import os
import json
import logging
from typing import Optional, Any, Dict
from datetime import datetime, timedelta
import asyncio

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# ======================
# Redis Configuration
# ======================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))  # 5 minutes default

class CacheManager:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.enabled = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    
    async def init_redis(self):
        """Initialize Redis connection"""
        if not self.enabled:
            logger.info("Redis caching disabled")
            return
        
        try:
            self.redis_client = redis.from_url(
                REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await self.redis_client.ping()
            logger.info("Redis connection established successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self.enabled = False
            self.redis_client = None
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.enabled or not self.redis_client:
            return None
        
        try:
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            ttl = ttl or CACHE_TTL
            serialized_value = json.dumps(value, default=str)
            await self.redis_client.setex(key, ttl, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern"""
        if not self.enabled or not self.redis_client:
            return 0
        
        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                return await self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.enabled or not self.redis_client:
            return False
        
        try:
            return await self.redis_client.exists(key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.enabled or not self.redis_client:
            return {"enabled": False}
        
        try:
            info = await self.redis_client.info()
            return {
                "enabled": True,
                "connected_clients": info.get("connected_clients", 0),
                "used_memory": info.get("used_memory_human", "0B"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "total_commands_processed": info.get("total_commands_processed", 0)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"enabled": True, "error": str(e)}
    
    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()

# Global cache manager instance
cache_manager = CacheManager()

# ======================
# Cache Decorators and Helpers
# ======================

def cache_key_for_stock(symbol: str, data_type: str) -> str:
    """Generate cache key for stock data"""
    return f"stock:{symbol.upper()}:{data_type}"

def cache_key_for_user(api_key: str, data_type: str) -> str:
    """Generate cache key for user data"""
    # Use hash of API key for privacy
    import hashlib
    key_hash = hashlib.md5(api_key.encode()).hexdigest()[:8]
    return f"user:{key_hash}:{data_type}"

async def get_cached_stock_data(symbol: str, data_type: str) -> Optional[Dict[str, Any]]:
    """Get cached stock data"""
    cache_key = cache_key_for_stock(symbol, data_type)
    return await cache_manager.get(cache_key)

async def cache_stock_data(symbol: str, data_type: str, data: Dict[str, Any], ttl: Optional[int] = None) -> bool:
    """Cache stock data"""
    cache_key = cache_key_for_stock(symbol, data_type)
    return await cache_manager.set(cache_key, data, ttl)

async def invalidate_stock_cache(symbol: str) -> int:
    """Invalidate all cached data for a stock"""
    pattern = f"stock:{symbol.upper()}:*"
    return await cache_manager.delete_pattern(pattern)

async def get_cached_user_data(api_key: str, data_type: str) -> Optional[Any]:
    """Get cached user data"""
    cache_key = cache_key_for_user(api_key, data_type)
    return await cache_manager.get(cache_key)

async def cache_user_data(api_key: str, data_type: str, data: Any, ttl: Optional[int] = None) -> bool:
    """Cache user data"""
    cache_key = cache_key_for_user(api_key, data_type)
    return await cache_manager.set(cache_key, data, ttl)

async def invalidate_user_cache(api_key: str) -> int:
    """Invalidate all cached data for a user"""
    pattern = cache_key_for_user(api_key, "*")
    return await cache_manager.delete_pattern(pattern)

# ======================
# Cache Warming
# ======================

async def warm_popular_stocks_cache():
    """Pre-warm cache with popular NEPSE stocks"""
    popular_stocks = [
        "NABIL", "SCBNL", "HBL", "EBL", "BOKL", "NICA", "NBL", "SBL", "PRVU", "GBIME",
        "UPPER", "CHDC", "SHPC", "AKPL", "HURJA", "RHPL", "UMHL", "UMRH", "CORBL", "JBBL"
    ]
    
    logger.info("Starting cache warming for popular stocks...")
    
    # This would be called periodically to keep popular stock data fresh
    # Implementation would fetch and cache data for these stocks
    
    for stock in popular_stocks:
        try:
            # Check if data is already cached and fresh
            cached_data = await get_cached_stock_data(stock, "price")
            if cached_data:
                continue  # Skip if already cached
            
            # Here you would fetch fresh data and cache it
            # This is just a placeholder - actual implementation would call the stock API
            logger.debug(f"Would warm cache for {stock}")
            
        except Exception as e:
            logger.error(f"Error warming cache for {stock}: {e}")
    
    logger.info("Cache warming completed")

# ======================
# Background Tasks
# ======================

async def start_cache_maintenance():
    """Start background cache maintenance tasks"""
    if not cache_manager.enabled:
        return
    
    async def maintenance_loop():
        while True:
            try:
                # Warm popular stocks cache every 5 minutes
                await warm_popular_stocks_cache()
                await asyncio.sleep(300)  # 5 minutes
            except Exception as e:
                logger.error(f"Cache maintenance error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retrying
    
    # Start the maintenance task
    asyncio.create_task(maintenance_loop())
    logger.info("Cache maintenance started")
