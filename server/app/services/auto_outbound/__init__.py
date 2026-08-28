"""Auto-outbound dial engine package."""

from app.services.auto_outbound.engine import (
    AutoOutboundDialEngine,
    DialSessionContext,
    get_dial_engine,
    set_dial_engine,
    try_handle_auto_outbound_answered,
    try_handle_auto_outbound_ended,
)
from app.services.auto_outbound.outcome_mapping import (
    AutoOutboundTerminalState,
    map_outcome,
)
from app.services.auto_outbound.capacity import DialCapacityPlanner
from app.services.auto_outbound.pacing import DefaultPacingResolver
from app.services.auto_outbound.reception import ReceptionDispatcher

__all__ = [
    "AutoOutboundDialEngine",
    "AutoOutboundTerminalState",
    "DefaultPacingResolver",
    "DialCapacityPlanner",
    "DialSessionContext",
    "ReceptionDispatcher",
    "get_dial_engine",
    "map_outcome",
    "set_dial_engine",
    "try_handle_auto_outbound_answered",
    "try_handle_auto_outbound_ended",
]
