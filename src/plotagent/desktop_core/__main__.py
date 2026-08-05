"""Run the PlotAgent desktop Core as a stdio sidecar."""

from __future__ import annotations

import signal
from types import FrameType

from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.runtime import CoreRuntime


class _SignalExit(BaseException):
    pass


def main() -> int:
    application = DesktopApplication()
    runtime = CoreRuntime(configure_services=application.configure_services)

    def handle_signal(_signum: int, _frame: FrameType | None) -> None:
        raise _SignalExit

    handled_signals = [signal.SIGINT, signal.SIGTERM]
    previous = {item: signal.getsignal(item) for item in handled_signals}
    for item in handled_signals:
        signal.signal(item, handle_signal)
    try:
        return runtime.run()
    except _SignalExit:
        runtime.close()
        return 0
    except BaseException:
        runtime.logger.event("DESKTOP_CORE_FATAL", error_code="INTERNAL_ERROR")
        runtime.close()
        return 1
    finally:
        application.close()
        for item, handler in previous.items():
            signal.signal(item, handler)


if __name__ == "__main__":
    raise SystemExit(main())
