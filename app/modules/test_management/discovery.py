"""
test_management/discovery.py
───────────────────────────────
Parses automation source files under tests/ to find test functions tagged
with an @allure.title("ID -- description") decorator, so DB test cases
(testcase_key) can be matched against real, currently-active automation code.

AST-based, not regex-over-raw-text: ast.walk() only visits real parsed
nodes, so commented-out @allure.title(...) lines are excluded automatically.
"""

import ast
import os
import re
from pathlib import Path

from fastapi import HTTPException

# Sources live in the sibling tests repo; the paths this module emits and accepts
# are relative to that repo's root, which is what the UI and the runner both use.
from app.core.paths import TESTS_DIR as _TESTS_DIR, TESTS_ROOT as _REPO_ROOT

_ID_PATTERN = re.compile(r"^\s*([A-Za-z]{1,4}_\d{2,4})\s*--?\s*(.*)$")

# Leading pytest/catalog prefix stripped when matching a source function name to a
# DB testcase_key. MUST stay in lockstep with the frontend's `normalizeFuncKey`
# (TestScreen.jsx). Example: source `test_LOGINPOS_TC_029` and sheet/DB key
# `LOGINPOS_TC_029` both reduce to `loginpos_tc_029` and therefore match — the
# author writes `test_` (pytest requires it) while the catalogued ID omits it.
_MATCH_PREFIX = re.compile(r"^(tc|test)_")


def normalize_match_key(name: str) -> str:
    """Reduce a testcase_key or a source `def` name to a common comparison key."""
    return _MATCH_PREFIX.sub("", (name or "").strip().lower())


def _resolve_safe_path(relative_path: str) -> Path:
    """Resolve a repo-relative path, rejecting anything outside tests/."""
    candidate = (_REPO_ROOT / relative_path).resolve()
    if candidate.suffix != ".py":
        raise HTTPException(400, "Only .py files can be inspected")
    if not candidate.is_relative_to(_TESTS_DIR):
        raise HTTPException(400, "Path must be inside tests/")
    if not candidate.is_file():
        raise HTTPException(404, f"File not found: {relative_path}")
    return candidate


def _extract_allure_title(decorator_list: list[ast.expr]) -> str | None:
    for dec in decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr == "title"
            and isinstance(dec.func.value, ast.Name)
            and dec.func.value.id == "allure"
            and dec.args
            and isinstance(dec.args[0], ast.Constant)
            and isinstance(dec.args[0].value, str)
        ):
            return dec.args[0].value
    return None


def discover_automation_tests(relative_path: str) -> list[dict]:
    """Given a repo-relative .py path under tests/, return every currently-active,
    pytest-collectable test function as {id, title, function_name, line}.

    Every `test*` function is returned (so the source `def` name is always
    available for DB matching / issue tracking), whether or not it carries an
    @allure.title. When the title is of the form "ID -- description", `id` and a
    cleaned `title` are split out; otherwise `id` is None and `title` is the raw
    allure title (or "" when there is none). Matching to a DB testcase_key is done
    by the caller on function_name (see TestScreen.jsx), which is robust to the
    tc_/test_ prefix difference between the DB key and the pytest function name.
    """
    absolute_path = _resolve_safe_path(relative_path)
    source = absolute_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(absolute_path))

    results: list[dict] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # pytest's default collection prefix — mirror it so we list exactly what runs.
        if not node.name.startswith("test"):
            continue

        raw_title = _extract_allure_title(node.decorator_list)
        tc_id: str | None = None
        title = raw_title or ""
        if raw_title:
            match = _ID_PATTERN.match(raw_title)
            if match:
                tc_id = match.group(1).upper()
                title = match.group(2).strip()

        results.append({
            "id": tc_id,
            "title": title,
            "function_name": node.name,
            "line": node.lineno,
            # Key for matching to a DB testcase_key (tc_/test_ prefix stripped).
            "match_key": normalize_match_key(node.name),
        })
    return results


def discover_type_folder(type_label: str) -> list[dict]:
    """Return every test function physically under tests/test_suites/<type>/.

    For folder-defined tests the folder location IS the type authority (no DB tag),
    so this powers the UI's "which tests will this type run" view. Walks the per-app
    subfolders and reuses discover_automation_tests() per file. Each item adds:
      • file — repo-relative path (e.g. tests/test_suites/smoke/regular_farmer/…)
      • app  — the per-app subfolder name (regular_farmer / common / …)
    The type→folder mapping is imported from tests/test_type_config.py so the folder
    convention stays defined in exactly one place.
    """
    try:
        from app.core.paths import ensure_tests_importable
        ensure_tests_importable()
        from tests.test_type_config import folder_for_type
    except ImportError:
        return []

    folder = folder_for_type(type_label)
    if not folder or not os.path.isdir(folder):
        return []

    folder_abs = os.path.abspath(folder)
    results: list[dict] = []
    for root, _dirs, files in os.walk(folder_abs):
        for fname in sorted(files):
            if not (fname.startswith("test_") and fname.endswith(".py")):
                continue
            abs_path = os.path.join(root, fname)
            rel = os.path.relpath(abs_path, _REPO_ROOT).replace("\\", "/")
            sub = os.path.relpath(abs_path, folder_abs).replace("\\", "/")
            app = sub.split("/")[0] if "/" in sub else ""
            try:
                for fn in discover_automation_tests(rel):
                    item = dict(fn)
                    item["file"] = rel
                    item["app"] = app
                    results.append(item)
            except Exception:
                continue  # skip a file that fails to parse rather than 500 the whole view
    return results
