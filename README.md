# automation-testing-backend

FastAPI backend for the test automation platform: the test management database
and API, the WebSocket the UI listens on, Jira and Slack integration, and
orchestration of test runs. The runs themselves — Android device, Appium, APKs,
pytest, Allure — happen on the **test runner** in the
[`automation-testing`](../automation-testing) repo, on the laptop.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing`](../automation-testing) and
[`automation-testing-frontend`](../automation-testing-frontend). The Python
package was renamed `new_backend` → `app` in the process.

## Layout

```
app/                        the FastAPI application (was new_backend/)
app/core/runner_hub.py      the connection to the test runner
app/modules/runner/         /runner/status and the runner's WebSocket (/runner/ws)
migrations/                 Alembic migrations
alembic.ini                 script_location = migrations
```

## How it reaches the laptop

Nothing on this side knows the laptop's address. The runner connects **out** to
this backend at `/runner/ws` and keeps the WebSocket open. Commands go down it,
and replies, a status heartbeat and run-finished events come back up:

```
frontend ──HTTPS──► backend ◄──WebSocket (opened by the laptop)── runner
                       ▲                                           │ pytest · Appium · adb · APKs
                       └──── logs, module status, results (HTTPS) ─┘
```

The repos share no code or file paths; everything goes over these URLs. There
is no authentication anywhere: whatever connects to `/runner/ws` is the runner,
and the newest connection replaces an older one. That is also how the laptop
reconnects after a drop or a backend redeploy. The connection lives in this
process, so run the backend as a **single process** (no multiple workers or
instances).

The `/test/*` endpoints keep their paths and payloads, so the frontend didn't
change. Behind them:

- **Status polls** (`/test/device-status`, `/test/appium/status`) answer from
  the runner's latest heartbeat. With no runner they read as "no device" and
  "Appium stopped".
- **Lists the page loads on open** (`/test/apk-list`, `/api/automation-tests`,
  `/api/test-type-tests`) come from the runner. With no runner they are empty,
  not errors.
- **Actions** (start and stop runs, Appium start and stop, reports) are
  commands to the runner. With no runner they answer **503** with the reason.
- `GET /runner/status` reports whether a runner is connected, and which machine.

## Where it can run

Anywhere, including Render. It needs no tests repo, adb, Appium or Allure. For a
cloud deploy, set:

- `CORS_ALLOW_ORIGINS` — include the deployed frontend's URL, or the browser
  blocks every call.
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` /
  `MYSQL_DATABASE` — they default to `localhost`, which doesn't exist on Render.
  `app/.env` is gitignored, so set these as service environment variables.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env          # CORS_ALLOW_ORIGINS
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
