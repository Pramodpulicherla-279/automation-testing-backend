"""
FastAPI routes for:
- Test script management (create, read, update, delete)
- Test run management (create, get results)
- API logs and metrics
- Live monitoring
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional
from app.modules.api_testing.models import (
    APILog, CreateScriptRequest, UpdateScriptRequest, StartRunRequest,
    TestScript, TestRun, RunStatus,
    MessageResponse, ErrorResponse,
    ScriptsListResponse, RunsListResponse, RunDetailResponse, Metric
)
from app.modules.api_testing.db_service import db
from app.modules.api_testing.service import run_api_test_flow, save_api_log, get_api_logs
import asyncio

router = APIRouter()


# ============================================================================
# Test Scripts Endpoints
# ============================================================================

@router.post("/scripts/create", response_model=dict)
async def create_script(request: CreateScriptRequest):
    """
    Save a new K6 test script to database
    
    Frontend calls this when user clicks "Save Script" button
    
    Payload:
    ```json
    {
      "name": "Payment API Load Test",
      "description": "Testing payment endpoint under load",
      "script": "import http from 'k6/http'...",
      "config": {
        "baseUrl": "http://localhost:8000",
        "stages": [...],
        "endpoints": [...]
      }
    }
    ```
    """
    try:
        # Create TestScript model
        script = TestScript(
            name=request.name,
            # description=request.description,
            script=request.script,
            config=request.config
        )
        
        # Save to MongoDB
        script_id = await db.create_script(script)
        print(f"✅ Script saved: {script_id} - {request.name}")
        
        return {
            "status": "success",
            "id": script_id,
            "message": f"Script '{request.name}' saved successfully"
        }
    
    except Exception as e:
        print(f"❌ Error creating script: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to save script: {str(e)}"
        )


@router.get("/scripts", response_model=ScriptsListResponse)
async def list_scripts(skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):


    """
    List all saved K6 test scripts
    
    Supports pagination. Returns scripts sorted by newest first.
    
    Query params:
    - skip: Number of records to skip (default: 0)
    - limit: Number of records to return (default: 100, max: 500)
    
    Response:
    ```json
    {
      "scripts": [
        {
          "id": "507f1f77bcf86cd799439011",
          "name": "Payment API Load Test",
          "description": "Testing payment endpoint",
          "script": "import http...",
          "config": {...},
          "createdAt": "2024-01-15T10:30:00Z",
          "updatedAt": "2024-01-15T10:30:00Z"
        }
      ],
      "count": 42
    }
    ```
    """
    try:
        scripts, count = await db.list_scripts(limit=limit, skip=skip)
        return ScriptsListResponse(scripts=scripts, count=count)
    
    except Exception as e:
        print(f"❌ Error listing scripts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch scripts: {str(e)}"
        )


@router.get("/scripts/{script_id}")
async def get_script(script_id: str):
    """
    Get single script by ID
    
    Used when user loads a previous script to edit or run
    """
    try:
        script = await db.get_script(script_id)
        if not script:
            raise HTTPException(
                status_code=404,
                detail=f"Script not found: {script_id}"
            )
        return script
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching script: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/scripts/{script_id}")
async def update_script(script_id: str, request: UpdateScriptRequest):
    """
    Update existing script
    
    Allows user to modify saved script details
    """
    try:
        # Check if script exists
        existing = await db.get_script(script_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Script not found")
        
        # Build update (only non-null fields)
        update_data = {}
        if request.name is not None:
            update_data["name"] = request.name
        # if request.description is not None:
        #     update_data["description"] = request.description
        if request.script is not None:
            update_data["script"] = request.script
        if request.config is not None:
            update_data["config"] = request.config
        
        # Create updated script
        updated_script = TestScript(
            name=update_data.get("name", existing.name),
            # description=update_data.get("description", existing.description),
            script=update_data.get("script", existing.script),
            config=update_data.get("config", existing.config)
        )
        
        success = await db.update_script(script_id, updated_script)
        
        if success:
            return MessageResponse(message="Script updated successfully")
        else:
            raise HTTPException(status_code=500, detail="Failed to update script")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error updating script: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/scripts/{script_id}")
async def delete_script(script_id: str):
    """
    Delete script
    
    Also deletes associated runs and their metrics/logs
    """
    try:
        success = await db.delete_script(script_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Script not found")
        
        # Delete associated runs
        runs, _ = await db.list_runs(script_id=script_id, limit=1000)
        for run in runs:
            await db.delete_run(run.id)
        
        return MessageResponse(message="Script and associated runs deleted")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting script: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Test Runs Endpoints
# ============================================================================

@router.post("/runs/start")
async def start_test_run(request: StartRunRequest):
    """
    Start a new K6 test run
    
    Frontend calls this when user clicks "Start Test" button
    
    Payload:
    ```json
    {
      "scriptId": "507f1f77bcf86cd799439011",
      "scriptName": "Payment API Load Test"
    }
    ```
    
    This endpoint:
    1. Creates run record in database
    2. Starts K6 execution in background
    3. Returns run ID for progress tracking
    
    Response:
    ```json
    {
      "status": "started",
      "run_id": "507f1f77bcf86cd799439012",
      "message": "Test started, check logs"
    }
    ```
    """
    try:
        print(f"🔥 Starting test run for script: {request.scriptId}")
        
        # Start K6 execution in background (async, non-blocking)
        # The run_api_test_flow will handle:
        # 1. Creating run record
        # 2. Executing K6
        # 3. Updating status
        # 4. Storing results
        asyncio.create_task(
            run_api_test_flow(request.scriptId, request.scriptName or "Unknown")
        )
        
        return {
            "status": "started",
            "message": "Test execution started. Check runs list for progress."
        }
    
    except Exception as e:
        print(f"❌ Error starting test run: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start test: {str(e)}"
        )


@router.get("/runs")
async def list_runs(script_id: Optional[str] = None, skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
    """
    List test runs
    
    Optionally filtered by script_id. Shows history of test executions.
    
    Query params:
    - script_id: Optional filter by script
    - skip: Pagination offset
    - limit: Number of records
    
    Response: List of runs with status, duration, summary
    """
    try:
        runs, count = await db.list_runs(script_id=script_id, skip=skip, limit=limit)
        return RunsListResponse(runs=runs, count=count)
    
    except Exception as e:
        print(f"❌ Error listing runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}")
async def get_run_details(run_id: str):
    """
    Get full run details with metrics and logs
    
    When user clicks on a run in history, show them:
    - Run metadata (start/end time, duration)
    - Performance summary (avg response time, p95, etc)
    - Detailed metrics (response time trends)
    - API logs from that run
    
    This is the "detailed view" of a historical test run
    """
    try:
        # Get run
        run = await db.get_run(run_id)
        if not run:
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        
        # Get logs for this run
        logs = await get_api_logs(run_id=run_id)
        
        # Get metrics for this run
        metrics = await db.get_metrics(run_id)
        
        # Build response
        response = RunDetailResponse(
            **run.dict(),
            logs=logs,
            metrics=metrics
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/metrics")
async def get_run_metrics(run_id: str, metric_name: Optional[str] = None):
    """
    Get detailed metrics for a run
    
    Optionally filter by metric name (http_req_duration, http_req_failed, etc)
    """
    try:
        metrics = await db.get_metrics(run_id=run_id, metric_name=metric_name)
        
        # Get aggregated stats
        summary = await db.get_run_metrics_summary(run_id)
        
        return {
            "metrics": metrics,
            "summary": summary
        }
    
    except Exception as e:
        print(f"❌ Error fetching metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    """
    Delete test run and all associated data
    """
    try:
        success = await db.delete_run(run_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Run not found")
        
        return MessageResponse(message="Run deleted successfully")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting run: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# API Logs Endpoints
# ============================================================================

@router.post("/logs")
async def add_log(log: APILog):
    """
    Save API log
    
    Called by mitmproxy script after each API call
    
    Payload:
    ```json
    {
      "method": "GET",
      "endpoint": "/api/health",
      "url": "http://localhost:8000/api/health",
      "status": 200,
      "response_time_ms": 5.2,
      "timestamp": "10:30:45.123"
    }
    ```
    """
    try:
        success = await save_api_log(log)
        if success:
            return MessageResponse(message="Log saved")
        else:
            raise HTTPException(status_code=500, detail="Failed to save log")
    
    except Exception as e:
        print(f"❌ Error saving log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logs/batch")
async def add_logs_batch(logs: list = Body(...)):
    """
    Save multiple logs at once
    
    More efficient than calling /logs multiple times
    """
    try:
        api_logs = [APILog(**log) for log in logs]
        count = await db.save_logs_batch(api_logs)
        
        return {
            "message": "Logs saved",
            "count": count
        }
    
    except Exception as e:
        print(f"❌ Error saving logs batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def fetch_logs(run_id: Optional[str] = None, limit: int = Query(200, ge=1, le=1000)):
    """
    Get API logs
    
    Optionally filtered by run_id
    
    Query params:
    - run_id: Optional filter by specific run
    - limit: Number of records (default: 200, max: 1000)
    """
    try:
        logs = await get_api_logs(run_id=run_id, limit=limit)
        return {
            "logs": logs,
            "count": len(logs)
        }
    
    except Exception as e:
        print(f"❌ Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health Check
# ============================================================================

# @router.get("/health")
# async def health_check():
#     """
#     Health check endpoint
    
#     Verifies backend is running and database is connected
#     """
#     try:
#         # Try a simple database operation
#         scripts, count = await db.list_scripts(limit=1)
        
#         return {
#             "status": "healthy",
#             "database": "connected",
#             "message": "API testing service is running"
#         }
    
#     except Exception as e:
#         print(f"⚠️  Health check failed: {e}")
#         return {
#             "status": "unhealthy",
#             "database": "disconnected",
#             "error": str(e)
#         }