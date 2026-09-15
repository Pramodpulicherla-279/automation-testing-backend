"""Which laptops have a test runner connected, and the WebSocket they connect to.

See app/core/runner_hub.py for how the connections work.
"""

from fastapi import APIRouter, WebSocket

from app.core.runner_hub import hub

router = APIRouter()


@router.get("/status")
async def runner_status():
    """{"connected": bool, "runners": [{id, device_connected, device, appium, busy, connected_at}]}"""
    return hub.status()


@router.websocket("/ws")
async def runner_socket(ws: WebSocket):
    await hub.serve(ws)
