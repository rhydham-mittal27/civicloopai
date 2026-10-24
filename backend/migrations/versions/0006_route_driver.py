"""A route belongs to one driver, and records when it was approved (sent to them)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0006_route_driver"
down_revision = "0005_vehicle_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    columns = {c["name"] for c in inspect(connection).get_columns("route_plans")}
    with op.batch_alter_table("route_plans") as batch:
        if "approved_at" not in columns:
            batch.add_column(sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
        if "worker_id" not in columns:
            batch.add_column(sa.Column("worker_id", sa.String(36), nullable=True))
            batch.create_index("ix_route_plans_worker_id", ["worker_id"])
            batch.create_foreign_key("fk_route_plans_worker", "users", ["worker_id"], ["id"])
        if "vehicle_id" not in columns:
            batch.add_column(sa.Column("vehicle_id", sa.String(36), nullable=True))
            batch.create_foreign_key("fk_route_plans_vehicle", "vehicles", ["vehicle_id"], ["id"])
    # routes made before this change get the driver of their first stop, when that job has one
    connection.execute(
        sa.text(
            "UPDATE route_plans SET worker_id = ("
            " SELECT wo.assigned_to FROM route_stops rs JOIN work_orders wo ON wo.id = rs.work_order_id"
            " WHERE rs.route_plan_id = route_plans.id ORDER BY rs.sequence LIMIT 1)"
            " WHERE worker_id IS NULL"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    columns = {c["name"] for c in inspect(connection).get_columns("route_plans")}
    with op.batch_alter_table("route_plans") as batch:
        for name in ("vehicle_id", "worker_id", "approved_at"):
            if name in columns:
                batch.drop_column(name)
