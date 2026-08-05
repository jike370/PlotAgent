"""Build-pinned Origin qualification declaration for the M0 K01 spike."""

DECLARED_ORIGIN_DISPLAY_NAME = "Origin2024 SR1"
DECLARED_ORIGIN_DISPLAY_VERSION = "10.10.178"
DECLARED_ORIGIN_RUNTIME_VERSION = 10.100178
DECLARED_ORIGIN_BITNESS = 64
DECLARED_ORIGINPRO_VERSION = "1.1.15"

ORIGIN_EXECUTABLE = "Origin64.exe"
ORIGIN_TEMPLATE_FILENAME = "origin.otp"
ORIGIN_TEMPLATE_ID = "origin-10.10.178-default-line"
ORIGIN_TEMPLATE_SHA256 = "588d94a13eee1140e55ff3edf04bc84e955b9c2c1dc3a40fc7b4a3932572d254"

K01_ADAPTER_ID = "plotagent.origin.k01.line"
K01_ADAPTER_VERSION = "0.1.0-m0"
K01_CAPABILITY = "O1"
K01_CHART_TYPE_ID = "K01"
ORIGIN_EXPORT_SCHEMA_VERSION = "1.0"

# Origin 2024 SR1's qualified origin.otp page size. M0 binds this native template
# size; arbitrary publication-layout resolution remains a later W4/W6 task.
K01_PAGE_WIDTH_MM = 272.288
K01_PAGE_HEIGHT_MM = 208.407

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
