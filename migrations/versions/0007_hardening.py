"""Sign-in revocation, retry-safe report creation, and one live work order per incident."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0007_hardening"
down_revision = "0006_route_driver"
branch_labels = None
depends_on = None


def _columns(connection, table: str) -> set[str]:
    return {c["name"] for c in inspect(connection).get_columns(table)}


def _indexes(connection, table: str) -> set[str]:
    return {i["name"] for i in inspect(connection).get_indexes(table)}


def upgrade() -> None:
    connection = op.get_bind()

    if "token_version" not in _columns(connection, "users"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))

    if "client_key" not in _columns(connection, "incidents"):
        with op.batch_alter_table("incidents") as batch:
            batch.add_column(sa.Column("client_key", sa.String(64), nullable=True))
            batch.create_unique_constraint("uq_incident_client_key", ["reporter_id", "client_key"])

    if "uq_work_order_live_per_incident" not in _indexes(connection, "work_orders"):
        # Older data may already hold two live orders for one incident. Keep the newest and cancel the others,
        # so the rule can be switched on without failing the upgrade.
        connection.execute(
            sa.text(
                "UPDATE work_orders SET status = 'CANCELLED' WHERE status != 'CANCELLED' AND EXISTS ("
                " SELECT 1 FROM work_orders newer WHERE newer.incident_id = work_orders.incident_id"
                " AND newer.status != 'CANCELLED' AND newer.created_at > work_orders.created_at)"
            )
        )
        op.create_index(
            "uq_work_order_live_per_incident",
            "work_orders",
            ["incident_id"],
            unique=True,
            sqlite_where=sa.text("status != 'CANCELLED'"),
            postgresql_where=sa.text("status != 'CANCELLED'"),
        )


def downgrade() -> None:
    connection = op.get_bind()
    if "uq_work_order_live_per_incident" in _indexes(connection, "work_orders"):
        op.drop_index("uq_work_order_live_per_incident", table_name="work_orders")
    if "client_key" in _columns(connection, "incidents"):
        with op.batch_alter_table("incidents") as batch:
            batch.drop_constraint("uq_incident_client_key", type_="unique")
            batch.drop_column("client_key")
    if "token_version" in _columns(connection, "users"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("token_version")
