from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.core import runner_client
from .models import TestRequest, ExistingTestRequest, RunCompleteEvent, RunFinishedEvent, LogMessage
from .service import start_test_flow, stop_test_flow, start_test_existing_flow, list_apks_flow, appium_start_flow, appium_status_flow, appium_stop_flow, allure_start_flow, device_status_flow, run_complete_flow, module_status_flow, api_generate_report_flow, log_step_flow, runner_run_finished_flow

router = APIRouter()


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
async def start_test(request: TestRequest):
    return await start_test_flow(request)

@router.post("/start-test-existing")
async def start_test_existing(request: ExistingTestRequest):
    return await start_test_existing_flow(request)

@router.get("/apk-list")
async def list_apks():
    return await list_apks_flow()

@router.post("/stop-test")
async def stop_test():
    stopped = await stop_test_flow()

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


@router.post("/runner/run-finished")
async def runner_run_finished(
    event: RunFinishedEvent,
    background_tasks: BackgroundTasks,
    x_runner_token: str = Header(default=""),
):
    # Only the runner may report results: they trigger the Slack summary.
    if not runner_client.is_runner_token(x_runner_token):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Runner-Token")
    background_tasks.add_task(runner_run_finished_flow, event)
    return {"ok": True}
