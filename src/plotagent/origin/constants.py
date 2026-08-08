"""Build-pinned Origin qualification declaration for the M0 K01 spike."""

from pathlib import Path

DECLARED_ORIGIN_DISPLAY_NAME = "Origin2024 SR1"
DECLARED_ORIGIN_DISPLAY_VERSION = "10.10.178"
DECLARED_ORIGIN_RUNTIME_VERSION = 10.100178
DECLARED_ORIGIN_BITNESS = 64
DECLARED_ORIGINPRO_VERSION = "1.1.15"

ORIGIN_EXECUTABLE = "Origin64.exe"
ORIGIN_TEMPLATE_FILENAME = "PlotAgent89x60.otpu"
ORIGIN_TEMPLATE_ID = "plotagent-10.10.178-89x60"
ORIGIN_TEMPLATE_SHA256 = "08a2f8f8f18d0d689e40d2c520d0416d7ee97b1945f613168f52337626feaedf"


def qualified_template_path() -> Path:
    """Return the build-owned template path; callers cannot supply another path."""

    return Path(__file__).resolve().parent / "assets" / ORIGIN_TEMPLATE_FILENAME


K01_ADAPTER_ID = "plotagent.origin.k01.line"
K01_ADAPTER_VERSION = "0.1.0-m0"
K01_CAPABILITY = "O1"
K01_CHART_TYPE_ID = "K01"
ORIGIN_EXPORT_SCHEMA_VERSION = "1.0"
# Origin interprets numeric symbol-size modifier columns in points. Keep the
# qualified scale in one shared constant so the plot and its size key cannot drift.
ORIGIN_VARIABLE_SIZE_FACTOR = 0.25

# Build-owned Origin 2024 SR1 template physical page size.
K01_PAGE_WIDTH_MM = 89.0
K01_PAGE_HEIGHT_MM = 60.0

PROJECT_FOLDERS = ("Data", "Analysis", "Graphs", "Metadata")
RAW_BOOK_NAME = "PARAWK01"
RAW_BOOK_LONG_NAME = "K01 Raw Data"
RAW_SHEET_NAME = "RawData"
RAW_SHEET_LONG_NAME = "Raw Data"
GRAPH_PAGE_NAME = "PAGRK01"
GRAPH_PAGE_LONG_NAME = "K01 Line Plot"
GRAPH_LAYER_NAME = "Layer1"
GRAPH_LAYER_LONG_NAME = "K01 Line Layer"
METADATA_BOOK_NAME = "PAMETAK01"
METADATA_BOOK_LONG_NAME = "PlotAgent Metadata"
MANIFEST_SHEET_NAME = "Manifest"
MANIFEST_SHEET_LONG_NAME = "Origin Export Manifest"

# This is the complete numeric property allowlist for the K01 spike. Values never come
# from a model, data cell, adapter config file, or caller-supplied property path.
K01_FIXED_NUMERIC_PROPERTIES = (("plot1.line.width", 1.0),)

WORKER_DEFAULT_TIMEOUT_SECONDS = 30.0
MIN_FREE_TARGET_BYTES = 10 * 1024 * 1024
