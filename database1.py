import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, DateTime, Boolean, Text, JSON, select, update, delete
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

# Database Configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://postgres:password@localhost:5432/nepse_mcp"
)

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

# Database Models
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
    
    watchlists: Mapped[List["Watchlist"]] = relationship("Watchlist", back_populates="api_key_obj")

class Watchlist(Base):
    __tablename__ = "watchlists"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    api_key_id: Mapped[str] = mapped_column(String(255), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
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

# Database Operations
class DatabaseManager:
    def __init__(self):
        self.session_factory = AsyncSessionLocal
        self._is_connected = False
    
    async def is_connected(self) -> bool:
        """Check if database is connected"""
        return self._is_connected
    
    async def init_database(self):
        """Initialize database tables"""
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            self._is_connected = True
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    async def close(self):
        """Close database connections"""
        await engine.dispose()
        self._is_connected = False
        logger.info("Database connections closed")
    
    async def create_api_key(
        self, 
        api_key: str, 
        client_name: str, 
        rate_limit: int = 100, 
        is_admin: bool = False
    ) -> bool:
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
                logger.info(f"Created API key for {client_name}")
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error creating API key: {e}")
                return False
    
    async def get_api_key(self, api_key: str) -> Optional[APIKey]:
        """Get API key details"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(
                    select(APIKey).where(APIKey.api_key == api_key, APIKey.is_active == True)
                )
                return result.scalar_one_or_none()
            except SQLAlchemyError as e:
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
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error updating API key usage: {e}")
                return False
    
    async def list_api_keys(self) -> List[Dict[str, Any]]:
        """List all API keys with basic info"""
        async with self.session_factory() as session:
            try:
                result = await session.execute(select(APIKey))
                keys = result.scalars().all()
                return [{
                    "api_key": key.api_key,
                    "client_name": key.client_name,
                    "rate_limit": key.rate_limit,
                    "requests_made": key.requests_made,
                    "is_admin": key.is_admin,
                    "last_used": key.last_used.isoformat() if key.last_used else None,
                    "created_at": key.created_at.isoformat()
                } for key in keys]
            except SQLAlchemyError as e:
                logger.error(f"Error listing API keys: {e}")
                return []
    
    async def revoke_api_key(self, api_key: str) -> bool:
        """Revoke an API key"""
        async with self.session_factory() as session:
            try:
                await session.execute(
                    update(APIKey)
                    .where(APIKey.api_key == api_key)
                    .values(is_active=False)
                )
                await session.commit()
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error revoking API key: {e}")
                return False
    
    async def add_to_watchlist(self, api_key: str, symbol: str) -> bool:
        """Add symbol to watchlist"""
        async with self.session_factory() as session:
            try:
                existing = await session.execute(
                    select(Watchlist).where(
                        Watchlist.api_key_id == api_key,
                        Watchlist.symbol == symbol.upper()
                    )
                )
                if existing.scalar_one_or_none():
                    return False
                
                watchlist_item = Watchlist(
                    api_key_id=api_key,
                    symbol=symbol.upper()
                )
                session.add(watchlist_item)
                await session.commit()
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error adding to watchlist: {e}")
                return False
    
    async def remove_from_watchlist(self, api_key: str, symbol: str) -> bool:
        """Remove symbol from watchlist"""
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
            except SQLAlchemyError as e:
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
            except SQLAlchemyError as e:
                logger.error(f"Error getting watchlist: {e}")
                return []
    
    async def log_request(
        self, 
        api_key: str, 
        endpoint: str, 
        method: str, 
        status_code: int,
        response_time_ms: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Log API request"""
        async with self.session_factory() as session:
            try:
                log_entry = RequestLog(
                    api_key_id=api_key,
                    endpoint=endpoint,
                    method=method,
                    status_code=status_code,
                    response_time_ms=response_time_ms,
                    error_message=error_message
                )
                session.add(log_entry)
                await session.commit()
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Error logging request: {e}")
                return False

# Global database manager instance
db_manager = DatabaseManager()

# Initialization
async def init_default_data():
    """Initialize default API keys"""
    admin_key = os.getenv("ADMIN_API_KEY")
    if admin_key:
        existing = await db_manager.get_api_key(admin_key)
        if not existing:
            await db_manager.create_api_key(
                api_key=admin_key,
                client_name="Admin",
                rate_limit=1000,
                is_admin=True
            )
            logger.info("Created default admin API key")