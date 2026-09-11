import asyncio
from fastapi import WebSocket
from fastapi import APIRouter
from starlette.websockets import WebSocketDisconnect

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        async with self._lock:
            connections = list(self.active_connections)

        if not connections:
            return

        async def safe_send(ws: WebSocket):
            try:
                await ws.send_json(message)
                return True
            except Exception:
                return False

        results = await asyncio.gather(
            *(safe_send(ws) for ws in connections),
            return_exceptions=True
        )

        for ws, ok in zip(connections, results):
            if ok is not True:
                await self.disconnect(ws)


# ✅ GLOBAL INSTANCE (IMPORTANT)
manager = ConnectionManager()

@router.websocket("/test-status")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Most frontends never send messages; this just keeps the socket open
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)

print("WebSocket manager initialized")

class TestRunManager:

    def __init__(self):
        self.running_tests = {}

    def start_test(self, run_id, process):
        self.running_tests[run_id] = process

    def stop_test(self, run_id):
        if run_id in self.running_tests:
            process = self.running_tests[run_id]
            process.kill()
            del self.running_tests[run_id]

    def get_active_runs(self):
        return list(self.running_tests.keys())


test_manager = TestRunManager()