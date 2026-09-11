"""
jira_integration/mongo_operations.py
────────────────────────────────────
Database operations for storing and retrieving Jira automation tickets.

Usage:
    from jira_integration.mongo_operations import save_ticket, get_ticket, get_all_tickets
    
    # Save a ticket
    ticket_data = {
        "issue_id": "AT-87",
        "summary": "Test failed",
        "module": "Onboarding",
        ...
    }
    result = save_ticket(ticket_data)
    
    # Get a ticket
    ticket = get_ticket("AT-87")
    
    # Get all tickets
    tickets = get_all_tickets(limit=10, status="Open")
"""

from .mongo_config import get_tickets_collection, is_mongodb_enabled
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid
import logging

logger = logging.getLogger("uvicorn.error")


def _generate_ticket_id() -> str:
    """Generate a unique ticket ID"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    unique_id = str(uuid.uuid4())[:8].upper()
    return f"{timestamp}-{unique_id}"


def save_ticket(
    issue_id: str,
    summary: str,
    module: str,
    feature: str,
    ticket_type: str = "created",           # "created" (Jira filed) | "removed" (dismissed)
    app_name: Optional[str] = None,
    app_version: Optional[str] = None,
    description: Optional[str] = None,
    test_name: Optional[str] = None,
    test_id: Optional[str] = None,          # ✅ FIX: no longer defaults to "Unknown"
    steps_executed: Optional[List[str]] = None,
    developer_name: Optional[str] = None,
    priority: str = "High",
    labels: Optional[List[str]] = None,
    assignee: Optional[str] = None,
    status: str = "Open",
    environment: str = "staging",
    start_date: Optional[str] = None,       # ✅ FIX: no longer defaults to datetime.now()
    due_date: Optional[str] = None,
    issue_url: Optional[str] = None,
    sprint: Optional[str] = None,
    fix_version: Optional[List[str]] = None,
    affects_version: Optional[List[str]] = None,
    **extra_fields
) -> Optional[str]:
    """
    Save a Jira ticket to MongoDB.

    ticket_type:
        "created"  → ticket was filed in Jira       → shown in Assigned tab
        "removed"  → payload was dismissed/not filed → shown in Unassigned tab

    Returns internal ticket_id string if saved successfully, None on failure.
    """
    if not is_mongodb_enabled():
        logger.warning("[MongoDB] Not connected — ticket not saved.")
        return None

    try:
        collection = get_tickets_collection()
        if collection is None:
            logger.error("[MongoDB] Could not get tickets collection")
            return None

        ticket_id = _generate_ticket_id()

        ticket_doc = {
            "ticket_id":        ticket_id,
            "issue_id":         issue_id,
            "ticket_type":      ticket_type,                    # "created" | "removed"
            "summary":          summary,
            "module":           module or "Unknown",
            "feature":          feature or "Unknown",
            "app_name":         app_name     or "Unknown",
            "app_version":      app_version  or "Unknown",
            "description":      description  or "",
            "test_name":        test_name    or "Unknown Test",
            "test_id":          test_id      or "",             # ✅ empty string, not "Unknown"
            "steps_executed":   steps_executed  or [],
            "developer_name":   developer_name  or "Unknown",
            "priority":         priority,
            "labels":           labels       or [],
            "assignee":         assignee     or "Unassigned",
            "status":           status,
            "environment":      environment,
            "start_date":       start_date,                     # ✅ None if not provided
            "due_date":         due_date,
            "issue_url":        issue_url    or "",
            "sprint":           sprint       or "",
            "fix_version":      fix_version  or [],
            "affects_version":  affects_version or [],
            "created_at":       datetime.now().isoformat(),
            "updated_at":       datetime.now().isoformat(),
            **extra_fields,
        }

        collection.insert_one(ticket_doc)
        logger.info(
            "[MongoDB] ✓ Ticket saved: %s (type=%s, internal_id=%s)",
            issue_id, ticket_type, ticket_id
        )
        return ticket_id

    except Exception as e:
        logger.error("[MongoDB] ✗ Error saving ticket %s: %s", issue_id, str(e))
        return None

def save_removed_ticket(
    issue_id: str,
    summary: str,
    module: str,
    feature: str = "Unknown",
    **kwargs
) -> Optional[str]:
    """
    Convenience wrapper — saves a ticket with ticket_type="removed".
    Called when a payload is dismissed without creating a Jira issue.
    """
    return save_ticket(
        issue_id=issue_id,
        summary=summary,
        module=module,
        feature=feature,
        ticket_type="removed",
        status="Unassigned",
        **kwargs,
    )

def get_ticket(issue_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a ticket by Jira issue key."""
    if not is_mongodb_enabled():
        return None

    try:
        collection = get_tickets_collection()
        if collection is None:
            return None

        ticket = collection.find_one({"issue_id": issue_id})
        if ticket:
            ticket["_id"] = str(ticket.get("_id"))
            logger.info("[MongoDB] Retrieved ticket: %s", issue_id)
            return ticket
        logger.info("[MongoDB] Ticket not found: %s", issue_id)
        return None

    except Exception as e:
        logger.error("[MongoDB] Error retrieving ticket %s: %s", issue_id, str(e))
        return None

def get_all_tickets(
    limit: int = 200,
    skip: int = 0,
    status: Optional[str] = None,
    module: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    ticket_type: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: int = -1,
) -> List[Dict[str, Any]]:
    """
    Retrieve tickets with optional filters.

    ✅ FIX: Exceptions are now RE-RAISED instead of being swallowed.
    This allows callers (e.g. jira_history_api) to detect MongoDB failures
    and fall back to session memory, rather than silently returning 0 results.

    ticket_type filter:
        "created"  → Assigned tab only
        "removed"  → Unassigned tab only
        None       → all tickets (default for history page)
    """
    if not is_mongodb_enabled():
        return []

    collection = get_tickets_collection()
    if collection is None:
        raise RuntimeError("[MongoDB] Tickets collection not available")

    # Verify connection is live with a quick ping before querying
    try:
        collection.database.client.admin.command("ping")
    except Exception as ping_err:
        raise RuntimeError(f"[MongoDB] Connection ping failed: {ping_err}") from ping_err

    filter_dict: Dict[str, Any] = {}
    if status:
        filter_dict["status"] = status
    if module:
        filter_dict["module"] = module
    if priority:
        filter_dict["priority"] = priority
    if assignee:
        filter_dict["assignee"] = assignee
    if ticket_type:
        filter_dict["ticket_type"] = ticket_type

    # ✅ Let exceptions propagate — no try/except here
    tickets = list(
        collection.find(filter_dict)
        .sort(sort_by, sort_order)
        .skip(skip)
        .limit(limit)
    )

    for ticket in tickets:
        ticket["_id"] = str(ticket.get("_id"))

    logger.info(
        "[MongoDB] Retrieved %d tickets (filter=%s)", len(tickets), filter_dict
    )
    return tickets


def update_ticket(issue_id: str, **update_fields) -> Optional[Dict[str, Any]]:
    """Update a ticket by Jira issue key."""
    if not is_mongodb_enabled():
        return None

    try:
        collection = get_tickets_collection()
        if collection is None:
            return None

        update_fields["updated_at"] = datetime.now().isoformat()

        result = collection.find_one_and_update(
            {"issue_id": issue_id},
            {"$set": update_fields},
            return_document=True,
        )

        if result:
            result["_id"] = str(result.get("_id"))
            logger.info("[MongoDB] Updated ticket: %s", issue_id)
            return result

        logger.warning("[MongoDB] Ticket not found for update: %s", issue_id)
        return None

    except Exception as e:
        logger.error("[MongoDB] Error updating ticket %s: %s", issue_id, str(e))
        return None

def delete_ticket(issue_id: str) -> bool:
    """Delete a ticket by Jira issue key."""
    if not is_mongodb_enabled():
        return False

    try:
        collection = get_tickets_collection()
        if collection is None:
            return False

        result = collection.delete_one({"issue_id": issue_id})
        if result.deleted_count > 0:
            logger.info("[MongoDB] Deleted ticket: %s", issue_id)
            return True
        logger.warning("[MongoDB] Ticket not found for deletion: %s", issue_id)
        return False

    except Exception as e:
        logger.error("[MongoDB] Error deleting ticket %s: %s", issue_id, str(e))
        return False

def get_statistics() -> Dict[str, Any]:
    """Return aggregate statistics about stored tickets."""
    if not is_mongodb_enabled():
        return {}

    try:
        collection = get_tickets_collection()
        if collection is None:
            return {}

        total = collection.count_documents({})

        by_status   = list(collection.aggregate([{"$group": {"_id": "$status",      "count": {"$sum": 1}}}]))
        by_priority = list(collection.aggregate([{"$group": {"_id": "$priority",    "count": {"$sum": 1}}}]))
        by_module   = list(collection.aggregate([{"$group": {"_id": "$module",      "count": {"$sum": 1}}}]))
        by_assignee = list(collection.aggregate([{"$group": {"_id": "$assignee",    "count": {"$sum": 1}}}]))
        by_type     = list(collection.aggregate([{"$group": {"_id": "$ticket_type", "count": {"$sum": 1}}}]))

        return {
            "total":       total,
            "by_status":   by_status,
            "by_priority": by_priority,
            "by_module":   by_module,
            "by_assignee": by_assignee,
            "by_type":     by_type,
        }

    except Exception as e:
        logger.error("[MongoDB] Error getting statistics: %s", str(e))
        return {}


def search_tickets(query: str, fields: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Search tickets by text across common fields."""
    if not is_mongodb_enabled():
        return []

    try:
        collection = get_tickets_collection()
        if collection is None:
            return []

        if not fields:
            fields = ["summary", "description", "module", "feature", "test_name", "developer_name"]

        regex_query = {"$regex": query, "$options": "i"}
        filter_dict = {"$or": [{field: regex_query} for field in fields]}

        tickets = list(collection.find(filter_dict).limit(50))
        for ticket in tickets:
            ticket["_id"] = str(ticket.get("_id"))

        logger.info("[MongoDB] Found %d tickets matching '%s'", len(tickets), query)
        return tickets

    except Exception as e:
        logger.error("[MongoDB] Error searching tickets: %s", str(e))
        return []