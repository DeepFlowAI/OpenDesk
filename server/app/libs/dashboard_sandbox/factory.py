"""Factory for the configured dashboard sandbox provider."""

from app.configs.settings import settings
from app.libs.dashboard_sandbox.base import DashboardSandbox


def create_dashboard_sandbox() -> DashboardSandbox:
    """Create the configured dashboard sandbox without leaking providers to services."""
    match settings.DASHBOARD_SANDBOX_PROVIDER:
        case "subprocess":
            from app.libs.dashboard_sandbox.providers.subprocess import SubprocessDashboardSandbox

            return SubprocessDashboardSandbox()
        case provider:
            raise ValueError(f"Unsupported dashboard sandbox provider: {provider}")
