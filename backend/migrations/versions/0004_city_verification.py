"""Cities opened by self-registration start unverified; every existing city counts as verified."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0004_city_verification"
down_revision = "0003_multi_tenancy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if "verified" not in {c["name"] for c in inspect(connection).get_columns("tenants")}:
        with op.batch_alter_table("tenants") as batch:
            batch.add_column(sa.Column("verified", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    connection = op.get_bind()
    if "verified" in {c["name"] for c in inspect(connection).get_columns("tenants")}:
        with op.batch_alter_table("tenants") as batch:
            batch.drop_column("verified")
