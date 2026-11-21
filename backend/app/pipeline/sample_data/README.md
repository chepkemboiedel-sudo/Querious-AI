# Built-in sample dataset

Fictional, synthetic retail data (POLICY D-3): no real people or companies. It is the only
multi-table dataset (POLICY D-6) and is loaded by `POST /datasets/sample`.

| Table | Rows | Columns |
| --- | --- | --- |
| `customers` | 20 | `customer_id`, `customer_name`, `city`, `segment`, `signup_date` |
| `orders` | 80 | `order_id`, `customer_id`, `order_date` (2025–2026), `category`, `status`, `amount` |

**The one join:** `orders.customer_id` → `customers.customer_id`. Every order's
`customer_id` exists in `customers` (tested in `backend/tests/test_datasets.py`).
The join is *declared* for the planner and validator only in `semantic_layer.yaml`
(H8, TMP-05); nothing in the loader declares or allows joins.

This draft is not frozen. TMP-33 freezes the sample dataset with the gold set (OD-3).
