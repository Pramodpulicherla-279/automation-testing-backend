from google import genai
from google.genai import types
import json
import os

# ── Client is created lazily so importing this module never raises an error
# ── even if GEMINI_API_KEY is not yet in the environment at import time.
_client = None

def _get_client():
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Add it to your backend/.env file and restart the server."
            )
        _client = genai.Client(api_key=api_key)
    return _client


def generate_jira_description(issue_data):

    prompt = f"""
You are a QA automation assistant.

Convert the following issue details into a professional Jira bug report.

Use EXACTLY this format — no deviations:

In the <app_name>, when a user <brief description of the scenario>, the issue occurs. <One sentence explaining what goes wrong and why it matters (e.g. improper state handling, missing refresh, etc.)>

Steps to Reproduce
1.
2.
3.
... (list every step clearly, starting from login if applicable)

Actual Result
<What actually happens after following the steps>

Expected Result
<What should have happened instead>

Rules:
- Title must be a plain sentence, not a question.
- Description must be a single short paragraph (2-3 sentences max).
- Steps must be numbered, one action per step.
- Actual Result and Expected Result must each be a single clear sentence.
- Do NOT include section headers like "Title:", just the label followed by the content on the next line.
- Only return the formatted output, nothing else.

Issue Details:
{json.dumps(issue_data, indent=2)}
"""

    resp = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2
        )
    )

    return resp.text.strip()

def generate_jira_title(issue_data):
    """Generate only the title — used separately by the /api/jira/enhance endpoint."""
 
    prompt = f"""
You are a QA automation assistant.
 
Generate a concise, professional Jira bug ticket title (max 80 characters) for the following issue.
 
Rules:
- Format: <app_name> <version> — <short description of what went wrong>
- Example: "Krishivaas Farmer 1.3.97 — Old UI displayed after switching from offline to online"
- Use present tense.
- Only return the title string, nothing else.
 
Issue details:
App: {issue_data.get("app_name", "Unknown")} v{issue_data.get("app_version", "")}
Module: {issue_data.get("module", "Unknown")}
Feature: {issue_data.get("feature", "")}
Test name: {issue_data.get("test_name", "")}
Raw description snippet: {str(issue_data.get("description", ""))[:300]}
"""
 
    resp = _get_client().models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2
        )
    )
 
    return resp.text.strip().strip('"').strip("'")