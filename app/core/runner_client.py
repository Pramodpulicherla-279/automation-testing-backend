"""HTTP client for the automation runner.

The runner (automation-testing/runner) owns everything that has to happen on the
machine with the Android device: device status, Appium, APK storage, pytest
runs, Allure and reading test sources. The backend reaches it at RUNNER_URL, so
the backend itself can run anywhere, including a cloud host with none of those.
"""

import asyncio
import os
import secrets

import requests
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

RUNNER_URL = (os.getenv("RUNNER_URL") or "http://localhost:8100").rstrip("/")
RUNNER_TOKEN = os.getenv("RUNNER_TOKEN", "")

# Downloading an APK from Google Drive happens inside the prepare call.
DOWNLOAD_TIMEOUT = 30 * 60


class RunnerUnavailable(RuntimeError):
    """The runner can't be used, so nothing machine-bound can be done right now."""


def call(method: str, path: str, *, json=None, params=None, timeout: float = 10):
    try:
        resp = requests.request(
            method, f"{RUNNER_URL}{path}", json=json, params=params,
            headers={"X-Runner-Token": RUNNER_TOKEN}, timeout=timeout,
        )
    except requests.RequestException as exc:
        raise RunnerUnavailable(
            f"The test runner at {RUNNER_URL} is unreachable ({type(exc).__name__}). "
            f"Start it on the machine with the Android device, and check RUNNER_URL."
        ) from exc

    if resp.status_code == 401:
        raise RunnerUnavailable(
            "The test runner rejected this backend's RUNNER_TOKEN. "
            "Set the same RUNNER_TOKEN on the backend and the runner."
        )
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        # Client errors are meaningful to the UI (busy, unknown APK, bad path);
        # anything else means the runner itself broke.
        raise HTTPException(status_code=resp.status_code if resp.status_code < 500 else 502,
                            detail=detail)
    return resp.json()


async def acall(method: str, path: str, **kwargs):
    return await asyncio.to_thread(call, method, path, **kwargs)


def is_runner_token(token: str) -> bool:
    """Authenticate a callback that claims to come from the runner."""
    return bool(RUNNER_TOKEN) and secrets.compare_digest(token.encode(), RUNNER_TOKEN.encode())
