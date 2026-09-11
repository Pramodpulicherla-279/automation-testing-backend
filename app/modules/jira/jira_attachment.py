import requests
from app.modules.jira.jira_config import config


def attach_screenshot(issue_key, screenshot_path):

    with open(screenshot_path, "rb") as f:

        files = {
            "file": (screenshot_path, f, "image/png")
        }

        response = requests.post(
            config.attachment_endpoint(issue_key),
            files=files,
            auth=config.auth,
            headers=config.attachment_headers
        )

    if response.status_code == 200:
        print(f"Screenshot attached to {issue_key}")
    else:
        print("Attachment failed:", response.text)