import pytest
from sqlalchemy.dialects import postgresql

from app.repositories.employee_repository import EmployeeRepository


class _Result:
    def scalar_one(self):
        return 0

    def scalars(self):
        return self

    def all(self):
        return []


class _CaptureDb:
    def __init__(self):
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _Result()


def _compiled_sql(stmt) -> str:
    return str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


@pytest.mark.asyncio
async def test_role_id_filter_avoids_distinct_on_json_columns():
    """PostgreSQL json has no equality operator, so DISTINCT employees.* 500s."""
    db = _CaptureDb()

    await EmployeeRepository.get_paginated(db, tenant_id=1, role_id_filters=[11])

    assert db.statements
    for stmt in db.statements:
        sql = _compiled_sql(stmt).lower()
        assert "distinct" not in sql
        assert "employee_roles.employee_id" in sql
        assert "employee_roles.role_id in (11)" in sql
