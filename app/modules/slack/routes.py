from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from .service import slack_events_flow
router = APIRouter()

@router.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks):
    return await slack_events_flow(request, background_tasks)
