"""
test_management/runner.py
────────────────────────────
Interface between the backend and the automation execution engine.

The backend never executes automation logic directly — it only talks to
AutomationRunnerService. Implemented as a mock for now; a real Appium-backed
implementation (potentially bridging into app.modules.test_runner)
can be swapped in later without touching service.py or routes.py.
"""

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class RunnerResult:
    testcase_id: str
    status: str  # "PASSED" | "FAILED"
    execution_time: float
    device_name: str
    os_version: str
    browser: str | None
    failure_reason: str | None
    started_at: datetime
    completed_at: datetime
    log_lines: list[tuple[str, str]] = field(default_factory=list)  # (level, message)


class AutomationRunnerService(ABC):
    @abstractmethod
    def run_tests(
        self, testcase_ids: list[str], environment: str | None, execution_type: str | None
    ) -> list[RunnerResult]: ...

    @abstractmethod
    def get_status(self, run_id: str) -> str: ...

    @abstractmethod
    def cancel_execution(self, run_id: str) -> bool: ...


_DEVICES = [
    ("Pixel 6", "Android 13"),
    ("Galaxy S21", "Android 12"),
    ("Chrome Desktop", "Windows 11"),
]

_FAILURES = [
    "Element not found: locator timed out after 10s",
    "Assertion failed: expected status 200, got 500",
    "App crashed during navigation",
    "Network timeout while loading page",
]


class MockRunnerService(AutomationRunnerService):
    """Fabricates plausible pass/fail results. Stands in for a real Appium-backed
    runner until one is wired up (see module docstring)."""

    def run_tests(
        self, testcase_ids: list[str], environment: str | None, execution_type: str | None
    ) -> list[RunnerResult]:
        results: list[RunnerResult] = []
        for testcase_id in testcase_ids:
            started = datetime.utcnow()
            passed = random.random() < 0.8
            duration = round(random.uniform(2.0, 45.0), 2)
            device, os_version = random.choice(_DEVICES)

            logs: list[tuple[str, str]] = [
                ("INFO", f"Starting execution for test case {testcase_id}"),
                ("INFO", f"Environment: {environment or 'default'}"),
            ]
            if passed:
                status, reason = "PASSED", None
                logs.append(("INFO", "All assertions passed"))
            else:
                status = "FAILED"
                reason = random.choice(_FAILURES)
                logs.append(("ERROR", reason))

            results.append(
                RunnerResult(
                    testcase_id=testcase_id,
                    status=status,
                    execution_time=duration,
                    device_name=device,
                    os_version=os_version,
                    browser=None,
                    failure_reason=reason,
                    started_at=started,
                    completed_at=started + timedelta(seconds=duration),
                    log_lines=logs,
                )
            )
        return results

    def get_status(self, run_id: str) -> str:
        return "COMPLETED"

    def cancel_execution(self, run_id: str) -> bool:
        return True


# ─────────────────────────────
# Singleton instance
# ─────────────────────────────
runner_service = MockRunnerService()
