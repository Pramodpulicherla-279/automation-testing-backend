from fastapi import APIRouter, BackgroundTasks, HTTPException
from .models import TestRequest, ExistingTestRequest, RunCompleteEvent, LogMessage
from .service import start_test_flow, stop_test_flow, start_test_existing_flow, list_apks_flow, appium_start_flow, appium_status_flow, appium_stop_flow, allure_start_flow, device_status_flow, run_complete_flow, module_status_flow, api_generate_report_flow, log_step_flow

router = APIRouter()


# You must import your existing manager
from app.core.websocket import manager   

@router.post("/log-step")
async def log_step(msg: LogMessage):
    await log_step_flow(msg)
    return {"status": "logged"}

@router.get("/device-status")
async def device_status():
    return await device_status_flow()

@router.post("/appium/start")
async def appium_start():
    return await appium_start_flow()

@router.get("/appium/status")
async def appium_status():
    return await appium_status_flow()

@router.post("/appium/stop")
async def appium_stop():
    return await appium_stop_flow()

@router.post("/module-status")
async def module_status(data: dict):
    return await module_status_flow(data)

@router.post("/start-test")
async def start_test(request: TestRequest, background_tasks: BackgroundTasks):
    return await start_test_flow(request, background_tasks, manager)

@router.post("/start-test-existing")
async def start_test_existing(request: ExistingTestRequest, background_tasks: BackgroundTasks):
    return await start_test_existing_flow(request, background_tasks, manager)

@router.get("/apk-list")
async def list_apks():
    return await list_apks_flow()

@router.post("/stop-test")
async def stop_test():
    stopped = stop_test_flow(manager)

    if stopped:
        return {"status": "stopped"}
    return {"status": "no-process"}

@router.post("/allure/start")
async def allure_start():
    return await allure_start_flow()

@router.post("/run-complete")
async def run_complete(event: RunCompleteEvent):
    return await run_complete_flow(event)

@router.post("/generate-report")
async def generate_report():
    return await api_generate_report_flow()
