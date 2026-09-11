"""Filesystem roots shared by the backend.

The automation suite lives in its own repo (`automation-testing`) since the mono
repo was split, but the backend still runs it, parses its sources and serves its
Allure output. Set TESTS_REPO_PATH when the two checkouts are not siblings.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Loaded here rather than relying on a caller, since whichever module imports
# this one first decides whether TESTS_REPO_PATH is visible.
load_dotenv()

BACKEND_ROOT = Path(__file__).resolve().parents[2]

TESTS_ROOT = Path(
    os.getenv("TESTS_REPO_PATH") or BACKEND_ROOT.parent / "automation-testing"
).expanduser().resolve()

TESTS_DIR = TESTS_ROOT / "tests"
UI_PARSER_DIR = TESTS_ROOT / "ui-parser"
ALLURE_RESULTS_DIR = TESTS_ROOT / "allure-results"
ALLURE_REPORT_DIR = TESTS_ROOT / "allure-report"


def ensure_tests_importable() -> str:
    """Put the tests repo on sys.path so `import tests.…` resolves, and return it."""
    root = str(TESTS_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


# ── Runtime data ────────────────────────────────────────────────────────────
# APKs and their extracted icons are uploaded/downloaded at runtime and are far
# too large to live in the repo, where a redeploy or fresh clone would lose
# them. They go to a machine-wide location instead — on Windows that is shared
# across user accounts, which matters because the backend runs under a secondary
# one. CI sets PLATFORM_DATA_DIR to a workspace or cache path.

def _default_data_root() -> Path:
    program_data = os.environ.get("PROGRAMDATA")
    if os.name == "nt" and program_data:
        return Path(program_data) / "TestAutomationPlatform"
    return Path.home() / ".test-automation-platform"


DATA_ROOT = Path(
    os.getenv("PLATFORM_DATA_DIR") or _default_data_root()
).expanduser().resolve()

APK_STORAGE_DIR = Path(
    os.getenv("APK_STORAGE_DIR") or DATA_ROOT / "apks"
).expanduser().resolve()

APK_ICON_DIR = Path(
    os.getenv("APK_ICON_DIR") or DATA_ROOT / "icons"
).expanduser().resolve()


def ensure_apk_dirs() -> None:
    APK_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    APK_ICON_DIR.mkdir(parents=True, exist_ok=True)


def resolve_apk(name: str) -> Path:
    """Resolve a client-supplied APK filename inside the storage dir.

    The name arrives from the UI, so it is reduced to a bare filename before
    joining — otherwise `../` in it would reach anywhere on the machine.
    """
    safe = os.path.basename(str(name or "").strip())
    if not safe or safe in (".", ".."):
        raise ValueError(f"Invalid APK name: {name!r}")
    return APK_STORAGE_DIR / safe
