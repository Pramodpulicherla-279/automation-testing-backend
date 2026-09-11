import asyncio
from contextlib import asynccontextmanager
from app.core.websocket import manager
from app.modules.api_testing.db_service import db
from app.core.logger import setup_logger
from app.core.state import state
from app.core.utils import ensure_adb_server

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

    if await asyncio.to_thread(ensure_adb_server):
        logger.info("✅ adb server ready for device detection")
    else:
        logger.warning("⚠️ adb server could not be started; check that platform-tools is installed")

    yield

    logger.info("🛑 Shutting down application")

    try:
        await db.disconnect()
        state.db_connected = False

        logger.info("✅ MongoDB disconnected")

    except Exception as e:
        logger.error(f"Shutdown error: {e}")