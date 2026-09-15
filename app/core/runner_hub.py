"""Connection to the test runner on the laptop.

The runner (automation-testing/runner) dials OUT to this backend over a
WebSocket and keeps it open. Commands for the device, Appium, APKs and runs go
down that socket and replies come back up it, so the backend never needs the
laptop's address and the laptop needs no inbound port or tunnel.

There is no authentication: whatever connects to /runner/ws is the runner, and
the newest connection replaces an older one, which is also what lets the laptop
reconnect after a dropped link. Connection state lives in this process, so run
the backend as a single worker.
"""

import asyncio
import time
import uuid
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

# Downloading an APK from a Drive link happens inside one prepare_apk command.
DOWNLOAD_TIMEOUT = 30 * 60
# Heartbeats arrive every few seconds; anything older means the runner is gone.
STATUS_MAX_AGE = 15


class RunnerUnavailable(Exception):
    """No runner can take the request right now."""


class RunnerHub:
    def __init__(self) -> None:
        self._ws: Optional[WebSocket] = None
        self._runner_name: Optional[str] = None
        self._connected_at: Optional[float] = None
        self._status: dict = {}
        self._status_at = 0.0
        self._pending: dict[str, asyncio.Future] = {}
        self._send_lock = asyncio.Lock()
        self._event_handlers: dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._tasks: set[asyncio.Task] = set()

    # ── State for the UI and the status polls ───────────────────────────────

    def status(self) -> dict:
        connected = self._ws is not None
        return {
            "connected": connected,
            "runner": self._runner_name if connected else None,
            "connected_at": self._connected_at,
            "busy": bool(connected and self._status.get("active_run")),
        }

    def heartbeat(self) -> Optional[dict]:
        """The runner's latest pushed status, or None if it isn't connected or has gone quiet."""
        if self._ws is None or time.monotonic() - self._status_at > STATUS_MAX_AGE:
            return None
        return self._status

    def on_event(self, name: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._event_handlers[name] = handler

    # ── The connection ──────────────────────────────────────────────────────

    async def serve(self, ws: WebSocket) -> None:
        if self._ws is not None:
            stale, self._ws = self._ws, None
            self._fail_pending("The test runner was replaced by a new connection.")
            try:
                await stale.close(code=4000)
            except Exception:
                pass

        await ws.accept()
        name = ws.headers.get("x-runner-name") or (ws.client.host if ws.client else "") or "unknown"
        self._ws, self._runner_name, self._connected_at = ws, name[:100], time.time()
        self._status, self._status_at = {}, 0.0
        try:
            while True:
                self._dispatch(await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            if self._ws is ws:
                self._ws = None
                self._runner_name = None
                self._connected_at = None
                self._status = {}
                self._fail_pending("The test runner disconnected.")

    def _dispatch(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "reply":
            future = self._pending.pop(message.get("id"), None)
            if future is not None and not future.done():
                future.set_result(message)
        elif kind == "status":
            self._status, self._status_at = message.get("status") or {}, time.monotonic()
        elif kind == "event":
            handler = self._event_handlers.get(message.get("name"))
            if handler is not None:
                task = asyncio.create_task(handler(message.get("payload") or {}))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RunnerUnavailable(reason))
        self._pending.clear()

    async def request(self, action: str, payload: Optional[dict] = None, *, timeout: float = 30):
        """Send a command to the runner and wait for its reply."""
        ws = self._ws
        if ws is None:
            raise RunnerUnavailable(
                "No test runner is connected. On the laptop, run `python -m runner` in the "
                "automation-testing repo with BACKEND_URL set to this backend."
            )
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            async with self._send_lock:
                await ws.send_json({"type": "command", "id": request_id,
                                    "action": action, "payload": payload or {}})
            reply = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise RunnerUnavailable(f"The test runner didn't answer '{action}' within {timeout:.0f}s.") from None
        except (WebSocketDisconnect, RuntimeError) as exc:
            raise RunnerUnavailable("The test runner disconnected.") from exc
        finally:
            self._pending.pop(request_id, None)

        if reply.get("ok"):
            return reply.get("result")
        status = int(reply.get("status") or 500)
        # Client errors mean something to the UI (busy, unknown APK, bad path);
        # anything else means the runner itself broke.
        raise HTTPException(status_code=status if status < 500 else 502,
                            detail=reply.get("detail") or f"The test runner failed '{action}'.")


hub = RunnerHub()
