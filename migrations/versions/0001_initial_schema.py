"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-20

"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE applications (
            application_id CHAR(36) PRIMARY KEY,
            application_name VARCHAR(150) NOT NULL,
            platform VARCHAR(30) NOT NULL,
            package_name VARCHAR(255),
            description TEXT,
            status BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE priorities (
            priority_id CHAR(36) PRIMARY KEY,
            priority_name VARCHAR(50) NOT NULL,
            color VARCHAR(30),
            display_order INT DEFAULT 0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE modules (
            module_id CHAR(36) PRIMARY KEY,
            application_id CHAR(36) NOT NULL,
            module_name VARCHAR(150) NOT NULL,
            description TEXT,
            display_order INT DEFAULT 0,
            status BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            CONSTRAINT fk_module_application
                FOREIGN KEY (application_id)
                REFERENCES applications(application_id)
                ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE test_cases (
            testcase_id CHAR(36) PRIMARY KEY,
            testcase_key VARCHAR(50) UNIQUE NOT NULL,
            title VARCHAR(300) NOT NULL,
            application_id CHAR(36) NOT NULL,
            module_id CHAR(36) NOT NULL,
            priority_id CHAR(36),
            test_types JSON NOT NULL,
            polarity VARCHAR(20),
            description TEXT,
            expected_result TEXT,
            automation_enabled BOOLEAN DEFAULT TRUE,
            status BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

            CONSTRAINT fk_tc_app
                FOREIGN KEY(application_id)
                REFERENCES applications(application_id),

            CONSTRAINT fk_tc_module
                FOREIGN KEY(module_id)
                REFERENCES modules(module_id),

            CONSTRAINT fk_tc_priority
                FOREIGN KEY(priority_id)
                REFERENCES priorities(priority_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE test_runs (
            run_id CHAR(36) PRIMARY KEY,
            run_name VARCHAR(200),
            application_id CHAR(36),
            module_id CHAR(36),
            test_type VARCHAR(100),
            environment VARCHAR(100),
            build_number VARCHAR(100),
            execution_type VARCHAR(30),
            triggered_by VARCHAR(150),
            status VARCHAR(30),
            started_at TIMESTAMP,
            completed_at TIMESTAMP,

            CONSTRAINT fk_run_app
                FOREIGN KEY(application_id)
                REFERENCES applications(application_id),

            CONSTRAINT fk_run_module
                FOREIGN KEY(module_id)
                REFERENCES modules(module_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE test_run_results (
            execution_id CHAR(36) PRIMARY KEY,
            run_id CHAR(36),
            testcase_id CHAR(36),
            status VARCHAR(30),
            execution_time DECIMAL(10,2),
            device_name VARCHAR(100),
            os_version VARCHAR(100),
            browser VARCHAR(100),
            failure_reason TEXT,
            allure_report TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,

            CONSTRAINT fk_result_run
                FOREIGN KEY(run_id)
                REFERENCES test_runs(run_id)
                ON DELETE CASCADE,

            CONSTRAINT fk_result_testcase
                FOREIGN KEY(testcase_id)
                REFERENCES test_cases(testcase_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE execution_logs (
            log_id CHAR(36) PRIMARY KEY,
            execution_id CHAR(36),
            log_level VARCHAR(20),
            message LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_log_execution
                FOREIGN KEY(execution_id)
                REFERENCES test_run_results(execution_id)
                ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE attachments (
            attachment_id CHAR(36) PRIMARY KEY,
            execution_id CHAR(36),
            file_name VARCHAR(255),
            file_type VARCHAR(50),
            file_url TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_attachment_execution
                FOREIGN KEY(execution_id)
                REFERENCES test_run_results(execution_id)
                ON DELETE CASCADE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE bugs (
            bug_id CHAR(36) PRIMARY KEY,
            execution_id CHAR(36),
            testcase_id CHAR(36),
            bug_title VARCHAR(255),
            severity VARCHAR(30),
            status VARCHAR(30),
            jira_ticket VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT fk_bug_execution
                FOREIGN KEY(execution_id)
                REFERENCES test_run_results(execution_id),

            CONSTRAINT fk_bug_testcase
                FOREIGN KEY(testcase_id)
                REFERENCES test_cases(testcase_id)
        )
        """
    )


def downgrade() -> None:
    for table in (
        "bugs",
        "attachments",
        "execution_logs",
        "test_run_results",
        "test_runs",
        "test_cases",
        "modules",
        "priorities",
        "applications",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table}")
