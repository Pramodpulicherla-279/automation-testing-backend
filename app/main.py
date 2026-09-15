
import os
import asyncio
import sys
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.runner_client import RunnerUnavailable
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


# Device, Appium, APK, run and discovery endpoints go through the runner on the
# machine with the Android device. When it can't be used they answer 503 with the
# reason instead of a bare 500, and everything else keeps working.
@app.exception_handler(RunnerUnavailable)
async def runner_unavailable(request: Request, exc: RunnerUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# Origins must be listed explicitly: credentials are allowed, and the CORS spec
# forbids combining that with a "*" wildcard. Trailing slashes are stripped
# because browsers send the Origin header without one.
CORS_ALLOW_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CORS_ALLOW_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True, 
    allow_methods=["*"], 
    allow_headers=["*"],
)

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