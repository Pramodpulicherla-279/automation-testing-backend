"""
jira_integration/mongo_config.py
────────────────────────────────
MongoDB configuration for storing Jira automation tickets.

Usage:
    from jira_integration.mongo_config import db, connect_mongodb, get_tickets_collection
"""

import os
import sys
import time
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from pymongo.errors import ServerSelectionTimeoutError
import logging

logger = logging.getLogger("uvicorn.error")

# ─────────────────────────────────────────────────────────────────────────────
# Robust .env loading — tries multiple locations so it works regardless of
# where the server is launched from.
# ─────────────────────────────────────────────────────────────────────────────
def _load_env() -> None:
    """
    Try loading .env from several candidate paths and stop at the first hit.
    Candidates (in priority order):
      1. Same directory as this file            → backend/jira_integration/.env  (unlikely)
      2. Parent of this file                    → backend/.env                   (most common)
      3. Parent of parent of this file          → project_root/.env
      4. Parent of parent / backend             → project_root/backend/.env
      5. Current working directory              → wherever uvicorn was launched from
    """
    _this_dir   = os.path.dirname(os.path.abspath(__file__))  # .../backend/jira_integration
    _backend    = os.path.dirname(_this_dir)                   # .../backend
    _proj_root  = os.path.dirname(_backend)                    # .../test-automation-platform

    candidates = [
        os.path.join(_backend,   ".env"),                      # backend/.env          ← correct
        os.path.join(_proj_root, "backend", ".env"),           # project/backend/.env
        os.path.join(_proj_root, ".env"),                      # project/.env
        os.path.join(os.getcwd(), ".env"),                     # cwd/.env
        os.path.join(_this_dir,  ".env"),                      # jira_integration/.env
    ]

    for path in candidates:
        if os.path.isfile(path):
            load_dotenv(dotenv_path=path, override=True)
            logger.debug("[MongoDB] Loaded .env from: %s", path)
            return

    # Last resort — let python-dotenv search upward from cwd
    load_dotenv(override=True)
    logger.warning("[MongoDB] Could not find .env in known locations; used default search.")


_load_env()


# ─────────────────────────────────────────────────────────────────────────────
# Config class
# ─────────────────────────────────────────────────────────────────────────────
class MongoDBConfig:
    """MongoDB configuration and connection management"""

    def __init__(self):
        self.mongo_uri = (os.getenv("MONGO_URI") or "").strip()
        self.db_name   = (os.getenv("MONGO_DB_NAME") or "jira_automation").strip()
        self.enabled   = (os.getenv("MONGO_ENABLED") or "true").lower() == "true"

        self.client = None
        self.db     = None

        # Debug — printed once at import time so you can see what was loaded
        _uri_preview = (
            self.mongo_uri[:40] + "..." if len(self.mongo_uri) > 40 else self.mongo_uri
        )
        print(
            f"[MongoDB] Config loaded | enabled={self.enabled} | "
            f"db={self.db_name} | uri={'(set) ' + _uri_preview if self.mongo_uri else '(NOT SET)'}"
        )

    def validate(self) -> bool:
        """Validate MongoDB configuration"""
        if not self.enabled:
            logger.info("[MongoDB] MongoDB integration disabled (MONGO_ENABLED=false)")
            return False

        if not self.mongo_uri:
            logger.warning(
                "[MongoDB] ⚠️ MONGO_URI not set. "
                "Add MONGO_URI=mongodb+srv://... to backend/.env and restart."
            )
            return False

        return True

    def connect(self) -> bool:
        """Connect to MongoDB with resilient timeout handling"""
        if not self.validate():
            return False

        try:
            logger.info("[MongoDB] Connecting to '%s'...", self.db_name)
            
            # ✅ FIX: Handle Windows SSL certificate issues
            # MongoDB Atlas requires valid SSL. On Windows with outdated certs,
            # disable verification as a workaround (will fix properly after)
            self.client = MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=30000,
                connectTimeoutMS=15000,
                socketTimeoutMS=30000,
                retryWrites=True,
                ssl=True,
                tlsAllowInvalidCertificates=True,  # ← Temporary workaround for Windows SSL
                tlsAllowInvalidHostnames=True,     # ← Allow hostname mismatch
            )

            logger.info("[MongoDB] Testing connection with ping...")
            self.client.admin.command("ping")

            self.db = self.client[self.db_name]
            logger.info("✅ [MongoDB] Connected successfully to '%s'", self.db_name)

            self._create_indexes()
            return True

        except ServerSelectionTimeoutError as e:
            logger.error(
                "[MongoDB] ❌ Connection timeout (30s) — MongoDB Atlas unreachable.\n"
                "   → SSL Certificate Issue (Windows)\n"
                "   → Run: pip install --upgrade certifi\n"
                "   → Error: %s", str(e)
            )
            return False
        except Exception as e:
            logger.error("[MongoDB] ❌ Connection error: %s", str(e))
            return False

    def _create_indexes(self):
        """Create database indexes for performance"""
        if self.db is None:
            return

        try:
            col = self.db["jira_tickets"]
            col.create_index([("issue_id",   ASCENDING)], unique=True, sparse=True)
            col.create_index([("ticket_id",  ASCENDING)], unique=True, sparse=True)
            col.create_index([("assignee",   ASCENDING)])
            col.create_index([("status",     ASCENDING)])
            col.create_index([("priority",   ASCENDING)])
            col.create_index([("module",     ASCENDING)])
            col.create_index([("created_at", ASCENDING)])
            col.create_index([("app_version", ASCENDING)])
            logger.info("[MongoDB] Indexes created/verified.")
        except Exception as e:
            logger.warning("[MongoDB] Warning creating indexes: %s", str(e))

    def disconnect(self):
        """Disconnect from MongoDB"""
        if self.client:
            self.client.close()
            logger.info("[MongoDB] Disconnected.")

    def get_collection(self, name: str):
        if self.db is None:  
           return None
        return self.db[name]
    
# ─────────────────────────────────────────────────────────────────────────────
# Singleton + public helpers
# ─────────────────────────────────────────────────────────────────────────────
mongo_config = MongoDBConfig()

# Auto-connect on module import
if mongo_config.enabled:
    mongo_config.connect()


def connect_mongodb() -> bool:
    """
    Public function to connect to MongoDB.
    Returns True if connection successful, False otherwise.
    """
    return mongo_config.connect()

def disconnect_mongodb() -> None:
    """Disconnect from MongoDB — call at app shutdown."""
    mongo_config.disconnect()


def get_tickets_collection():
    """Return the jira_tickets collection, or None if not connected."""
    return mongo_config.get_collection("jira_tickets")


def is_mongodb_enabled() -> bool:
    """True only when MongoDB is enabled AND actively connected."""
    return mongo_config.db is not None