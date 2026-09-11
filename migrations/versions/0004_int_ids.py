"""switch all test-management PKs/FKs from CHAR(36) UUIDs to AUTO_INCREMENT integers

Rebuilds the 9 tables with integer surrogate keys. applications, modules and
priorities rows are preserved (captured, tables rebuilt, re-inserted with new
sequential ids, remapping the module->application FK). All downstream tables
(test_cases, test_runs, results, logs, attachments, bugs) are empty at this
revision, so nothing is preserved there.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


# ── Full DDL for the rebuilt (integer-id) schema ──────────────────────────────
_CREATE_STATEMENTS = [
    """
    CREATE TABLE applications (
        application_id INT AUTO_INCREMENT PRIMARY KEY,
        application_name VARCHAR(150) NOT NULL,
        platform VARCHAR(30) NOT NULL,
        package_name VARCHAR(255),
        variant VARCHAR(30),
        description TEXT,
        status BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE priorities (
        priority_id INT AUTO_INCREMENT PRIMARY KEY,
        priority_name VARCHAR(50) NOT NULL,
        color VARCHAR(30),
        display_order INT DEFAULT 0
    )
    """,
    """
    CREATE TABLE modules (
        module_id INT AUTO_INCREMENT PRIMARY KEY,
        application_id INT NOT NULL,
        module_name VARCHAR(150) NOT NULL,
        description TEXT,
        display_order INT DEFAULT 0,
        status BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_module_application
            FOREIGN KEY (application_id) REFERENCES applications(application_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE test_cases (
        testcase_id INT AUTO_INCREMENT PRIMARY KEY,
        testcase_key VARCHAR(50) UNIQUE NOT NULL,
        title VARCHAR(300) NOT NULL,
        application_id INT NOT NULL,
        module_id INT NOT NULL,
        priority_id INT,
        test_types JSON NOT NULL,
        polarity VARCHAR(20),
        description TEXT,
        expected_result TEXT,
        automation_enabled BOOLEAN DEFAULT TRUE,
        status BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_tc_app FOREIGN KEY(application_id) REFERENCES applications(application_id),
        CONSTRAINT fk_tc_module FOREIGN KEY(module_id) REFERENCES modules(module_id),
        CONSTRAINT fk_tc_priority FOREIGN KEY(priority_id) REFERENCES priorities(priority_id)
    )
    """,
    """
    CREATE TABLE test_runs (
        run_id INT AUTO_INCREMENT PRIMARY KEY,
        run_name VARCHAR(200),
        application_id INT,
        module_id INT,
        test_type VARCHAR(100),
        environment VARCHAR(100),
        build_number VARCHAR(100),
        execution_type VARCHAR(30),
        triggered_by VARCHAR(150),
        status VARCHAR(30),
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        CONSTRAINT fk_run_app FOREIGN KEY(application_id) REFERENCES applications(application_id),
        CONSTRAINT fk_run_module FOREIGN KEY(module_id) REFERENCES modules(module_id)
    )
    """,
    """
    CREATE TABLE test_run_results (
        execution_id INT AUTO_INCREMENT PRIMARY KEY,
        run_id INT,
        testcase_id INT,
        status VARCHAR(30),
        execution_time DECIMAL(10,2),
        device_name VARCHAR(100),
        os_version VARCHAR(100),
        browser VARCHAR(100),
        failure_reason TEXT,
        allure_report TEXT,
        started_at TIMESTAMP NULL,
        completed_at TIMESTAMP NULL,
        CONSTRAINT fk_result_run FOREIGN KEY(run_id) REFERENCES test_runs(run_id) ON DELETE CASCADE,
        CONSTRAINT fk_result_testcase FOREIGN KEY(testcase_id) REFERENCES test_cases(testcase_id)
    )
    """,
    """
    CREATE TABLE execution_logs (
        log_id INT AUTO_INCREMENT PRIMARY KEY,
        execution_id INT,
        log_level VARCHAR(20),
        message LONGTEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_log_execution FOREIGN KEY(execution_id) REFERENCES test_run_results(execution_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE attachments (
        attachment_id INT AUTO_INCREMENT PRIMARY KEY,
        execution_id INT,
        file_name VARCHAR(255),
        file_type VARCHAR(50),
        file_url TEXT,
        uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_attachment_execution FOREIGN KEY(execution_id) REFERENCES test_run_results(execution_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE bugs (
        bug_id INT AUTO_INCREMENT PRIMARY KEY,
        execution_id INT,
        testcase_id INT,
        bug_title VARCHAR(255),
        severity VARCHAR(30),
        status VARCHAR(30),
        jira_ticket VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_bug_execution FOREIGN KEY(execution_id) REFERENCES test_run_results(execution_id),
        CONSTRAINT fk_bug_testcase FOREIGN KEY(testcase_id) REFERENCES test_cases(testcase_id)
    )
    """,
]

# Drop order respects FK dependencies (children first).
_DROP_ORDER = [
    "bugs", "attachments", "execution_logs", "test_run_results",
    "test_runs", "test_cases", "modules", "priorities", "applications",
]


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Capture the data worth preserving (order-independent; remap FKs later).
    apps = conn.execute(sa.text(
        "SELECT application_id, application_name, platform, package_name, variant, "
        "description, status FROM applications"
    )).mappings().all()
    priorities = conn.execute(sa.text(
        "SELECT priority_id, priority_name, color, display_order FROM priorities"
    )).mappings().all()
    modules = conn.execute(sa.text(
        "SELECT module_id, application_id, module_name, description, display_order, status "
        "FROM modules"
    )).mappings().all()

    # 2. Drop every table, then recreate with the integer-id schema.
    conn.execute(sa.text("SET FOREIGN_KEY_CHECKS = 0"))
    for table in _DROP_ORDER:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
    conn.execute(sa.text("SET FOREIGN_KEY_CHECKS = 1"))
    for stmt in _CREATE_STATEMENTS:
        conn.execute(sa.text(stmt))

    # 3. Re-insert preserved rows, capturing the new integer ids as we go.
    app_id_map: dict = {}
    for a in apps:
        res = conn.execute(
            sa.text(
                "INSERT INTO applications "
                "(application_name, platform, package_name, variant, description, status) "
                "VALUES (:name, :platform, :pkg, :variant, :desc, :status)"
            ),
            {
                "name": a["application_name"], "platform": a["platform"],
                "pkg": a["package_name"], "variant": a["variant"],
                "desc": a["description"], "status": a["status"],
            },
        )
        app_id_map[a["application_id"]] = res.lastrowid

    for p in priorities:
        conn.execute(
            sa.text(
                "INSERT INTO priorities (priority_name, color, display_order) "
                "VALUES (:name, :color, :order)"
            ),
            {"name": p["priority_name"], "color": p["color"], "order": p["display_order"]},
        )

    for m in modules:
        conn.execute(
            sa.text(
                "INSERT INTO modules "
                "(application_id, module_name, description, display_order, status) "
                "VALUES (:app_id, :name, :desc, :order, :status)"
            ),
            {
                "app_id": app_id_map.get(m["application_id"]),
                "name": m["module_name"], "desc": m["description"],
                "order": m["display_order"], "status": m["status"],
            },
        )


def downgrade() -> None:
    # One-way structural change; reverting to UUID keys with re-seeded data is not
    # supported. Recreate from 0001–0003 if you need the old schema.
    raise NotImplementedError("Downgrade from integer ids to UUID ids is not supported.")
