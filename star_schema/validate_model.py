from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DIMENSIONS = {
    "DIM_DATE", "DIM_GEOGRAPHY", "DIM_CUSTOMER", "DIM_PRODUCT",
    "DIM_PROMOTION", "DIM_SALES_EMPLOYEE", "DIM_SHIPPER",
}
FACTS = {
    "FACT_SALES", "FACT_ORDERS", "FACT_PAYMENTS", "FACT_RETURNS",
    "FACT_REVIEWS", "FACT_SHIPMENTS", "FACT_INVENTORY_SNAPSHOT", "FACT_WEB_TRAFFIC",
}
FACT_GRAINS = {
    "FACT_SALES": ("ORDER_ID", "SOURCE_ROW_NUMBER"),
    "FACT_ORDERS": ("ORDER_ID",),
    "FACT_PAYMENTS": ("ORDER_ID",),
    "FACT_RETURNS": ("RETURN_ID",),
    "FACT_REVIEWS": ("REVIEW_ID",),
    "FACT_SHIPMENTS": ("ORDER_ID",),
    "FACT_INVENTORY_SNAPSHOT": ("SNAPSHOT_DATE_KEY", "PRODUCT_KEY"),
    "FACT_WEB_TRAFFIC": ("TRAFFIC_DATE_KEY", "TRAFFIC_SOURCE"),
}
REQUIRED_MEASURES = {
    "FACT_SALES": {"QUANTITY", "UNIT_PRICE", "NET_SALES_AMOUNT", "COGS_AMOUNT", "GROSS_PROFIT_AMOUNT"},
    "FACT_ORDERS": {"ORDER_COUNT", "PAYMENT_VALUE", "SHIPPING_FEE", "REFUND_AMOUNT", "NET_REVENUE_AFTER_RETURNS"},
    "FACT_INVENTORY_SNAPSHOT": {"STOCK_ON_HAND", "DAYS_OF_SUPPLY", "FILL_RATE"},
    "FACT_WEB_TRAFFIC": {"SESSIONS", "UNIQUE_VISITORS", "PAGE_VIEWS", "BOUNCE_RATE"},
}


@dataclass
class Check:
    name: str
    status: str
    details: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_tables(sql: str) -> dict[str, str]:
    pattern = re.compile(r"CREATE\s+OR\s+REPLACE\s+TABLE\s+(\w+)\s*\((.*?)\)\s*;", re.I | re.S)
    return {name.upper(): body.upper() for name, body in pattern.findall(sql)}


def validate_static(schema_path: Path) -> list[Check]:
    source = schema_path.read_text(encoding="utf-8")
    upper = source.upper()
    tables = parse_tables(source)
    expected = DIMENSIONS | FACTS
    checks: list[Check] = []

    missing = sorted(expected - set(tables))
    extra = sorted(set(tables) - expected)
    checks.append(Check("Đầy đủ bảng Star Schema", "PASS" if not missing and not extra else "FAIL",
                        "Đủ 7 dimension và 8 fact" if not missing and not extra else f"Thiếu={missing}; dư={extra}"))

    missing_pk = [table for table in expected if table in tables and "PRIMARY KEY" not in tables[table]]
    checks.append(Check("Primary key metadata", "PASS" if not missing_pk else "FAIL",
                        "15/15 bảng có primary key" if not missing_pk else f"Thiếu: {missing_pk}"))

    missing_grains = []
    for table, columns in FACT_GRAINS.items():
        body = tables.get(table, "")
        grain = ", ".join(columns)
        if not re.search(rf"UNIQUE\s*\(\s*{re.escape(grain).replace(r'\ ', r'\s*')}\s*\)", body):
            missing_grains.append(f"{table}({grain})")
    checks.append(Check("Ràng buộc grain", "PASS" if not missing_grains else "FAIL",
                        "8/8 fact có UNIQUE theo grain" if not missing_grains else f"Thiếu: {missing_grains}"))

    foreign_key_count = len(re.findall(r"FOREIGN\s+KEY\s*\(", upper))
    checks.append(Check("Quan hệ fact/dimension", "PASS" if foreign_key_count == 33 else "FAIL",
                        f"Foreign keys khai báo: {foreign_key_count}; kỳ vọng: 33"))

    missing_scd = []
    for table in DIMENSIONS - {"DIM_DATE"}:
        body = tables.get(table, "")
        absent = [column for column in ("VALID_FROM", "VALID_TO", "IS_CURRENT") if column not in body]
        if absent:
            missing_scd.append(f"{table}: {absent}")
    checks.append(Check("SCD Type 2 columns", "PASS" if not missing_scd else "FAIL",
                        "6/6 dimension nghiệp vụ có SCD columns" if not missing_scd else "; ".join(missing_scd)))

    missing_measures = []
    for table, measures in REQUIRED_MEASURES.items():
        absent = sorted(measures - set(re.findall(r"\b[A-Z][A-Z0-9_]*\b", tables.get(table, ""))))
        if absent:
            missing_measures.append(f"{table}: {absent}")
    checks.append(Check("Measure phân tích", "PASS" if not missing_measures else "FAIL",
                        "Các measure bắt buộc đầy đủ" if not missing_measures else "; ".join(missing_measures)))

    forbidden = [token for token in ("PRAGMA", " AUTOINCREMENT", " REAL ", " TEXT ") if token in upper]
    snowflake_types = all(token in upper for token in ("NUMBER(", "DATE", "BOOLEAN", "TIMESTAMP_NTZ"))
    checks.append(Check("Snowflake-native DDL", "PASS" if not forbidden and snowflake_types else "FAIL",
                        "Sử dụng kiểu dữ liệu Snowflake; không còn cú pháp SQLite" if not forbidden and snowflake_types
                        else f"Forbidden={forbidden}; native_types={snowflake_types}"))

    unenforced_count = len(re.findall(r"NOT\s+ENFORCED", upper))
    checks.append(Check("Constraint policy", "PASS" if unenforced_count >= 48 else "FAIL",
                        f"{unenforced_count} PK/FK/UNIQUE constraints khai báo NOT ENFORCED; được kiểm tra bằng quality gate"))
    return checks


def validate_live(connection_name: str) -> list[Check]:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError("Install data_warehouse/requirements.txt before live validation") from exc
    connection = snowflake.connector.connect(connection_name=connection_name, autocommit=True)
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT TABLE_NAME
            FROM STUDENT_SALES_DW.INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA='CORE' AND TABLE_TYPE='BASE TABLE'
            """
        )
        tables = {row[0] for row in cursor.fetchall()}
        missing = sorted((DIMENSIONS | FACTS) - tables)
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM STUDENT_SALES_DW.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA='CORE'
            """
        )
        column_count = int(cursor.fetchone()[0])
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM STUDENT_SALES_DW.INFORMATION_SCHEMA.TABLE_CONSTRAINTS
            WHERE TABLE_SCHEMA='CORE'
              AND CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY')
            """
        )
        constraint_count = int(cursor.fetchone()[0])
        return [
            Check("Live Snowflake tables", "PASS" if not missing else "FAIL",
                  "15/15 tables exist" if not missing else f"Missing: {missing}"),
            Check("Live Snowflake columns", "PASS" if column_count > 100 else "FAIL",
                  f"CORE column count: {column_count}"),
            Check("Live Snowflake constraint metadata", "PASS" if constraint_count == 63 else "FAIL",
                  f"PK/UNIQUE/FK constraints: {constraint_count}/63"),
        ]
    finally:
        cursor.close()
        connection.close()


def write_report(path: Path, schema_path: Path, checks: list[Check], live_requested: bool) -> None:
    failed = sum(check.status == "FAIL" for check in checks)
    lines = [
        "# Báo cáo kiểm tra Star Schema Snowflake", "",
        f"- DDL: `{schema_path}`",
        f"- Thời điểm UTC: `{utc_now()}`",
        f"- Kiểm tra live Snowflake: `{'YES' if live_requested else 'SKIPPED - chưa có connection'}`",
        f"- Kết luận phần đã chạy: `{'PASS' if failed == 0 else 'FAIL'}`",
        f"- Số kiểm tra thất bại: `{failed}`", "",
        "| Kiểm tra | Trạng thái | Chi tiết |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {check.name} | {check.status} | {check.details} |" for check in checks)
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Validate the Snowflake Star Schema before Data Warehouse deployment.")
    parser.add_argument("--schema", type=Path, default=root / "sql" / "star_schema.sql")
    parser.add_argument("--connection-name", default=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME"))
    parser.add_argument("--report", type=Path, default=root / "output" / "model_validation_report.md")
    args = parser.parse_args()

    checks = validate_static(args.schema)
    if args.connection_name:
        checks.extend(validate_live(args.connection_name))
    write_report(args.report, args.schema.resolve(), checks, bool(args.connection_name))
    failed = [check for check in checks if check.status == "FAIL"]
    print(f"star_schema_checks={len(checks)}")
    print(f"failed_star_schema_checks={len(failed)}")
    print(f"live_validation={'yes' if args.connection_name else 'skipped'}")
    print(f"report={args.report.resolve()}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
