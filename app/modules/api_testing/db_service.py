import os
from datetime import datetime
from typing import List, Optional, Dict, Any

from bson import ObjectId

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorDatabase,
    AsyncIOMotorCollection
)

from pymongo import ASCENDING, DESCENDING

from app.modules.api_testing.models import (
    TestScript,
    TestRun,
    Metric,
    APILog,
    TestScriptResponse,
    TestRunResponse,
    RunStatus
)

class Database:

    def __init__(self):

        self.mongo_url = os.getenv(
            "MONGO_URL",
            "mongodb://localhost:2717"
        )

        self.db_name = os.getenv(
            "MONGO_DB",
            "k6_testing"
        )

        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None

        self.scripts_collection: Optional[
            AsyncIOMotorCollection
        ] = None

        self.runs_collection: Optional[
            AsyncIOMotorCollection
        ] = None

        self.metrics_collection: Optional[
            AsyncIOMotorCollection
        ] = None

        self.logs_collection: Optional[
            AsyncIOMotorCollection
        ] = None

    async def connect(self):
        try:
            print(f"🔗 Connecting MongoDB: {self.mongo_url}")
            print(f"📦 Database: {self.db_name}")
    
            self.client = AsyncIOMotorClient(
                self.mongo_url,
                serverSelectionTimeoutMS=5000  # fail fast
            )
    
            # Force connection check
            await self.client.admin.command("ping")
    
            self.db = self.client[self.db_name]
    
            self.scripts_collection = self.db["test_scripts"]
            self.runs_collection = self.db["test_runs"]
            self.metrics_collection = self.db["test_metrics"]
            self.logs_collection = self.db["api_logs"]
    
            await self.create_indexes()
    
            print("✅ MongoDB connected")
    
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            self.client = None

    async def disconnect(self):

        if self.client:
            self.client.close()
            print("🔌 MongoDB disconnected")

    async def create_indexes(self):

        await self.scripts_collection.create_index(
            [("createdAt", DESCENDING)]
        )

        await self.runs_collection.create_index(
            [("startTime", DESCENDING)]
        )

        await self.logs_collection.create_index(
            [("timestamp", DESCENDING)]
        )

    # =====================================================
    # SCRIPTS
    # =====================================================

    async def create_script(
        self,
        script: TestScript
    ) -> str:

        result = await self.scripts_collection.insert_one(
            script.dict()
        )

        return str(result.inserted_id)

    async def get_script(
        self,
        script_id: str
    ) -> Optional[TestScriptResponse]:

        try:

            doc = await self.scripts_collection.find_one(
                {
                    "_id": ObjectId(script_id)
                }
            )

            if not doc:
                return None

            doc["id"] = str(doc["_id"])
            del doc["_id"]

            return TestScriptResponse(**doc)

        except Exception as e:

            print(f"❌ get_script error: {e}")

            return None

    async def list_scripts(
        self,
        limit: int = 100,
        skip: int = 0
    ):

        try:

            count = await self.scripts_collection.count_documents({})

            cursor = (
                self.scripts_collection
                .find({})
                .sort("createdAt", DESCENDING)
                .skip(skip)
                .limit(limit)
            )

            docs = await cursor.to_list(
                length=limit
            )

            scripts = []

            for doc in docs:

                doc["id"] = str(doc["_id"])
                del doc["_id"]

                scripts.append(
                    TestScriptResponse(**doc)
                )

            return scripts, count

        except Exception as e:

            print(f"❌ list_scripts error: {e}")

            return [], 0

    async def update_script(
        self,
        script_id: str,
        script: TestScript
    ) -> bool:

        try:

            data = script.dict()

            data["updatedAt"] = datetime.utcnow()

            result = await self.scripts_collection.update_one(
                {
                    "_id": ObjectId(script_id)
                },
                {
                    "$set": data
                }
            )

            return result.modified_count > 0

        except Exception as e:

            print(f"❌ update_script error: {e}")

            return False

    async def delete_script(
        self,
        script_id: str
    ) -> bool:

        try:

            result = await self.scripts_collection.delete_one(
                {
                    "_id": ObjectId(script_id)
                }
            )

            return result.deleted_count > 0

        except Exception as e:

            print(f"❌ delete_script error: {e}")

            return False

    # =====================================================
    # RUNS
    # =====================================================

    async def create_run(
        self,
        run: TestRun
    ) -> str:

        result = await self.runs_collection.insert_one(
            run.dict()
        )

        return str(result.inserted_id)

    async def get_run(
        self,
        run_id: str
    ) -> Optional[TestRunResponse]:

        try:

            doc = await self.runs_collection.find_one(
                {
                    "_id": ObjectId(run_id)
                }
            )

            if not doc:
                return None

            doc["_id"] = str(doc["_id"])

            return TestRunResponse(**doc)

        except Exception as e:

            print(f"❌ get_run error: {e}")

            return None

    async def list_runs(
        self,
        script_id: Optional[str] = None,
        limit: int = 50,
        skip: int = 0
    ):

        try:

            query = {}

            if script_id:
                query["scriptId"] = script_id

            count = await self.runs_collection.count_documents(
                query
            )

            cursor = (
                self.runs_collection
                .find(query)
                .sort("startTime", DESCENDING)
                .skip(skip)
                .limit(limit)
            )

            docs = await cursor.to_list(
                length=limit
            )

            runs = []

            for doc in docs:

                doc["_id"] = str(doc["_id"])

                runs.append(
                    TestRunResponse(**doc)
                )

            return runs, count

        except Exception as e:

            print(f"❌ list_runs error: {e}")

            return [], 0

    async def update_run_status(
        self,
        run_id: str,
        status: RunStatus,
        summary: Optional[Dict] = None
    ) -> bool:

        try:

            data = {
                "status": status.value
            }

            if summary:
                data["summary"] = summary

            if status == RunStatus.COMPLETED:
                data["endTime"] = datetime.utcnow()

            result = await self.runs_collection.update_one(
                {
                    "_id": ObjectId(run_id)
                },
                {
                    "$set": data
                }
            )

            return result.modified_count > 0

        except Exception as e:

            print(
                f"❌ update_run_status error: {e}"
            )

            return False

    async def delete_run(
        self,
        run_id: str
    ) -> bool:

        try:

            await self.runs_collection.delete_one(
                {
                    "_id": ObjectId(run_id)
                }
            )

            await self.metrics_collection.delete_many(
                {
                    "runId": run_id
                }
            )

            await self.logs_collection.delete_many(
                {
                    "run_id": run_id
                }
            )

            return True

        except Exception as e:

            print(f"❌ delete_run error: {e}")

            return False

    # =====================================================
    # LOGS
    # =====================================================

    async def save_log(
        self,
        log: APILog
    ):

        await self.logs_collection.insert_one(
            log.dict()
        )

    async def get_logs(
        self,
        run_id: Optional[str] = None,
        limit: int = 200
    ):

        query = {}

        if run_id:
            query["run_id"] = run_id

        cursor = (
            self.logs_collection
            .find(query)
            .sort("timestamp", DESCENDING)
            .limit(limit)
        )

        docs = await cursor.to_list(
            length=limit
        )

        return [
            APILog(**doc)
            for doc in docs
        ]

    # =====================================================
    # METRICS
    # =====================================================

    async def get_metrics(
        self,
        run_id: str
    ):

        cursor = self.metrics_collection.find(
            {
                "runId": run_id
            }
        )

        docs = await cursor.to_list(
            length=10000
        )

        return [
            Metric(**doc)
            for doc in docs
        ]


db = Database()

