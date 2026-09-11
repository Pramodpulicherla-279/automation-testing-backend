
from fastapi import APIRouter
from .models import JiraEnhanceRequest, AnalyzeReq
from .service import enhance_jira_issue_flow, analyze_ui_screenshots_flow
router = APIRouter()


@router.post("/enhance")
async def enhance_jira_issue(req: JiraEnhanceRequest):
    return await enhance_jira_issue_flow(req)

@router.post("/ui-screenshots/analyze")
async def analyze_ui_screenshots(req: AnalyzeReq):
    return await analyze_ui_screenshots_flow(req)
