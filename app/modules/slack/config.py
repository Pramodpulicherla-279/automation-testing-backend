PACKAGE_VARIANT_MAP = {
    "com.agribride.krishivaas.farmer_app":       "regular_farmer",
    "com.agribride.krishivaas.client_app":       "regular_client",
    "com.agribride.krishivaas.farmer_state_app": "state_farmer",
    "com.agribride.krishivaas.client_state_app": "state_client",
}
APP_VARIANTS = {
    "regular_farmer": [
        {"name": "Login",       "path": "tests/test_cases/regular_farmer_test_cases/test_login_pytest.py"},
        {"name": "Dashboard",   "path": "tests/test_cases/regular_farmer_test_cases/TestOnboarding.py"},
        {"name": "Add Updates", "path": "tests/farmer/test_updates.py"},
    ],
    "regular_client": [
        {"name": "Login",       "path": "tests/test_cases/regular_client_test_cases/login_pytest.py"},
        {"name": "Marketplace", "path": "tests/client/test_marketplace.py"},
        {"name": "Cart",        "path": "tests/client/test_cart.py"},
    ],
    "state_farmer": [
        {"name": "Login",   "path": "tests/state_farmer/test_login.py"},
        {"name": "Schemes", "path": "tests/state_farmer/test_schemes.py"},
    ],
    "state_client": [
        {"name": "Login",      "path": "tests/test_cases/state_client_test_cases/test_login_pytest.py"},
        {"name": "Onboarding", "path": "tests/test_cases/state_client_test_cases/test_Onboarding.py"},
    ],
}

APP_DEVELOPER_MAP = {
    "regular_farmer": "@Anuj",
    "regular_client": "@samad ahmed",
    "state_farmer":   "@Swaroopa",
    "state_client":   "@Vikash Chandra",
}

APP_CONFIG = {
    "regular_farmer": {
        "developer_name": "Pramod",   # 👈 IMPORTANT
        "slack_user_id": "U0AT2P7V1K2",   # 👈 IMPORTANT
        "channel_id": "C0AJY6W7FFF"
    },
    "regular_client": {
        "developer_name": "Kiran",
        "slack_user_id": "U02BBBBBBB",
        "channel_id": "C0AJY6W7FFF"
    },
    "state_farmer": {
        "developer_name": "Swaroopa",
        "slack_user_id": "U03CCCCCCC",
        "channel_id": "C0AJY6W7FFF"
    },
    "state_client": {
        "developer_name": "Vikash Chandra",
        "slack_user_id": "U04DDDDDD",
        "channel_id": "C0AJY6W7FFF"
    }
}
