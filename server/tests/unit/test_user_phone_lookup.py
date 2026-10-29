"""Exercise lookup predicates against the existing Python matching rules."""
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import postgresql

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.call_user_association_service import phone_match_keys


PHONES = [
    None, "", "---", "18601123206", "+86 (186) 0112-3206",
    "0086 186 0112 3206", "0018601123206", "8601123206",
    "+1 212-555-0123", "2125550123", "0012125550123",
    "862125550123", "8612125550123", "000018601123206",
    "010-8888-1234", "400-800-1234", "15500008888",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", PHONES)
async def test_phone_lookup_preserves_matching_and_tenant_isolation(target):
    db = SimpleNamespace(execute=AsyncMock(return_value=Mock(
        scalars=Mock(return_value=Mock(all=Mock(return_value=[])))
    )))
    keys = phone_match_keys(target)
    await UserRepository.list_by_phone_match_keys(db, 1, keys)
    if not keys:
        db.execute.assert_not_awaited()
        return

    statement = db.execute.await_args.args[0]
    # SQLite runs the real WHERE predicate with PostgreSQL's regexp_replace
    # emulated; no external database or application data is used.
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.connection.driver_connection.create_function(
            "regexp_replace", -1,
            lambda value, pattern, replacement, *flags: (
                None if value is None else re.sub(
                    pattern, replacement, value, count=0 if flags == ("g",) else 1
                )
            ),
        )
        conn.execute(text("CREATE TABLE users (id INTEGER, tenant_id INTEGER, phone TEXT)"))
        conn.execute(text("INSERT INTO users VALUES (:id, :tenant, :phone)"), [
            {"id": i, "tenant": tenant, "phone": phone}
            for tenant in (1, 2) for i, phone in enumerate(PHONES)
        ])
        matches = list(conn.execute(statement.with_only_columns(User.id)).scalars())
    engine.dispose()
    assert matches == [i for i, phone in enumerate(PHONES) if phone_match_keys(phone) & keys]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "regexp_replace(phone, '\\D', '', 'g')" in sql
    assert " IN " in sql
