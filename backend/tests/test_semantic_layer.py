"""Issue #16 (TMP-05): load and validate semantic_layer.yaml per dataset (US-12, RC-05, DD-03, H8)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.pipeline import loader
from app.semantic.loader import PATH_ENV, VERSION_PREFIX, SemanticLayerError, load_section
from app.semantic.schema import DatasetSection, SemanticLayerFile
from tests.conftest import FIXTURES, upload

SEMANTIC = FIXTURES / "semantic"
REPO_LAYER = Path(__file__).resolve().parents[2] / "semantic_layer.yaml"

# The sample's schema as the loader profiles it (names and DuckDB types only).
SAMPLE_SCHEMA = {
    "customers": {"customer_id": "BIGINT", "customer_name": "VARCHAR", "city": "VARCHAR",
                  "segment": "VARCHAR", "signup_date": "DATE"},
    "orders": {"order_id": "BIGINT", "customer_id": "BIGINT", "order_date": "DATE",
               "category": "VARCHAR", "status": "VARCHAR", "amount": "DOUBLE"},
}

JOIN = """
    joins:
      - name: orders_to_customers
        description: Each order belongs to the customer with the same customer_id.
        left: orders.customer_id
        right: customers.customer_id
"""


@pytest.fixture
def use_layer(monkeypatch: pytest.MonkeyPatch):
    """Point the app at a semantic-layer file for this test."""

    def _use(path: Path) -> Path:
        monkeypatch.setenv(PATH_ENV, str(path))
        return path

    return _use


def write_layer(tmp_path: Path, sample_section: str) -> Path:
    path = tmp_path / "semantic_layer.yaml"
    path.write_text(f"format_version: 1\ndatasets:\n  sample:\n{sample_section}", encoding="utf-8")
    return path


def rejection(path: Path, schema: dict = SAMPLE_SCHEMA) -> str:
    with pytest.raises(SemanticLayerError) as caught:
        load_section("sample", schema, path)
    return str(caught.value)


# --- AC1: the format, one section per dataset, every definition described -------------

def test_format_has_one_section_per_dataset_with_terms_metrics_and_joins() -> None:
    import yaml

    file = SemanticLayerFile.model_validate(yaml.safe_load((SEMANTIC / "active_customer.yaml").read_text(encoding="utf-8")))
    assert set(file.datasets) == {"sample", "Valid_Sales.CSV"}

    sample = DatasetSection.model_validate(file.datasets["sample"])
    assert [j.name for j in sample.joins] == ["orders_to_customers"]
    assert [t.name for t in sample.terms] == ["active customer"]
    assert [m.name for m in sample.metrics] == ["total order amount"]
    assert all(item.description for item in [*sample.joins, *sample.terms, *sample.metrics])


def test_a_definition_without_a_description_is_rejected(tmp_path: Path) -> None:
    path = write_layer(tmp_path, """
    joins:
      - name: orders_to_customers
        left: orders.customer_id
        right: customers.customer_id
""")
    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': join 'orders_to_customers' is missing 'description'."
    )


def test_a_blank_description_is_rejected(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN.replace("Each order belongs to the customer with the same customer_id.", "' '"))
    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': join 'orders_to_customers': "
        "String should have at least 1 character."
    )


def test_names_must_be_unique_within_a_section(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN + """
      - name: Orders_To_Customers
        description: The same join again.
        left: orders.customer_id
        right: customers.customer_id
""")
    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': the section: the join name 'Orders_To_Customers' is used more than once."
    )


def test_the_file_needs_its_format_version(tmp_path: Path) -> None:
    path = tmp_path / "semantic_layer.yaml"
    path.write_text("datasets: {}\n", encoding="utf-8")
    assert rejection(path) == "semantic_layer.yaml: the file is missing 'format_version'."


def test_a_section_that_is_not_a_mapping_names_its_dataset(tmp_path: Path) -> None:
    path = tmp_path / "semantic_layer.yaml"
    path.write_text("format_version: 1\ndatasets:\n  sample: [a, b]\n  other.csv: [c]\n", encoding="utf-8")

    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': the section must be a mapping with "
        "'joins', 'terms' and 'metrics'."
    )
    # Another dataset's broken section does not block this one.
    assert load_section("valid_sales.csv", {"valid_sales": {"revenue": "DOUBLE"}}, path).section == DatasetSection()


def test_invalid_yaml_names_the_line(use_layer) -> None:
    assert rejection(SEMANTIC / "not_yaml.yaml") == (
        "semantic_layer.yaml is not valid YAML at line 5, column 1. Fix the file and load the dataset again."
    )


# --- AC2: the active dataset's section is validated each time it becomes active --------

def test_loading_the_sample_validates_its_section(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "term_missing_column.yaml")

    response = client.post("/datasets/sample")

    assert response.status_code == 422
    assert response.json()["detail"]["reason"] == "semantic_layer"
    assert client.get("/datasets/active").json()["dataset"] is None


def test_section_is_revalidated_when_the_active_dataset_changes(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "active_customer.yaml")
    assert client.post("/datasets/sample").status_code == 200
    assert upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes()).status_code == 200

    # The steward breaks the sample's section offline; making the sample active again checks it.
    use_layer(SEMANTIC / "join_missing_column.yaml")
    rejected = client.post("/datasets/sample")

    assert rejected.status_code == 422
    assert client.get("/datasets/active").json()["dataset"]["name"] == "valid_sales.csv"
    terms = client.get("/semantic/terms").json()["semantic_layer"]
    assert terms["dataset_key"] == "valid_sales.csv"


def test_active_dataset_is_revalidated_after_an_offline_edit(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "active_customer.yaml")
    assert client.post("/datasets/sample").status_code == 200

    use_layer(SEMANTIC / "term_missing_column.yaml")  # e.g. edited before a restart
    response = client.get("/semantic/terms")

    assert response.status_code == 422
    assert response.json()["detail"] == {
        "reason": "semantic_layer",
        "message": "The term 'active customer' refers to the column 'orders.order_dt', "
                   "which does not exist in the table 'orders'.",
    }


# --- AC3: an upload with no section has no terms and no joins, and is not an error -----

def test_upload_without_a_section_has_no_terms_and_no_joins(client: TestClient, use_layer) -> None:
    use_layer(REPO_LAYER)

    response = upload(client, "other_products.csv", (FIXTURES / "other_products.csv").read_bytes())

    assert response.status_code == 200
    layer = loader.active_semantic_layer()
    assert layer.dataset_key == "other_products.csv"
    assert layer.section == DatasetSection()
    assert client.get("/semantic/terms").json()["semantic_layer"]["terms"] == []


def test_no_file_means_no_sections(tmp_path: Path) -> None:
    layer = load_section("sample", SAMPLE_SCHEMA, tmp_path / "missing.yaml")
    assert layer.section == DatasetSection()


def test_an_upload_section_is_matched_by_file_name_ignoring_case(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "active_customer.yaml")

    assert upload(client, "valid_sales.csv", (FIXTURES / "valid_sales.csv").read_bytes()).status_code == 200

    assert [m.name for m in loader.active_semantic_layer().section.metrics] == ["total revenue"]


# --- AC4: the sample's section holds its terms and its one declared join ---------------

def test_sample_section_holds_its_terms_and_one_join(client: TestClient, use_layer) -> None:
    use_layer(REPO_LAYER)

    assert client.post("/datasets/sample").status_code == 200

    section = loader.active_semantic_layer().section
    assert [(j.name, j.left, j.right) for j in section.joins] == [
        ("orders_to_customers", "orders.customer_id", "customers.customer_id")
    ]
    assert [t.name for t in section.terms] == ["active customer"]
    assert all(t.join == "orders_to_customers" for t in section.terms)


# --- AC5: a definition with a missing column is rejected, naming the term and column ---

def test_term_with_missing_column_is_rejected_naming_term_and_column(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "term_missing_column.yaml")

    # loader.DatasetError, looked up now: test_datasets reloads the loader module.
    with pytest.raises(loader.DatasetError) as caught:
        loader.load_sample()

    assert caught.value.reason == "semantic_layer"
    assert str(caught.value) == (
        "The term 'active customer' refers to the column 'orders.order_dt', "
        "which does not exist in the table 'orders'."
    )


def test_metric_with_missing_column_is_rejected(tmp_path: Path) -> None:
    path = write_layer(tmp_path, """
    metrics:
      - name: total order amount
        description: The sum of the amount of every order.
        aggregation: sum
        column: orders.total
""")
    assert rejection(path) == (
        "The metric 'total order amount' refers to the column 'orders.total', "
        "which does not exist in the table 'orders'."
    )


def test_metric_sum_on_text_is_rejected(tmp_path: Path) -> None:
    path = write_layer(tmp_path, """
    metrics:
      - name: total status
        description: Not a number.
        aggregation: sum
        column: orders.status
""")
    assert rejection(path) == (
        "The metric 'total status' uses 'sum' on the column 'orders.status', which is VARCHAR, not a number."
    )


# --- AC6: a join with a missing table or column is rejected at load time --------------

def test_join_with_missing_table_is_rejected(client: TestClient, use_layer) -> None:
    use_layer(SEMANTIC / "join_missing_table.yaml")

    response = client.post("/datasets/sample")

    assert response.status_code == 422
    assert response.json()["detail"]["message"] == (
        "The join 'orders_to_shops' refers to the table 'shops', which does not exist in this dataset."
    )


def test_join_with_missing_column_is_rejected() -> None:
    assert rejection(SEMANTIC / "join_missing_column.yaml") == (
        "The join 'orders_to_customers' refers to the column 'orders.cust_id', "
        "which does not exist in the table 'orders'."
    )


def test_join_must_connect_two_tables(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN.replace("right: customers.customer_id", "right: orders.order_id"))
    assert rejection(path) == "The join 'orders_to_customers' must connect two different tables."


# --- AC7: the SDD example loads; inexpressible definitions are rejected ---------------

def test_sdd_active_customer_term_loads_from_fixture() -> None:
    layer = load_section("sample", SAMPLE_SCHEMA, SEMANTIC / "active_customer.yaml")

    (term,) = layer.section.terms
    assert term.name == "active customer"
    assert term.description == "A customer with an order in the last 90 days."
    assert term.count_distinct == "customers.customer_id"
    assert term.join == "orders_to_customers"
    assert (term.filter.column, term.filter.op, term.filter.value) == ("orders.order_date", "within_last_days", 90)


def test_term_with_free_sql_is_rejected() -> None:
    assert rejection(SEMANTIC / "term_free_sql.yaml") == (
        "semantic_layer.yaml, dataset 'sample': term 'repeat customer' uses 'sql', which this format "
        "does not support. A term must be a declared join plus one filter with a distinct count "
        "(count_distinct, join, filter)."
    )


def test_term_with_another_aggregation_is_rejected(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN + """
    terms:
      - name: big spender
        description: Total amount over 1000.
        sum: orders.amount
        join: orders_to_customers
        filter: {column: orders.amount, op: ">", value: 1000}
""")
    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': term 'big spender' uses 'sum', which this format "
        "does not support. A term must be a declared join plus one filter with a distinct count "
        "(count_distinct, join, filter)."
    )


def test_term_with_undeclared_join_is_rejected() -> None:
    assert rejection(SEMANTIC / "term_undeclared_join.yaml") == (
        "The term 'active customer' uses the join 'orders_to_customers', which is not declared for "
        "this dataset. Declare it under 'joins' or use a declared join."
    )


def test_term_outside_its_join_tables_is_rejected(tmp_path: Path) -> None:
    schema = {**SAMPLE_SCHEMA, "shops": {"shop_id": "BIGINT", "opened": "DATE"}}
    path = write_layer(tmp_path, JOIN + """
    terms:
      - name: new shop customer
        description: A customer of a shop opened in the last 90 days.
        count_distinct: customers.customer_id
        join: orders_to_customers
        filter: {column: shops.opened, op: within_last_days, value: 90}
""")
    assert rejection(path, schema) == (
        "The term 'new shop customer' cannot be expressed with the join 'orders_to_customers': its "
        "counted column and its filter column must be in the two tables that the join connects."
    )


def test_relative_date_filter_needs_a_date_column(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN + """
    terms:
      - name: recent customer
        description: Wrong column type.
        count_distinct: customers.customer_id
        join: orders_to_customers
        filter: {column: orders.status, op: within_last_days, value: 90}
""")
    assert rejection(path) == (
        "The term 'recent customer' uses 'within_last_days' on the column 'orders.status', "
        "which is VARCHAR, not a date."
    )


def test_relative_date_filter_needs_whole_days(tmp_path: Path) -> None:
    path = write_layer(tmp_path, JOIN + """
    terms:
      - name: recent customer
        description: Days must be a whole number.
        count_distinct: customers.customer_id
        join: orders_to_customers
        filter: {column: orders.order_date, op: within_last_days, value: "ninety"}
""")
    assert rejection(path) == (
        "semantic_layer.yaml, dataset 'sample': term 'recent customer': "
        "the 'within_last_days' filter needs a whole number of days, 1 or more."
    )


# --- AC8: a read-only API returns every term with its description ---------------------

def test_terms_api_returns_every_term_with_its_description(client: TestClient, use_layer) -> None:
    use_layer(REPO_LAYER)
    client.post("/datasets/sample")

    body = client.get("/semantic/terms").json()["semantic_layer"]

    assert body["dataset_key"] == "sample"
    assert body["terms"] == [
        {"name": "active customer", "description": "A customer with an order in the last 90 days."}
    ]


def test_terms_api_without_an_active_dataset(client: TestClient) -> None:
    assert client.get("/semantic/terms").json() == {"semantic_layer": None}


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_terms_cannot_be_edited_through_the_api(client: TestClient, method: str) -> None:
    assert getattr(client, method)("/semantic/terms").status_code == 405


def test_no_endpoint_can_edit_terms() -> None:
    from app.main import app

    # Every route the app serves, from its OpenAPI description.
    paths = app.openapi()["paths"]
    term_paths = {path: set(ops) for path, ops in paths.items() if "semantic" in path or "term" in path}
    assert term_paths == {"/semantic/terms": {"get"}}


# --- AC9: a semantic-layer version value for the audit record -------------------------

def test_version_is_stable_and_changes_with_the_section(tmp_path: Path) -> None:
    first = load_section("sample", SAMPLE_SCHEMA, REPO_LAYER).version
    again = load_section("sample", SAMPLE_SCHEMA, REPO_LAYER).version
    edited = tmp_path / "semantic_layer.yaml"
    edited.write_text(REPO_LAYER.read_text(encoding="utf-8").replace("last 90 days.", "last 90 days!"), encoding="utf-8")

    assert first.startswith(VERSION_PREFIX)
    assert first == again
    assert load_section("sample", SAMPLE_SCHEMA, edited).version != first


def test_version_ignores_comments_and_layout(tmp_path: Path) -> None:
    reformatted = tmp_path / "semantic_layer.yaml"
    reformatted.write_text("# a comment\n" + REPO_LAYER.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    assert (load_section("sample", SAMPLE_SCHEMA, reformatted).version
            == load_section("sample", SAMPLE_SCHEMA, REPO_LAYER).version)


def test_version_differs_for_no_section_and_an_empty_section(tmp_path: Path) -> None:
    empty = tmp_path / "semantic_layer.yaml"
    empty.write_text("format_version: 1\ndatasets:\n  sample: {}\n", encoding="utf-8")

    assert (load_section("sample", SAMPLE_SCHEMA, empty).version
            != load_section("sample", SAMPLE_SCHEMA, tmp_path / "missing.yaml").version)


def test_active_version_is_available_for_the_audit_record(client: TestClient, use_layer) -> None:
    use_layer(REPO_LAYER)
    client.post("/datasets/sample")

    version = loader.active_semantic_layer().version

    assert client.get("/semantic/terms").json()["semantic_layer"]["version"] == version
    assert version == load_section("sample", SAMPLE_SCHEMA, REPO_LAYER).version
