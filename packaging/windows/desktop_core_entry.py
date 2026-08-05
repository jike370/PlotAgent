"""Stable PyInstaller entry for the same Core runtime used in development."""

from plotagent.desktop_core.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
