from pydantic import BaseModel
from typing import List, Optional, Any

class JiraPayloadRequest(BaseModel):
    ticket_id:       Optional[str]       = None
    issue_id:        Optional[str]       = None
    app_name:        Optional[str]       = None
    app_version:     Optional[str]       = None
    module:          Optional[str]       = None
    feature:         Optional[str]       = None
    issue_summary:   Optional[str]       = None
    title:           Optional[str]       = None
    test_name:       Optional[str]       = None
    test_id:         Optional[str]       = None
    steps_executed:  Optional[List[Any]] = None
    developer_name:  Optional[str]       = None
    description:     Optional[str]       = None
    start_date:      Optional[str]       = None
    end_date:        Optional[str]       = None
    fix_version:     Optional[List[str]] = None
    affects_version: Optional[List[str]] = None
    sprint:          Optional[str]       = None

class JiraCreateRequest(BaseModel):
    app_name:        Optional[str]       = None
    app_version:     Optional[str]       = None
    module:          Optional[str]       = None
    feature:         Optional[str]       = None
    issue_summary:   Optional[str]       = None
    test_name:       Optional[str]       = None
    test_id:         Optional[str]       = None
    steps_executed:  Optional[List[Any]] = None
    developer_name:  Optional[str]       = None
    priority:        Optional[str]       = None
    title:           Optional[str]       = None
    description:     Optional[str]       = None
    parent:          Optional[str]       = None
    fix_version:     Optional[List[str]] = None
    affects_version: Optional[List[str]] = None
    priority:        Optional[str]       = None
    issue_id:        Optional[str]       = None
    issue_url:       Optional[str]       = None
    ticket_id:       Optional[str]       = None
    start_date:      Optional[str]       = None
    end_date:        Optional[str]       = None
    sprint:          Optional[str]       = None
