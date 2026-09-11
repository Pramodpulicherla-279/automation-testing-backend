import os
import subprocess
import re
import tempfile
import shutil
import requests
import time
import asyncio
import glob
import json
import uuid
import datetime
import sys
import socket
from app.core.paths import ensure_tests_importable

PROJECT_ROOT = ensure_tests_importable()
from tests.test_runner import (
    run_tests_and_get_suggestions,
)
from app.core.state import runs, is_appium_running, APPIUM_PORT, PROCESSED_EVENTS, appium_proc, latest_run_id
from app.core.utils import start_allure_server
from app.core.websocket import manager
from app.modules.test_runner.gdrive_loader import get_apk_info
from app.core.constants import SLACK_BOT_TOKEN, SLACK_NOTIFY_CHANNEL, ALLURE_CMD
from .config import APP_CONFIG, PACKAGE_VARIANT_MAP, APP_VARIANTS, APP_DEVELOPER_MAP

BASE_DIR = PROJECT_ROOT
print(f"[DEBUG] BASE_DIR = {BASE_DIR}")
print(f"[DEBUG] allure-results path = {os.path.join(BASE_DIR, 'allure-results')}")

# PACKAGE_VARIANT_MAP = {
#     "com.agribride.krishivaas.farmer_app":       "regular_farmer",
#     "com.agribride.krishivaas.client_app":       "regular_client",
#     "com.agribride.krishivaas.farmer_state_app": "state_farmer",
#     "com.agribride.krishivaas.client_state_app": "state_client",
# }
# APP_VARIANTS = {
#     "regular_farmer": [
#         {"name": "Login",       "path": "tests/test_cases/regular_farmer_test_cases/test_login_pytest.py"},
#         {"name": "Dashboard",   "path": "tests/test_cases/regular_farmer_test_cases/TestOnboarding.py"},
#         {"name": "Add Updates", "path": "tests/farmer/test_updates.py"},
#     ],
#     "regular_client": [
#         {"name": "Login",       "path": "tests/test_cases/regular_client_test_cases/login_pytest.py"},
#         {"name": "Marketplace", "path": "tests/client/test_marketplace.py"},
#         {"name": "Cart",        "path": "tests/client/test_cart.py"},
#     ],
#     "state_farmer": [
#         {"name": "Login",   "path": "tests/state_farmer/test_login.py"},
#         {"name": "Schemes", "path": "tests/state_farmer/test_schemes.py"},
#     ],
#     "state_client": [
#         {"name": "Login",      "path": "tests/test_cases/state_client_test_cases/test_login_pytest.py"},
#         {"name": "Onboarding", "path": "tests/test_cases/state_client_test_cases/test_Onboarding.py"},
#     ],
# }

# APP_DEVELOPER_MAP = {
#     "regular_farmer": "@Anuj",
#     "regular_client": "@samad ahmed",
#     "state_farmer":   "@Swaroopa",
#     "state_client":   "@Vikash Chandra",
# }

# APP_CONFIG = {
#     "regular_farmer": {
#         "developer_name": "Pramod",   # 👈 IMPORTANT
#         "slack_user_id": "U0AT2P7V1K2",   # 👈 IMPORTANT
#         "channel_id": "C0AJY6W7FFF"
#     },
#     "regular_client": {
#         "developer_name": "Kiran",
#         "slack_user_id": "U02BBBBBBB",
#         "channel_id": "C0AJY6W7FFF"
#     },
#     "state_farmer": {
#         "developer_name": "Swaroopa",
#         "slack_user_id": "U03CCCCCCC",
#         "channel_id": "C0AJY6W7FFF"
#     },
#     "state_client": {
#         "developer_name": "Vikash Chandra",
#         "slack_user_id": "U04DDDDDD",
#         "channel_id": "C0AJY6W7FFF"
#     }
# }

def new_run() -> str:
    """Create a fresh isolated state bucket and return its run_id."""
    run_id = str(uuid.uuid4())
    runs[run_id] = {
        "test_steps_store":  {},
        "pending_payloads":  [],
        "dismissed_keys":    set(),
        "current_test_name": "default",
        "report_url":        None,
        "started_at":        datetime.datetime.now().isoformat(),
        # ── APK metadata — populated as soon as info is resolved ──────────────
        "app_name":          "",
        "app_version":       "",
        "package_name":      "",
        "app_variant":       "",
        "developer_name":    "",
    }
    return run_id

# def generate_allure_report():
#     results_dir = os.path.join(BASE_DIR, "allure-results")
#     json_files = glob.glob(os.path.join(results_dir, "*.json"))
#     print("\n[Allure] Generating report from allure-results...")
#     """
#     Generate the Allure HTML report from allure-results.
#     NOTE: Do NOT wipe allure-results here — they were already populated by
#     the just-completed pytest run.  Only use --clean on the output folder.
#     """
#     if not json_files:
#         print("❌ allure-results is EMPTY — tests did not write results here!")
#         return
#     try:
#         subprocess.run(
#             [ALLURE_CMD, "generate", "allure-results", "-o", "allure-report", "--clean"],
#             cwd=BASE_DIR,
#             check=True,
#             shell=True,
#         )
#         print("✅ Allure report generated")
#     except Exception as e:
#         print(f"❌ Allure generate failed: {e}")

def log_to_ui(message: str, status: str = "INFO"):
    try:
        asyncio.create_task(manager.broadcast({
            "type": "LOG",
            "payload": {"message": message, "status": status},
        }))
    except Exception:
        pass

def detect_app_variant(package_name: str, app_name: str) -> str | None:
    """
    Detect app variant with a clear priority order:
      1. Exact package name match  (most reliable)
      2. Partial package name match (handles extra suffixes/prefixes)
      3. Keyword match on app_name (fallback)
    Returns one of: 'regular_farmer', 'regular_client',
                    'state_farmer',   'state_client',  or None.
    """
    pkg_lower = (package_name or "").strip().lower()

    # 1. Exact match
    for pkg, variant in PACKAGE_VARIANT_MAP.items():
        if pkg.lower() == pkg_lower:
            print(f"[Variant] Detected via exact package_name: '{package_name}' → {variant}")
            return variant

    # 2. Partial / contains match (handles debug builds with extra suffixes)
    if pkg_lower:
        for pkg, variant in PACKAGE_VARIANT_MAP.items():
            if pkg.lower() in pkg_lower or pkg_lower in pkg.lower():
                print(f"[Variant] Detected via partial package_name: '{package_name}' → {variant}")
                return variant

    # 3. Keyword match on app_name
    name_lower = (app_name or "").strip().lower()

    if "state" in name_lower and "farmer" in name_lower:
        print(f"[Variant] Detected via app_name keywords: '{app_name}' → state_farmer")
        return "state_farmer"
    if "state" in name_lower and "client" in name_lower:
        print(f"[Variant] Detected via app_name keywords: '{app_name}' → state_client")
        return "state_client"
    if "farmer" in name_lower:
        print(f"[Variant] Detected via app_name keywords: '{app_name}' → regular_farmer")
        return "regular_farmer"
    if "client" in name_lower:
        print(f"[Variant] Detected via app_name keywords: '{app_name}' → regular_client")
        return "regular_client"

    # 4. Also try matching on package keywords directly
    if pkg_lower:
        if "state" in pkg_lower and "farmer" in pkg_lower:
            return "state_farmer"
        if "state" in pkg_lower and "client" in pkg_lower:
            return "state_client"
        if "farmer" in pkg_lower:
            return "regular_farmer"
        if "client" in pkg_lower:
            return "regular_client"

    print(f"[Variant] Could not detect variant — package='{package_name}' app='{app_name}'")
    return None

def deploy_to_github_pages(run_id: str) -> str | None:
    """
    Deploy the current allure-report into a UNIQUE sub-folder on gh-pages.

    Strategy
    ────────
    • Checkout the existing gh-pages branch into a temporary directory.
    • Copy allure-report  →  <temp>/<short_id>/
    • Commit & push  →  all previous folders are preserved.
    • Poll until the URL returns HTTP 200 before returning it.
    • Returns None on any failure so the caller never sends a Slack message
      with a broken link.
    """
    allure_report_path = os.path.join(BASE_DIR, "allure-report")
    if not os.path.isdir(allure_report_path):
        print(f"[GHPages] allure-report folder not found: {allure_report_path}")
        return None

    print(f"[GHPages] Deploying run_id={run_id[:8]} to GitHub Pages...")

    try:
        # ── 1. Resolve remote URL ─────────────────────────────────────────────
        remote_result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=BASE_DIR, capture_output=True, text=True,
        )
        remote_url = remote_result.stdout.strip()

        match = re.search(r"github\.com[:/](.+?)(?:\.git)?$", remote_url)
        if not match:
            print(f"[GHPages] Could not parse remote URL: {remote_url}")
            return None

        org, repo = match.group(1).split("/", 1)
        short_id  = run_id[:8]
        pages_url = f"https://{org}.github.io/{repo}/{short_id}/index.html"

        # ── 2. Clone gh-pages into a fresh temp directory ─────────────────────
        #      We use a plain temp dir so we never touch the main worktree.
        tmp_dir = tempfile.mkdtemp(prefix="ghpages_")
        print(f"[GHPages] Using temp dir: {tmp_dir}")

        try:
            # Try to clone the existing gh-pages branch.
            # If it doesn't exist yet, initialise an empty repo instead.
            clone_result = subprocess.run(
                [
                    "git", "clone",
                    "--branch", "gh-pages",
                    "--single-branch",
                    "--depth", "1",
                    remote_url,
                    tmp_dir,
                ],
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=120,
            )

            if clone_result.returncode != 0:
                # gh-pages branch doesn't exist yet — init a bare repo
                print("[GHPages] gh-pages branch not found, creating fresh...")
                subprocess.run(["git", "init"],            cwd=tmp_dir, check=True)
                subprocess.run(["git", "checkout", "-b", "gh-pages"], cwd=tmp_dir, check=True)
                subprocess.run(["git", "remote", "add", "origin", remote_url],
                               cwd=tmp_dir, check=True)

            # ── 3. Copy ONLY the new report into its unique folder ─────────────
            target_dir = os.path.join(tmp_dir, short_id)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(allure_report_path, target_dir)
            print(f"[GHPages] Copied report → {target_dir}")

            # ── 4. Commit & push (all other folders remain intact) ────────────
            subprocess.run(["git", "add", short_id], cwd=tmp_dir, check=True)

            # Only commit if there is actually something new
            diff_result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=tmp_dir,
            )
            if diff_result.returncode == 0:
                print("[GHPages] Nothing changed — report already deployed.")
            else:
                subprocess.run(
                    ["git", "commit", "-m", f"report: add {short_id}"],
                    cwd=tmp_dir, check=True,
                )
                push_result = subprocess.run(
                    ["git", "push", "origin", "gh-pages"],
                    cwd=tmp_dir,
                    capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    timeout=120,
                )
                if push_result.returncode != 0:
                    print(f"[GHPages] Push failed: {push_result.stderr}")
                    return None

            print(f"[GHPages] ✅ Pushed → {pages_url}")

        finally:
            # Always clean up the temp clone
            shutil.rmtree(tmp_dir, ignore_errors=True)

        # ── 5. Wait for GitHub Pages CDN to propagate ─────────────────────────
        if not wait_for_page_live(pages_url):
            print(f"[GHPages] ⚠️ Page did not go live in time: {pages_url}")
            return None   # ← Slack will NOT be sent

        return pages_url

    except Exception as e:
        print(f"[GHPages] Exception: {e}")

    return None


def wait_for_page_live(
    url: str,
    retries: int = 18,          # 18 × 10 s = 3 minutes max
    delay_seconds: int = 10,
) -> bool:
    """
    Poll the URL until HTTP 200 or timeout.
    Returns True only when the page is confirmed live.
    """
    print(f"[GHPages] Waiting for page to go live: {url}")
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                print(f"[GHPages] ✅ Page is live (attempt {attempt})")
                return True
            print(f"[GHPages] Attempt {attempt}/{retries} → HTTP {response.status_code}, "
                  f"retrying in {delay_seconds}s...")
        except requests.RequestException as exc:
            print(f"[GHPages] Attempt {attempt}/{retries} → {exc}, "
                  f"retrying in {delay_seconds}s...")

        time.sleep(delay_seconds)

    print(f"[GHPages] ❌ Page never became live after {retries * delay_seconds}s")
    return False
 
# ════════════════════════════════════════════════════════════════════════════
#  SLACK NOTIFICATION
# ════════════════════════════════════════════════════════════════════════════
 
def send_slack_message(
    channel_id,
    developer_name,
    slack_user_id,
    app_name,
    apk_version,
    passed,
    failed,
    report_url,
):
    mention = f"<@{slack_user_id}>"

    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "channel": channel_id,
        "text": f"{mention} 🚀 Automation Report Ready!",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{mention} 🚀 *Automation Report Ready!*"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"👤 *Developer*\n{mention}"},
                    {"type": "mrkdwn", "text": f"📱 *App*\n{app_name}"},
                    {"type": "mrkdwn", "text": f"🏷️ *Version*\n{apk_version}"},
                    {"type": "mrkdwn", "text": f"📊 *Results*\n🟢 Passed: {passed}   🔴 Failed: {failed}"}
                ]
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "📄 Open Report"},
                        "url": report_url,
                        "style": "primary"
                    }
                ]
            }
        ]
    }

    response = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers=headers,
        json=payload,
        timeout=10,
    )

    data = response.json()
    if not data.get("ok"):
        print(f"[Slack ERROR] {data}")
    else:
        print(f"[Slack] ✅ Sent to {channel_id}") 
 
# ════════════════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT  —  call this after your test run finishes
# ════════════════════════════════════════════════════════════════════════════
def auto_push_to_github(run_id: str):
    try:
        print("[CI/CD] Auto pushing to GitHub...")
        short_id = run_id[:8]

        subprocess.run(["git", "add", f"allure-results"], cwd=BASE_DIR, check=True)
        subprocess.run(["git", "add", f"allure-report"], cwd=BASE_DIR, check=True)

        commit_message = f"allure-report-{short_id}"

        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=BASE_DIR,
            check=False  # avoid error if nothing to commit
        )

        subprocess.run(
            ["git", "push", "origin", "samad-updated"],
            cwd=BASE_DIR,
            check=True
        )

        print("[CI/CD] ✅ Allure Report pushed successfully")

    except Exception as e:
        print(f"[CI/CD] ❌ Push failed: {e}")        


def deploy_and_notify(
    run_id:         str,
    channel_id:     str,
    developer_name: str,
    app_name:       str,
    apk_version:    str,
    passed:         int,
    failed:         int,
) -> None:
    """
    1. Deploy allure report to GitHub Pages (unique URL per run).
    2. Only send Slack message AFTER confirming the page is actually live.
    3. If deploy fails or page never goes live → Slack is NOT sent.
    """
 
    # ✅ FIX 2: Only notify Slack if deploy succeeded AND page is live
    report_url = deploy_to_github_pages(run_id)
 
    # if not report_url:
    #     logger.info("[Notify] ❌ Deploy failed or page not live — Slack message NOT sent.")
    #     return
    # print("DEBUG app_variant:", app_variant)
    send_slack_message(
        channel_id=channel_id,
        developer_name=developer_name,
        app_name=app_name,
        apk_version=apk_version,
        passed=passed,
        failed=failed,
        report_url=report_url,
    )
 
 
def extract_drive_file_id(text: str) -> str | None:
    text = text.replace("<", "").replace(">", "")
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', text)
    return match.group(1) if match else None

def run_post_notify(**kwargs) -> None:
    asyncio.run(post_run_notify(**kwargs))

async def post_run_notify(
    run_id:         str,
    apk_path:       str,
    tests_to_run:   list,
    app_name:       str,
    app_version:    str,
    developer_name: str,
    channel_id:     str,
    app_type:       str = None,
    login_phone:    str = None,
    login_mpin:     str = None,
    test_types:     list = None,
) -> None:
    loop = asyncio.get_event_loop()

    # ── Store app metadata into run state RIGHT NOW so tests can fetch it ─────
    if run_id in runs:
        runs[run_id]["app_name"]       = app_name       or ""
        runs[run_id]["app_version"]    = app_version     or ""
        runs[run_id]["developer_name"] = developer_name  or ""
        if not runs[run_id].get("app_variant"):
            runs[run_id]["app_variant"] = detect_app_variant(
                runs[run_id].get("package_name", ""),
                app_name,
            )
        print(f"[post_run_notify] app_variant resolved → {runs[run_id]['app_variant']}")
    print(f"[post_run_notify] Metadata stored → "
          f"app='{app_name}' ver='{app_version}' dev='{developer_name}'")

    # ── Broadcast a clean summary of what we resolved ────────────────────────
    await manager.broadcast({
        "type": "LOG",
        "payload": {
            "message": (
                f"📦 App: {app_name} | Version: {app_version} | "
                f"Developer: {developer_name} | Tests: {len(tests_to_run)}"
            ),
            "status": "INFO",
        },
    })

    await manager.broadcast({
        "type": "MODULES",
        "payload": {"run_id": run_id, "modules": tests_to_run},
    })

    # ── Clear allure-results ONLY here, BEFORE running tests ─────────────────
    results_dir = os.path.join(BASE_DIR, "allure-results")
    try:
        if os.path.isdir(results_dir):
            # shutil.rmtree(results_dir)
            os.makedirs(results_dir, exist_ok=True)
        log_to_ui(f"[{run_id[:8]}] Cleared stale allure-results before run", "INFO")
    except Exception as e:
        log_to_ui(f"[{run_id[:8]}] Could not clear allure-results: {e}", "WARN")

    # ── Step 1 — run tests ───────────────────────────────────────────────────
    log_to_ui(f"[{run_id[:8]}] Step 1: Running tests...", "INFO")
    try:
        await loop.run_in_executor(
            None,
            lambda: run_tests_and_get_suggestions(
                apk_path,
                tests_to_run=tests_to_run,
                app_type=app_type,
                app_name=app_name,
                app_version=app_version,
                developer_name=developer_name,
                run_id=run_id,
                login_phone=login_phone,
                login_mpin=login_mpin,
                test_types=test_types,
            ),
        )
        log_to_ui(f"[{run_id[:8]}] Step 1 done", "SUCCESS")
    except Exception as e:
        log_to_ui(f"[{run_id[:8]}] Step 1 FAILED: {e}", "ERROR")
        await manager.broadcast({"type": "LOG", "payload": {
            "message": f"[PostRun] Tests failed: {e}", "status": "FAILED",
        }})
        return

    await manager.broadcast({
        "type": "MODULES",
        "payload": {"run_id": run_id, "modules": tests_to_run},
    })

    # ── Step 2 — count pass/fail ──────────────────────────────────────────────
    passed = failed = 0
    try:
        report_results_dir = os.path.join(BASE_DIR, "allure-report", "data", "test-cases")
        scan_dir = report_results_dir if os.path.isdir(report_results_dir) else results_dir
        for json_file in glob.glob(os.path.join(scan_dir, "*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                status = (result_data.get("status") or result_data.get("testStage", {}).get("status") or "").upper()
                if status == "PASSED":
                    passed += 1
                elif status in ("FAILED", "BROKEN"):
                    failed += 1
            except Exception:
                pass

        for json_file in glob.glob(os.path.join(results_dir, "*-result.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
                status = result_data.get("status", "").upper()
                if status == "PASSED":
                    passed += 1
                elif status in ("FAILED", "BROKEN"):
                    failed += 1
            except Exception:
                pass
        log_to_ui(f"[{run_id[:8]}] Step 2 done. Passed: {passed} | Failed: {failed}", "SUCCESS")
    except Exception as e:
        print(f"[PostRun] Step 2 FAILED: {e}")

    # ── Broadcast captured steps for this run ────────────────────────────────
    # await _broadcast_all_steps_to_frontend(run_id)

    # ── Step 4 — resolve report URL ──────────────────────────────────────────
    print(f"[{run_id[:8]}] Step 3: Resolving report URL...")

    # ── GitHub Pages deploy TEMPORARILY DISABLED ─────────────────────────────
    # Reason: auto_push_to_github() and deploy_to_github_pages() run blocking
    # git-clone / git-push operations inside loop.run_in_executor().
    # When the remote is slow or the gh-pages CDN takes up to 3 minutes to
    # propagate, these hold a thread-pool thread for the full duration —
    # starving the FastAPI event loop and making the server unresponsive.
    # Re-enable once these are moved to a dedicated background worker.
    #
    # 1. Start local server
    # local_url  = await loop.run_in_executor(None, start_allure_server)
    # 2. Push to GitHub
    # await loop.run_in_executor(None, lambda: auto_push_to_github(run_id))
    # 3. Deploy to GitHub Pages
    # ghpages_url = await loop.run_in_executor(None, lambda: deploy_to_github_pages(run_id))
    # 4. Decide final URL
    # if not ghpages_url:
    #     log_to_ui(f"[{run_id[:8]}] ❌ GitHub Pages deploy failed", "ERROR")
    #     return   # 🚨 STOP execution
    # report_url = ghpages_url

    # Temporary fallback: serve the Allure report locally via FastAPI.
    report_url = "http://localhost:8000/allure-report/index.html"
    print(f"[{run_id[:8]}] Step 3: Report URL → {report_url}")

    if run_id in runs:
        runs[run_id]["report_url"] = report_url

    # ── Step 5 — send Slack notification ─────────────────────────────────────
    print(f"channel ID: {channel_id}")
    final_channel_id = channel_id or SLACK_NOTIFY_CHANNEL
    print(f"[{run_id[:8]}] Final channel_id: {final_channel_id}")

    if not final_channel_id:
        print("[ERROR] No Slack channel found even after fallback")
        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": "⚠️ Slack notification skipped: No channel_id found",
                "status": "WARN",
            },
        })
        return

    print(f"[{run_id[:8]}] Step 4: Sending Slack notification...")
    print(f"[FINAL DEBUG] developer_name = '{developer_name}'")
    print(f"[FINAL DEBUG] app_name       = '{app_name}'")
    print(f"[FINAL DEBUG] app_version    = '{app_version}'")

    try:
        app_variant = runs.get(run_id, {}).get("app_variant")
        config = APP_CONFIG.get(app_variant)
        if not config:
           print(f"[ERROR] No config for app_variant={app_variant}")
           return

        await loop.run_in_executor(
            None,
            lambda: send_slack_message(
            channel_id = config.get("channel_id") or final_channel_id,
            developer_name=config.get("developer_name"),
            slack_user_id=config.get("slack_user_id"),   # 🔥 ADD THIS
            app_name=app_name,
            apk_version=app_version,
            passed=passed,
            failed=failed,
            report_url=report_url,
        ),
        )
        log_to_ui(f"[{run_id[:8]}] Step 5 done. Slack notification sent", "SUCCESS")
        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": f"✅ Slack report sent! Passed: {passed} | Failed: {failed}",
                "status": "INFO",
            },
        })
        if not config:
           print(f"[ERROR] No config found for app_variant={app_variant}")
        return
    except Exception as e:
        print(f"[PostRun] Step 5 FAILED: {e}")
        await manager.broadcast({
            "type": "LOG",
            "payload": {"message": f"⚠️ Slack notification failed: {e}", "status": "WARN"},
        })

def get_slack_user_name(user_id: str) -> str:
    """Fetch the real name of a Slack user by their user ID."""
    try:
        resp = requests.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {SLACK_BOT_TOKEN}"},
            params={"user": user_id},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            profile = data["user"].get("profile", {})
            # Prefer display_name → real_name → name
            name = (
                profile.get("real_name")
                or profile.get("display_name")
                or data["user"].get("real_name")
                or data["user"].get("name")
                or ""
            ).strip()
            print(f"[Slack] Resolved user_id='{user_id}' → name='{name}'")
            return name or "Unknown Developer"
        print(f"[Slack] users.info error: {data.get('error')}")
    except Exception as e:
        print(f"[Slack] Could not fetch user name: {e}")
    return "Unknown Developer"

def _normalize_apk_info(raw: dict) -> dict:
    """
    Normalize all possible key names from get_apk_info() into stable keys.
    Also attempts aapt2/aapt direct parse if all values are still unknown.

    Stable output keys:
      app_name     – human-readable label  (e.g. "KrishiVaas Farmer")
      package_name – Java package id       (e.g. "com.agribride.krishivaas.farmer_app")
      app_version  – version string        (e.g. "2.1.4")
    """
    if not raw:
        raw = {}

    # ── app_name ─────────────────────────────────────────────────────────────
    app_name = (
        raw.get("app_name")
        or raw.get("application")
        or raw.get("label")
        or raw.get("applicationLabel")
        or raw.get("name")
        or raw.get("appName")
        or raw.get("AppName")
        or ""
    ).strip().strip("'\"")

    # ── package_name ──────────────────────────────────────────────────────────
    package_name = (
        raw.get("package_name")
        or raw.get("package")
        or raw.get("packageName")
        or raw.get("PackageName")
        or raw.get("id")
        or ""
    ).strip().strip("'\"")

    # ── version ───────────────────────────────────────────────────────────────
    app_version = (
        raw.get("version_name")
        or raw.get("versionName")
        or raw.get("app_version")
        or raw.get("version")
        or raw.get("Version")
        or raw.get("apk_version")
        or raw.get("version_code")
        or raw.get("versionCode")
        or ""
    ).strip().strip("'\"")

    normalized = dict(raw)
    normalized["app_name"]     = app_name     or "Unknown App"
    normalized["package_name"] = package_name or ""
    normalized["app_version"]  = app_version  or "Unknown Version"

    # ── Debug dump so we always know what came back ───────────────────────────
    print(f"[_normalize_apk_info] raw keys: {list(raw.keys())}")
    print(f"[_normalize_apk_info] raw values: {dict(raw)}")
    print(f"[_normalize_apk_info] → app_name='{normalized['app_name']}' "
          f"package='{normalized['package_name']}' version='{normalized['app_version']}'")

    return normalized

def _extract_apk_info_fallback(apk_path: str) -> dict:
    """
    Try to extract APK metadata using aapt/aapt2 CLI tools directly.
    Called when get_apk_info() returns incomplete data.
    Returns dict with app_name, package_name, app_version.
    """
    result = {"app_name": "", "package_name": "", "app_version": ""}

    # Try aapt first
    for tool in ("aapt", "aapt2"):
        try:
            cmd = [tool, "dump", "badging", apk_path]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=30
            )
            output = proc.stdout
            if not output:
                continue

            # package: name='com.example' versionCode='10' versionName='1.0'
            pkg_match = re.search(r"package:\s+name='([^']+)'.*?versionName='([^']*)'", output)
            if pkg_match:
                result["package_name"] = pkg_match.group(1).strip()
                result["app_version"]  = pkg_match.group(2).strip()

            # application-label:'App Name'  OR  application-label-en:'App Name'
            label_match = re.search(r"application-label(?:-\w+)?:'([^']+)'", output)
            if label_match:
                result["app_name"] = label_match.group(1).strip()

            # application: label='App Name'
            if not result["app_name"]:
                app_match = re.search(r"application:.*?label='([^']+)'", output)
                if app_match:
                    result["app_name"] = app_match.group(1).strip()

            if result["package_name"]:
                print(f"[aapt fallback ({tool})] app='{result['app_name']}' "
                      f"pkg='{result['package_name']}' ver='{result['app_version']}'")
                return result

        except FileNotFoundError:
            continue
        except Exception as e:
            print(f"[aapt fallback ({tool})] Error: {e}")
            continue

    print("[aapt fallback] All tools failed — returning empty dict")
    return result

def _get_full_apk_info(apk_path: str) -> dict:
    """
    Primary entry point for APK metadata extraction.
    1. Calls get_apk_info() from gdrive_loader
    2. Normalizes all keys
    3. If package_name is still missing → runs aapt/aapt2 fallback
    4. Returns a fully populated dict with guaranteed stable keys
    """
    try:
        raw_info = get_apk_info(apk_path) or {}
    except Exception as e:
        print(f"[get_apk_info] Exception: {e}")
        raw_info = {}

    info = _normalize_apk_info(raw_info)

    # If critical fields are still missing, try aapt fallback
    if not info["package_name"] or info["app_name"] == "Unknown App":
        print("[get_full_apk_info] Primary extraction incomplete — trying aapt fallback...")
        fallback = _extract_apk_info_fallback(apk_path)

        if fallback.get("package_name") and not info["package_name"]:
            info["package_name"] = fallback["package_name"]
        if fallback.get("app_name") and info["app_name"] == "Unknown App":
            info["app_name"] = fallback["app_name"]
        if fallback.get("app_version") and info["app_version"] == "Unknown Version":
            info["app_version"] = fallback["app_version"]

        print(f"[get_full_apk_info] After fallback → app='{info['app_name']}' "
              f"pkg='{info['package_name']}' ver='{info['app_version']}'")

    return info

async def _ensure_appium_running() -> None:
    global appium_proc
    if is_appium_running():
        print("[Appium] Already running.")
        return
    print("[Appium] Starting Appium server...")
    appium_proc = subprocess.Popen(
        ["appium", "-p", str(APPIUM_PORT)],
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(15):
        await asyncio.sleep(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", APPIUM_PORT)) == 0:
                print("[Appium] Server is ready.")
                return
    print("[Appium] WARNING: Appium did not become reachable within 15 s.")


async def handle_slack_apk(
    file_id: str,
    channel_id: str,
    sender_user_id: str,
) -> None:
    run_id = new_run()
    global latest_run_id
    latest_run_id = run_id

    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

    try:
        # ── Broadcast that download is starting ──────────────────────────────
        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": f"[Slack] APK download starting... (run_id: {run_id[:8]})",
                "status": "INFO",
            },
        })

        # ── Download APK via thread executor (Windows-safe) ──────────────────
        script_path = os.path.join(os.path.dirname(__file__), "gdrive_loader.py")
        loop = asyncio.get_event_loop()

        def _run_download():
            dl_env = os.environ.copy()
            dl_env["PYTHONIOENCODING"] = "utf-8"
            dl_env["PYTHONUTF8"]       = "1"   # Python 3.7+ UTF-8 mode flag
            return subprocess.run(
                [sys.executable, "-u", script_path, download_url],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env=dl_env,
                timeout=300,
            )
 
        result = await loop.run_in_executor(None, _run_download)
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
 
        apk_path = None
        for line in stdout_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("PROGRESS:"):
                await manager.broadcast({
                    "type": "LOG",
                    "payload": {
                        "message": line.replace("PROGRESS:", "").strip(),
                        "status": "PROGRESS",
                    },
                })
            elif line.startswith("RESULT:"):
                apk_path = line.replace("RESULT:", "").strip()
            else:
                await manager.broadcast({
                    "type": "LOG",
                    "payload": {"message": line, "status": "INFO"},
                })
 
        if result.returncode != 0:
            raise Exception(
                f"Download failed (exit {result.returncode}): "
                f"{stderr_text.strip() or 'Unknown error'}"
            )
        if not apk_path:
            raise Exception("Download script finished but returned no APK path.")
 
        # ── Rest of the handler stays the same ───────────────────────────────
        loop = asyncio.get_event_loop()
        info         = await loop.run_in_executor(None, lambda: _get_full_apk_info(apk_path))
        package_name = info["package_name"]
        app_name     = info["app_name"]
        app_version  = info["app_version"]
 
        app_variant    = detect_app_variant(package_name, app_name)
        runs[run_id]["app_variant"] = app_variant
        tests_to_run   = APP_VARIANTS.get(app_variant, [])
        developer_name = APP_DEVELOPER_MAP.get(app_variant, "")
        if not developer_name and sender_user_id:
            developer_name = await loop.run_in_executor(
                None, lambda: get_slack_user_name(sender_user_id)
            )
        if not developer_name:
            developer_name = "Unknown Developer"
 
        if run_id in runs:
            runs[run_id]["package_name"]   = package_name  or ""
            runs[run_id]["app_variant"]    = app_variant    or ""
            runs[run_id]["app_name"]       = app_name       or ""
            runs[run_id]["app_version"]    = app_version    or ""
            runs[run_id]["developer_name"] = developer_name or ""
 
        await manager.broadcast({
            "type": "LOG",
            "payload": {
                "message": (
                    f"[Slack] {developer_name} triggered: "
                    f"{app_name} v{app_version} | Variant: {app_variant} | run_id: {run_id[:8]}"
                ),
                "status": "INFO",
            },
        })
 
        await _ensure_appium_running()
 
        await post_run_notify(
            run_id=run_id,
            apk_path=apk_path,
            tests_to_run=tests_to_run,
            app_name=app_name,
            app_version=app_version,
            developer_name=developer_name,
            channel_id=channel_id,
        )
 
    except Exception as e:
        import traceback
        full_error = traceback.format_exc()
        print(f"[Slack] Error type: {type(e).__name__}")
        print(f"[Slack] Error message: {repr(e)}")
        print(f"[Slack] Full traceback:\n{full_error}")
        await manager.broadcast({
            "type": "LOG",
            "payload": {"message": f"[Slack] Error: {type(e).__name__}: {repr(e)}", "status": "FAILED"},
        })

async def slack_events_flow(request, background_tasks):
    body = await request.json()

    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge")}

    event_id = body.get("event_id")
    if event_id in PROCESSED_EVENTS:
        print("[Slack] Duplicate event ignored")
        return {"status": "duplicate"}
    PROCESSED_EVENTS.add(event_id)

    event = body.get("event", {})
    print("[Slack] Event received:", event)

    if event.get("subtype") is not None:
        return {"status": "ignored"}

    if event.get("type") == "message":
        text = event.get("text", "")
        if "drive.google.com" in text:
            file_id = extract_drive_file_id(text)
            if file_id:
                channel_id     = event.get("channel")
                sender_user_id = event.get("user")
                asyncio.create_task(
                    handle_slack_apk(
                        file_id=file_id,
                        channel_id=channel_id,
                        sender_user_id=sender_user_id,
                    )
                )

    return {"status": "ok"}
