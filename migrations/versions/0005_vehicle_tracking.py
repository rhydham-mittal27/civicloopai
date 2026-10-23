"""Live vehicle tracking: vehicles and their GPS history."""

from alembic import op
from sqlalchemy import inspect

revision = "0005_vehicle_tracking"
down_revision = "0004_city_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from civicloop import models  # noqa: F401
    from civicloop.db import Base

    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names())
    tables = [Base.metadata.tables[name] for name in ("vehicles", "vehicle_pings") if name not in existing]
    if tables:
        Base.metadata.create_all(bind=connection, tables=tables)


def downgrade() -> None:
    connection = op.get_bind()
    existing = set(inspect(connection).get_table_names())
    for name in ("vehicle_pings", "vehicles"):
        if name in existing:
            op.drop_table(name)
