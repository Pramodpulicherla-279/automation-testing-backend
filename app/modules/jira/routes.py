from fastapi import APIRouter
from .service import health_flow, jira_test_connection_flow, get_steps_flow, add_step_flow, reset_steps_flow, receive_jira_payload_flow, get_pending_payloads_flow, dismiss_payload_flow, jira_create_flow, add_comment_flow, jira_history_api_flow, list_jira_tickets_flow, jira_stats_slow
from .models import JiraPayloadRequest, JiraCreateRequest
from app.core.state import jira_history, jira_comments

router = APIRouter()

@router.get("/health")
async def health():
    return await health_flow()

@router.get("/test-connection")
async def jira_test_connection():
    return await jira_test_connection_flow()

@router.get("/steps/{test_name}")
async def get_steps(test_name: str):
    return await get_steps_flow(test_name)

@router.post("/steps")
async def add_step(data: dict):
    return await add_step_flow(data)

@router.post("/reset-steps")
async def reset_steps():
    return await reset_steps_flow()

@router.post("/payload")
async def receive_jira_payload(req: JiraPayloadRequest):
    return await receive_jira_payload_flow(req)

@router.get("/payloads")
async def get_pending_payloads():
    return await get_pending_payloads_flow()

@router.post("/dismiss")
async def dismiss_payload(data: dict):
    return await dismiss_payload_flow(data)

@router.post("/create")
async def jira_create(req: JiraCreateRequest):
    return await jira_create_flow(req)

@router.get("/history")
async def jira_history_api():
    return await jira_history_api_flow()

@router.get("/comments/{issue_key}")
async def get_comments(issue_key: str):
    return {"comments": jira_comments.get(issue_key, [])}

@router.post("/comments/{issue_key}")
async def add_comment(issue_key: str, data: dict):
    return await add_comment_flow(issue_key, data)
   
@router.get("/history")
async def jira_history_legacy():
    return {"issues": [
        {"key": e.get("issue_id",""), "summary": e.get("title",""),
         "status": e.get("status","Assigned"), "url": e.get("issue_url",""),
         "priority": e.get("priority",""), "assignee": e.get("developer_name",""),
         "updated": e.get("created_at","")}
        for e in jira_history
    ]}    

@router.get("/tickets")
async def list_jira_tickets():
    return await list_jira_tickets_flow()


@router.get("/stats")
async def jira_stats():
    return await jira_stats_slow()