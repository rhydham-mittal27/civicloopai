"""Developer CLI for the ML layer.

    python -m civicloop.ml_tools seed --count 1500   # simulated history, for demos and tests only
    python -m civicloop.ml_tools train               # train the risk model from the database
    python -m civicloop.ml_tools status
"""

from __future__ import annotations

import argparse
import json
import os

from civicloop.db import create_engine, create_session_factory, init_db
from civicloop.models import User, UserRole
from civicloop.repositories import AuditEventRepository, UserRepository
from civicloop.services.ml import MLService


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["seed", "train", "status"])
    parser.add_argument("--count", type=int, default=1500)
    parser.add_argument("--city", default="Chandigarh", help="the city (tenant) to seed, train or report on")
    parser.add_argument("--database-url", default=os.getenv("CIVICLOOP_DATABASE_URL", "sqlite:///civicloop.db"))
    args = parser.parse_args()

    engine = create_engine(args.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        from civicloop.tenancy import bind_tenant, get_or_create_tenant

        bind_tenant(session, get_or_create_tenant(session, args.city, verified=True)[0].id)
        if args.command == "seed":
            from civicloop.synthetic import seed_synthetic_history

            print(f"added {seed_synthetic_history(session, args.count)} SYNTHETIC reports (not real data)")
            return
        users = UserRepository(session)
        ml = MLService(session, AuditEventRepository(session), users)
        if args.command == "status":
            print(json.dumps(ml.status(), indent=2, default=str))
            return
        admin = session.query(User).filter(User.role == UserRole.ADMIN, User.is_active.is_(True)).first()
        if admin is None:
            raise SystemExit("Training is recorded against an admin account; create one first.")
        result = ml.train_risk(admin.id)
        session.commit()
        print(result["reason"])


if __name__ == "__main__":
    main()
