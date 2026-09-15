# automation-testing-backend

FastAPI backend for the test automation platform: the test management database
and API, the WebSocket the UI listens on, Jira and Slack integration, and
orchestration of test runs. The runs themselves (the Android device, Appium,
APKs, pytest and Allure) happen on the **runner** in the
[`automation-testing`](../automation-testing) repo, which this service calls
over HTTP.

Split out of the `test-automation-platform` mono repo alongside
[`automation-testing`](../automation-testing) and
[`automation-testing-frontend`](../automation-testing-frontend). The Python
package was renamed `new_backend` → `app` in the process.

## Layout

```
app/                        the FastAPI application (was new_backend/)
app/core/runner_client.py   HTTP client for the runner (RUNNER_URL, RUNNER_TOKEN)
app/core/paths.py           filesystem roots, used where the runner imports this package
migrations/                 Alembic migrations
alembic.ini                 script_location = migrations
```

## How it reaches the device

```
frontend ──HTTP──► backend ──HTTP + RUNNER_TOKEN──► runner (laptop)
                     ▲                                 │  pytest · Appium · adb · APKs
                     └──── logs, module status, ───────┘
                           run-finished
```

The `/test/*` endpoints keep their paths and payloads, so the frontend is
unchanged. Behind them, each call goes to the runner:

| Backend endpoint | Runner call |
|---|---|
| `GET /test/device-status` | `GET /device-status` |
| `GET /test/appium/status`, `POST /test/appium/start` · `stop` | `/appium/…` |
| `GET /test/apk-list` | `GET /apks` |
| `POST /test/start-test`, `/test/start-test-existing` | `POST /apks/prepare`, then `POST /runs` |
| `POST /test/stop-test` | `POST /runs/stop` |
| `POST /test/generate-report`, `/test/allure/start` | `POST /report`, `POST /allure/start` |
| `GET /api/automation-tests`, `/api/test-type-tests` | `GET /discovery/…` |

A run executes in the background on the runner. When it ends, the runner calls
`POST /test/runner/run-finished` (checked against `RUNNER_TOKEN`), which sends
the Slack summary.

If the runner can't be reached, or rejects the token, those endpoints answer
**503** with the reason. The two status polls instead read as "no device" and
"Appium stopped", so the UI isn't flooded with errors. The rest of the API is
unaffected.

## Where it can run

Anywhere. It no longer needs the tests repo, adb, Appium or Allure on its own
host. For a cloud deploy (e.g. Render), set:

- `RUNNER_URL` — the tunnel URL that reaches the runner on the laptop.
- `RUNNER_TOKEN` — the same value the runner uses.
- `CORS_ALLOW_ORIGINS` — include the deployed frontend's URL, or the browser
  blocks every call.
- `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` /
  `MYSQL_DATABASE` — they default to `localhost`, which doesn't exist on Render.
  `app/.env` is gitignored, so set these as service environment variables.

## Setup

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env          # RUNNER_URL, RUNNER_TOKEN, CORS_ALLOW_ORIGINS
cp app/.env.example app/.env  # DB and integration secrets
```

## Running

```bash
python -X utf8 -m uvicorn app.main:app --reload --port 8000
```

Start the runner as well (see the `automation-testing` README). Without it the
UI shows no device and runs can't start.

Migrations:

```bash
alembic upgrade head
```
