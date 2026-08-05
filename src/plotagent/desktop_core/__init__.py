"""Bounded stdio runtime for the PlotAgent desktop Core."""

from plotagent.desktop_core.application import DesktopApplication, ProjectSession
from plotagent.desktop_core.runtime import CoreRuntime
from plotagent.desktop_core.services import RpcContext, ServiceRegistry
from plotagent.desktop_core.tasks import CancellationToken, TaskRegistry

__all__ = [
    "CancellationToken",
    "CoreRuntime",
    "DesktopApplication",
    "ProjectSession",
    "RpcContext",
    "ServiceRegistry",
    "TaskRegistry",
]
