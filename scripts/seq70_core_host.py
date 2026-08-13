"""Run an isolated desktop Core for the Pi SEQ-70 evaluator."""

from __future__ import annotations

import argparse
from pathlib import Path

from plotagent.desktop_core.application import DesktopApplication
from plotagent.desktop_core.runtime import CoreRuntime
from plotagent.storage.catalog import Catalog

_PROVIDER_SETTING_KEY = "agent.provider.active"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--provider-catalog", type=Path, required=True)
    args = parser.parse_args()
    application = DesktopApplication(args.root)
    source_catalog = Catalog.open(args.provider_catalog)
    try:
        provider_setting = source_catalog.get_setting(_PROVIDER_SETTING_KEY)
    finally:
        source_catalog.close()
    if provider_setting is not None:
        application.catalog.set_setting(_PROVIDER_SETTING_KEY, provider_setting)
    runtime = CoreRuntime(configure_services=application.configure_services)
    try:
        return runtime.run()
    finally:
        runtime.close()
        application.close()


if __name__ == "__main__":
    raise SystemExit(main())
