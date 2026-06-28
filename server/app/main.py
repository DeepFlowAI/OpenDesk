import logging
import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.configs.logging import setup_logging
from app.configs.settings import settings, assert_safe_production_config
from app.core.trace import set_request_id, set_trace_id
from app.libs.observability import init_observability, shutdown_observability
from app.routers import register_routers
from app.core.exceptions import register_exception_handlers
from app.db.session import AsyncSessionLocal, engine
from app.db.migration import run_migrations
from app.db.seed import seed_system_defaults
from app.extensions import load_extensions

# Init order matters: observability must be ready *before* setup_logging() so
# the OTel logging handler can be attached to the root logger from the start.
init_observability()
setup_logging()


async def _visitor_timeout_close_worker() -> None:
    from app.services.visitor_timeout_close_service import VisitorTimeoutCloseService

    logger = logging.getLogger(__name__)
    interval = settings.VISITOR_TIMEOUT_CLOSE_SCAN_INTERVAL_SECONDS
    batch_size = settings.VISITOR_TIMEOUT_CLOSE_SCAN_BATCH_SIZE
    while True:
        try:
            redis = None
            if settings.REDIS_URL:
                from app.db.redis import redis_client

                redis = redis_client.client
            async with AsyncSessionLocal() as db:
                result = await VisitorTimeoutCloseService.process_due_states(
                    db,
                    redis,
                    limit=batch_size,
                )
            if result["reminded"] or result["closed"]:
                logger.info(
                    "visitor_timeout_close_scan checked=%s reminded=%s closed=%s skipped=%s",
                    result["checked"],
                    result["reminded"],
                    result["closed"],
                    result["skipped"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Visitor timeout auto-close scan failed")
        await asyncio.sleep(interval)


async def _open_agent_bot_timeout_worker() -> None:
    from app.services.open_agent_bot_timeout_service import OpenAgentBotTimeoutService

    logger = logging.getLogger(__name__)
    interval = settings.OPEN_AGENT_BOT_TIMEOUT_SCAN_INTERVAL_SECONDS
    batch_size = settings.OPEN_AGENT_BOT_TIMEOUT_SCAN_BATCH_SIZE
    while True:
        try:
            async with AsyncSessionLocal() as db:
                result = await OpenAgentBotTimeoutService.process_expired_conversations(
                    db,
                    limit=batch_size,
                )
            if result["closed"]:
                logger.info(
                    "open_agent_bot_timeout_scan checked=%s closed=%s skipped=%s",
                    result["checked"],
                    result["closed"],
                    result["skipped"],
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("OpenAgent bot timeout scan failed")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_safe_production_config()
    run_migrations()
    async with AsyncSessionLocal() as db:
        await seed_system_defaults(db)
        await db.commit()
    if settings.REDIS_URL:
        from app.db.redis import redis_client
        await redis_client.initialize()

    visitor_timeout_task = None
    if settings.VISITOR_TIMEOUT_CLOSE_WORKER_ENABLED:
        visitor_timeout_task = asyncio.create_task(
            _visitor_timeout_close_worker(),
            name="visitor-timeout-close-worker",
        )
    bot_timeout_task = None
    if settings.OPEN_AGENT_BOT_TIMEOUT_WORKER_ENABLED:
        bot_timeout_task = asyncio.create_task(
            _open_agent_bot_timeout_worker(),
            name="open-agent-bot-timeout-worker",
        )

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

    if visitor_timeout_task is not None:
        visitor_timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await visitor_timeout_task
    if bot_timeout_task is not None:
        bot_timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await bot_timeout_task

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
    # Flush remaining batched spans/logs before the process exits.
    shutdown_observability()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def trace_context_middleware(request: Request, call_next):
        """Assign a trace_id to every request so all logs emitted while
        handling it carry the same correlation id. Honors a client-supplied
        ``X-Trace-Id`` / ``X-Request-Id`` when present, and echoes the
        resolved trace_id back in the ``X-Trace-Id`` response header."""
        incoming = request.headers.get("X-Trace-Id")
        trace_id = set_trace_id(incoming if incoming else None)
        set_request_id(request.headers.get("X-Request-Id"))
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    cors_origins = settings.cors_origins
    # The CORS spec forbids combining a "*" origin with credentials, so we only
    # enable credentialed cross-origin requests when an explicit allowlist is set.
    allow_credentials = cors_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
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
