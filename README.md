# automation-testing-backend

FastAPI backend for the test automation platform. Orchestrates test runs, Appium
and ADB, Allure reporting, Jira and Slack integration, APK handling and the test
management database.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing`](../automation-testing) and
[`automation-testing-frontend`](../automation-testing-frontend). The Python
package was renamed `new_backend` → `app` in the process.

## Layout

```
app/                 the FastAPI application (was new_backend/)
app/core/paths.py    locates the sibling tests repo and the runtime data dir
migrations/          Alembic migrations
alembic.ini          script_location = migrations
```

## APK storage

APKs and the icons extracted from them are **not** kept in the repo — they are
hundreds of megabytes each and a redeploy or fresh clone would lose them. They
live in a machine-wide data directory instead:

```
%PROGRAMDATA%\TestAutomationPlatform\
├── apks\     served to the UI by GET /test/apk-list
└── icons\    served at /static/icons/<name>.png
```

On Windows this is shared across user accounts, which matters because the
backend runs under a secondary one. Elsewhere it defaults to
`~/.test-automation-platform`.

Override with `PLATFORM_DATA_DIR` — that is the knob CI should set, pointing at
a workspace or cache path so APKs persist between pipeline runs:

```bash
PLATFORM_DATA_DIR=D:\ci\test-automation-data
```

`APK_STORAGE_DIR` and `APK_ICON_DIR` override the two folders individually. All
three are read in `app/core/paths.py`; the directories are created on startup,
so a fresh machine or CI runner needs no manual setup.

## Requires the tests repo

This service does not just talk to the automation suite, it loads it: it imports
`tests.test_runner`, reads `tests.test_type_config`, AST-parses files under
`tests/`, runs the `ui-parser` validator and serves Allure output generated
there. It expects `automation-testing` as a **sibling folder**:

```
Projects/
├── automation-testing/
└── automation-testing-backend/
```

If your checkouts are not side by side, set `TESTS_REPO_PATH` (see
`.env.example`).

## This service is machine-bound

It shells out to `adb`, Appium and the Allure CLI, and drives a physically
connected Android device. It is meant to run on the laptop that has those, not
on a cloud host. To reach it from a frontend deployed elsewhere, expose it
through a tunnel and point `VITE_API_BASE_URL` at that URL.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env          # TESTS_REPO_PATH, ALLURE_CMD
cp app/.env.example app/.env  # DB and integration secrets
```

## Running

```bash
python -X utf8 -m uvicorn app.main:app --reload --port 8000
```

Migrations:

```bash
alembic upgrade head
```
