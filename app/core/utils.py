import socket
import re
import datetime
import asyncio
import os
import shutil
import time
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from fastapi import HTTPException
from typing import List, Optional, Dict, Any
from app.core.websocket import manager
from app.core.state import test_steps_store, allure_proc
from app.core.constants import UI_SCREENSHOTS_BASE, BASE_DIR
from app.modules.jira.jira_service import calculate_duration, is_unknown

def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    
def resolve_steps_for_test(test_name: str) -> List[str]:
    """
    Called only by receive_jira_payload. Pops the matched bucket so
    the next test starts clean.

    Resolution order:
      1. Exact key  (test_name) — set when conftest sends [TEST_START:xxx]
      2. "default"  bucket      — set when no [TEST_START:] is used
      3. Empty list
    """
    if test_name and test_name in test_steps_store:
        steps = test_steps_store.pop(test_name)
        print(f"✅ Steps resolved (exact) → {test_name}: {steps}")
        return steps
    if "default" in test_steps_store:
        steps = test_steps_store.pop("default")
        print(f"✅ Steps resolved (default fallback) → {test_name}: {steps}")
        return steps
    print(f"⚠️  No steps in store for {test_name}")
    return []

def make_dismiss_key(payload: dict) -> str:
    tn = str(payload.get("test_name") or "").strip()
    md = str(payload.get("module")    or "").strip()
    if tn:
        return f"tn::{md}::{tn}"
    title = str(payload.get("issue_summary") or payload.get("title") or "").strip()
    return f"sum::{md}::{title}"

def latest_run_id() -> str:
    runs = [p for p in UI_SCREENSHOTS_BASE.iterdir() if p.is_dir()]
    if not runs:
        raise HTTPException(404, detail="No UI screenshots found. Run tests and capture screenshots first.")
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0].name

def extract_steps_from_numbered_list(text: str) -> List[str]:
    """
    Parse lines matching '1. Step text' from any block of text.
    Used as a fallback when steps_executed list is empty but the
    conftest already embedded them in the description string.
    Returns a de-duplicated list preserving order.
    """
    seen:  set   = set()
    steps: list  = []
    for line in text.splitlines():
        m = re.match(r'^\s*\d+\.\s+(.+)$', line)
        if m:
            step = m.group(1).strip()
            if step and step not in seen:
                seen.add(step)
                steps.append(step)
    return steps

def format_description_with_steps(
        description:    str,
        app_name:       Optional[str] = None,
        app_version:    Optional[str] = None,
        module:         Optional[str] = None,
        test_name:      Optional[str] = None,
        developer_name: Optional[str] = None,
        start_date:     Optional[str] = None,
        end_date:       Optional[str] = None,
        sprint:         Optional[str] = None,
        steps_executed: Optional[List[str]] = None,
    ) -> str:
        """
        Build a clean plain-text description:
        <error / base text>
        ==================================================
        METADATA
        ==================================================
        App / Version / Module / Test / Developer / Start / End / Duration / Sprint
        ==================================================
        STEPS EXECUTED
        ==================================================
        1. step …

        Strips any previously embedded steps / metadata blocks first so this
        function is safe to call repeatedly without causing duplication.
        """
        # 1. Remove any previously embedded steps/metadata from the raw description
        base = strip_embedded_steps_from_description(
            description.strip() if description else "Test automation failure detected."
        ).strip() or "Test automation failure detected."

        lines = [base, "", "=" * 50, "METADATA", "=" * 50]

        if app_name       and not is_unknown(app_name):       lines.append(f"App: {app_name}")
        if app_version    and not is_unknown(app_version):    lines.append(f"Version: {app_version}")
        if module         and not is_unknown(module):         lines.append(f"Module: {module}")
        if test_name      and not is_unknown(test_name):      lines.append(f"Test: {test_name}")
        if developer_name and not is_unknown(developer_name): lines.append(f"Developer: {developer_name}")
        if start_date:     lines.append(f"Start: {start_date}")
        if end_date:       lines.append(f"End: {end_date}")
        if start_date and end_date:
            lines.append(f"Duration: {calculate_duration(start_date, end_date)}")
        if sprint:         lines.append(f"Sprint: {sprint}")

        # 2. Append steps ONCE
        if steps_executed:
            lines += ["", "=" * 50, "STEPS EXECUTED", "=" * 50]
            for i, step in enumerate(steps_executed, 1):
                lines.append(f"{i}. {step}")

        return "\n".join(lines)

def _extract_steps_from_numbered_list(text: str) -> List[str]:
    """
    Parse lines matching '1. Step text' from any block of text.
    Used as a fallback when steps_executed list is empty but the
    conftest already embedded them in the description string.
    Returns a de-duplicated list preserving order.
    """
    seen:  set   = set()
    steps: list  = []
    for line in text.splitlines():
        m = re.match(r'^\s*\d+\.\s+(.+)$', line)
        if m:
            step = m.group(1).strip()
            if step and step not in seen:
                seen.add(step)
                steps.append(step)
    return steps

def strip_embedded_steps_from_description(text: str) -> str:
    """
    Remove any 'Steps Executed:' block AND any '==...== STEPS EXECUTED ==...=='
    block that the conftest or a previous formatting pass wrote into the
    description string, so we never render steps twice.

    Also removes the formatted METADATA block so format_description_with_steps
    can rebuild it cleanly.
    """
    if not text:
        return text

    lines  = text.splitlines()
    result = []
    skip   = False

    i = 0
    while i < len(lines):
        stripped = lines[i].strip()

        # ── Detect start of an embedded "Steps Executed:" prose block ──
        if re.match(r'^steps\s+executed\s*:?\s*$', stripped, re.IGNORECASE):
            skip = True
            i += 1
            continue

        # ── Detect start of a separator-bordered section header ──
        # Matches lines that are all '=' characters (our separator)
        if re.match(r'^={10,}$', stripped):
            # Peek at next non-blank line to see if it's a known header
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                header = lines[j].strip().upper()
                if header in ("STEPS EXECUTED", "METADATA"):
                    # Skip the separator + header + following separator
                    skip = (header == "STEPS EXECUTED")
                    if header == "METADATA":
                        # Skip entire METADATA block up to next separator or EOF
                        i = j + 1
                        # skip over trailing separator after header text
                        while i < len(lines) and not re.match(r'^={10,}$', lines[i].strip()):
                            i += 1
                        i += 1  # skip the closing separator itself
                        skip = False
                        continue
                    else:
                        # STEPS EXECUTED — skip separator, header, next separator, and content
                        i = j + 1
                        # skip closing separator
                        while i < len(lines) and not re.match(r'^={10,}$', lines[i].strip()):
                            i += 1
                        i += 1  # skip the closing separator
                        skip = False
                        continue

        # ── While inside a steps block, skip numbered lines ──
        if skip:
            if re.match(r'^\d+\.', stripped):
                i += 1
                continue
            else:
                # Non-numbered line ends the prose steps block
                skip = False

        result.append(lines[i])
        i += 1

    return "\n".join(result).rstrip()

# Pre-compiled step-capture patterns (checked in order; first match wins)
STEP_CAPTURE_PATTERNS: List[re.Pattern] = [
    # [FOUND] name='Foo'  or  [FOUND] name="Foo"
    re.compile(r'\[FOUND\]\s+name=[\'"]([^\'"]+)[\'"]', re.IGNORECASE),
    # [CLICK] some label  /  [TAP] ...  /  [PRESSED] ...  /  [TAPPED] ...
    re.compile(r'\[(?:CLICK|TAP|PRESSED|TAPPED)\]\s+(.+)', re.IGNORECASE),
    # [STEP] Step description
    re.compile(r'\[STEP\]\s+(.+)', re.IGNORECASE),
    # [ACTION] did something
    re.compile(r'\[ACTION\]\s+(.+)', re.IGNORECASE),
    # ✅ Step name  (emitted by Appium helper methods)
    re.compile(r'✅\s+(?:Step\s+)?[–—-]?\s*(.+)', re.IGNORECASE),
]

def parse_step_from_message(message: str) -> Optional[str]:
    """Return the captured step label from a log message, or None."""
    for pattern in STEP_CAPTURE_PATTERNS:
        m = pattern.search(message)
        if m:
            step = m.group(1).strip()
            if step:
                return step
    return None

def generate_run_id():
    return str(uuid.uuid4())


def current_timestamp():
    return datetime.utcnow().isoformat()