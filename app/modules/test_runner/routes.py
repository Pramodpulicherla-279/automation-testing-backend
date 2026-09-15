from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from .models import TestRequest, ExistingTestRequest, RunCompleteEvent, LogMessage
from .service import start_test_flow, stop_test_flow, start_test_existing_flow, list_apks_flow, appium_start_flow, appium_status_flow, appium_stop_flow, allure_start_flow, device_status_flow, run_complete_flow, module_status_flow, api_generate_report_flow, log_step_flow, jira_assignee_name_flow

router = APIRouter()

# `runner` names the laptop to act on; it may be omitted while only one is connected.


@router.post("/log-step")
async def log_step(msg: LogMessage):
    await log_step_flow(msg)
    return {"status": "logged"}

@router.get("/device-status")
async def device_status(runner: Optional[str] = None):
    return await device_status_flow(runner)

@router.post("/appium/start")
async def appium_start(runner: Optional[str] = None):
    return await appium_start_flow(runner)

@router.get("/appium/status")
async def appium_status(runner: Optional[str] = None):
    return await appium_status_flow(runner)

@router.post("/appium/stop")
async def appium_stop(runner: Optional[str] = None):
    return await appium_stop_flow(runner)

@router.post("/module-status")
async def module_status(data: dict):
    return await module_status_flow(data)

@router.post("/start-test")
async def start_test(request: TestRequest):
    return await start_test_flow(request)

@router.post("/start-test-existing")
async def start_test_existing(request: ExistingTestRequest):
    return await start_test_existing_flow(request)

@router.get("/apk-list")
async def list_apks(runner: Optional[str] = None):
    return await list_apks_flow(runner)

@router.post("/stop-test")
async def stop_test(runner: Optional[str] = None):
    stopped = await stop_test_flow(runner)

    if stopped:
        return {"status": "stopped"}
    return {"status": "no-process"}

@router.post("/allure/start")
async def allure_start(runner: Optional[str] = None):
    return await allure_start_flow(runner)

@router.post("/run-complete")
async def run_complete(event: RunCompleteEvent):
    return await run_complete_flow(event)

@router.post("/generate-report")
async def generate_report(runner: Optional[str] = None):
    return await api_generate_report_flow(runner)


# The suite asks for this instead of holding Jira credentials on the laptop.
@router.get("/jira/assignee-name")
def jira_assignee_name():
    return jira_assignee_name_flow()
