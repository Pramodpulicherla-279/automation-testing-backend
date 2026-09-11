import os

# from core.utils import is_unknown
from .jira_config import config
from typing import Optional, List, Dict, Any
from requests.auth import HTTPBasicAuth
import requests
import json
from datetime import datetime, timedelta


def search_duplicate_issue(summary: str):
    """
    Search Jira for existing bug with same summary.
    """
    jql = f'project={config.project_key} AND summary~"{summary}" AND statusCategory!=Done'

    payload = {
        "jql": jql,
        "maxResults": 5,
        "fields": ["summary"],
    }

    response = requests.post(
        config.search_endpoint,
        json=payload,
        auth=config.auth,
        headers=config.json_headers,
        timeout=30,
    )

    if response.status_code == 200:
        issues = response.json().get("issues", [])
        if issues:
            return issues[0]["key"]

    return None

def is_unknown(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        s = value.strip()
        return not s or s.lower().startswith("unknown")
    return False

def _normalize_steps(steps_executed):
    if not steps_executed:
        return []
    return [str(step).strip() for step in steps_executed if str(step).strip()]

def _extract_nodeid_from_description(description_text: str) -> str | None:
    """
    Looks for:
      Test Case:
      <nodeid>
    """
    if not description_text:
        return None

    lines = [ln.rstrip("\r") for ln in description_text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "test case:":
            for j in range(i + 1, min(i + 10, len(lines))):
                candidate = lines[j].strip()
                if candidate:
                    return candidate
            return None
    return None


def _parse_environment_kv_from_description(description_text: str) -> dict:
    """
    Extracts simple key/value lines if present.
    """
    if not description_text:
        return {}

    out: dict[str, str] = {}
    lines = [ln.strip() for ln in description_text.splitlines()]
    key_map = {
        "app": "app_name",
        "version": "app_version",
        "apk version": "app_version",
        "app version": "app_version",
        "developer": "developer_name",
        "module": "module",
        "feature": "feature",
        "test": "test_name",
        "test id": "test_id",
    }

    for ln in lines:
        if ":" not in ln:
            continue
        left, right = ln.split(":", 1)
        k = left.strip().lower()
        v = right.strip()
        if not v:
            continue
        if k in key_map:
            out[key_map[k]] = v

    return out


def _extract_app_name_from_environment_block(description_text: str) -> str | None:
    """
    If description contains:
      Environment:
      Krishivaas Farmer APK

    return "Krishivaas Farmer".
    """
    if not description_text:
        return None

    lines = [ln.strip() for ln in description_text.splitlines()]
    for i, ln in enumerate(lines):
        if ln.lower() == "environment:":
            for j in range(i + 1, min(i + 10, len(lines))):
                candidate = lines[j].strip()
                if not candidate:
                    continue
                if candidate.lower().startswith("automation payload"):
                    return None
                if candidate.lower().endswith(" apk"):
                    return candidate[:-4].strip()
                return candidate
    return None


def _infer_module_from_nodeid(nodeid: str) -> str | None:
    if not nodeid:
        return None
    s = nodeid.lower()
    if "login" in s:
        return "Login"
    if "onboarding" in s or "addfarm" in s:
        return "Onboarding"
    if "marketplace" in s:
        return "Marketplace"
    if "cart" in s:
        return "Cart"
    return None


def _infer_feature_from_nodeid(nodeid: str) -> str | None:
    return _infer_module_from_nodeid(nodeid)


def _infer_test_name_from_nodeid(nodeid: str) -> str | None:
    """
    nodeid example:
      tests/.../test_login_pytest.py::TestLogin::test_login_success
    """
    if not nodeid:
        return None
    parts = [p for p in str(nodeid).split("::") if p]
    return parts[-1] if parts else None


def _build_business_payload(
    app_name=None,
    app_version=None,
    module=None,
    feature=None,
    issue_summary=None,
    test_name=None,
    test_id=None,
    steps_executed=None,
    developer_name=None,
):
    return {
        "app_name": app_name or "Unknown App",
        "app_version": app_version or "Unknown Version",
        "module": module or "Unknown Module",
        "feature": feature or "Unknown Feature",
        "issue_summary": issue_summary or "Automation Failure",
        "test_name": test_name or "Unknown Test",
        "steps_executed": _normalize_steps(steps_executed),
        "developer_name": developer_name or "Unknown Developer",
    }


def get_jira_user_display_name(account_id: str) -> str | None:
    if not account_id:
        return None

    resp = requests.get(
        f"{config.url}/rest/api/3/user",
        params={"accountId": account_id},
        auth=config.auth,
        headers={"Accept": "application/json"},
        timeout=20,
    )
    if resp.status_code == 200:
        return (resp.json() or {}).get("displayName")
    return None


def _adf_to_text(adf: dict | None) -> str:
    if not isinstance(adf, dict):
        return ""

    out: list[str] = []

    def walk(node):
        if not isinstance(node, dict):
            return
        t = node.get("type")

        if t == "text":
            out.append(node.get("text", ""))
            return

        if t in {"paragraph", "heading", "blockquote"}:
            for c in node.get("content", []) or []:
                walk(c)
            out.append("\n")
            return

        if t in {"bulletList", "orderedList"}:
            for c in node.get("content", []) or []:
                walk(c)
            out.append("\n")
            return

        if t == "listItem":
            out.append("- ")
            for c in node.get("content", []) or []:
                walk(c)
            out.append("\n")
            return

        for c in node.get("content", []) or []:
            walk(c)

    walk(adf)
    text = "".join(out)
    lines = [ln.rstrip() for ln in text.splitlines()]
    return "\n".join([ln for ln in lines if ln.strip()]).strip()


def _extract_embedded_automation_payload(description_text: str) -> dict | None:
    """
    Parses the JSON block embedded under:
      Automation Payload:
      { ...json... }
    """
    if not description_text:
        return None

    marker = "Automation Payload:"
    idx = description_text.find(marker)
    if idx == -1:
        return None

    after = description_text[idx + len(marker):].strip()
    after = after.split("\n\nAllure Report:", 1)[0].strip()

    try:
        return json.loads(after)
    except Exception:
        start = after.find("{")
        end = after.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(after[start:end + 1])
            except Exception:
                return None

    return None


def fetch_issue_from_jira(issue_key: str, *, fields: list[str] | None = None) -> dict | None:
    if not issue_key:
        return None

    params = {}
    if fields:
        params["fields"] = ",".join(fields)

    resp = requests.get(
        f"{config.url}/rest/api/3/issue/{issue_key}",
        params=params,
        auth=config.auth,
        headers={"Accept": "application/json"},
        timeout=30,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def _fix_env_label() -> str:
    """
    Your rule: fix version must be Production or Staging.
    Controlled via env var APP_ENV (or JIRA_FIX_ENV).
    """
    env = (os.getenv("JIRA_FIX_ENV") or os.getenv("APP_ENV") or "production").strip().lower()
    return "Staging" if env in {"stage", "staging", "uat", "test"} else "Production"


def calculate_duration(start_date: Optional[str], end_date: Optional[str]) -> str:
    """Calculate test duration from ISO format dates."""
    if not start_date or not end_date:
        return "Unknown"
    
    try:
        start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        duration = (end - start).total_seconds()
        minutes = int(duration / 60)
        seconds = int(duration % 60)
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"
    except Exception as e:
        print(f"[WARN] Could not calculate duration: {e}")
        return "Unknown"


def _text_to_adf(text: str) -> dict:
    """
    Convert plain text to Atlassian Document Format (ADF).
    Handles multiline text by splitting into paragraphs.
    """
    if not text:
        text = "Test automation failure detected."
    
    paragraphs = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}]
            })
    
    if not paragraphs:
        paragraphs = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Test automation failure detected."}]
            }
        ]
    
    return {
        "type": "doc",
        "version": 1,
        "content": paragraphs
    }


def _build_formatted_description(
    description: str,
    app_name: Optional[str] = None,
    app_version: Optional[str] = None,
    module: Optional[str] = None,
    feature: Optional[str] = None,
    test_name: Optional[str] = None,
    test_id: Optional[str] = None,
    steps_executed: Optional[List[str]] = None,
    developer_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sprint: Optional[str] = None,
) -> dict:
    """
    Build a formatted description in ADF (Atlassian Document Format).
    Since custom fields aren't available, we embed the data in the description.
    Returns ADF JSON structure, not plain text.
    """
    content = []
    
    # Add main description
    main_desc = description.strip() if description else "Test automation failure detected."
    for line in main_desc.split("\n"):
        line = line.strip()
        if line:
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}]
            })
    
    metadata_lines = []
    if app_name and not is_unknown(app_name):
        metadata_lines.append(f"App: {app_name}")
    if app_version and not is_unknown(app_version):
        metadata_lines.append(f"Version: {app_version}")
    if module and not is_unknown(module):
        metadata_lines.append(f"Module: {module}")
    if feature and not is_unknown(feature):
        metadata_lines.append(f"Feature: {feature}")
    if test_name and not is_unknown(test_name):
        metadata_lines.append(f"Test: {test_name}")
    if developer_name and not is_unknown(developer_name):
        metadata_lines.append(f"Developer: {developer_name}")
    if start_date:
        metadata_lines.append(f"Start: {start_date}")
    if end_date:
        metadata_lines.append(f"End: {end_date}")
    if start_date and end_date:
        duration = calculate_duration(start_date, end_date)
        metadata_lines.append(f"Duration: {duration}")
    if sprint:
        metadata_lines.append(f"Sprint: {sprint}")
    
    if metadata_lines:
        content.append({
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Metadata"}]
        })

        for line in metadata_lines:
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}]
            })
    
    # Add steps section if available
    if steps_executed and len(steps_executed) > 0:
        content.append({
            "type": "heading",
            "attrs": {"level": 3},
            "content": [{"type": "text", "text": "Steps Executed"}]
        })
        
        for i, step in enumerate(steps_executed, 1):
            content.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": f"{i}. {step}"}]
            })
    
    return {
        "type": "doc",
        "version": 1,
        "content": content
    }


def build_extended_jira_payload(issue_key: str, business_payload: dict) -> dict:
    """
    Extended payload for console/frontend.

    Your mapping rules:
      1) app_version = APK version (must be passed from runner/CLI or embedded payload)
      2) affects_version = [app_name]
         fix_version = [Production|Staging]
      3) start_date = today's date
      4) parent = module
         sprint = "Automation" (hardcoded)
    """
    issue = fetch_issue_from_jira(
        issue_key,
        fields=["summary", "description", "assignee", "duedate"],
    ) or {}

    fields_obj = issue.get("fields", {}) or {}
    summary = fields_obj.get("summary") or ""
    description_text = _adf_to_text(fields_obj.get("description"))

    # Prefer embedded payload from Jira description if present
    embedded = _extract_embedded_automation_payload(description_text) or {}

    merged = dict(business_payload or {})
    for k in [
        "app_name",
        "app_version",
        "module",
        "feature",
        "issue_summary",
        "test_name",
        "test_id",
        "steps_executed",
        "developer_name",
    ]:
        if k in embedded and embedded.get(k) not in (None, "", [], {}):
            merged[k] = embedded[k]

    # Extra fallback: if app_name still unknown, try to parse from description
    if is_unknown(merged.get("app_name")):
        env_app = _extract_app_name_from_environment_block(description_text)
        if env_app:
            merged["app_name"] = env_app

    # Developer name preference: Jira assignee displayName
    assignee = fields_obj.get("assignee") or {}
    assignee_name = assignee.get("displayName") if isinstance(assignee, dict) else None
    if assignee_name:
        merged["developer_name"] = assignee_name

    app_name = merged.get("app_name") or "Unknown App"
    app_version = merged.get("app_version") or "Unknown Version"
    module = merged.get("module") or "Unknown Module"

    affects_versions = [app_name] if not is_unknown(app_name) else []
    fix_versions = [_fix_env_label()]
    sprint_val = "Automation"
    start_date_val = datetime.today().isoformat()

    end_date_val = fields_obj.get("duedate")
    if not end_date_val:
        end_date_val = (datetime.today() + timedelta(days=1)).isoformat()

    merged.update(
        {
            "issue_id": issue_key,
            "issue_url": f"{config.url}/browse/{issue_key}",
            "title": summary,
            "description": description_text,
            "app_version": app_version,
            "affects_version": affects_versions,
            "fix_version": fix_versions,
            "parent": module,
            "sprint": sprint_val,
            "start_date": start_date_val,
            "end_date": end_date_val,
        }
    )

    return merged


def create_jira_issue(
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
    fix_version: Optional[str] = None,
    affects_version: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    sprint: Optional[str] = None,
) -> Optional[str]:
    """
    Create a JIRA issue using STANDARD FIELDS ONLY.
    
    Metadata is embedded in the description instead of custom fields.
    This works with any JIRA instance without custom field configuration.
    
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
        JIRA issue key (e.g., "AT-87") or None if creation failed
    """
    
    if not all([config.url, config.email, config.api_token, config.project_key]):
        raise Exception(
            f"JIRA config incomplete: url={config.url}, email={config.email}, "
            f"token_set={bool(config.api_token)}, project_key={config.project_key}"
        )

    print("\n" + "=" * 70)
    print("[JIRA] Creating issue...")
    print("=" * 70)

    # Build formatted description with embedded metadata (returns ADF format)
    formatted_description_adf = _build_formatted_description(
        description=description,
        app_name=app_name,
        app_version=app_version,
        module=module,
        feature=feature,
        test_name=test_name,
        test_id=test_id,
        steps_executed=steps_executed,
        developer_name=developer_name,
        start_date=start_date,
        end_date=end_date,
        sprint=sprint,
    )

    # Prepare issue fields — STANDARD FIELDS ONLY
    fields = {
        "project": {"key": config.project_key},
        "summary": summary or issue_summary or "Test Automation Failure",
        "description": formatted_description_adf,  # ← ADF format
        "issuetype": {"name": issue_type or config.issue_type or "Bug"},
        "priority": {"name": priority or config.priority or "High"},
    }

    # Add labels for categorization
    labels = ["automation", "mobile-app"]
    if app_name and not is_unknown(app_name):
        labels.append(app_name.lower().replace(" ", "-"))
    if module and not is_unknown(module):
        labels.append(module.lower())
    fields["labels"] = labels

    # Due date (tomorrow)
    due_date = (datetime.today() + timedelta(days=1)).isoformat().split("T")[0]
    fields["duedate"] = due_date

    # Assign to configured user if available
    if config.assignee_id:
        fields["assignee"] = {"id": config.assignee_id}

    print(f"[JIRA] Summary: {fields['summary']}")
    print(f"[JIRA] Labels: {', '.join(labels)}")
    print(f"[JIRA] Due Date: {due_date}")
    print(f"[JIRA] Project: {config.project_key}")

    # Create issue via JIRA REST API
    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    url = f"{config.url}/rest/api/3/issue"

    def _post_issue(payload_fields: dict) -> requests.Response:
        print(f"[JIRA] POST {url}")
        return requests.post(
            url,
            auth=auth,
            headers=headers,
            json={"fields": payload_fields},
            timeout=15,
        )

    def _response_error_text(response: requests.Response) -> str:
        try:
            error_payload = response.json()
        except Exception:
            return response.text[:1000]

        if isinstance(error_payload, dict):
            error_messages = error_payload.get("errorMessages") or []
            field_errors = error_payload.get("errors") or {}
            pieces = []
            if error_messages:
                pieces.append("; ".join(str(item) for item in error_messages))
            if field_errors:
                pieces.append(
                    ", ".join(f"{field}: {message}" for field, message in field_errors.items())
                )
            if pieces:
                return " | ".join(pieces)
        return json.dumps(error_payload, indent=2)

    try:
        response = _post_issue(fields)

        if response.status_code == 400 and "assignee" in fields:
            error_text = _response_error_text(response).lower()
            if "assignee" in error_text or "assign" in error_text:
                print("[JIRA] Retrying without assignee after Jira validation error")
                fallback_fields = dict(fields)
                fallback_fields.pop("assignee", None)
                response = _post_issue(fallback_fields)

        print(f"[JIRA] Response status: {response.status_code}")

        if response.status_code == 201:
            data = response.json()
            issue_key = data.get("key")
            issue_id = data.get("id")

            print(f"\n✓ JIRA Issue Created Successfully!")
            print(f"  Issue Key: {issue_key}")
            print(f"  Issue ID: {issue_id}")
            print(f"  URL: {config.url}/browse/{issue_key}")
            print("=" * 70 + "\n")

            return issue_key

        elif response.status_code == 400:
            error_text = _response_error_text(response)
            print(f"\n✗ JIRA 400 Bad Request")
            print(f"  Error: {error_text}")
            raise Exception(f"JIRA 400: {error_text}")

        elif response.status_code == 401:
            raise Exception(
                f"JIRA 401 Unauthorized: Check JIRA_EMAIL and JIRA_API_TOKEN in .env"
            )

        elif response.status_code == 403:
            raise Exception(
                f"JIRA 403 Forbidden: No permission to create issues in {config.project_key}"
            )

        else:
            raise Exception(f"JIRA {response.status_code}: {response.text[:500]}")

    except requests.exceptions.Timeout:
        raise Exception(
            "JIRA request timed out (15s). Check JIRA_URL and network connectivity."
        )
    except requests.exceptions.ConnectionError:
        raise Exception(f"Cannot connect to JIRA at {config.url}. Check JIRA_URL in .env")
    except Exception as e:
        print(f"\n✗ Error creating JIRA issue: {e}")
        print("=" * 70 + "\n")
        raise


def get_jira_issue(issue_key: str) -> Optional[Dict[str, Any]]:
    """Fetch JIRA issue details."""
    if not all([config.url, config.email, config.api_token]):
        raise Exception("JIRA config incomplete")

    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json"}
    url = f"{config.url}/rest/api/3/issue/{issue_key}"

    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch {issue_key}: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error fetching issue: {e}")
        return None


def add_comment(issue_key: str, comment_text: str) -> bool:
    """Add a comment to a JIRA issue."""
    if not all([config.url, config.email, config.api_token]):
        raise Exception("JIRA config incomplete")

    auth = HTTPBasicAuth(config.email, config.api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    comment_adf = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment_text}],
                }
            ],
        }
    }

    url = f"{config.url}/rest/api/3/issue/{issue_key}/comments"

    try:
        response = requests.post(
            url,
            json=comment_adf,
            auth=auth,
            headers=headers,
            timeout=20,
        )

        if response.status_code == 201:
            print(f"✓ Comment added to {issue_key}")
            return True
        else:
            print(f"Failed to add comment: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error adding comment: {e}")
        return False