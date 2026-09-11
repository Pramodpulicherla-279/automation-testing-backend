"""
test_management/models.py
────────────────────────────
Pydantic request/response schemas for the Test Management module.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────
# Status-ish free-text VARCHAR columns — validated here at the API layer,
# not constrained in the DB (which just stores VARCHAR).
# ─────────────────────────────
TestResultStatus = Literal["PASSED", "FAILED", "SKIPPED", "BLOCKED", "PENDING"]
ExecutionType = Literal["Automated", "Manual"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
BugSeverity = Literal["Critical", "Major", "Minor", "Trivial"]
BugStatus = Literal["Open", "In Progress", "Resolved", "Closed", "Reopened"]
Polarity = Literal["Positive", "Negative"]

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200

# ─────────────────────────────
# Common
# ─────────────────────────────
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


# ─────────────────────────────
# Applications
# ─────────────────────────────
class ApplicationBase(BaseModel):
    application_name: str = Field(..., max_length=150)
    platform: str = Field(..., max_length=30)
    package_name: str | None = Field(None, max_length=255)
    # Automation role key: regular_farmer | regular_client | state_farmer | state_client
    variant: str | None = Field(None, max_length=30)
    description: str | None = None
    status: bool = True


class ApplicationCreate(ApplicationBase):
    pass


class ApplicationUpdate(BaseModel):
    application_name: str | None = Field(None, max_length=150)
    platform: str | None = Field(None, max_length=30)
    package_name: str | None = Field(None, max_length=255)
    variant: str | None = Field(None, max_length=30)
    description: str | None = None
    status: bool | None = None


class ApplicationRead(ApplicationBase):
    model_config = ConfigDict(from_attributes=True)

    application_id: int
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────
# Modules
# ─────────────────────────────
class ModuleBase(BaseModel):
    application_id: int
    module_name: str = Field(..., max_length=150)
    description: str | None = None
    display_order: int = 0
    status: bool = True


class ModuleCreate(ModuleBase):
    pass


class ModuleUpdate(BaseModel):
    module_name: str | None = Field(None, max_length=150)
    description: str | None = None
    display_order: int | None = None
    status: bool | None = None


class ModuleRead(ModuleBase):
    model_config = ConfigDict(from_attributes=True)

    module_id: int
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────
# Priorities
# ─────────────────────────────
class PriorityBase(BaseModel):
    priority_name: str = Field(..., max_length=50)
    color: str | None = Field(None, max_length=30)
    display_order: int = 0


class PriorityCreate(PriorityBase):
    pass


class PriorityUpdate(BaseModel):
    priority_name: str | None = Field(None, max_length=50)
    color: str | None = Field(None, max_length=30)
    display_order: int | None = None


class PriorityRead(PriorityBase):
    model_config = ConfigDict(from_attributes=True)

    priority_id: int


# ─────────────────────────────
# Test Cases
# ─────────────────────────────
class TestCaseBase(BaseModel):
    title: str = Field(..., max_length=300)
    application_id: int
    module_id: int
    priority_id: int | None = None
    test_types: list[str] = Field(default_factory=list)
    polarity: Polarity | None = None
    description: str | None = None
    expected_result: str | None = None
    automation_enabled: bool = True
    status: bool = True


class TestCaseCreate(TestCaseBase):
    testcase_key: str | None = Field(None, max_length=50, description="Auto-generated if omitted")


class TestCaseUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    module_id: int | None = None
    priority_id: int | None = None
    test_types: list[str] | None = None
    polarity: Polarity | None = None
    description: str | None = None
    expected_result: str | None = None
    automation_enabled: bool | None = None
    status: bool | None = None


class TestCaseRead(TestCaseBase):
    model_config = ConfigDict(from_attributes=True)

    testcase_id: int
    testcase_key: str
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────
# Test Run Results
# ─────────────────────────────
class TestRunResultBase(BaseModel):
    run_id: int | None = None
    testcase_id: int | None = None
    status: TestResultStatus | None = None
    execution_time: Decimal | None = None
    device_name: str | None = None
    os_version: str | None = None
    browser: str | None = None
    failure_reason: str | None = None
    allure_report: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class TestRunResultCreate(TestRunResultBase):
    pass


class TestRunResultUpdate(BaseModel):
    status: TestResultStatus | None = None
    execution_time: Decimal | None = None
    device_name: str | None = None
    os_version: str | None = None
    browser: str | None = None
    failure_reason: str | None = None
    allure_report: str | None = None
    completed_at: datetime | None = None


class TestRunResultRead(TestRunResultBase):
    model_config = ConfigDict(from_attributes=True)

    execution_id: int


# ─────────────────────────────
# Test Runs
# ─────────────────────────────
class TestRunCreate(BaseModel):
    application_id: int
    module_id: int | None = None
    test_type: str | None = None
    environment: str | None = None
    build_number: str | None = None
    execution_type: ExecutionType = "Automated"
    triggered_by: str | None = None
    run_name: str | None = None


class TestRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    run_name: str | None
    application_id: int | None
    module_id: int | None
    test_type: str | None
    environment: str | None
    build_number: str | None
    execution_type: str | None
    triggered_by: str | None
    status: str | None
    started_at: datetime | None
    completed_at: datetime | None


class TestRunDetailRead(TestRunRead):
    results: list[TestRunResultRead] = Field(default_factory=list)


class RunTestsSummary(BaseModel):
    run: TestRunRead
    total: int
    passed: int
    failed: int
    skipped: int
    results: list[TestRunResultRead]


# ── Live pytest run reporting (real Appium runs) ──────────────────────────────
class PytestRunStart(BaseModel):
    app_type: str | None = None       # automation variant; resolved to application_id
    run_name: str | None = None
    environment: str | None = None
    build_number: str | None = None
    triggered_by: str | None = None


class PytestResultRecord(BaseModel):
    test_name: str                    # source `def` name, e.g. test_LOGINPOS_TC_029
    status: str                       # pytest outcome (passed/failed/skipped); normalized server-side
    execution_time: float | None = None
    failure_reason: str | None = None
    device_name: str | None = None
    os_version: str | None = None
    browser: str | None = None


class PytestRunFinish(BaseModel):
    status: str | None = None         # explicit status; otherwise derived from recorded results
    exit_status: int | None = None


# ─────────────────────────────
# Execution Logs
# ─────────────────────────────
class ExecutionLogEntry(BaseModel):
    log_level: LogLevel = "INFO"
    message: str


class ExecutionLogBulkCreate(BaseModel):
    execution_id: int
    logs: list[ExecutionLogEntry] = Field(default_factory=list)


class ExecutionLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    log_id: int
    execution_id: int | None
    log_level: str | None
    message: str | None
    created_at: datetime


# ─────────────────────────────
# Attachments
# ─────────────────────────────
class AttachmentBase(BaseModel):
    execution_id: int | None = None
    file_name: str | None = Field(None, max_length=255)
    file_type: str | None = Field(None, max_length=50)
    file_url: str | None = None


class AttachmentCreate(AttachmentBase):
    pass


class AttachmentUpdate(BaseModel):
    file_name: str | None = Field(None, max_length=255)
    file_type: str | None = Field(None, max_length=50)
    file_url: str | None = None


class AttachmentRead(AttachmentBase):
    model_config = ConfigDict(from_attributes=True)

    attachment_id: int
    uploaded_at: datetime


# ─────────────────────────────
# Bugs
# ─────────────────────────────
class BugCreate(BaseModel):
    execution_id: int | None = None
    testcase_id: int | None = None
    bug_title: str = Field(..., max_length=255)
    severity: BugSeverity
    status: BugStatus = "Open"
    jira_ticket: str | None = Field(None, max_length=100)


class BugRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bug_id: int
    execution_id: int | None
    testcase_id: int | None
    bug_title: str | None
    severity: str | None
    status: str | None
    jira_ticket: str | None
    created_at: datetime


# ─────────────────────────────
# Automation discovery (matches DB test cases to real source code)
# ─────────────────────────────
class AutomationTestCase(BaseModel):
    id: str | None = None          # split from "ID -- desc" allure title, if present
    title: str
    function_name: str             # the source `def` name — used to match a DB testcase_key
    line: int
    match_key: str | None = None   # function_name with tc_/test_ prefix stripped (for DB matching)


class TypeFolderTest(AutomationTestCase):
    file: str                      # repo-relative path under tests/test_suites/<type>/
    app: str = ""                  # per-app subfolder (regular_farmer / common / …)


# ─────────────────────────────
# Bulk upload (test cases from Excel)
# ─────────────────────────────
class BulkUploadResult(BaseModel):
    total_rows: int                # data rows read from the sheet (header excluded)
    created: int
    skipped: int                   # duplicate testcase_key (already in DB or repeated in file)
    errors: int
    created_keys: list[str] = Field(default_factory=list)
    skipped_keys: list[str] = Field(default_factory=list)
    error_details: list[str] = Field(default_factory=list)


# ─────────────────────────────
# Dashboard
# ─────────────────────────────
class LatestRun(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: int
    run_name: str | None
    application_id: int | None
    status: str | None
    started_at: datetime | None
    completed_at: datetime | None


class RecentFailure(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    execution_id: int
    testcase_id: int | None
    run_id: int | None
    failure_reason: str | None
    completed_at: datetime | None


class DashboardSummary(BaseModel):
    total_testcases: int
    smoke_count: int
    regression_count: int
    pass_percentage: float
    fail_percentage: float
    latest_runs: list[LatestRun]
    recent_failures: list[RecentFailure]


class ExecutionHistoryPoint(BaseModel):
    date: date
    passed: int
    failed: int
    total: int
