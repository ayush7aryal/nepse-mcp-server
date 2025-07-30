import os
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, Boolean, Text, JSON, select, update, delete
from sqlalchemy.dialects.postgresql import UUID
import uuid

logger = logging.getLogger(__name__)

# ======================
# Database Configuration
# ======================

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:password@localhost:5432/nepse_mcp"
)

# For Azure PostgreSQL, the URL format should be:
# postgresql+asyncpg://username:password@servername.postgres.database.azure.com:5432/database_name

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)

AsyncSessionLocal = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# ======================
# Database Models
# ======================

class Base(DeclarativeBase):
    pass

class APIKey(Base):
    __tablename__ = "api_keys"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(255))
    rate_limit: Mapped[int] = mapped_column(Integer, default=100)
    requests_made: Mapped[int] = mapped_column(Integer, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationship to user watchlists
    watchlists: Mapped[List["Watchlist"]] = relationship("Watchlist", back_populates="api_key_obj")

class Watchlist(Base):
    __tablename__ = "watchlists"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id: Mapped[str] = mapped_column(String(255), index=True)  # References APIKey.api_key
    symbol: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationship back to API key
    api_key_obj: Mapped["APIKey"] = relationship("APIKey", back_populates="watchlists")

class RequestLog(Base):
    __tablename__ = "request_logs"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id: Mapped[str] = mapped_column(String(255), index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(10))
    status_code: Mapped[int] = mapped_column(Integer)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

# ======================
# Database Operations
# ======================

class DatabaseManager:
    def __init__(self):
        self.session_factory = AsyncSessionLocal
    
    async def get_session(self) -> AsyncSession:
        """Get database session"""
        return self.session_factory()
    
    async def init_database(self):
        """Initialize database tables"""
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    async def create_api_key(
        self, 
        api_key: str, 
        client_name: str, 
        rate_limit: int = 100, 
        is_admin: bool = False
    ) -> APIKey:
        """Create a new API key"""
        async with self.session_factory() as session:
            try:
                db_api_key = APIKey(
                    api_key=api_key,
                    client_name=client_name,
                    rate_limit=rate_limit,
                    is_admin=is_admin
                )
                session.add(db_api_key)
                await session.commit()
                await session.refresh(db_api_key)
                logger.info(f"Created API key for {client_name}")
                return db_api_key
            except Exception as e:
                await session.rollback()
                logger.error(f"Error creating API key: {e}")
                raise
    
    async def get_api_key(self, api_key: str) -> Optional[APIKey]:
        """Get API key details"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(APIKey).where(APIKey.api_key == api_key, APIKey.is_active == True)
                )
                return result.scalar_one_or_none()
            except Exception as e:
                logger.error(f"Error getting API key: {e}")
                return None
    
    async def update_api_key_usage(self, api_key: str) -> bool:
        """Update API key usage statistics"""
        async with self.session_factory() as session:
            try:
                await session.execute(
                    update(APIKey)
                    .where(APIKey.api_key == api_key)
                    .values(
                        requests_made=APIKey.requests_made + 1,
                        last_used=datetime.utcnow()
                    )
                )
                await session.commit()
                return True
            except Exception as e:
                logger.error(f"Error updating API key usage: {e}")
                await session.rollback()
                return False
    
    async def get_all_api_keys(self) -> List[APIKey]:
        """Get all API keys (admin only)"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(select(APIKey))
                return result.scalars().all()
            except Exception as e:
                logger.error(f"Error getting all API keys: {e}")
                return []
    
    async def add_to_watchlist(self, api_key: str, symbol: str) -> bool:
        """Add symbol to user's watchlist"""
        async with self.session_factory() as session:
            try:
                # Check if already exists
                existing = await session.execute(
                    select(Watchlist).where(
                        Watchlist.api_key_id == api_key,
                        Watchlist.symbol == symbol.upper()
                    )
                )
                if existing.scalar_one_or_none():
                    return False  # Already exists
                
                watchlist_item = Watchlist(
                    api_key_id=api_key,
                    symbol=symbol.upper()
                )
                session.add(watchlist_item)
                await session.commit()
                logger.info(f"Added {symbol} to watchlist for {api_key}")
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Error adding to watchlist: {e}")
                return False
    
    async def remove_from_watchlist(self, api_key: str, symbol: str) -> bool:
        """Remove symbol from user's watchlist"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    delete(Watchlist).where(
                        Watchlist.api_key_id == api_key,
                        Watchlist.symbol == symbol.upper()
                    )
                )
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                logger.error(f"Error removing from watchlist: {e}")
                return False
    
    async def get_watchlist(self, api_key: str) -> List[str]:
        """Get user's watchlist"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(Watchlist.symbol).where(Watchlist.api_key_id == api_key)
                )
                return [row[0] for row in result.fetchall()]
            except Exception as e:
                logger.error(f"Error getting watchlist: {e}")
                return []
    
    async def log_request(
        self, 
        api_key: str, 
        endpoint: str, 
        method: str, 
        status_code: int,
        response_time_ms: Optional[int] = None,
        error_message: Optional[str] = None,
        request_data: Optional[Dict[str, Any]] = None
    ):
        """Log API request"""
        async with self.session_factory() as session:
            try:
                log_entry = RequestLog(
                    api_key_id=api_key,
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    error_message=error_message,
                    request_data=request_data
                )
                session.add(log_entry)
                await session.commit()
            except Exception as e:
                logger.error(f"Error logging request: {e}")
                # Don't raise here as logging shouldn't break the main flow
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get comprehensive usage statistics"""
        async with self.session_factory() as session:
            try:
                # Get API key stats
                api_keys_result = await session.execute(select(APIKey))
                api_keys = api_keys_result.scalars().all()
                
                total_requests = sum(key.requests_made for key in api_keys)
                active_clients = sum(1 for key in api_keys if key.last_used is not None)
                
                # Get recent request logs (last 24 hours)
                from datetime import timedelta
                yesterday = datetime.utcnow() - timedelta(days=1)
                recent_logs_result = await session.execute(
                    select(RequestLog).where(RequestLog.timestamp >= yesterday)
                )
                recent_logs = recent_logs_result.scalars().all()
                
                return {
                    "total_requests": total_requests,
                    "total_clients": len(api_keys),
                    "active_clients": active_clients,
                    "recent_requests_24h": len(recent_logs),
                    "clients": {
                        key.api_key: {
                            "client_name": key.client_name,
                            "requests_made": key.requests_made,
                            "rate_limit": key.rate_limit,
                            "last_used": key.last_used.isoformat() if key.last_used else None,
                            "created_at": key.created_at.isoformat(),
                            "is_admin": key.is_admin,
                            "is_active": key.is_active
                        }
                        for key in api_keys
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
            except Exception as e:
                logger.error(f"Error getting usage stats: {e}")
                return {"error": str(e)}

# Global database manager instance
db_manager = DatabaseManager()

# ======================
# Database Dependencies
# ======================

async def get_db_session():
    """FastAPI dependency to get database session"""
    async with db_manager.session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

# ======================
# Initialization
# ======================

async def init_default_data():
    """Initialize default API keys"""
    try:
        # Check if admin key exists
        admin_key = os.getenv("ADMIN_API_KEY", "admin_default_key")
        existing_admin = await db_manager.get_api_key(admin_key)
        
        if not existing_admin:
            await db_manager.create_api_key(
                api_key=admin_key,
                client_name="Admin",
                rate_limit=1000,
                is_admin=True
            )
            logger.info("Created default admin API key")
        
        # Check if demo key exists
        demo_key = "demo_key_123"
        existing_demo = await db_manager.get_api_key(demo_key)
        
        if not existing_demo:
            await db_manager.create_api_key(
                api_key=demo_key,
                client_name="Demo Client",
                rate_limit=100,
                is_admin=False
            )
            logger.info("Created default demo API key")
            
    except Exception as e:
        logger.error(f"Error initializing default data: {e}")
        raise
