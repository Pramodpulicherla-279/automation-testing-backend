"""
test_management/routes.py
────────────────────────────
Thin route declarations — every handler calls straight into service.py.
Prefix ("/api") is applied once at inclusion time in app/main.py,
matching every other router there.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.test_management import models as schemas
from app.modules.test_management import service
from app.modules.test_management.database import SessionLocal, get_db

router = APIRouter()


# ── Applications ─────────────────────────────────────────────────────────
# Hardcoded fallback for the unified app's four roles. Served when the MySQL
# database is unreachable (e.g. running this backend on a machine that is NOT the
# DB host → "Access denied for user 'automation_user'@'localhost'"), so the app
# dropdown still populates off-machine. Mirrors the real rows: `variant` is the
# authoritative UI→automation key; ids/names match the seeded DB. Keep in sync if
# the real Applications table changes.
_SEED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
_HARDCODED_APPLICATIONS = [
    {"application_id": 1, "application_name": "Unified Regular Client App", "platform": "Android",
     "package_name": "com.agribride.krishivaas.client_app", "variant": "regular_client",
     "description": "Hardcoded (DB offline)", "status": True, "created_at": _SEED_TS, "updated_at": _SEED_TS},
    {"application_id": 3, "application_name": "Unified Regular Farmer", "platform": "Android",
     "package_name": "com.agribride.krishivaas.farmer_app", "variant": "regular_farmer",
     "description": "Hardcoded (DB offline)", "status": True, "created_at": _SEED_TS, "updated_at": _SEED_TS},
    {"application_id": 4, "application_name": "Unified Telangana Client App", "platform": "Android",
     "package_name": "com.agribride.krishivaas.client_state_app", "variant": "state_client",
     "description": "Hardcoded (DB offline)", "status": True, "created_at": _SEED_TS, "updated_at": _SEED_TS},
    {"application_id": 2, "application_name": "Unified Telangana Farmer", "platform": "Android",
     "package_name": "com.agribride.krishivaas.farmer_state_app", "variant": "state_farmer",
     "description": "Hardcoded (DB offline)", "status": True, "created_at": _SEED_TS, "updated_at": _SEED_TS},
]


def _hardcoded_applications_response(page: int, page_size: int) -> dict:
    apps = _HARDCODED_APPLICATIONS
    total = len(apps)
    page = max(1, page)
    page_size = max(1, page_size)
    start = (page - 1) * page_size
    items = apps[start:start + page_size]
    total_pages = (total + page_size - 1) // page_size
    return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}


@router.post("/applications", response_model=schemas.ApplicationRead, status_code=status.HTTP_201_CREATED)
def create_application(payload: schemas.ApplicationCreate, db: Session = Depends(get_db)):
    return service.create_application_flow(payload, db)


@router.get("/applications", response_model=schemas.PaginatedResponse[schemas.ApplicationRead])
def list_applications(status: bool | None = None, q: str | None = None, page: int = 1, page_size: int = 20):
    """
    List applications. Manages its own session (not Depends(get_db)) so a DB outage
    is fully contained here: if MySQL is unreachable, serve the hardcoded list so the
    UI dropdown keeps working instead of 500-ing.
    """
    db = SessionLocal()
    try:
        return service.list_applications_flow(status, q, page, page_size, db)
    except SQLAlchemyError as exc:
        print(f"[applications] DB unavailable ({exc.__class__.__name__}); serving hardcoded application list.")
        return _hardcoded_applications_response(page, page_size)
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.get("/applications/{application_id}", response_model=schemas.ApplicationRead)
def get_application(application_id: int, db: Session = Depends(get_db)):
    return service.get_application_flow(application_id, db)


@router.put("/applications/{application_id}", response_model=schemas.ApplicationRead)
def update_application(application_id: int, payload: schemas.ApplicationUpdate, db: Session = Depends(get_db)):
    return service.update_application_flow(application_id, payload, db)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: int, db: Session = Depends(get_db)):
    service.delete_application_flow(application_id, db)


# ── Modules ───────────────────────────────────────────────────────────────
@router.post("/modules", response_model=schemas.ModuleRead, status_code=status.HTTP_201_CREATED)
def create_module(payload: schemas.ModuleCreate, db: Session = Depends(get_db)):
    return service.create_module_flow(payload, db)


@router.get("/modules", response_model=schemas.PaginatedResponse[schemas.ModuleRead])
def list_modules(application_id: int | None = None, status: bool | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_modules_flow(application_id, status, page, page_size, db)


@router.get("/modules/{module_id}", response_model=schemas.ModuleRead)
def get_module(module_id: int, db: Session = Depends(get_db)):
    return service.get_module_flow(module_id, db)


@router.put("/modules/{module_id}", response_model=schemas.ModuleRead)
def update_module(module_id: int, payload: schemas.ModuleUpdate, db: Session = Depends(get_db)):
    return service.update_module_flow(module_id, payload, db)


@router.delete("/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_module(module_id: int, db: Session = Depends(get_db)):
    service.delete_module_flow(module_id, db)


# ── Priorities ────────────────────────────────────────────────────────────
@router.post("/priorities", response_model=schemas.PriorityRead, status_code=status.HTTP_201_CREATED)
def create_priority(payload: schemas.PriorityCreate, db: Session = Depends(get_db)):
    return service.create_priority_flow(payload, db)


@router.get("/priorities", response_model=schemas.PaginatedResponse[schemas.PriorityRead])
def list_priorities(page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_priorities_flow(page, page_size, db)


@router.get("/priorities/{priority_id}", response_model=schemas.PriorityRead)
def get_priority(priority_id: int, db: Session = Depends(get_db)):
    return service.get_priority_flow(priority_id, db)


@router.put("/priorities/{priority_id}", response_model=schemas.PriorityRead)
def update_priority(priority_id: int, payload: schemas.PriorityUpdate, db: Session = Depends(get_db)):
    return service.update_priority_flow(priority_id, payload, db)


@router.delete("/priorities/{priority_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_priority(priority_id: int, db: Session = Depends(get_db)):
    service.delete_priority_flow(priority_id, db)


# ── Test Cases ────────────────────────────────────────────────────────────
@router.post("/test-cases", response_model=schemas.TestCaseRead, status_code=status.HTTP_201_CREATED)
def create_test_case(payload: schemas.TestCaseCreate, db: Session = Depends(get_db)):
    return service.create_test_case_flow(payload, db)


@router.post("/test-cases/bulk-upload", response_model=schemas.BulkUploadResult)
async def bulk_upload_test_cases(
    application_id: int = Form(...),
    module_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    content = await file.read()
    return service.bulk_upload_test_cases_flow(content, file.filename, application_id, module_id, db)


@router.get("/test-cases/bulk-template")
def download_bulk_template():
    data = service.build_bulk_template_xlsx()
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="test_cases_bulk_template.xlsx"'},
    )


@router.get("/test-cases/type-tags")
def test_case_type_tags(db: Session = Depends(get_db)):
    """testcase_key -> test_types; the suite uses it to filter shared tests by type."""
    return service.test_case_type_tags_flow(db)


@router.get("/test-cases", response_model=schemas.PaginatedResponse[schemas.TestCaseRead])
def list_test_cases(
    application_id: int | None = None,
    module_id: int | None = None,
    priority_id: int | None = None,
    test_type: str | None = None,
    status: bool | None = None,
    polarity: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    return service.list_test_cases_flow(application_id, module_id, priority_id, test_type, status, polarity, q, page, page_size, db)


@router.get("/test-cases/{testcase_id}", response_model=schemas.TestCaseRead)
def get_test_case(testcase_id: int, db: Session = Depends(get_db)):
    return service.get_test_case_flow(testcase_id, db)


@router.put("/test-cases/{testcase_id}", response_model=schemas.TestCaseRead)
def update_test_case(testcase_id: int, payload: schemas.TestCaseUpdate, db: Session = Depends(get_db)):
    return service.update_test_case_flow(testcase_id, payload, db)


@router.delete("/test-cases/{testcase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_case(testcase_id: int, db: Session = Depends(get_db)):
    service.delete_test_case_flow(testcase_id, db)


# ── Automation discovery ──────────────────────────────────────────────────
@router.get("/automation-tests", response_model=list[schemas.AutomationTestCase])
async def discover_automation_tests(path: str):
    return await service.discover_automation_tests_flow(path)


@router.get("/test-type-tests", response_model=list[schemas.TypeFolderTest])
async def discover_type_folder_tests(type: str):
    """Tests physically located under tests/test_suites/<type>/ (folder-defined type)."""
    return await service.discover_type_folder_flow(type)


# ── Test Runs ─────────────────────────────────────────────────────────────
@router.post("/run-tests", response_model=schemas.RunTestsSummary, status_code=status.HTTP_201_CREATED)
def run_tests(payload: schemas.TestRunCreate, db: Session = Depends(get_db)):
    return service.run_tests_flow(payload, db)


@router.get("/test-runs", response_model=schemas.PaginatedResponse[schemas.TestRunRead])
def list_test_runs(application_id: int | None = None, module_id: int | None = None, status: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_test_runs_flow(application_id, module_id, status, page, page_size, db)


# ── Live pytest run reporting (real Appium runs) ──────────────────────────
@router.post("/test-runs/start", response_model=schemas.TestRunRead, status_code=status.HTTP_201_CREATED)
def start_pytest_run(payload: schemas.PytestRunStart, db: Session = Depends(get_db)):
    return service.start_pytest_run_flow(payload, db)


@router.post("/test-runs/{run_id}/result", response_model=schemas.TestRunResultRead, status_code=status.HTTP_201_CREATED)
def record_pytest_result(run_id: int, payload: schemas.PytestResultRecord, db: Session = Depends(get_db)):
    return service.record_pytest_result_flow(run_id, payload, db)


@router.post("/test-runs/{run_id}/finish", response_model=schemas.TestRunRead)
def finish_pytest_run(run_id: int, payload: schemas.PytestRunFinish, db: Session = Depends(get_db)):
    return service.finish_pytest_run_flow(run_id, payload, db)


@router.get("/test-runs/{run_id}", response_model=schemas.TestRunDetailRead)
def get_test_run(run_id: int, db: Session = Depends(get_db)):
    return service.get_test_run_flow(run_id, db)


@router.post("/test-runs/{run_id}/cancel", response_model=schemas.TestRunRead)
def cancel_test_run(run_id: int, db: Session = Depends(get_db)):
    return service.cancel_test_run_flow(run_id, db)


# ── Test Run Results ──────────────────────────────────────────────────────
@router.post("/test-run-results", response_model=schemas.TestRunResultRead, status_code=status.HTTP_201_CREATED)
def create_test_run_result(payload: schemas.TestRunResultCreate, db: Session = Depends(get_db)):
    return service.create_test_run_result_flow(payload, db)


@router.get("/test-run-results", response_model=schemas.PaginatedResponse[schemas.TestRunResultRead])
def list_test_run_results(run_id: int | None = None, testcase_id: int | None = None, status: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_test_run_results_flow(run_id, testcase_id, status, page, page_size, db)


@router.get("/test-run-results/{execution_id}", response_model=schemas.TestRunResultRead)
def get_test_run_result(execution_id: int, db: Session = Depends(get_db)):
    return service.get_test_run_result_flow(execution_id, db)


@router.put("/test-run-results/{execution_id}", response_model=schemas.TestRunResultRead)
def update_test_run_result(execution_id: int, payload: schemas.TestRunResultUpdate, db: Session = Depends(get_db)):
    return service.update_test_run_result_flow(execution_id, payload, db)


@router.delete("/test-run-results/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test_run_result(execution_id: int, db: Session = Depends(get_db)):
    service.delete_test_run_result_flow(execution_id, db)


# ── Execution Logs (append-only) ─────────────────────────────────────────
@router.post("/execution-logs", response_model=list[schemas.ExecutionLogRead], status_code=status.HTTP_201_CREATED)
def create_execution_logs(payload: schemas.ExecutionLogBulkCreate, db: Session = Depends(get_db)):
    return service.create_execution_logs_flow(payload, db)


@router.get("/execution-logs", response_model=list[schemas.ExecutionLogRead])
def list_execution_logs(execution_id: int, db: Session = Depends(get_db)):
    return service.list_execution_logs_flow(execution_id, db)


# ── Attachments ───────────────────────────────────────────────────────────
@router.post("/attachments", response_model=schemas.AttachmentRead, status_code=status.HTTP_201_CREATED)
def create_attachment(payload: schemas.AttachmentCreate, db: Session = Depends(get_db)):
    return service.create_attachment_flow(payload, db)


@router.get("/attachments", response_model=schemas.PaginatedResponse[schemas.AttachmentRead])
def list_attachments(execution_id: int | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_attachments_flow(execution_id, page, page_size, db)


@router.get("/attachments/{attachment_id}", response_model=schemas.AttachmentRead)
def get_attachment(attachment_id: int, db: Session = Depends(get_db)):
    return service.get_attachment_flow(attachment_id, db)


@router.put("/attachments/{attachment_id}", response_model=schemas.AttachmentRead)
def update_attachment(attachment_id: int, payload: schemas.AttachmentUpdate, db: Session = Depends(get_db)):
    return service.update_attachment_flow(attachment_id, payload, db)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    service.delete_attachment_flow(attachment_id, db)


# ── Bugs ──────────────────────────────────────────────────────────────────
@router.post("/bugs", response_model=schemas.BugRead, status_code=status.HTTP_201_CREATED)
def create_bug(payload: schemas.BugCreate, db: Session = Depends(get_db)):
    return service.create_bug_flow(payload, db)


@router.get("/bugs", response_model=schemas.PaginatedResponse[schemas.BugRead])
def list_bugs(testcase_id: int | None = None, execution_id: int | None = None, status: str | None = None, severity: str | None = None, page: int = 1, page_size: int = 20, db: Session = Depends(get_db)):
    return service.list_bugs_flow(testcase_id, execution_id, status, severity, page, page_size, db)


@router.get("/bugs/{bug_id}", response_model=schemas.BugRead)
def get_bug(bug_id: int, db: Session = Depends(get_db)):
    return service.get_bug_flow(bug_id, db)


# ── Dashboard ─────────────────────────────────────────────────────────────
@router.get("/dashboard/summary", response_model=schemas.DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)):
    return service.dashboard_summary_flow(db)


@router.get("/dashboard/execution-history", response_model=list[schemas.ExecutionHistoryPoint])
def get_execution_history(days: int = 30, db: Session = Depends(get_db)):
    return service.execution_history_flow(days, db)
