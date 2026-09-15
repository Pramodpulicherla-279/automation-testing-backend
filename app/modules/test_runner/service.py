"""Test-run orchestration.

Everything that touches the Android device, Appium, APK files or the suite runs
on the laptop's test runner, which keeps a WebSocket open to this backend
(app/core/runner_hub.py). This service holds no files or tools of its own, so it
can run anywhere, including a cloud host.
"""

import json

import requests
from fastapi import HTTPException

from app.core.constants import SLACK_NOTIFY_CHANNEL
from app.core.events import broadcast_async
from app.core.logger import logger
from app.core.runner_hub import DOWNLOAD_TIMEOUT, RunnerUnavailable, hub
from app.core.state import PAYLOAD_PREFIXES, current_test_name, reset_run_state, runs, test_steps_store
from app.core.utils import parse_step_from_message
from app.core.websocket import manager
from app.modules.jira.jira_config import config as jira_config
from app.modules.slack.config import APP_DEVELOPER_MAP, APP_VARIANTS
from app.modules.slack.service import detect_app_variant, new_run, notify_run_finished, start_remote_run

latest_run_id = None


async def log_step_flow(msg):
    global test_steps_store, current_test_name

    message = msg.message

    # ── Test context switch ──────────────────────────────────────────────
    if "[TEST_START:" in message:
        try:
            new_test = message.split("[TEST_START:")[1].split("]")[0].strip()
            if new_test and new_test != current_test_name:
                current_test_name = new_test
                test_steps_store.setdefault(current_test_name, [])
                print(f"🔄 Test context switched → {current_test_name}")
        except Exception as e:
            print(f"❌ TEST_START parse warning: {e}")

    # ── Step capture (all patterns) ──────────────────────────────────────
    try:
        bucket = (
            message.split("[TEST:")[1].split("]")[0].strip()
            if "[TEST:" in message else current_test_name
        )
        step = parse_step_from_message(message)
        if step:
            test_steps_store.setdefault(bucket, [])
            if step not in test_steps_store[bucket]:
                test_steps_store[bucket].append(step)
                print(f"✅ Step captured → {bucket}: {step}")
    except Exception as e:
        print(f"❌ Step capture warning: {e}")

    # ── Payload prefix handling ──────────────────────────────────────────
    for prefix in PAYLOAD_PREFIXES:
        if message.startswith(prefix):
            raw = message[len(prefix):].strip()
            try:
                payload = json.loads(raw)
                steps = payload.get('steps_executed') or []
                clean_line = (f"[PAYLOAD] {payload.get('issue_id','')} | "
                              f"{payload.get('module','?')} | {payload.get('test_name','?')} | "
                              f"Steps ({len(steps)}): {', '.join(steps[:3]) if steps else 'none'}")
                broadcast_async({"type": "LOG", "payload": {"message": clean_line, "status": "PAYLOAD"}})
            except Exception as exc:
                logger.warning("Failed to parse payload: %s", exc)
            return {"status": "ok"}

    broadcast_async({"type": "LOG", "payload": {"message": message, "status": msg.status}})
    return {"status": "ok"}


# ── Device / Appium / APKs ──────────────────────────────────────────────────
# The UI polls the two status endpoints every few seconds. They answer from the
# runner's latest heartbeat instead of a round trip, and read as "no device" /
# "stopped" while no runner is connected.

async def device_status_flow():
    status = hub.heartbeat() or {}
    return {"connected": bool(status.get("device_connected"))}


async def appium_status_flow():
    status = hub.heartbeat() or {}
    return {"status": status.get("appium", "stopped")}


async def appium_start_flow():
    return await hub.request("appium_start", timeout=30)


async def appium_stop_flow():
    return await hub.request("appium_stop", timeout=30)


async def list_apks_flow():
    # Loaded when the page opens: with the runner offline that is an empty list, not an error.
    try:
        return await hub.request("list_apks")
    except RunnerUnavailable:
        return {"apks": []}


async def module_status_flow(data: dict):
    module = data.get("module")
    status = data.get("status")

    # Special signal: new run starting — broadcast RUN_START so frontend clears
    if module == "__RUN_START__":
        broadcast_async({"type": "RUN_START", "payload": {}})
    else:

        broadcast_async({"type": "MODULE", "payload": {
            "module": module, "status": status, "message": data.get("message", "")
        }})
    return {"status": "ok"}


# ── Starting runs ───────────────────────────────────────────────────────────

def _begin_run(request) -> str:
    global latest_run_id
    reset_run_state()
    run_id = latest_run_id = new_run()
    runs[run_id]["network_config"] = getattr(request, "network_config", None)
    return run_id


async def _start_on_runner(request, run_id: str, prepared: dict, message: str) -> dict:
    """Resolve what to run from the APK the runner prepared, then start it there."""
    info = prepared.get("info") or {}
    app_name = info.get("app_name")
    app_version = info.get("app_version")
    package_name = info.get("package_name")

    # Prefer the role picked in the UI: the unified app ships every role in one
    # package, so the package name alone can't tell them apart.
    app_variant = getattr(request, "app_type", None) or detect_app_variant(package_name, app_name)
    tests_to_run = request.tests_to_run or APP_VARIANTS.get(app_variant, [])
    if not tests_to_run:
        raise HTTPException(
            status_code=400,
            detail=f"No test scripts configured for variant '{app_variant}'.",
        )
    developer_name = APP_DEVELOPER_MAP.get(app_variant, "Unknown Developer")

    runs[run_id].update(
        app_name=app_name or "",
        app_version=app_version or "",
        package_name=package_name or "",
        app_variant=app_variant or "",
        developer_name=developer_name or "",
    )
    await manager.broadcast({"type": "LOG", "payload": {
        "message": f"Detected app variant: {app_variant}", "status": "INFO",
    }})

    await start_remote_run(
        run_id=run_id,
        apk_name=prepared["apk_name"],
        tests_to_run=tests_to_run,
        app_name=app_name,
        app_version=app_version,
        developer_name=developer_name,
        channel_id=SLACK_NOTIFY_CHANNEL,
        app_type=app_variant,
        login_phone=getattr(request, "login_phone", None),
        login_mpin=getattr(request, "login_mpin", None),
        test_types=getattr(request, "test_types", None),
    )

    return {
        "status": "success",
        "message": message,
        "run_id": run_id,
        "app_icon": prepared.get("icon"),
        "apk_path": prepared["apk_name"],
        **info,
        "app_name": app_name,
        "package_name": package_name,
        "app_variant": app_variant,
        "app_version": app_version,
        "tests_to_run": tests_to_run,
    }


async def start_test_flow(request):
    run_id = _begin_run(request)
    await manager.broadcast({"type": "LOG", "payload": {
        "message": "Downloading the APK on the runner...", "status": "INFO",
    }})
    try:
        prepared = await hub.request("prepare_apk", {"url": request.url}, timeout=DOWNLOAD_TIMEOUT)
    except HTTPException as exc:
        await manager.broadcast({"type": "LOG", "payload": {
            "message": f"Download interrupted: {exc.detail}", "status": "FAILED",
        }})
        raise
    return await _start_on_runner(request, run_id, prepared, "APK downloaded. Test starting...")


async def start_test_existing_flow(request):
    run_id = _begin_run(request)
    # Reading the APK's manifest and icon on the runner takes a few seconds.
    prepared = await hub.request("prepare_apk", {"apk_name": request.apk_name}, timeout=120)
    await manager.broadcast({"type": "RUN_START", "payload": {}})
    await manager.broadcast({"type": "LOG", "payload": {
        "message": f"Using existing APK: {request.apk_name}", "status": "INFO",
    }})
    return await _start_on_runner(request, run_id, prepared, "Using existing APK. Test starting...")


# ── Stopping / reporting ────────────────────────────────────────────────────

async def stop_test_flow() -> bool:
    result = await hub.request("stop_run", timeout=15)
    return bool(result.get("stopped"))


async def allure_start_flow():
    return await hub.request("allure_start", timeout=30)


async def run_complete_flow(event):
    await manager.broadcast({"type": "RUN_COMPLETE", "payload": {"report_url": event.report_url}})
    return {"ok": True}


async def api_generate_report_flow():
    return await hub.request("generate_report", timeout=30)


async def _on_run_finished(payload: dict) -> None:
    await notify_run_finished(
        payload.get("run_id", ""),
        passed=int(payload.get("passed") or 0),
        failed=int(payload.get("failed") or 0),
        stopped=bool(payload.get("stopped")),
        error=payload.get("error"),
    )


# The runner reports the end of a run over its connection, which is what
# authenticates it — no separate callback URL or token needed.
hub.on_event("run-finished", _on_run_finished)


def jira_assignee_name_flow() -> dict:
    """Display name of the configured Jira assignee.

    Resolved here so the laptop needs no Jira credentials; the suite records it
    as who triggered the run.
    """
    if not (jira_config.assignee_id and jira_config.url and jira_config.email and jira_config.api_token):
        return {"name": ""}
    try:
        resp = requests.get(
            f"{jira_config.url}/rest/api/3/user",
            params={"accountId": jira_config.assignee_id},
            auth=jira_config.auth,
            headers={"Accept": "application/json"},
            timeout=8,
        )
    except requests.RequestException as exc:
        logger.warning("Jira assignee lookup failed: %s", exc)
        return {"name": ""}
    return {"name": (resp.json() or {}).get("displayName", "") if resp.ok else ""}
