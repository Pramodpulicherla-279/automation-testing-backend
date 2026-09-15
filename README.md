# automation-testing-backend

FastAPI backend for the test automation platform: the test management database
and API, the WebSocket the UI listens on, Jira and Slack integration, and
orchestration of test runs. The runs themselves — Android device, Appium, APKs,
pytest, Allure — happen on **test runners** on the laptops (the `runner`
package in [`automation-testing`](../automation-testing)).

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing`](../automation-testing) and
[`automation-testing-frontend`](../automation-testing-frontend). The Python
package was renamed `new_backend` → `app` in the process.

## Layout

```
app/                        the FastAPI application (was new_backend/)
app/core/runner_hub.py      the connections to the laptops' test runners
app/modules/runner/         /runner/status and the runners' WebSocket (/runner/ws)
migrations/                 Alembic migrations
alembic.ini                 script_location = migrations
```

## How it reaches the laptops

Nothing on this side knows a laptop's address. Each laptop's runner connects
**out** to `/runner/ws` and keeps the WebSocket open. Commands go down it, and
replies, a status heartbeat and run-finished events come back up. The repos
share no code or file paths; everything goes over URLs.

```
                        ┌──WebSocket (opened by laptop A)── runner A + phone
frontend ──HTTPS──► backend
                        └──WebSocket (opened by laptop B)── runner B + phone
```

- **Laptops are named** by their runner: the laptop's hostname, or its
  `RUNNER_NAME`. `GET /runner/status` lists the connected ones, with each
  one's phone, Appium state and whether it's busy. A new connection under a
  name already connected replaces the old one, which is how a laptop reconnects.
- **Laptop endpoints take `?runner=<name>`**: device and Appium status, Appium
  start and stop, the APK list, stop, reports. Starting a run takes
  `runner_id` in the body. With exactly one laptop connected, you can leave it
  out.
- **Reading test sources** (`/api/automation-tests`, `/api/test-type-tests`)
  can go to any laptop, since they all have the same suite.
- **Live messages carry the run's id.** All laptops' runs share the
  `/ws/test-status` feed, and each screen shows only the run it started. The
  UI supplies the run id when it starts a run, so it can recognize its run
  from the very first message.
- **When a laptop isn't available:** status polls read "no device" / "Appium
  stopped", and the APK and test lists come back empty. Actions answer **503**
  with the reason, such as the laptop not being connected, or several laptops
  being connected and none chosen.

There is no authentication: anything that connects to `/runner/ws` is treated as
a laptop. Connection state lives in this process, so run the backend as a
**single process** (no multiple workers or instances).

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
