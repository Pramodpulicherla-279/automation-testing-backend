"""
test_management/discovery.py
───────────────────────────────
Matching catalogued test cases to pytest function names. Reading the test
sources themselves happens on the test runner, next to the suite.
"""

import re

# Leading pytest/catalog prefix stripped when matching a source function name to a
# DB testcase_key. MUST stay in lockstep with the runner's copy
# (automation-testing/runner/discovery.py) and the frontend's `normalizeFuncKey`
# (TestScreen.jsx). Example: source `test_LOGINPOS_TC_029` and sheet/DB key
# `LOGINPOS_TC_029` both reduce to `loginpos_tc_029` and therefore match — the
# author writes `test_` (pytest requires it) while the catalogued ID omits it.
_MATCH_PREFIX = re.compile(r"^(tc|test)_")


def normalize_match_key(name: str) -> str:
    """Reduce a testcase_key or a source `def` name to a common comparison key."""
    return _MATCH_PREFIX.sub("", (name or "").strip().lower())
