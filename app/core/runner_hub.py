"""Connections to the test runners on the laptops.

Each laptop's runner (automation-testing/runner) dials OUT to this backend over a
WebSocket and keeps it open, so the backend never needs a laptop's address and
the laptops need no inbound port or tunnel. Commands for a laptop's device,
Appium, APKs and runs go down its socket and replies come back up it.

Runners are identified by the name they send (the laptop's hostname by
default). A new connection under a name that is already connected replaces the
old one, which is how a laptop reconnects after a dropped link. There is no
authentication. Connection state lives in this process, so run the backend as a
single worker.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from fastapi import HTTPException, WebSocket, WebSocketDisconnect

# Downloading an APK from a Drive link happens inside one prepare_apk command.
DOWNLOAD_TIMEOUT = 30 * 60
# Heartbeats arrive every few seconds; anything older means the laptop has gone quiet.
STATUS_MAX_AGE = 15


class RunnerUnavailable(Exception):
    """No runner can take the request right now."""


@dataclass
class _Runner:
    ws: WebSocket
    connected_at: float
    status: dict = field(default_factory=dict)
    status_at: float = 0.0
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def fresh_status(self) -> dict:
        return self.status if time.monotonic() - self.status_at <= STATUS_MAX_AGE else {}


class RunnerHub:
    def __init__(self) -> None:
        self._runners: dict[str, _Runner] = {}
        self._pending: dict[str, tuple[str, asyncio.Future]] = {}
        self._event_handlers: dict[str, Callable[[dict], Awaitable[None]]] = {}
        self._tasks: set[asyncio.Task] = set()

    # ── Which laptops are there ─────────────────────────────────────────────

    def runners(self) -> list[dict]:
        listed = []
        for name, runner in sorted(self._runners.items()):
            status = runner.fresh_status()
            listed.append({
                "id": name,
                "connected_at": runner.connected_at,
                "device_connected": bool(status.get("device_connected")),
                "device": status.get("device"),
                "appium": status.get("appium", "stopped"),
                "busy": bool(status.get("active_run")),
            })
        return listed

    def status(self) -> dict:
        runners = self.runners()
        return {"connected": bool(runners), "runners": runners}

    def _resolve(self, runner: Optional[str], *, any_runner: bool = False) -> str:
        if runner:
            if runner in self._runners:
                return runner
            raise RunnerUnavailable(f"Laptop '{runner}' isn't connected. Start its runner, or pick another laptop.")
        if not self._runners:
            raise RunnerUnavailable(
                "No test runner is connected. On a laptop, start the runner (`python -m runner` in the "
                "automation-testing repo, or its auto-start task) with BACKEND_URL set to this backend."
            )
        if len(self._runners) > 1 and not any_runner:
            raise RunnerUnavailable("Several laptops are connected; choose which one to use.")
        # Every laptop has the same suite, so where any will do, prefer one that isn't busy.
        idle = [name for name, r in self._runners.items() if not r.fresh_status().get("active_run")]
        return (idle or list(self._runners))[0]

    def heartbeat(self, runner: Optional[str] = None) -> Optional[dict]:
        """A laptop's latest pushed status, or None if it isn't connected or has gone quiet."""
        try:
            name = self._resolve(runner)
        except RunnerUnavailable:
            return None
        return self._runners[name].fresh_status() or None

    def on_event(self, name: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._event_handlers[name] = handler

    # ── The connections ─────────────────────────────────────────────────────

    async def serve(self, ws: WebSocket) -> None:
        name = (ws.headers.get("x-runner-name") or (ws.client.host if ws.client else "") or "unknown")[:100]
        stale = self._runners.pop(name, None)
        if stale is not None:
            self._fail_pending(name, "The test runner reconnected.")
            try:
                await stale.ws.close(code=4000)
            except Exception:
                pass

        await ws.accept()
        runner = _Runner(ws=ws, connected_at=time.time())
        self._runners[name] = runner
        try:
            while True:
                self._dispatch(runner, await ws.receive_json())
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            if self._runners.get(name) is runner:
                del self._runners[name]
                self._fail_pending(name, "The test runner disconnected.")

    def _dispatch(self, runner: _Runner, message: dict) -> None:
        kind = message.get("type")
        if kind == "reply":
            entry = self._pending.pop(message.get("id"), None)
            if entry is not None and not entry[1].done():
                entry[1].set_result(message)
        elif kind == "status":
            runner.status, runner.status_at = message.get("status") or {}, time.monotonic()
        elif kind == "event":
            handler = self._event_handlers.get(message.get("name"))
            if handler is not None:
                task = asyncio.create_task(handler(message.get("payload") or {}))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    def _fail_pending(self, name: str, reason: str) -> None:
        for request_id, (owner, future) in list(self._pending.items()):
            if owner == name:
                del self._pending[request_id]
                if not future.done():
                    future.set_exception(RunnerUnavailable(reason))

    async def request(self, action: str, payload: Optional[dict] = None, *, runner: Optional[str] = None,
                      any_runner: bool = False, timeout: float = 30):
        """Send a command to a laptop's runner and wait for its reply.

        `runner` names the laptop; it may be omitted when only one is connected,
        or when `any_runner` is set because any laptop can answer.
        """
        name = self._resolve(runner, any_runner=any_runner)
        target = self._runners[name]
        request_id = uuid.uuid4().hex
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (name, future)
        try:
            async with target.send_lock:
                await target.ws.send_json({"type": "command", "id": request_id,
                                           "action": action, "payload": payload or {}})
            reply = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            raise RunnerUnavailable(f"Laptop '{name}' didn't answer '{action}' within {timeout:.0f}s.") from None
        except (WebSocketDisconnect, RuntimeError) as exc:
            raise RunnerUnavailable(f"Laptop '{name}' disconnected.") from exc
        finally:
            self._pending.pop(request_id, None)

        if reply.get("ok"):
            return reply.get("result")
        status = int(reply.get("status") or 500)
        # Client errors mean something to the UI (busy, unknown APK, bad path);
        # anything else means the runner itself broke.
        raise HTTPException(status_code=status if status < 500 else 502,
                            detail=reply.get("detail") or f"Laptop '{name}' failed '{action}'.")


hub = RunnerHub()
