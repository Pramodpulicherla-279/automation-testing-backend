"""seed reference data

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-20

"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

priorities_table = sa.table(
    "priorities",
    sa.column("priority_id", sa.CHAR(36)),
    sa.column("priority_name", sa.String(50)),
    sa.column("color", sa.String(30)),
    sa.column("display_order", sa.Integer),
)

applications_table = sa.table(
    "applications",
    sa.column("application_id", sa.CHAR(36)),
    sa.column("application_name", sa.String(150)),
    sa.column("platform", sa.String(30)),
    sa.column("package_name", sa.String(255)),
    sa.column("description", sa.Text),
    sa.column("status", sa.Boolean),
)


def upgrade() -> None:
    op.bulk_insert(
        priorities_table,
        [
            {"priority_id": str(uuid.uuid4()), "priority_name": "Critical", "color": "#EF4444", "display_order": 1},
            {"priority_id": str(uuid.uuid4()), "priority_name": "High", "color": "#F97316", "display_order": 2},
            {"priority_id": str(uuid.uuid4()), "priority_name": "Medium", "color": "#FACC15", "display_order": 3},
            {"priority_id": str(uuid.uuid4()), "priority_name": "Low", "color": "#22C55E", "display_order": 4},
        ],
    )

    op.bulk_insert(
        applications_table,
        [
            {
                "application_id": str(uuid.uuid4()),
                "application_name": "Regular Farmer App",
                "platform": "Android",
                "package_name": "com.krishivaas.regular",
                "description": "Regular Farmer Application",
                "status": True,
            },
            {
                "application_id": str(uuid.uuid4()),
                "application_name": "State Farmer App",
                "platform": "Android",
                "package_name": "com.krishivaas.state",
                "description": "State Farmer Application",
                "status": True,
            },
            {
                "application_id": str(uuid.uuid4()),
                "application_name": "Regular Client App",
                "platform": "Android",
                "package_name": "com.krishivaas.client",
                "description": "Regular Client Application",
                "status": True,
            },
            {
                "application_id": str(uuid.uuid4()),
                "application_name": "State Client App",
                "platform": "Android",
                "package_name": "com.krishivaas.stateclient",
                "description": "State Client Application",
                "status": True,
            },
            {
                "application_id": str(uuid.uuid4()),
                "application_name": "Admin Portal",
                "platform": "Web",
                "package_name": None,
                "description": "Web Admin Portal",
                "status": True,
            },
        ],
    )


def downgrade() -> None:
    op.execute("DELETE FROM applications")
    op.execute("DELETE FROM priorities")
