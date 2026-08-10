"""Build-pinned declarations for the production Origin adapter."""

DECLARED_ORIGIN_DISPLAY_NAME = "Origin2024 SR1"
DECLARED_ORIGIN_DISPLAY_VERSION = "10.10.178"
DECLARED_ORIGIN_RUNTIME_VERSION = 10.100178
DECLARED_ORIGIN_BITNESS = 64
DECLARED_ORIGINPRO_VERSION = "1.1.15"

ORIGIN_EXECUTABLE = "Origin64.exe"
# Origin interprets numeric symbol-size modifier columns in points. Keep the
# qualified scale in one shared constant so the plot and its size key cannot drift.
ORIGIN_VARIABLE_SIZE_FACTOR = 0.25

WORKER_DEFAULT_TIMEOUT_SECONDS = 30.0
MIN_FREE_TARGET_BYTES = 10 * 1024 * 1024
