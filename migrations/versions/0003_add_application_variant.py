"""add variant column to applications

Adds the automation role key (regular_farmer | regular_client | state_farmer |
state_client) used to map a UI application selection to its test folder, now that
the four unified-app roles all share a single package_name.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22

"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE applications ADD COLUMN variant VARCHAR(30) NULL AFTER package_name"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP COLUMN variant")
