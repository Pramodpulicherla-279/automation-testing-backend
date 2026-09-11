
import os
import asyncio
import sys
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.paths import APK_ICON_DIR, ensure_apk_dirs
from app.modules.test_runner.routes import router as test_router
from app.modules.jira.routes import router as jira_router
from app.modules.llm.routes import router as llm_router
from app.modules.api_testing.routes import router as api_testing_router
from app.core.websocket import router as websocket_router
from app.modules.slack.routes import router as slack_router
from app.modules.network_simulate.routes import router as network_simulate_router
from app.modules.test_management.routes import router as test_management_router
from app.core.events import lifespan

if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

app = FastAPI(
    title="Testing Platform API",
    version="1.0.0",
    lifespan=lifespan
)

# app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

# Icons are extracted from APKs into the runtime data dir, outside the repo;
# this is what makes the /static/icons/… URLs handed to the UI resolvable.
ensure_apk_dirs()
app.mount("/static/icons", StaticFiles(directory=APK_ICON_DIR), name="apk-icons")

app.include_router(websocket_router, prefix="/ws")
app.include_router(test_router, prefix="/test")
app.include_router(test_management_router, prefix="/api")
# app.include_router(jira_router, prefix="/jira")
# app.include_router(llm_router, prefix="/llm")
# app.include_router(slack_router, prefix="/slack")
# app.include_router(api_testing_router, prefix="/api-testing")
# app.include_router(network_simulate_router, prefix="/network-simulate")

# Health Check

@app.get("/")
async def root():
    return {
        "status": "running",
        "service": "Testing Platform API"
    }

# ── Windows asyncio subprocess fix ──────────────────────────────────────────
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
 
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)