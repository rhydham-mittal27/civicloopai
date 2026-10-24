"""Multi-tenancy: every row belongs to one city, and a request only ever sees its own city's rows.

Two session hooks do the work so no repository or route has to remember a `WHERE tenant_id`:

* reads: when a session carries ``info["tenant_id"]`` every SELECT on a tenant-scoped table is
  filtered to that tenant (``with_loader_criteria``);
* writes: new rows are stamped with the tenant of whatever they hang off (their incident, work
  order, actor...), or else the session's tenant. A row that disagrees with the session's tenant is
  refused.

Background workers and CLI tools open sessions without a tenant. They see everything, and the rows
they create inherit the tenant of the incident they work on.
"""

from __future__ import annotations

import os
import re
from typing import Any

from sqlalchemy import insert, event, select
from sqlalchemy.orm import Session, with_loader_criteria

from civicloop.models import Tenant, TenantScoped, User, new_id

TENANT_KEY = "tenant_id"
DEFAULT_SLUG = "default"
PINCODE_PATTERN = re.compile(r"^[1-9][0-9]{5}$")


class TenantMismatchError(RuntimeError):
    """A write tried to cross a tenant boundary."""


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def normalise_city(name: str) -> str:
    return " ".join(part.capitalize() for part in name.strip().split())


def normalise_pincode(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    code = re.sub(r"\s+", "", str(value))
    if not PINCODE_PATTERN.match(code):
        raise ValueError("Pincode must be 6 digits and cannot start with 0")
    return code


def platform_admin_emails() -> set[str]:
    """Operators of the whole deployment, named in CIVICLOOP_PLATFORM_ADMINS (comma separated emails)."""
    return {e.strip().lower() for e in os.getenv("CIVICLOOP_PLATFORM_ADMINS", "").split(",") if e.strip()}


def get_or_create_tenant(
    session: Session, city: str, state: str | None = None, *, verified: bool = False
) -> tuple[Tenant, bool]:
    """Find a city by name, or create it. Returns (tenant, created)."""
    slug = slugify(city)
    if not slug:
        raise ValueError("City is required")
    tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
    if tenant is not None:
        return tenant, False
    tenant = Tenant(name=normalise_city(city), slug=slug, state=(state or "").strip() or None, verified=verified)
    session.add(tenant)
    session.flush()
    return tenant, True


def default_tenant(session: Session) -> Tenant:
    """The catch-all city for rows created outside any request (tests, tools). Safe inside a flush."""
    for pending in session.new:
        if isinstance(pending, Tenant) and pending.slug == DEFAULT_SLUG:
            return pending
    tenant = session.scalar(select(Tenant).where(Tenant.slug == DEFAULT_SLUG))
    if tenant is None:
        # Written straight away, not queued with session.add(): with foreign keys enforced the city must exist
        # before the rows that point at it, and the unit of work does not order unrelated tables.
        tenant_id = new_id()
        session.execute(insert(Tenant).values(id=tenant_id, name="Default city", slug=DEFAULT_SLUG))
        tenant = session.get(Tenant, tenant_id)
    return tenant


REQUEST_KEY = "request_scoped"


def bind_tenant(session: Session, tenant_id: str | None) -> None:
    """Scope a session to one tenant (None lifts the scope, for workers and tools).

    A session that serves a signed-in request is marked request-scoped, and on it None is refused: lifting the
    scope there has to be a deliberate `lift_scope()`, so a forgotten argument can never show every city's data.
    """
    if tenant_id is None:
        if session.info.get(REQUEST_KEY):
            raise RuntimeError("A request session must stay scoped to one city; use lift_scope() for cross-city routes")
        session.info.pop(TENANT_KEY, None)
    else:
        session.info[TENANT_KEY] = tenant_id


def lift_scope(session: Session) -> None:
    """Deliberately look across every city (platform routes and the signed-in user's own home row)."""
    session.info.pop(TENANT_KEY, None)


def session_tenant(session: Session) -> str | None:
    return session.info.get(TENANT_KEY)


# attributes that point at a parent row, and the parent's class name
_PARENTS = (
    ("incident_id", "Incident"),
    ("work_order_id", "WorkOrder"),
    ("route_plan_id", "RoutePlan"),
    ("cluster_id", "DuplicateCluster"),
    ("vehicle_id", "Vehicle"),
)
_ACTORS = ("actor_id", "created_by", "reporter_id", "submitted_by", "approved_by")


def _inherited_tenant(session: Session, obj: Any) -> str | None:
    from civicloop import models

    for attr, class_name in _PARENTS:
        parent_id = getattr(obj, attr, None)
        if parent_id:
            parent = session.get(getattr(models, class_name), parent_id)
            if parent is not None and parent.tenant_id:
                return parent.tenant_id
    return None


def _actor_tenant(session: Session, obj: Any) -> str | None:
    for attr in _ACTORS:
        user_id = getattr(obj, attr, None)
        if user_id:
            user = session.get(User, user_id)
            if user is not None and user.tenant_id:
                return user.tenant_id
    return None


@event.listens_for(Session, "do_orm_execute")
def _scope_reads(state: Any) -> None:
    if not state.is_select or state.is_column_load:
        return
    tenant_id = state.session.info.get(TENANT_KEY)
    if tenant_id is None:
        return
    state.statement = state.statement.options(
        with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tenant_id, include_aliases=True)
    )


@event.listens_for(Session, "before_flush")
def _stamp_writes(session: Session, flush_context: Any, instances: Any) -> None:
    pending = [obj for obj in session.new if isinstance(obj, TenantScoped)]
    if not pending:
        return
    current = session.info.get(TENANT_KEY)
    with session.no_autoflush:
        for obj in pending:
            if obj.tenant_id is None:
                obj.tenant_id = (
                    _inherited_tenant(session, obj)
                    or current
                    or _actor_tenant(session, obj)  # a platform admin acting in another city stamps that city, not their own
                    or default_tenant(session).id
                )
            if current is not None and obj.tenant_id != current:
                raise TenantMismatchError("A record cannot be written into another city's data")
