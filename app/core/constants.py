import os
from pathlib import Path
import threading
from dotenv import load_dotenv
load_dotenv() 

from app.core.paths import ALLURE_REPORT_DIR as _ALLURE_REPORT_DIR, TESTS_ROOT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(os.path.abspath(__file__))))
ALLURE_CMD = os.getenv("ALLURE_CMD", r"C:\Users\Pramo\scoop\shims\allure")
# pytest writes allure-results/ and generates allure-report/ inside the tests repo.
ALLURE_REPORT_DIR = str(_ALLURE_REPORT_DIR)
ALLURE_CWD = str(TESTS_ROOT)

UI_SCREENSHOTS_BASE = Path(__file__).resolve().parents[1] / "artifacts" / "ui_screenshots"
UI_SCREENSHOTS_BASE.mkdir(parents=True, exist_ok=True)
allure_start_lock = threading.Lock()
SLACK_BOT_TOKEN      = os.getenv("SLACK_BOT_TOKEN")
SLACK_NOTIFY_CHANNEL = os.getenv("SLACK_NOTIFY_CHANNEL")
print(f"Loaded SLACK_BOT_TOKEN: {SLACK_BOT_TOKEN}, SLACK_NOTIFY_CHANNEL: {SLACK_NOTIFY_CHANNEL}")