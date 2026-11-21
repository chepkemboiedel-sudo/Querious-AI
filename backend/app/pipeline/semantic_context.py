"""Connects a dataset to its section of ``semantic_layer.yaml`` (TMP-05; US-12, RC-05, H8).

The dataset loader calls ``semantic_layer_for`` before it makes a new dataset active, so a
dataset never becomes active with a section that does not match its schema. Reading the
active dataset (for example after a restart) validates the section again, because the
steward may have edited the file offline in the meantime (``loader.active_semantic_layer``).

The check uses only the stored schema profile (names and types). It never opens the dataset.
"""

from __future__ import annotations

from app.pipeline.schema_profile import TableProfile
from app.semantic.loader import ActiveSemanticLayer, load_section
from app.semantic.schema import SAMPLE_KEY


def dataset_key(kind: str, name: str) -> str:
    """The section key: ``sample`` for the built-in sample, otherwise the upload's file name."""
    return SAMPLE_KEY if kind == "sample" else name


def semantic_layer_for(kind: str, name: str, tables: list[TableProfile]) -> ActiveSemanticLayer:
    """Validate the dataset's section against its schema profile. Raises ``SemanticLayerError``."""
    schema = {table.name: {c.name: c.type for c in table.columns} for table in tables}
    return load_section(dataset_key(kind, name), schema)
