"""Extension loader.

Product modules (reports, telephony, sms_platform, tenants, verify_files)
live in this package and ship with the application. On startup, every
subpackage that defines ``register(app: FastAPI) -> None`` is auto-loaded
and typically registers extra routers.

Adding a module is additive: drop a new subpackage here with a
``register(app)`` function.
"""
import importlib
import logging
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def _augment_path_with_private_overlay() -> None:
    """Append an optional local overlay directory to this package's search path.

    In-tree modules are found first. No-op when the overlay directory is absent.
    """
    repo_root = Path(__file__).resolve().parents[3]
    private_dir = repo_root / "private" / "extensions" / "server"
    if not private_dir.is_dir():
        return
    path_str = str(private_dir)
    if path_str not in __path__:
        __path__.append(path_str)


_augment_path_with_private_overlay()


def load_extensions(app: "FastAPI") -> list[str]:
    """Discover and register all extension subpackages.

    Returns the list of successfully-loaded extension names (for logging).
    Extension import / register failures are logged but never raise — a
    broken extension must not prevent the rest of the app from booting.
    """
    loaded: list[str] = []
    seen: set[str] = set()
    for _finder, name, ispkg in pkgutil.iter_modules(__path__):
        if not ispkg or name.startswith("_") or name in seen:
            continue
        seen.add(name)
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception:
            logger.exception("Failed to import extension '%s'", name)
            continue
        register = getattr(mod, "register", None)
        if not callable(register):
            logger.warning("Extension '%s' has no register(app) function — skipped", name)
            continue
        try:
            register(app)
        except Exception:
            logger.exception("register() failed for extension '%s'", name)
            continue
        loaded.append(name)
        logger.info("Loaded extension: %s", name)
    if loaded:
        logger.info("Loaded %d extension(s): %s", len(loaded), ", ".join(loaded))
    # Expose to request handlers (e.g. /api/v1/system/info) as a single source
    # of truth for which add-on modules are active in this build.
    app.state.loaded_extensions = loaded
    return loaded
