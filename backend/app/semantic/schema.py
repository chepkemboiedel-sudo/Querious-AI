"""The ``semantic_layer.yaml`` format 🔒 (ARCHITECTURE.md Section 5; US-12, RC-05, DD-03, H8).

A data steward edits the file offline (POLICY Section 1). It holds **one section per
dataset**. Each section declares the dataset's business terms, metrics and allowed joins,
each with a plain-English description. A dataset with no section has no terms, no metrics
and no joins, and that is not an error.

```yaml
format_version: 1
datasets:
  sample:                      # the built-in sample dataset
    joins:
      - name: orders_to_customers
        description: Each order belongs to the customer with the same customer_id.
        left: orders.customer_id
        right: customers.customer_id
    terms:
      - name: active customer
        description: A customer with an order in the last 90 days.
        count_distinct: customers.customer_id
        join: orders_to_customers
        filter: {column: orders.order_date, op: within_last_days, value: 90}
    metrics:
      - name: total order amount
        description: The sum of the amount of every order.
        aggregation: sum
        column: orders.amount
  sales_2025.csv:              # an upload, keyed by its file name (case is ignored)
    metrics: [...]
```

Section keys: ``sample`` is the built-in sample dataset; any other key is the file name of
an upload, compared without regard to case (``dataset_key`` in ``app.pipeline.semantic_context``).

Columns are written ``table.column``. Table names never contain a dot (the loader makes
them safe), so everything after the first dot is the column name.

A **term** is always a declared join plus one filter, counted with a distinct count, as in
the SDD example (*active customer* = a customer with an order in the last 90 days). A term
that needs anything else (free-form SQL, several joins, another aggregation) cannot be
written in this format and is rejected when the file is loaded. A **metric** is one
aggregation over one column. Relative dates (``within_last_days``) stay relative here; they
are resolved to absolute dates before compiling (ARCHITECTURE.md Section 8, "Dates").

This module checks only the shape. Checking the names against the dataset's schema is
``app.semantic.loader``'s job, because the schema is known only when a dataset is active.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

FORMAT_VERSION = 1
SAMPLE_KEY = "sample"

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
# ``table.column``: a table name, a dot, then a non-empty column name.
ColumnRef = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[^.\s]+\.\S.*$")]
Scalar = Union[bool, int, float, str]

FilterOp = Literal["=", "!=", "<", "<=", ">", ">=", "in", "within_last_days"]
Aggregation = Literal["sum", "avg", "min", "max", "count", "count_distinct"]


def split_ref(ref: str) -> tuple[str, str]:
    """``"orders.order_date"`` -> ``("orders", "order_date")``."""
    table, column = ref.split(".", 1)
    return table, column


class _Strict(BaseModel):
    # Unknown keys are refused, so a definition the format cannot express (for example
    # a ``sql:`` key) is rejected instead of silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Join(_Strict):
    """An allowed join: ``left`` equals ``right``. Only declared joins may be used (H8, AR-6)."""

    name: Name
    description: Description
    left: ColumnRef
    right: ColumnRef


class Filter(_Strict):
    column: ColumnRef
    op: FilterOp
    value: Union[Scalar, list[Scalar]]

    @model_validator(mode="after")
    def _value_fits_op(self) -> "Filter":
        if self.op == "in":
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("the 'in' filter needs a non-empty list of values")
        elif isinstance(self.value, list):
            raise ValueError(f"the '{self.op}' filter needs one value, not a list")
        if self.op == "within_last_days" and (
            isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 1
        ):
            raise ValueError("the 'within_last_days' filter needs a whole number of days, 1 or more")
        return self


class Term(_Strict):
    """A business term: a declared join plus one filter, with a distinct count."""

    name: Name
    description: Description
    count_distinct: ColumnRef
    join: Name
    filter: Filter


class Metric(_Strict):
    name: Name
    description: Description
    aggregation: Aggregation
    column: ColumnRef


class DatasetSection(_Strict):
    """Everything declared for one dataset. All three lists may be empty."""

    joins: list[Join] = Field(default_factory=list)
    terms: list[Term] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_are_unique(self) -> "DatasetSection":
        for kind, items in (("join", self.joins), ("term", self.terms), ("metric", self.metrics)):
            seen: set[str] = set()
            for item in items:
                key = item.name.casefold()
                if key in seen:
                    raise ValueError(f"the {kind} name '{item.name}' is used more than once")
                seen.add(key)
        return self


class SemanticLayerFile(_Strict):
    """The whole file. Sections stay raw here: only the active dataset's section is parsed."""

    format_version: Literal[1]
    datasets: dict[str, Union[dict, None]] = Field(default_factory=dict)
