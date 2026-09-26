from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlparse


EXPECTED_STAGE_TABLES = 12
EXPECTED_CORE_TARGETS = {
    "DIM_DATE", "DIM_GEOGRAPHY", "DIM_CUSTOMER", "DIM_PRODUCT",
    "DIM_PROMOTION", "DIM_SALES_EMPLOYEE", "DIM_SHIPPER", "FACT_SALES",
    "BRIDGE_SALES_PROMOTION", "FACT_PAYMENTS", "FACT_RETURNS", "FACT_REVIEWS",
    "FACT_SHIPMENTS", "FACT_INVENTORY_SNAPSHOT", "FACT_WEB_TRAFFIC", "FACT_ORDERS",
}
EXPECTED_VIEWS = {
    "VW_SALES_DAILY", "VW_PRODUCT_PERFORMANCE", "VW_CUSTOMER_360",
    "VW_INVENTORY_LATEST", "VW_MARKETING_DAILY", "VW_DELIVERY_PERFORMANCE",
    "VW_PROMOTION_PERFORMANCE",
}


@dataclass
class Check:
    name: str
    status: str
    details: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    root = Path(__file__).resolve().parent
    project_root = root.parent
    sql_root = root / "sql"
    checks: list[Check] = []

    sql_files = sorted(sql_root.glob("*.sql")) + [project_root / "star_schema" / "sql" / "star_schema.sql"]
    bad_parse = []
    statement_counts = {}
    for path in sql_files:
        statements = [statement for statement in sqlparse.split(path.read_text(encoding="utf-8")) if statement.strip()]
        statement_counts[path.name] = len(statements)
        if not statements or any(statement.count("(") != statement.count(")") for statement in statements):
            bad_parse.append(path.name)
    checks.append(Check(
        "SQL bundle structure", "PASS" if not bad_parse else "FAIL",
        f"Parsed statement counts: {statement_counts}" if not bad_parse else f"Invalid: {bad_parse}",
    ))

    stage_sql = (sql_root / "02_stage_schema.sql").read_text(encoding="utf-8")
    stage_tables = set(re.findall(r"CREATE\s+OR\s+REPLACE\s+TRANSIENT\s+TABLE\s+(STG_\w+)", stage_sql, re.I))
    checks.append(Check(
        "Staging table coverage", "PASS" if len(stage_tables) == EXPECTED_STAGE_TABLES else "FAIL",
        f"Stage tables: {len(stage_tables)}/{EXPECTED_STAGE_TABLES}",
    ))

    transform_sql = (sql_root / "03_transform.sql").read_text(encoding="utf-8")
    transform_targets = {name.upper() for name in re.findall(r"INSERT\s+INTO\s+(\w+)", transform_sql, re.I)}
    missing_targets = sorted(EXPECTED_CORE_TARGETS - transform_targets)
    unexpected_targets = sorted(transform_targets - EXPECTED_CORE_TARGETS)
    checks.append(Check(
        "Transform target coverage", "PASS" if not missing_targets and not unexpected_targets else "FAIL",
        "All 16 CORE targets are populated" if not missing_targets and not unexpected_targets
        else f"Missing={missing_targets}; unexpected={unexpected_targets}",
    ))

    obsolete_tokens = [
        token for token in ("PRIMARY_PROMOTION_KEY", "SECONDARY_PROMOTION_KEY", "VALID_FROM", "VALID_TO", "IS_CURRENT")
        if token in transform_sql.upper()
    ]
    checks.append(Check(
        "Transform-model consistency", "PASS" if not obsolete_tokens else "FAIL",
        "No obsolete SCD2 or dual-promotion columns" if not obsolete_tokens else f"Obsolete: {obsolete_tokens}",
    ))

    views_sql = (sql_root / "04_analytics_views.sql").read_text(encoding="utf-8")
    actual_views = {name.upper() for name in re.findall(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+(\w+)", views_sql, re.I)}
    checks.append(Check(
        "Analytical view coverage", "PASS" if actual_views == EXPECTED_VIEWS else "FAIL",
        "All 7 analytical views are defined" if actual_views == EXPECTED_VIEWS
        else f"Missing={sorted(EXPECTED_VIEWS - actual_views)}; extra={sorted(actual_views - EXPECTED_VIEWS)}",
    ))

    quality_sql = (sql_root / "05_quality_checks.sql").read_text(encoding="utf-8")
    first_id = re.search(r"WITH\s+RAW_CHECKS\s+AS\s*\(\s*SELECT\s+(\d+)\s+AS\s+CHECK_ID", quality_sql, re.I)
    check_ids = ([int(first_id.group(1))] if first_id else []) + [
        int(value) for value in re.findall(r"UNION\s+ALL\s+SELECT\s+(\d+)\s*,\s*'", quality_sql, re.I)
    ]
    expected_ids = list(range(1, 36))
    checks.append(Check(
        "Quality-gate coverage", "PASS" if sorted(check_ids) == expected_ids else "FAIL",
        "35 unique checks are defined" if sorted(check_ids) == expected_ids else f"IDs={check_ids}",
    ))

    control_sql = (sql_root / "01_control_schema.sql").read_text(encoding="utf-8").upper()
    control_ok = (
        control_sql.count("CREATE TABLE IF NOT EXISTS") == 3
        and "PRIMARY KEY (BATCH_RUN_ID, CHECK_ID)" in control_sql
        and "FOREIGN KEY (BATCH_RUN_ID) REFERENCES ETL_BATCH_LOG" in control_sql
    )
    checks.append(Check(
        "Batch audit persistence", "PASS" if control_ok else "FAIL",
        "Batch, dataset and DQ history are preserved by BATCH_RUN_ID" if control_ok else "Control schema is not batch-safe",
    ))

    build_source = (root / "build_warehouse.py").read_text(encoding="utf-8")
    ordered_tokens = [
        'execute_sql_file(cursor, sql_root / "01_control_schema.sql")',
        'execute_sql_file(cursor, star_schema_sql)',
        'execute_sql_file(cursor, sql_root / "02_stage_schema.sql")',
        'execute_sql_file(cursor, sql_root / "03_transform.sql")',
        'execute_sql_file(cursor, sql_root / "04_analytics_views.sql")',
        'execute_sql_file(cursor, sql_root / "05_quality_checks.sql")',
    ]
    positions = [build_source.find(token) for token in ordered_tokens]
    order_ok = all(position >= 0 for position in positions) and positions == sorted(positions)
    checks.append(Check(
        "Deployment order", "PASS" if order_ok else "FAIL",
        "Control → Star Schema → Stage → Transform → Views → Quality gate" if order_ok else f"Positions={positions}",
    ))

    source_validator = (root / "validate_source.py").read_text(encoding="utf-8")
    canonical_selector_ok = (
        '.silver_pipeline_work_*/prepared' in source_validator
        and '.tmp_silver_normalize/prepared' not in source_validator
    )
    checks.append(Check(
        "Canonical Silver selection", "PASS" if canonical_selector_ok else "FAIL",
        "Automatic discovery is restricted to .silver_pipeline_work_*/prepared"
        if canonical_selector_ok else "Temporary/non-canonical Silver can still be selected automatically",
    ))

    deploy_script = (root / "run_snowflake_deploy.ps1").read_text(encoding="utf-8")
    deploy_tokens = [
        '"validate_lineage.py"',
        '"validate_source.py"',
        '"star_schema\\validate_model.py"',
        '"validate_pipeline.py"',
        '"build_warehouse.py"',
        '"validate_warehouse.py"',
    ]
    deploy_positions = [deploy_script.find(token) for token in deploy_tokens]
    deploy_order_ok = all(position >= 0 for position in deploy_positions) and deploy_positions == sorted(deploy_positions)
    checks.append(Check(
        "End-to-end gate order", "PASS" if deploy_order_ok else "FAIL",
        "Raw lineage → Silver baseline → Star model → SQL bundle → Snowflake build → live reconciliation"
        if deploy_order_ok else f"Positions={deploy_positions}",
    ))

    failed = [check for check in checks if check.status == "FAIL"]
    report = root / "output" / "pipeline_validation_report.md"
    lines = [
        "# Báo cáo kiểm tra pipeline Snowflake", "",
        f"- Thời điểm UTC: `{utc_now()}`",
        f"- Kết luận: `{'PASS' if not failed else 'FAIL'}`",
        f"- Số kiểm tra thất bại: `{len(failed)}`", "",
        "| Kiểm tra | Trạng thái | Chi tiết |", "| --- | --- | --- |",
    ]
    lines.extend(f"| {check.name} | {check.status} | {check.details} |" for check in checks)
    lines.append("")
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")

    print(f"pipeline_checks={len(checks)}")
    print(f"failed_pipeline_checks={len(failed)}")
    print(f"report={report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
