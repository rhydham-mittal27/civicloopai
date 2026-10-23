"""Multi-tenancy: cities as tenants, and a tenant on every row.

Everything that exists before this migration is the original pilot city, Chandigarh.
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_multi_tenancy"
down_revision = "0002_auth_password"
branch_labels = None
depends_on = None

TABLES = [
    "users", "incidents", "media_assets", "analysis_results", "duplicate_clusters",
    "duplicate_cluster_members", "risk_assessments", "work_orders", "route_plans",
    "route_stops", "verification_records", "audit_events", "evaluation_runs",
    "sensor_readings", "jobs",
]


def upgrade() -> None:
    connection = op.get_bind()
    inspector = inspect(connection)
    if "tenants" not in inspector.get_table_names():
        op.create_table(
            "tenants",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("name", sa.String(150), nullable=False),
            sa.Column("slug", sa.String(160), nullable=False, unique=True),
            sa.Column("state", sa.String(100)),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_tenants_slug", "tenants", ["slug"], unique=True)
    pilot_id = str(uuid.uuid4())
    existing = connection.execute(sa.text("SELECT id FROM tenants WHERE slug = 'chandigarh'")).scalar()
    if existing is None:
        connection.execute(
            sa.text("INSERT INTO tenants (id, name, slug, state, is_active) VALUES (:id, 'Chandigarh', 'chandigarh', 'Chandigarh', :t)"),
            {"id": pilot_id, "t": True},
        )
    else:
        pilot_id = existing

    for table in TABLES:
        if table not in inspector.get_table_names():
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if "tenant_id" not in columns:
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("tenant_id", sa.String(36), nullable=True))
            connection.execute(sa.text(f"UPDATE {table} SET tenant_id = :t WHERE tenant_id IS NULL"), {"t": pilot_id})
            with op.batch_alter_table(table) as batch:
                batch.alter_column("tenant_id", existing_type=sa.String(36), nullable=False)
                batch.create_foreign_key(f"fk_{table}_tenant", "tenants", ["tenant_id"], ["id"])
                batch.create_index(f"ix_{table}_tenant_id", ["tenant_id"])
    for table in ("users", "incidents"):
        columns = {c["name"] for c in inspect(connection).get_columns(table)}
        if "pincode" not in columns:
            with op.batch_alter_table(table) as batch:
                batch.add_column(sa.Column("pincode", sa.String(6), nullable=True))
                batch.create_index(f"ix_{table}_pincode", ["pincode"])


def downgrade() -> None:
    connection = op.get_bind()
    inspector = inspect(connection)
    for table in ("users", "incidents"):
        if "pincode" in {c["name"] for c in inspector.get_columns(table)}:
            indexes = {i["name"] for i in inspector.get_indexes(table)}
            with op.batch_alter_table(table) as batch:
                if f"ix_{table}_pincode" in indexes:
                    batch.drop_index(f"ix_{table}_pincode")
                batch.drop_column("pincode")
    for table in reversed(TABLES):
        if table not in inspector.get_table_names():
            continue
        if "tenant_id" not in {c["name"] for c in inspector.get_columns(table)}:
            continue
        indexes = {i["name"] for i in inspector.get_indexes(table)}
        foreign_keys = {fk["name"] for fk in inspector.get_foreign_keys(table) if fk["referred_table"] == "tenants"}
        with op.batch_alter_table(table) as batch:
            if f"ix_{table}_tenant_id" in indexes:
                batch.drop_index(f"ix_{table}_tenant_id")
            for name in foreign_keys:
                if name:
                    batch.drop_constraint(name, type_="foreignkey")
            batch.drop_column("tenant_id")
    op.drop_table("tenants")
