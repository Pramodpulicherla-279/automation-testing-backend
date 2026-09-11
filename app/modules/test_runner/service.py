import os
import sys
import asyncio
import subprocess
import json
import socket
import threading
from fastapi.responses import JSONResponse
from typing import Dict, List
# import core.state as state
from app.core.state import (
    test_steps_store,
    current_test_name,
    pending_payloads,
    dismissed_keys,
    PAYLOAD_PREFIXES
)
from app.core.state import reset_run_state, runs, appium_proc, APPIUM_PORT
from app.core.utils import pick_free_port, parse_step_from_message, ADB_PATH, build_tool_env, JAVA_HOME
from app.core.constants import ALLURE_CMD, ALLURE_REPORT_DIR
from fastapi import HTTPException
from app.core.websocket import manager
from app.core.logger import logger
from app.core.events import broadcast_async
from app.modules.slack.service import APP_DEVELOPER_MAP, new_run, detect_app_variant, run_post_notify
from app.core.constants import SLACK_NOTIFY_CHANNEL
from app.core.paths import APK_STORAGE_DIR, ensure_apk_dirs, ensure_tests_importable, resolve_apk

# Test paths sent by the UI are relative to the tests repo, not to this one.
PROJECT_ROOT = ensure_tests_importable()
from tests.test_runner import (
    stop_current_tests,
    generate_report
)
from app.modules.slack.config import APP_VARIANTS, APP_DEVELOPER_MAP
from .gdrive_loader import download_apk, extract_app_icon, get_apk_info


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
APKS_DIR = str(APK_STORAGE_DIR)
ensure_apk_dirs()

DOWNLOAD_PROCESS_OBJ = None

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


async def device_status_flow():
    try:
        result = subprocess.run([ADB_PATH, "devices"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().splitlines()[1:]
        return {"connected": any("\tdevice" in line for line in lines)}
    except Exception as e:
        logger.error(f"adb devices check failed (ADB_PATH={ADB_PATH}): {e}")
        return {"connected": False}
    
async def appium_start_flow():
    global appium_proc
    if appium_proc is not None and appium_proc.poll() is None:
        return {"status": "running", "message": "Appium is already running via backend."}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", APPIUM_PORT)) == 0:
            return {"status": "running", "message": f"Appium already active on port {APPIUM_PORT}"}
    try:
        # Launch Appium with JAVA_HOME / ANDROID_HOME guaranteed in its environment,
        # so the UiAutomator2 driver can find java (APK signature verification) even
        # when the backend itself was started without them (secondary Windows account).
        appium_env = build_tool_env()
        appium_proc = subprocess.Popen(["appium", "-p", str(APPIUM_PORT)],
                                         shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         env=appium_env)
        msg = f"Appium started on port {APPIUM_PORT}"
        if not JAVA_HOME:
            msg += " (⚠️ no JDK found — set JAVA_HOME; APK signature checks may fail)"
        return {"status": "started", "message": msg, "java_home": JAVA_HOME}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    
async def download_apk_from_url(url: str, manager):
    global DOWNLOAD_PROCESS_OBJ

    script_path = os.path.join(os.path.dirname(__file__), "gdrive_loader.py")

    apk_path = None
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    DOWNLOAD_PROCESS_OBJ = await asyncio.create_subprocess_exec(
        sys.executable,
        "-u",
        script_path,
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    async for line in DOWNLOAD_PROCESS_OBJ.stdout:
        decoded = line.decode("utf-8").strip()

        if decoded.startswith("PROGRESS:"):
            await manager.broadcast({
                "type": "LOG",
                "payload": {"message": decoded.replace("PROGRESS:", ""), "status": "PROGRESS"}
            })
        elif decoded.startswith("RESULT:"):
            apk_path = decoded.replace("RESULT:", "").strip()
        elif decoded:
            await manager.broadcast({
                "type": "LOG",
                "payload": {"message": decoded, "status": "INFO"}
            })

    await DOWNLOAD_PROCESS_OBJ.wait()

    if DOWNLOAD_PROCESS_OBJ.returncode != 0:
        stderr_data = await DOWNLOAD_PROCESS_OBJ.stderr.read()
        raise Exception(stderr_data.decode())

    if not apk_path:
        raise Exception("APK path not returned")

    return apk_path

async def appium_status_flow():
    global appium_proc
    if appium_proc is not None and appium_proc.poll() is None:
        return {"status": "running", "port": APPIUM_PORT}
    return {"status": "stopped"}

async def appium_stop_flow():
    global appium_proc
    if appium_proc is not None:
        if os.name == "nt":
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(appium_proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                appium_proc.kill()
        appium_proc = None
        return {"status": "stopped"}
    return {"status": "not_running"}

async def list_apks_flow():
    try:
        files = [name for name in os.listdir(APKS_DIR) if name.lower().endswith((".apk", ".apks"))]
        return {"apks": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

# async def start_test_flow(request, background_tasks, manager):
#     reset_run_state()
#     global DOWNLOAD_PROCESS_OBJ, latest_run_id
    
#     run_id = new_run()
#     latest_run_id = run_id

#     # store network config
#     network_config = getattr(request, "network_config", None)
    
#     runs[run_id] = runs.get(run_id, {})
#     runs[run_id]["network_config"] = network_config

#     try:
#         await manager.broadcast({
#             "type": "LOG",
#             "payload": {
#                 "message": "Starting APK download...", 
#                 "status": "INFO"
#             }
#         })

#         await manager.broadcast({"type": "LOG", "payload": {"message": "Starting APK download...", "status": "INFO"}})
#         script_path = os.path.join(os.path.dirname(__file__), "gdrive_loader.py")
#         apk_path = None
#         env = os.environ.copy()
#         env["PYTHONIOENCODING"] = "utf-8"
        
#         DOWNLOAD_PROCESS_OBJ = await asyncio.create_subprocess_exec(
#             sys.executable, "-u", script_path, request.url,
#             stdout=asyncio.subprocess.PIPE, 
#             stderr=asyncio.subprocess.PIPE, 
#             env=env
#         )

#         async for line in DOWNLOAD_PROCESS_OBJ.stdout:
#             decoded_line = line.decode("utf-8").strip()
#             if decoded_line.startswith("PROGRESS:"):
#                 await manager.broadcast({"type": "LOG", "payload": {
#                     "message": decoded_line.replace("PROGRESS:",""), "status": "PROGRESS"
#                 }})
#             elif decoded_line.startswith("RESULT:"):
#                 apk_path = decoded_line.replace("RESULT:","").strip()
#             elif decoded_line:
#                 await manager.broadcast({"type": "LOG", "payload": {"message": decoded_line, "status": "INFO"}})
        
#         await DOWNLOAD_PROCESS_OBJ.wait()
#         if DOWNLOAD_PROCESS_OBJ.returncode != 0:
#             stderr_data = await DOWNLOAD_PROCESS_OBJ.stderr.read()
#             raise Exception(f"Script Error: {stderr_data.decode('utf-8').strip() or 'Unknown error'}")
#         if not apk_path:
#             raise Exception("Download script finished but returned no path.")
        
#         DOWNLOAD_PROCESS_OBJ = None

#         icon_url      = extract_app_icon(apk_path)
#         full_icon_url = f"http://localhost:8000{icon_url}" if icon_url else None

#         info         = get_apk_info(apk_path) or {}
#         app_name     = info.get("app_name")
#         app_version  = info["app_version"]
#         package_name = info.get("package_name")
#         app_variant  = detect_app_variant.get(package_name, app_name)
#         tests_to_run = request.tests_to_run or APP_VARIANTS.get(app_variant, [])
        
#          # ── Store into run state immediately so conftest can fetch it ─────────
#         developer_name = APP_DEVELOPER_MAP.get(app_variant, "Unknown Developer")
#         if run_id in runs:
#             runs[run_id]["app_name"]       = app_name       or ""
#             runs[run_id]["app_version"]    = app_version     or ""
#             runs[run_id]["package_name"]   = package_name   or ""
#             runs[run_id]["app_variant"]    = app_variant     or ""
#             runs[run_id]["developer_name"] = developer_name or ""
#         await manager.broadcast({
#             "type": "LOG",
#             "payload": {
#                 "message": f"Detected app variant: {app_variant}", "status": "INFO"
#             },
#         })

#         background_tasks.add_task(
#             run_post_notify,
#             run_id=run_id,
#             apk_path=apk_path,
#             tests_to_run   = tests_to_run,
#             app_name       = info.get("app_name"),
#             app_version    = info.get("app_version"),
#             developer_name = info.get("developer_name"),
#             # developer_name=APP_DEVELOPER_MAP.get(app_variant, "Unknown Developer"),
#             channel_id=SLACK_NOTIFY_CHANNEL,
#         )

#         return {
#             "status": "success", 
#             "message": "APK Downloaded. Test Starting...",
#             "run_id": run_id,
#             "app_icon": full_icon_url, 
#             "apk_path": apk_path, 
#             **info,
#             "status": "success",
#             "message": "APK Downloaded. Test Starting...",
#             "app_icon": full_icon_url,
#             "app_name": app_name,
#             "package_name": package_name,
#             "apk_path": apk_path,
#             "app_variant": app_variant,
#             "app_version": app_version,
#         }

#     except Exception as e:
#         DOWNLOAD_PROCESS_OBJ = None
#         await manager.broadcast({"type": "LOG", "payload": {
#             "message": f"Download interrupted: {str(e)}", "status": "FAILED",
#         }})
#         raise HTTPException(status_code=400, detail=f"Download Failed: {str(e)}")

async def start_test_flow(request, background_tasks, manager):
    reset_run_state()

    global DOWNLOAD_PROCESS_OBJ, latest_run_id

    run_id = new_run()
    latest_run_id = run_id

    # store network config
    network_config = getattr(request, "network_config", None)

    runs[run_id] = runs.get(run_id, {})
    runs[run_id]["network_config"] = network_config

    try:
        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": "Starting APK download...",
                "status": "INFO"
            }
        })

        # Run download directly in thread pool instead of subprocess
        # because subprocess may use wrong Python environment
        loop = asyncio.get_event_loop()

        def progress_callback(msg):
            clean = msg.replace('\r', '').strip()

            if clean:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast({
                        "type": "LOG",
                        "payload": {
                            "message": clean,
                            "status": "PROGRESS"
                        }
                    }),
                    loop
                )

        apk_path = await loop.run_in_executor(
            None,
            lambda: download_apk(request.url, progress_callback)
        )

        DOWNLOAD_PROCESS_OBJ = None

        if not apk_path:
            raise Exception("Download failed: APK path not returned")

        # Extract app icon
        icon_url = extract_app_icon(apk_path)
        full_icon_url = f"http://localhost:8000{icon_url}" if icon_url else None

        # Get APK info
        info = get_apk_info(apk_path) or {}

        app_name = info.get("app_name")
        app_version = info.get("app_version")
        package_name = info.get("package_name")

        # Prefer the UI-selected role over package detection (unified app).
        app_variant = getattr(request, "app_type", None) or detect_app_variant(package_name, app_name)

        tests_to_run = request.tests_to_run or APP_VARIANTS.get(
            app_variant,
            []
        )

        # Store run metadata
        developer_name = APP_DEVELOPER_MAP.get(
            app_variant,
            "Unknown Developer"
        )

        if run_id in runs:
            runs[run_id]["app_name"] = app_name or ""
            runs[run_id]["app_version"] = app_version or ""
            runs[run_id]["package_name"] = package_name or ""
            runs[run_id]["app_variant"] = app_variant or ""
            runs[run_id]["developer_name"] = developer_name or ""

        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": f"Detected app variant: {app_variant}",
                "status": "INFO"
            }
        })

        # Start tests in background
        background_tasks.add_task(
            run_post_notify,
            run_id=run_id,
            apk_path=apk_path,
            tests_to_run=tests_to_run,
            app_name=info.get("app_name"),
            app_version=info.get("app_version"),
            developer_name=developer_name,
            channel_id=SLACK_NOTIFY_CHANNEL,
            app_type=app_variant,
            login_phone=getattr(request, "login_phone", None),
            login_mpin=getattr(request, "login_mpin", None),
            test_types=getattr(request, "test_types", None),
        )

        return {
            "status": "success",
            "message": "APK Downloaded. Test Starting...",
            "run_id": run_id,
            "app_icon": full_icon_url,
            "apk_path": apk_path,
            **info,
            "app_name": app_name,
            "package_name": package_name,
            "app_variant": app_variant,
            "app_version": app_version,
        }

    except Exception as e:
        DOWNLOAD_PROCESS_OBJ = None

        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": f"Download interrupted: {str(e)}",
                "status": "FAILED"
            }
        })

        raise HTTPException(
            status_code=400,
            detail=f"Download Failed: {str(e)}"
        )
    
async def start_test_existing_flow(request, background_tasks, manager):
    global latest_run_id

    run_id        = new_run()
    latest_run_id = run_id

    # store network config
    network_config = getattr(request, "network_config", None)
    
    runs[run_id] = runs.get(run_id, {})
    runs[run_id]["network_config"] = network_config

    reset_run_state()

    try:
        try:
            apk_path = str(resolve_apk(request.apk_name))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not os.path.isfile(apk_path):
            raise HTTPException(status_code=404, detail="APK not found on server")
        
        await manager.broadcast({"type": "RUN_START", "payload": {}})
        await manager.broadcast({"type": "LOG", "payload": {
            "message": f"Using existing APK: {request.apk_name}", "status": "INFO"
        }})

        icon_url      = extract_app_icon(apk_path)
        full_icon_url = f"http://localhost:8000{icon_url}" if icon_url else None
        info = get_apk_info(apk_path) or {}
        package_name = info["package_name"]
        app_name     = info["app_name"]
        app_version  = info["app_version"]
        # Prefer the role explicitly chosen in the UI (unified app: one package =
        # many roles, so package-name detection can't disambiguate). Fall back to
        # package detection only when the UI didn't send a variant.
        app_variant   = getattr(request, "app_type", None) or detect_app_variant(package_name, app_name)
        variant_tests = APP_VARIANTS.get(app_variant, [])
        tests_to_run = request.tests_to_run

        if tests_to_run:
            # Test paths are repo-relative and live at the repo root, NOT under
            # app (which is what BASE_DIR points to) — validate against
            # PROJECT_ROOT, the same base the pytest runner uses.
            valid   = [t for t in tests_to_run if os.path.isfile(os.path.join(PROJECT_ROOT, t["path"]))]
            invalid = [t for t in tests_to_run if t not in valid]

            if invalid:
                bad_paths = [t["path"] for t in invalid]
                await manager.broadcast({"type": "LOG", "payload": {
                    "message": (
                        f"⚠️  {len(invalid)} invalid path(s) removed: {bad_paths}. "
                        f"Falling back to APP_VARIANTS defaults for variant '{app_variant}'."
                    ),
                    "status": "WARN",
                }})
            tests_to_run = valid if valid else variant_tests
        else:
            tests_to_run = variant_tests

        if not tests_to_run:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No valid test scripts found for variant '{app_variant}'. "
                    f"Check APP_VARIANTS paths in server.py."
                ),
            )

        await manager.broadcast({"type": "LOG", "payload": {
            "message": f"Running {len(tests_to_run)} test(s): {[t['name'] for t in tests_to_run]}",
            "status": "INFO",
        }})

        background_tasks.add_task(
            run_post_notify,
            run_id=run_id,
            apk_path=apk_path,
            tests_to_run   = request.tests_to_run,
            app_name       = info.get("app_name"),
            app_version    = info.get("app_version"),
            # developer_name = info.get("developer_name"),
            developer_name=APP_DEVELOPER_MAP.get(app_variant, "Unknown Developer"),
            channel_id=SLACK_NOTIFY_CHANNEL,
            # Prefer the role explicitly chosen in the UI; fall back to the
            # package-detected variant only if the UI didn't send one.
            app_type=getattr(request, "app_type", None) or app_variant,
            login_phone=getattr(request, "login_phone", None),
            login_mpin=getattr(request, "login_mpin", None),
            test_types=getattr(request, "test_types", None),
        )


        return {
            "status": "success", 
            "message": "Using existing APK. Test Starting...",
            "run_id":       run_id,
            "app_icon": full_icon_url, 
            "apk_path": apk_path, 
            **info,
            "app_variant":  app_variant,
            "tests_to_run": tests_to_run,
        }

    except HTTPException:
        raise
    except Exception as e:
        await manager.broadcast({"type": "LOG", "payload": {
            "message": f"Failed to start test: {str(e)}", "status": "FAILED"
            }})
        raise HTTPException(status_code=400, detail=f"Failed: {str(e)}")

def stop_test_flow(manager):
    stopped = False

    global DOWNLOAD_PROCESS_OBJ

    if DOWNLOAD_PROCESS_OBJ:
        DOWNLOAD_PROCESS_OBJ.terminate()
        stopped = True

    if stop_current_tests():
        stopped = True

    return stopped

async def allure_start_flow():
    port = pick_free_port()
    subprocess.Popen([ALLURE_CMD, "open", "-h", "127.0.0.1", "-p", str(port), ALLURE_REPORT_DIR],
                     cwd=BASE_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True,
                     env=build_tool_env())  # allure needs java on PATH / JAVA_HOME
    return JSONResponse({"url": f"http://127.0.0.1:{port}"})

async def run_complete_flow(event):
    await manager.broadcast({"type": "RUN_COMPLETE", "payload": {"report_url": event.report_url}})
    return {"ok": True}

async def api_generate_report_flow():
    try:
        threading.Thread(target=generate_report).start()
        return {"status": "ok", "message": "Report generation started"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

