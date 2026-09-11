"""
jira_integration/mongo_jira_integration.py
───────────────────────────────────────────
Bridge between Jira issue creation and MongoDB storage.

Usage:
    from jira_integration.mongo_jira_integration import create_and_store_jira_issue

    # Create issue in Jira AND save to MongoDB
    result = create_and_store_jira_issue(
        summary="Test failed",
        description="Detailed description",
        app_name="Krishivaas Farmer",
        ...
    )
"""

from .jira_service import create_jira_issue
from . import jira_service
from . import mongo_operations
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger("uvicorn.error")


def create_and_store_jira_issue(
    summary: str,
    description: str,
    app_name: Optional[str] = None,
    app_version: Optional[str] = None,
    module: Optional[str] = None,
    feature: Optional[str] = None,
    issue_summary: Optional[str] = None,
    test_name: Optional[str] = None,
    test_id: Optional[str] = None,
    steps_executed: Optional[List[str]] = None,
    developer_name: Optional[str] = None,
    issue_type: Optional[str] = None,
    priority: Optional[str] = None,
    fix_version: Optional[List[str]] = None,
    affects_version: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sprint: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Create a JIRA issue AND store it in MongoDB.

    This function:
    1. Creates the issue in Jira via create_jira_issue()
    2. Saves all the data to MongoDB for record keeping
    3. Returns both the Jira issue key and MongoDB ticket ID

    Args:
        summary: Issue summary/title
        description: Issue description
        app_name: App name (e.g., "Krishivaas Farmer")
        app_version: App version (e.g., "1.3.96")
        module: Module being tested
        feature: Feature name
        issue_summary: Another summary field
        test_name: Name of the test
        test_id: ID of the test
        steps_executed: List of automation steps
        developer_name: Developer responsible
        start_date: Test start time (ISO format)
        end_date: Test end time (ISO format)
        sprint: Sprint name for JIRA

    Returns:
        {
            "success": True,
            "issue_id": "AT-87",
            "ticket_id": "20240329123456-ABC12345",
            "issue_url": "https://..../browse/AT-87",
            "error": None
        }
    """
    try:
        print("\n" + "=" * 70)
        print("[JIRA + MONGO] Creating issue in Jira and storing in MongoDB...")
        print("=" * 70)

        # Step 1 — Create issue in Jira
        issue_key = jira_service.create_jira_issue(
            summary=summary,
            description=description,
            app_name=app_name,
            app_version=app_version,
            module=module,
            feature=feature,
            issue_summary=issue_summary,
            test_name=test_name,
            test_id=test_id,
            steps_executed=steps_executed,
            developer_name=developer_name,
            issue_type=issue_type,
            priority=priority,
            fix_version=fix_version,
            affects_version=affects_version,
            start_date=start_date,
            end_date=end_date,
            sprint=sprint,
        )

        if not issue_key:
            logger.error("[JIRA + MONGO] Failed to create Jira issue")
            return {
                "success":  False,
                "issue_id": None,
                "ticket_id": None,
                "error":    "Failed to create Jira issue",
            }

        logger.info("[JIRA + MONGO] ✓ Jira issue created: %s", issue_key)

        # Build the Jira browse URL for storage
        from .jira_config import config
        issue_url = f"{config.url}/browse/{issue_key}"

        # Step 2 — Save to MongoDB with ALL fields
        # ✅ FIX: ticket_type="created", sprint, fix/affects_version, issue_url all passed
        ticket_id = mongo_operations.save_ticket(
            issue_id=issue_key,
            summary=summary,
            module=module             or "Unknown",
            feature=feature           or "Unknown",
            ticket_type="created",                          # ← explicit
            app_name=app_name,
            app_version=app_version,
            description=description,
            test_name=test_name,
            test_id=test_id,                                # passed as-is, no "Unknown" default
            steps_executed=steps_executed,
            developer_name=developer_name,
            priority=priority         or "High",
            labels=[
                "automation",
                "mobile-app",
                (module or "").lower().replace(" ", "-"),
            ],
            assignee=developer_name   or "Unassigned",
            status="Open",
            environment="staging",
            start_date=start_date,                          # ← stored as provided
            due_date=end_date,                              # ← stored as provided (not same as start)
            issue_url=issue_url,                            # ← Jira browse URL
            sprint=sprint             or "",
            fix_version=fix_version   or [],
            affects_version=affects_version or [],
        )

        if ticket_id:
            logger.info("[JIRA + MONGO] ✓ Ticket saved to MongoDB: %s", ticket_id)
        else:
            logger.warning(
                "[JIRA + MONGO] ⚠️ Jira issue created (%s) but MongoDB save failed", issue_key
            )

        print("[JIRA + MONGO] ✓ Complete!")
        print("=" * 70 + "\n")

        return {
            "success":   True,
            "issue_id":  issue_key,
            "ticket_id": ticket_id or "N/A",
            "issue_url": issue_url,
            "error":     None if ticket_id else "MongoDB save failed",
        }

        

    except Exception as e:
        error_msg = str(e)
        logger.error("[JIRA + MONGO] ✗ Error: %s", error_msg)
        return {
            "success":   False,
            "issue_id":  None,
            "ticket_id": None,
            "error":     error_msg,
        }

def store_removed_ticket(
    issue_id: str,
    summary: str,
    module: str,
    feature: str,
    app_name: Optional[str] = None,
    app_version: Optional[str] = None,
    description: Optional[str] = None,
    test_name: Optional[str] = None,
    test_id: Optional[str] = None,
    steps_executed: Optional[List[str]] = None,
    developer_name: Optional[str] = None,
    priority: str = "High",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sprint: Optional[str] = None,
    fix_version: Optional[List[str]] = None,
    affects_version: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Store a dismissed/removed ticket in MongoDB with ticket_type="removed".

    Called when the user dismisses a payload from the Issue Panel — they chose
    NOT to file a Jira issue for this failure.  These tickets appear in the
    Unassigned tab of Jira History.

    ✅ FIX: explicitly passes ticket_type="removed" and status="Unassigned"
    so the document is correctly identified in get_all_tickets() / _normalise().
    """
    try:
        ticket_id = mongo_operations.save_ticket(
            issue_id=issue_id,
            summary=summary,
            module=module             or "Unknown",
            feature=feature           or "Unknown",
            ticket_type="removed",                          # ← explicit (was missing before)
            app_name=app_name,
            app_version=app_version,
            description=description,
            test_name=test_name,
            test_id=test_id,
            steps_executed=steps_executed,
            developer_name=developer_name,
            priority=priority,
            labels=[
                "automation",
                "dismissed",
                (module or "").lower().replace(" ", "-"),
            ],
            assignee=developer_name   or "Unassigned",
            status="Unassigned",                            # visible in Unassigned tab
            environment="staging",
            start_date=start_date,
            due_date=end_date,
            issue_url="",                                   # no Jira URL for dismissed tickets
            sprint=sprint             or "",
            fix_version=fix_version   or [],
            affects_version=affects_version or [],
        )

        if ticket_id:
            logger.info("[JIRA + MONGO] ✓ Removed ticket saved: %s → %s", issue_id, ticket_id)
        else:
            logger.warning("[JIRA + MONGO] ⚠️ Failed to save removed ticket: %s", issue_id)

        return ticket_id

    except Exception as e:
        logger.error("[JIRA + MONGO] ✗ Error saving removed ticket %s: %s", issue_id, str(e))
        return None
    
def get_stored_ticket(issue_id: str) -> Optional[Dict[str, Any]]:
    return mongo_operations.get_ticket(issue_id)

def get_all_stored_tickets(**filters) -> List[Dict[str, Any]]:
    """
    Retrieve all stored tickets from MongoDB.

    Args:
        **filters: Optional filters (status, module, priority, assignee)

    Returns:
        List of tickets
    """
    return mongo_operations.get_all_tickets(**filters)


def update_stored_ticket(issue_id: str, **updates) -> Optional[Dict[str, Any]]:
    """
    Update a stored ticket in MongoDB.

    Args:
        issue_id: Jira issue key
        **updates: Fields to update

    Returns:
        Updated ticket data if successful
    """
    return mongo_operations.update_ticket(issue_id, **updates)


def get_ticket_statistics() -> Dict[str, Any]:
    """Get statistics about stored tickets."""
    return mongo_operations.get_statistics()


def search_stored_tickets(query: str) -> List[Dict[str, Any]]:
    """
    Search stored tickets by text.

    Args:
        query: Search query

    Returns:
        List of matching tickets
    """
    return mongo_operations.search_tickets(query)