"""Verify file API extension.

Registers ``/api/v1/verify-files/*`` for the Tenant Platform to manage domain
ownership verification files (e.g. Tencent's ``XFu51qFh2n.txt``). Files are
stored in the database and materialized to ``settings.VERIFY_FILES_DIR`` so
nginx can serve them at the deployment root path.
"""
from fastapi import FastAPI


def register(app: FastAPI) -> None:
    from .router import public_router, router

    app.include_router(router, prefix="/api/v1")
    # Public root-path serving (nginx proxies `/<name>.txt` here).
    app.include_router(public_router)
