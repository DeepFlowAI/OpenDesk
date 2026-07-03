import subprocess

import pytest

from app.db import migration


def test_run_migrations_raises_when_alembic_fails(monkeypatch):
    monkeypatch.setattr(migration.settings, "AUTO_MIGRATE", True)

    def fake_run(args, capture_output, text):
        return subprocess.CompletedProcess(
            args,
            255,
            stdout="",
            stderr="Multiple head revisions are present",
        )

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Database migration failed"):
        migration.run_migrations()


def test_run_migrations_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(migration.settings, "AUTO_MIGRATE", False)

    def fake_run(*_args, **_kwargs):
        raise AssertionError("alembic should not run when auto-migrate is disabled")

    monkeypatch.setattr(migration.subprocess, "run", fake_run)

    migration.run_migrations()
