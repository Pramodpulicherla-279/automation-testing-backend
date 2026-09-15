"""Status of the laptop's test runner, and the WebSocket it connects to.

See app/core/runner_hub.py for how the connection works.
"""

from fastapi import APIRouter, WebSocket

from app.core.runner_hub import hub

router = APIRouter()


@router.get("/status")
async def runner_status():
    return hub.status()


@router.websocket("/ws")
async def runner_socket(ws: WebSocket):
    await hub.serve(ws)
