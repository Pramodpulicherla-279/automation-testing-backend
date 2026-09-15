import asyncio
from contextlib import asynccontextmanager
from app.core.websocket import manager
from app.modules.api_testing.db_service import db
from app.core.logger import setup_logger
from app.core.state import state

logger = setup_logger()

def broadcast_async(message: dict) -> None:
    try:
        asyncio.create_task(manager.broadcast(message))
    except RuntimeError:
        pass

@asynccontextmanager
async def lifespan(app):

    logger.info("🚀 Starting application")

    try:
        await db.connect()
        state.db_connected = True

        logger.info("✅ MongoDB connected")

    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    yield

    logger.info("🛑 Shutting down application")

    try:
        await db.disconnect()
        state.db_connected = False

        logger.info("✅ MongoDB disconnected")

    except Exception as e:
        logger.error(f"Shutdown error: {e}")