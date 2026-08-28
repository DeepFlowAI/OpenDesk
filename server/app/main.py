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


async def _sms_bulk_send_worker() -> None:
    from app.services.sms_bulk_send_service import SmsBulkSendService

    logger = logging.getLogger(__name__)
    interval = settings.SMS_BULK_SEND_SCAN_INTERVAL_SECONDS
    while True:
        try:
            stats = await SmsBulkSendService.run_tick()
            if any(stats.values()):
                logger.info("sms_bulk_send_tick %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Bulk SMS send tick failed")
        await asyncio.sleep(interval)


async def _event_delivery_worker() -> None:
    from app.services.event_delivery_service import EventDeliveryService

    logger = logging.getLogger(__name__)
    interval = settings.EVENT_DELIVERY_SCAN_INTERVAL_SECONDS
    loop = asyncio.get_running_loop()
    next_cleanup_at = 0.0
    while True:
        try:
            stats = await EventDeliveryService.run_tick()
            if any(stats.values()):
                logger.info("event_delivery_tick %s", stats)
            if loop.time() >= next_cleanup_at:
                deleted = await EventDeliveryService.cleanup_completed()
                if deleted:
                    logger.info("event_delivery_cleanup deleted=%s", deleted)
                next_cleanup_at = (
                    loop.time() + settings.EVENT_DELIVERY_CLEANUP_INTERVAL_SECONDS
                )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Event delivery scan failed")
        await asyncio.sleep(interval)


async def _call_wrapup_timeout_worker() -> None:
    from app.services.call_wrapup_timeout_service import CallWrapupTimeoutService

    logger = logging.getLogger(__name__)
    interval = settings.CALL_WRAPUP_TIMEOUT_SCAN_INTERVAL_SECONDS
    while True:
        try:
            from app.db.redis import redis_client

            processed = await CallWrapupTimeoutService.process_expired(
                redis_client.client
            )
            if processed:
                logger.info("call_wrapup_timeout_scan processed=%s", processed)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Call wrap-up timeout scan failed")
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
    sms_bulk_send_task = None
    if settings.SMS_BULK_SEND_WORKER_ENABLED:
        sms_bulk_send_task = asyncio.create_task(
            _sms_bulk_send_worker(),
            name="sms-bulk-send-worker",
        )
    event_delivery_task = None
    if settings.EVENT_DELIVERY_WORKER_ENABLED:
        event_delivery_task = asyncio.create_task(
            _event_delivery_worker(),
            name="event-delivery-worker",
        )
    wrapup_timeout_task = None
    if settings.CALL_WRAPUP_TIMEOUT_WORKER_ENABLED and settings.REDIS_URL:
        wrapup_timeout_task = asyncio.create_task(
            _call_wrapup_timeout_worker(),
            name="call-wrapup-timeout-worker",
        )

    auto_outbound_engine = None
    if settings.AUTO_OUTBOUND_DIAL_WORKER_ENABLED and settings.REDIS_URL:
        try:
            from app.db.redis import redis_client as _ao_redis
            from app.services.auto_outbound import AutoOutboundDialEngine, set_dial_engine
            from app.services.auto_outbound.capacity import DialCapacityPlanner
            from app.services.auto_outbound.reception import ReceptionDispatcher

            _ao_client = _ao_redis.client
            auto_outbound_engine = AutoOutboundDialEngine(
                redis=_ao_client,
                reception=ReceptionDispatcher(redis=_ao_client),
                pacing_resolver=DialCapacityPlanner(redis=_ao_client),
            )
            set_dial_engine(auto_outbound_engine)
            await auto_outbound_engine.start()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Auto outbound dial worker failed to start; continuing without it"
            )
            auto_outbound_engine = None
            try:
                from app.services.auto_outbound import set_dial_engine

                set_dial_engine(None)
            except Exception:  # noqa: BLE001
                pass

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
            if orchestrator is not None and not orchestrator._started:
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
    if sms_bulk_send_task is not None:
        sms_bulk_send_task.cancel()
        with suppress(asyncio.CancelledError):
            await sms_bulk_send_task
    if event_delivery_task is not None:
        event_delivery_task.cancel()
        with suppress(asyncio.CancelledError):
            await event_delivery_task
    if wrapup_timeout_task is not None:
        wrapup_timeout_task.cancel()
        with suppress(asyncio.CancelledError):
            await wrapup_timeout_task
    if auto_outbound_engine is not None:
        try:
            await auto_outbound_engine.stop()
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("Auto outbound dial worker stop failed")

    # Shutdown call center: drain in-flight call workflows first so blue/green
    # rollouts do not tear down orchestration mid-call, then disconnect.
    if orchestrator is not None:
        try:
            await orchestrator.drain(timeout=float(settings.CALL_CENTER_DRAIN_TIMEOUT))
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception("Call center orchestrator drain failed")
        try:
            await orchestrator.stop()
        except Exception:  # noqa: BLE001
            pass

    # Keep the stopped engine registered while orchestration drains so terminal
    # call events can still finalize auto-outbound records and release slots.
    if auto_outbound_engine is not None:
        try:
            from app.services.auto_outbound import set_dial_engine

            set_dial_engine(None)
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
