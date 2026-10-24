"""Add password storage for local authentication."""

from alembic import op
from sqlalchemy import Column, String, inspect

revision = "0002_auth_password"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    if "password_hash" not in columns:
        op.add_column("users", Column("password_hash", String(length=255), nullable=True))


def downgrade() -> None:
    connection = op.get_bind()
    columns = {column["name"] for column in inspect(connection).get_columns("users")}
    if "password_hash" in columns:
        op.drop_column("users", "password_hash")