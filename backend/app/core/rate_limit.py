"""One atomic request counter per verified user, shared through the database."""
from time import time

from fastapi import HTTPException
from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import config
from app.models.database import RequestBudget


def check_request_budget(sessions, user_id):
    minute = int(time() // 60)
    with sessions() as db:
        insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
        count = db.scalar(insert(RequestBudget).values(id=user_id, window=minute, count=1).on_conflict_do_update(
            index_elements=[RequestBudget.id],
            set_={"window": minute, "count": case((RequestBudget.window == minute, RequestBudget.count + 1), else_=1)},
        ).returning(RequestBudget.count))
        db.commit()
    if count > config.user_requests_per_minute:
        raise HTTPException(429, "Too many requests. Wait briefly before retrying.", headers={"Retry-After": str(60 - int(time()) % 60)})
