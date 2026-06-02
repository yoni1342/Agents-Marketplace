"""Database engine + session dependency.

Mirrors Bench's db setup so the model/router code reads the same, but
points at the marketplace's own database (``settings.database_url``).
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, create_engine

from .config import settings

# pool_pre_ping avoids handing out a connection the DB has already dropped
# (common behind a managed Postgres that recycles idle connections).
engine = create_engine(settings.database_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
