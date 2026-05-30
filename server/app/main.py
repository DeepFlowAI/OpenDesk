import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.configs.settings import settings
from app.routers import register_routers
from app.core.exceptions import register_exception_handlers
from app.db.session import AsyncSessionLocal, engine
from app.db.migration import run_migrations
from app.db.seed import seed_system_defaults
from app.extensions import load_extensions

LOG_FORMAT = "%(asctime)s %(levelname)s [%(filename)s:%(lineno)d %(funcName)s] %(message)s"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, force=True)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()
    async with AsyncSessionLocal() as db:
        await seed_system_defaults(db)
        await db.commit()
    if settings.REDIS_URL:
        from app.db.redis import redis_client
        await redis_client.initialize()

    # Optional: call-center orchestrator. Off by default in OSS to avoid
    # crashing the app when no telephony kernel is reachable.
    orchestrator = None
    if settings.CALL_CENTER_ENABLED:
        try:
            from app.services.call_center.orchestrator import get_orchestrator
            orchestrator = get_orchestrator()
            await orchestrator.start()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Call center orchestrator failed to start; continuing without it"
            )
            orchestrator = None

    yield

    # Shutdown call center
    if orchestrator is not None:
        try:
            await orchestrator.stop()
        except Exception:  # noqa: BLE001
            pass

    # Shutdown realtime transport
    from app.libs.realtime.factory import _instance as rt_instance
    if rt_instance:
        await rt_instance.close()
    if settings.REDIS_URL:
        from app.db.redis import redis_client
        await redis_client.close()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    register_routers(app)
    load_extensions(app)
    return app


_fastapi_app = create_app()

# Wrap with realtime transport (Socket.IO) so both REST and WS share one ASGI entry
from app.libs.realtime import create_realtime_transport  # noqa: E402

_rt = create_realtime_transport()

# Register Socket.IO event handlers before wrapping
from app.socketio import register_socketio_handlers  # noqa: E402
register_socketio_handlers()

app = _rt.wrap_asgi(_fastapi_app)
