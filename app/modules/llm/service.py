import asyncio
from pathlib import Path
import subprocess
import sys
import json
from fastapi import HTTPException
from app.core.logger import logger
from app.core.utils import latest_run_id
from app.core.constants import UI_SCREENSHOTS_BASE
from .generate_jira_desc import generate_jira_description, generate_jira_title


async def enhance_jira_issue_flow(req):
    """
    Calls Gemini to generate a polished title + full formatted description
    (with Steps to Reproduce, Actual Result, Expected Result) and returns
    them so the frontend can paste directly into the issue card fields.
    """
 
    issue_data = req.model_dump(exclude_none=True)
 
    try:
        loop = asyncio.get_event_loop()
 
        # Run both calls concurrently
        enhanced_description, enhanced_title = await asyncio.gather(
            loop.run_in_executor(None, generate_jira_description, issue_data),
            loop.run_in_executor(None, generate_jira_title, issue_data),
        )
 
    except Exception as exc:
        logger.error("[/llm/enhance] Gemini call failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail=f"LLM enhancement failed: {str(exc)}",
        )
 
    logger.info(
        "[/llm/enhance] Enhanced issue_id=%s title='%s'",
        req.issue_id, enhanced_title,
    )
 
    return {
        "status":      "enhanced",
        "issue_id":    req.issue_id,
        "title":       enhanced_title,
        "description": enhanced_description,
    }

async def analyze_ui_screenshots_flow(req):
    print("UI parser api called")
    run_id = req.run_id or latest_run_id()
    print(run_id)
    run_dir = UI_SCREENSHOTS_BASE / run_id
    if not run_dir.exists():
        raise HTTPException(404, detail=f"Run screenshots folder not found: {run_id}")

    # The ui-parser validator and the screenshots live on the runner's machine,
    # and this analysis hasn't been moved onto the runner yet.
    raise HTTPException(503, detail="UI screenshot analysis runs on the test runner and isn't wired to it yet.")

    # Call validator as subprocess to avoid import issues (folder name ui-parser has a hyphen)
    cmd = [sys.executable, str(validator), "--root-dir", str(run_dir)]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        raise HTTPException(500, detail=f"UI validator failed: {proc.stderr.strip() or proc.stdout.strip()}")

    payload = json.loads(proc.stdout or "{}")
    results = payload.get("results", [])

    # Add screenshot_url expected by your React component
    for r in results:
        rel = r.get("relative_path")
        r["screenshot_url"] = f"/ui-screenshots/{run_id}/{rel}" if rel else None

    return {"run_id": run_id, "results": results}
