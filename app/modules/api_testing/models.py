from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================================
# Enums
# ============================================================================

class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# API Logs (from mitmproxy)
# ============================================================================

class APILog(BaseModel):
    """Single API call log"""
    method: str
    endpoint: str
    url: str
    status: int
    response_time_ms: float
    timestamp: str
    run_id: Optional[str] = None  # Link to test run


# ============================================================================
# Test Scripts (User-created K6 scripts)
# ============================================================================

class Stage(BaseModel):
    """Load testing stage"""
    id: int
    type: str  # rampUp, constant, rampDown, spike
    duration: int  # seconds
    target: int  # target VUs


class Endpoint(BaseModel):
    """API endpoint to test"""
    id: int
    method: str
    path: str
    name: str
    enabled: bool
    weight: int
    expectedStatus: List[int]
    headers: str = ""
    body: str = ""


class TestScriptConfig(BaseModel):
    """Configuration extracted from script or builder"""
    baseUrl: str
    stages: List[Stage]
    endpoints: List[Endpoint]
    requestTimeout: int = 10000


class TestScript(BaseModel):
    """Saved K6 test script"""
    name: str
    # description: Optional[str] = None
    script: str  # The actual K6 JavaScript code
    config: TestScriptConfig  # Structured config for re-editing
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)


class TestScriptResponse(TestScript):

    id: str

    class Config:
        populate_by_name = True


# ============================================================================
# Test Runs (Execution History)
# ============================================================================

class RunSummary(BaseModel):
    """Summary metrics for a test run"""
    totalRequests: int = 0
    failedRequests: int = 0
    avgResponseTime: float = 0.0
    p95: Optional[float] = None
    p99: Optional[float] = None
    successRate: float = 100.0


class TestRun(BaseModel):
    """Record of a test execution"""
    scriptId: str  # Reference to test_scripts._id
    scriptName: str
    status: RunStatus = RunStatus.PENDING
    startTime: datetime = Field(default_factory=datetime.utcnow)
    endTime: Optional[datetime] = None
    duration: Optional[int] = None  # seconds
    summary: RunSummary = Field(default_factory=RunSummary)
    outputUrl: Optional[str] = None  # Link to InfluxDB/Grafana


class TestRunResponse(TestRun):
    id: str
    class Config:
        populate_by_name = True


# ============================================================================
# Metrics (Detailed performance data)
# ============================================================================

class MetricTags(BaseModel):
    """Tags for metric filtering"""
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status: Optional[str] = None
    scenario: Optional[str] = None


class Metric(BaseModel):
    """Single metric data point"""
    runId: str  # Reference to test_runs._id
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metric: str  # http_req_duration, http_req_failed, vus, etc.
    value: float
    tags: MetricTags = Field(default_factory=MetricTags)


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateScriptRequest(BaseModel):
    """Request to save a new test script"""
    name: str
    # description: Optional[str] = None
    script: str  # K6 JavaScript code
    config: TestScriptConfig


class UpdateScriptRequest(BaseModel):
    """Request to update existing script"""
    name: Optional[str] = None
    # description: Optional[str] = None
    script: Optional[str] = None
    config: Optional[TestScriptConfig] = None


class StartRunRequest(BaseModel):
    """Request to start a test run"""
    scriptId: str  # MongoDB ObjectId of the script to run
    scriptName: Optional[str] = None  # For convenience


class BatchLogs(BaseModel):
    """Save multiple logs in one request"""
    logs: List[APILog]
    runId: Optional[str] = None


# ============================================================================
# Response Models
# ============================================================================

class MessageResponse(BaseModel):
    """Generic success response"""
    message: str


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    details: Optional[Dict[str, Any]] = None


class ScriptsListResponse(BaseModel):
    """List of all scripts"""
    scripts: List[TestScriptResponse]
    count: int


class RunsListResponse(BaseModel):
    """List of all runs"""
    runs: List[TestRunResponse]
    count: int


class RunDetailResponse(TestRunResponse):
    """Full run details with logs and metrics"""
    logs: List[APILog] = Field(default_factory=list)
    metrics: List[Metric] = Field(default_factory=list)