from pydantic import BaseModel
from typing import List, Dict, Optional

class RunCompleteEvent(BaseModel):
    report_url: str

class ExistingTestRequest(BaseModel):
    apk_name: str
    tests_to_run: Optional[List[Dict[str, str]]] = None
    # Target automation role selected in the UI (regular_farmer | regular_client |
    # state_farmer | state_client). Drives post-login landed-app detection & switch.
    app_type: Optional[str] = None
    run_id: Optional[str] = None
    # Mobile number + MPIN provided in the UI to log in with (overrides accounts.json).
    login_phone: Optional[str] = None
    login_mpin: Optional[str] = None
    # Test types selected in the UI (Smoke / Regression / End-to-End / Sanity). Drives
    # both folder-based collection (test_suites/<type>/) and the DB test_types filter.
    test_types: Optional[List[str]] = None

class LogMessage(BaseModel):
    message: str
    status: str = "INFO"

class TestRequest(BaseModel):
    url: str
    tests_to_run: Optional[List[Dict[str, str]]] = None
    app_type: Optional[str] = None
    run_id: Optional[str] = None
    login_phone: Optional[str] = None
    login_mpin: Optional[str] = None
    test_types: Optional[List[str]] = None
