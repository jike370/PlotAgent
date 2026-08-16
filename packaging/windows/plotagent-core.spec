import os
from pathlib import Path


project_root = Path(SPECPATH).resolve().parents[1]
wheel_site_packages = os.environ.get("PLOTAGENT_WHEEL_SITE_PACKAGES")
if not wheel_site_packages:
    raise RuntimeError("PLOTAGENT_WHEEL_SITE_PACKAGES must point to the staged wheel install")
native_distribution_source = (
    Path(wheel_site_packages)
    / "plotagent"
    / "engine"
    / "backends"
    / "origin"
    / "native_distribution.c"
)
native_visual_source = native_distribution_source.with_name("native_visual_t1.c")
if not native_distribution_source.is_file():
    raise RuntimeError(
        f"staged wheel is missing the Origin distribution bridge: {native_distribution_source}"
    )
if not native_visual_source.is_file():
    raise RuntimeError(f"staged wheel is missing the Origin visual bridge: {native_visual_source}")

analysis = Analysis(
    [str(project_root / "packaging" / "windows" / "desktop_core_entry.py")],
    pathex=[wheel_site_packages],
    binaries=[],
    datas=[
        (
            str(native_distribution_source),
            "plotagent/engine/backends/origin",
        ),
        (
            str(native_visual_source),
            "plotagent/engine/backends/origin",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="plotagent-core",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="plotagent-core",
)
