from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from snowflake_connection import connect


DATABASE = "STUDENT_SALES_DW"
EXPECTED_DIMENSIONS = {
    "DIM_DATE", "DIM_GEOGRAPHY", "DIM_CUSTOMER", "DIM_PRODUCT",
    "DIM_PROMOTION", "DIM_SALES_EMPLOYEE", "DIM_SHIPPER",
}
EXPECTED_FACTS = {
    "FACT_SALES", "FACT_ORDERS", "FACT_PAYMENTS", "FACT_RETURNS",
    "FACT_REVIEWS", "FACT_SHIPMENTS", "FACT_INVENTORY_SNAPSHOT", "FACT_WEB_TRAFFIC",
}
EXPECTED_BRIDGES = {"BRIDGE_SALES_PROMOTION"}
EXPECTED_VIEWS = {
    "VW_SALES_DAILY", "VW_PRODUCT_PERFORMANCE", "VW_CUSTOMER_360",
    "VW_INVENTORY_LATEST", "VW_MARKETING_DAILY", "VW_DELIVERY_PERFORMANCE",
    "VW_PROMOTION_PERFORMANCE",
}


@dataclass
class Check:
    name: str
    category: str
    status: str
    details: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scalar(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchone()[0]


def close_enough(left, right, tolerance: float = 0.01) -> bool:
    return left is not None and right is not None and abs(float(left) - float(right)) <= tolerance


def validate(cursor, expected: dict) -> tuple[list[Check], list[tuple]]:
    checks: list[Check] = []
    cursor.execute(f"USE WAREHOUSE STUDENT_SALES_ETL_WH")
    cursor.execute(f"USE DATABASE {DATABASE}")

    cursor.execute(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='CORE' AND TABLE_TYPE='BASE TABLE'"
    )
    core_tables = {row[0] for row in cursor.fetchall()}
    missing_tables = sorted((EXPECTED_DIMENSIONS | EXPECTED_FACTS | EXPECTED_BRIDGES) - core_tables)
    checks.append(Check("Core Star Schema tables", "model", "PASS" if not missing_tables else "FAIL",
                        "7 dimensions, 8 facts and 1 bridge exist" if not missing_tables else f"Missing: {missing_tables}"))

    cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS WHERE TABLE_SCHEMA='ANALYTICS'")
    views = {row[0] for row in cursor.fetchall()}
    missing_views = sorted(EXPECTED_VIEWS - views)
    checks.append(Check("Analytical views", "model", "PASS" if not missing_views else "FAIL",
                        "All 7 analytical views exist" if not missing_views else f"Missing: {missing_views}"))

    broken_views = []
    for view in sorted(EXPECTED_VIEWS & views):
        try:
            cursor.execute(f"SELECT * FROM ANALYTICS.{view} LIMIT 1").fetchone()
        except Exception as exc:
            broken_views.append(f"{view}: {exc}")
    checks.append(Check("Analytical views executable", "model", "PASS" if not broken_views else "FAIL",
                        "All views execute" if not broken_views else "; ".join(broken_views)))

    cursor.execute(
        "SELECT BATCH_RUN_ID, SOURCE_BATCH_ID, STATUS, SOURCE_MODE FROM CONTROL.ETL_BATCH_LOG ORDER BY BATCH_RUN_ID DESC LIMIT 1"
    )
    batch = cursor.fetchone()
    batch_run_id = -1 if batch is None else int(batch[0])
    batch_ok = batch is not None and batch[2] == "SUCCESS" and batch[1] == expected["source_batch_id"]
    checks.append(Check("Latest ETL batch", "pipeline", "PASS" if batch_ok else "FAIL",
                        "No batch" if batch is None else f"run={batch[0]}, source_batch={batch[1]}, status={batch[2]}, mode={batch[3]}"))

    cursor.execute(
        """
        SELECT DATASET_NAME, SOURCE_ROW_COUNT, TARGET_TABLE, TARGET_ROW_COUNT, STATUS
        FROM CONTROL.ETL_DATASET_LOG
        WHERE BATCH_RUN_ID = %s
        ORDER BY DATASET_NAME
        """
        , (batch_run_id,)
    )
    synchronization = cursor.fetchall()
    logged = {row[0]: row for row in synchronization}
    bad_sync = []
    for dataset, expected_count in expected["row_counts"].items():
        row = logged.get(dataset)
        if row is None or int(row[1]) != expected_count or int(row[3]) != expected_count or row[4] != "PASS":
            bad_sync.append((dataset, row, expected_count))
    checks.append(Check("Silver-to-Gold row synchronization", "completeness",
                        "PASS" if not bad_sync else "FAIL",
                        "12/12 canonical datasets match" if not bad_sync else f"Mismatches: {bad_sync}"))

    dq_total = int(scalar(cursor, f"SELECT COUNT(*) FROM CONTROL.DQ_RESULTS WHERE BATCH_RUN_ID={batch_run_id}"))
    dq_failed = int(scalar(cursor, f"SELECT COUNT(*) FROM CONTROL.DQ_RESULTS WHERE BATCH_RUN_ID={batch_run_id} AND STATUS='FAIL'"))
    dq_ok = dq_total == 35 and dq_failed == 0
    checks.append(Check("Snowflake data-quality gate", "quality", "PASS" if dq_ok else "FAIL",
                        f"checks={dq_total}/35; failed={dq_failed}"))

    expected_measures = expected["measures"]
    measure_queries = {
        "net_sales": "SELECT ROUND(SUM(NET_SALES_AMOUNT),2) FROM CORE.FACT_SALES",
        "payment_value": "SELECT ROUND(SUM(PAYMENT_VALUE),2) FROM CORE.FACT_PAYMENTS",
        "refund_amount": "SELECT ROUND(SUM(REFUND_AMOUNT),2) FROM CORE.FACT_RETURNS",
        "shipping_fee": "SELECT ROUND(SUM(SHIPPING_FEE),2) FROM CORE.FACT_SHIPMENTS",
    }
    for name, query in measure_queries.items():
        actual = scalar(cursor, query)
        expected_value = expected_measures[name]
        checks.append(Check(f"{name} reconciliation", "financial",
                            "PASS" if close_enough(actual, expected_value) else "FAIL",
                            f"expected={expected_value:,.2f}; Snowflake={float(actual):,.2f}"))

    sales = scalar(cursor, "SELECT ROUND(SUM(NET_SALES_AMOUNT),2) FROM CORE.FACT_SALES")
    orders = scalar(cursor, "SELECT ROUND(SUM(NET_SALES_AMOUNT),2) FROM CORE.FACT_ORDERS")
    product_view = scalar(cursor, "SELECT ROUND(SUM(NET_SALES),2) FROM ANALYTICS.VW_PRODUCT_PERFORMANCE")
    promotion_view = scalar(cursor, "SELECT ROUND(SUM(ATTRIBUTED_NET_SALES),2) FROM ANALYTICS.VW_PROMOTION_PERFORMANCE")
    checks.append(Check("Net sales across Snowflake layers", "cross_layer_consistency",
                        "PASS" if close_enough(sales, orders) and close_enough(sales, product_view)
                        and close_enough(sales, promotion_view) else "FAIL",
                        f"sales={float(sales):,.2f}; orders={float(orders):,.2f}; "
                        f"product_view={float(product_view):,.2f}; promotion_view={float(promotion_view):,.2f}"))

    grain_queries = {
        "FACT_SALES": "SELECT COUNT(*) FROM (SELECT ORDER_ID,SOURCE_ROW_NUMBER FROM CORE.FACT_SALES GROUP BY 1,2 HAVING COUNT(*)>1)",
        "FACT_ORDERS": "SELECT COUNT(*) FROM (SELECT ORDER_ID FROM CORE.FACT_ORDERS GROUP BY 1 HAVING COUNT(*)>1)",
        "FACT_PAYMENTS": "SELECT COUNT(*) FROM (SELECT ORDER_ID FROM CORE.FACT_PAYMENTS GROUP BY 1 HAVING COUNT(*)>1)",
        "FACT_RETURNS": "SELECT COUNT(*) FROM (SELECT RETURN_ID FROM CORE.FACT_RETURNS GROUP BY 1 HAVING COUNT(*)>1)",
        "FACT_REVIEWS": "SELECT COUNT(*) FROM (SELECT REVIEW_ID FROM CORE.FACT_REVIEWS GROUP BY 1 HAVING COUNT(*)>1)",
        "FACT_SHIPMENTS": "SELECT COUNT(*) FROM (SELECT ORDER_ID FROM CORE.FACT_SHIPMENTS GROUP BY 1 HAVING COUNT(*)>1)",
        "FACT_INVENTORY_SNAPSHOT": "SELECT COUNT(*) FROM (SELECT SNAPSHOT_DATE_KEY,PRODUCT_KEY FROM CORE.FACT_INVENTORY_SNAPSHOT GROUP BY 1,2 HAVING COUNT(*)>1)",
        "FACT_WEB_TRAFFIC": "SELECT COUNT(*) FROM (SELECT TRAFFIC_DATE_KEY,TRAFFIC_SOURCE FROM CORE.FACT_WEB_TRAFFIC GROUP BY 1,2 HAVING COUNT(*)>1)",
    }
    duplicate_grains = {table: int(scalar(cursor, query)) for table, query in grain_queries.items()}
    failed_grains = {table: count for table, count in duplicate_grains.items() if count}
    checks.append(Check("Fact grain uniqueness", "model", "PASS" if not failed_grains else "FAIL",
                        "All 8 fact grains are unique" if not failed_grains else str(failed_grains)))

    bridge_duplicates = int(scalar(
        cursor,
        "SELECT COUNT(*) FROM (SELECT SALES_KEY,PROMOTION_SEQUENCE FROM CORE.BRIDGE_SALES_PROMOTION "
        "GROUP BY 1,2 HAVING COUNT(*)>1)",
    ))
    bridge_bad_weights = int(scalar(
        cursor,
        "SELECT COUNT(*) FROM (SELECT SALES_KEY FROM CORE.BRIDGE_SALES_PROMOTION "
        "GROUP BY 1 HAVING ABS(SUM(ALLOCATION_WEIGHT)-1)>0.000001)",
    ))
    checks.append(Check(
        "Promotion bridge integrity", "model",
        "PASS" if bridge_duplicates == 0 and bridge_bad_weights == 0 else "FAIL",
        f"duplicate_sequences={bridge_duplicates}; invalid_weight_sums={bridge_bad_weights}",
    ))
    bridge_rows = int(scalar(cursor, "SELECT COUNT(*) FROM CORE.BRIDGE_SALES_PROMOTION"))
    expected_bridge_rows = int(expected["promotion_bridge"]["expected_bridge_rows"])
    checks.append(Check(
        "Promotion bridge completeness", "completeness",
        "PASS" if bridge_rows == expected_bridge_rows else "FAIL",
        f"expected={expected_bridge_rows:,}; Snowflake={bridge_rows:,}",
    ))
    return checks, synchronization


def write_report(path: Path, checks: list[Check], synchronization: list[tuple]) -> None:
    failed = sum(check.status == "FAIL" for check in checks)
    lines = [
        "# Báo cáo kiểm thử Data Warehouse trên Snowflake", "",
        f"- Database: `{DATABASE}`",
        f"- Thời điểm UTC: `{utc_now()}`",
        f"- Kết luận: `{'PASS' if failed == 0 else 'FAIL'}`",
        f"- Số kiểm tra thất bại: `{failed}`", "",
        "| Kiểm tra | Nhóm | Trạng thái | Chi tiết |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(f"| {c.name} | {c.category} | {c.status} | {c.details} |" for c in checks)
    lines.extend(["", "## Đồng bộ Silver → Snowflake Gold", "",
                  "| Dataset | Source rows | Target table | Target rows | Status |",
                  "| --- | ---: | --- | ---: | --- |"])
    lines.extend(f"| `{r[0]}` | {int(r[1]):,} | `{r[2]}` | {int(r[3]):,} | {r[4]} |" for r in synchronization)
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Validate the deployed Snowflake Data Warehouse.")
    parser.add_argument("--connection-name", default=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "default"))
    parser.add_argument("--expected-metrics", type=Path, default=root / "output" / "expected_metrics.json")
    parser.add_argument("--report", type=Path, default=root / "output" / "snowflake_validation_report.md")
    args = parser.parse_args()

    expected = json.loads(args.expected_metrics.read_text(encoding="utf-8"))
    connection = connect(args.connection_name)
    cursor = connection.cursor()
    try:
        checks, synchronization = validate(cursor, expected)
    finally:
        cursor.close()
        connection.close()
    write_report(args.report, checks, synchronization)
    failed = [check for check in checks if check.status == "FAIL"]
    print(f"snowflake_checks={len(checks)}")
    print(f"failed_snowflake_checks={len(failed)}")
    print(f"report={args.report.resolve()}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
