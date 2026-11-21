"""Safe executor: the only code that opens the active dataset after it is loaded (RC-01, H3).

This Issue (#4, TMP-03) starts the module with the read-only connection only. The 15 s
timeout, the 5,000-row limit and the single-``SELECT`` gate are added by TMP-12.

What the connection guarantees:

- the DuckDB file is opened with ``read_only=True``: any statement that would change the
  dataset (``INSERT``, ``UPDATE``, ``DELETE``, ``CREATE``, ``DROP``, ``ALTER`` ...) fails;
- external access is off: no ``COPY ... TO``, ``ATTACH``, ``read_csv`` of other files and no
  extension install, so nothing can be written elsewhere or fetched over the network;
- the configuration is locked, so a query cannot switch these settings back on.

DuckDB still lets a connection create ``TEMP`` objects. They live only in that
connection's memory, are discarded when it closes and never touch the dataset file.

Note: in DuckDB 2.x an error is raised when the result is fetched, not when
``execute()`` returns, so callers must fetch (or close) to see the failure.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from app.pipeline.storage import active_db_path

READ_ONLY_CONFIG: dict[str, object] = {
    "enable_external_access": False,
    "autoinstall_known_extensions": False,
    "autoload_known_extensions": False,
    "lock_configuration": True,
}


class NoActiveDatasetError(LookupError):
    """There is no loaded dataset to open."""


def connect_read_only(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the active dataset (or ``path``) read-only. The caller must close it."""
    target = path if path is not None else active_db_path()
    if not target.is_file():
        raise NoActiveDatasetError("No dataset is loaded. Upload a CSV or load the sample dataset.")
    return duckdb.connect(str(target), read_only=True, config=dict(READ_ONLY_CONFIG))
