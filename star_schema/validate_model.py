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
    "FACT_REVIEWS", "FACT_SHIPMENTS", "FACT_INVENTORY_SNAPSHOT",
    "FACT_WEB_TRAFFIC",
}
BRIDGES = {"BRIDGE_SALES_PROMOTION"}
EXPECTED_TABLES = DIMENSIONS | FACTS | BRIDGES

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
    "FACT_SALES": {"QUANTITY", "UNIT_PRICE", "GROSS_SALES_AMOUNT", "DISCOUNT_AMOUNT", "NET_SALES_AMOUNT", "COGS_AMOUNT", "GROSS_PROFIT_AMOUNT"},
    "FACT_ORDERS": {"ORDER_COUNT", "PAYMENT_VALUE", "SHIPPING_FEE", "REFUND_AMOUNT", "NET_REVENUE_AFTER_RETURNS"},
    "FACT_PAYMENTS": {"PAYMENT_VALUE", "INSTALLMENTS"},
    "FACT_RETURNS": {"RETURN_QUANTITY", "REFUND_AMOUNT"},
    "FACT_REVIEWS": {"RATING"},
    "FACT_SHIPMENTS": {"SHIPPING_FEE", "DAYS_TO_SHIP", "DAYS_TO_DELIVER"},
    "FACT_INVENTORY_SNAPSHOT": {"STOCK_ON_HAND", "DAYS_OF_SUPPLY", "FILL_RATE", "SELL_THROUGH_RATE"},
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


def unique_constraint_exists(body: str, columns: tuple[str, ...]) -> bool:
    pattern = r"UNIQUE\s*\(\s*" + r"\s*,\s*".join(map(re.escape, columns)) + r"\s*\)"
    return re.search(pattern, body, re.I) is not None


def validate_static(schema_path: Path) -> list[Check]:
    source = schema_path.read_text(encoding="utf-8")
    upper = source.upper()
    tables = parse_tables(source)
    checks: list[Check] = []

    missing = sorted(EXPECTED_TABLES - set(tables))
    extra = sorted(set(tables) - EXPECTED_TABLES)
    checks.append(Check(
        "Đầy đủ bảng Star Schema",
        "PASS" if not missing and not extra else "FAIL",
        "Đủ 7 dimension, 8 fact và 1 bridge" if not missing and not extra else f"Thiếu={missing}; dư={extra}",
    ))

    missing_pk = sorted(table for table in EXPECTED_TABLES if "PRIMARY KEY" not in tables.get(table, ""))
    checks.append(Check(
        "Primary key metadata", "PASS" if not missing_pk else "FAIL",
        "16/16 bảng có primary key" if not missing_pk else f"Thiếu: {missing_pk}",
    ))

    missing_grains = [
        f"{table}({', '.join(columns)})"
        for table, columns in FACT_GRAINS.items()
        if not unique_constraint_exists(tables.get(table, ""), columns)
    ]
    checks.append(Check(
        "Ràng buộc grain fact", "PASS" if not missing_grains else "FAIL",
        "8/8 fact có UNIQUE theo grain" if not missing_grains else f"Thiếu: {missing_grains}",
    ))

    bridge = tables.get("BRIDGE_SALES_PROMOTION", "")
    bridge_ok = (
        unique_constraint_exists(bridge, ("SALES_KEY", "PROMOTION_SEQUENCE"))
        and all(column in bridge for column in ("PROMOTION_KEY", "PROMOTION_SEQUENCE", "ALLOCATION_WEIGHT"))
    )
    checks.append(Check(
        "Bridge khuyến mãi", "PASS" if bridge_ok else "FAIL",
        "Có grain sales-promotion, sequence và allocation weight" if bridge_ok else "Bridge thiếu grain hoặc cột phân bổ",
    ))

    foreign_key_count = len(re.findall(r"FOREIGN\s+KEY\s*\(", upper))
    checks.append(Check(
        "Quan hệ khóa ngoại", "PASS" if foreign_key_count == 33 else "FAIL",
        f"Foreign keys khai báo: {foreign_key_count}; kỳ vọng: 33",
    ))

    snowflaked_dimensions = sorted(table for table in DIMENSIONS if "FOREIGN KEY" in tables.get(table, ""))
    checks.append(Check(
        "Cấu trúc sao thuần", "PASS" if not snowflaked_dimensions else "FAIL",
        "Không có quan hệ dimension-to-dimension" if not snowflaked_dimensions else f"Dimension bị snowflake: {snowflaked_dimensions}",
    ))

    scd_tokens = [token for token in ("VALID_FROM", "VALID_TO", "IS_CURRENT") if token in upper]
    checks.append(Check(
        "Chiến lược lịch sử dimension", "PASS" if not scd_tokens else "FAIL",
        "Type 1 full-refresh nhất quán với Silver snapshot" if not scd_tokens else f"Còn cột SCD2 không được ETL hỗ trợ: {scd_tokens}",
    ))

    lineage_missing: list[str] = []
    for table in (DIMENSIONS - {"DIM_DATE"}) | FACTS:
        body = tables.get(table, "")
        absent = [column for column in ("SOURCE_BATCH_ID", "SOURCE_RECORD_HASH", "ETL_LOADED_AT_UTC") if column not in body]
        if absent:
            lineage_missing.append(f"{table}: {absent}")
    bridge_lineage_missing = [column for column in ("SOURCE_BATCH_ID", "ETL_LOADED_AT_UTC") if column not in bridge]
    if bridge_lineage_missing:
        lineage_missing.append(f"BRIDGE_SALES_PROMOTION: {bridge_lineage_missing}")
    checks.append(Check(
        "Lineage kỹ thuật", "PASS" if not lineage_missing else "FAIL",
        "Dimension, fact và bridge giữ batch/hash/load timestamp phù hợp" if not lineage_missing else "; ".join(lineage_missing),
    ))

    missing_measures = []
    for table, measures in REQUIRED_MEASURES.items():
        tokens = set(re.findall(r"\b[A-Z][A-Z0-9_]*\b", tables.get(table, "")))
        absent = sorted(measures - tokens)
        if absent:
            missing_measures.append(f"{table}: {absent}")
    checks.append(Check(
        "Measure phân tích", "PASS" if not missing_measures else "FAIL",
        "Measure bắt buộc đầy đủ ở cả 8 fact" if not missing_measures else "; ".join(missing_measures),
    ))

    forbidden = [token for token in ("PRAGMA", " AUTOINCREMENT", " REAL ", " TEXT ") if token in upper]
    snowflake_types = all(token in upper for token in ("NUMBER(", "DATE", "BOOLEAN", "TIMESTAMP_NTZ"))
    checks.append(Check(
        "Snowflake-native DDL", "PASS" if not forbidden and snowflake_types else "FAIL",
        "Sử dụng kiểu Snowflake; không có cú pháp SQLite" if not forbidden and snowflake_types
        else f"Forbidden={forbidden}; native_types={snowflake_types}",
    ))

    constraint_count = len(re.findall(r"\b(?:PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE)\s*\(", upper))
    unenforced_count = len(re.findall(r"NOT\s+ENFORCED", upper))
    constraints_ok = constraint_count == 65 and unenforced_count == constraint_count
    checks.append(Check(
        "Constraint policy", "PASS" if constraints_ok else "FAIL",
        f"Constraints={constraint_count}/65; NOT ENFORCED={unenforced_count}/{constraint_count}",
    ))
    return checks


def validate_live(connection_name: str) -> list[Check]:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise RuntimeError("Install data_warehouse/requirements.txt before live validation") from exc

    connection = snowflake.connector.connect(connection_name=connection_name, autocommit=True)
    cursor = connection.cursor()
    try:
        # Connections authenticated with a PAT do not necessarily inherit a
        # current database from the named connection.  Set it explicitly so
        # the CORE references below are deterministic in every environment.
        cursor.execute("USE DATABASE STUDENT_SALES_DW")
        cursor.execute(
            "SELECT TABLE_NAME FROM STUDENT_SALES_DW.INFORMATION_SCHEMA.TABLES "
            "WHERE TABLE_SCHEMA='CORE' AND TABLE_TYPE='BASE TABLE'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        missing = sorted(EXPECTED_TABLES - tables)
        cursor.execute(
            "SELECT COUNT(*) FROM STUDENT_SALES_DW.INFORMATION_SCHEMA.TABLE_CONSTRAINTS "
            "WHERE TABLE_SCHEMA='CORE' AND CONSTRAINT_TYPE IN ('PRIMARY KEY','UNIQUE','FOREIGN KEY')"
        )
        constraint_count = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM CORE.FACT_SALES F LEFT JOIN CORE.BRIDGE_SALES_PROMOTION B "
            "ON B.SALES_KEY=F.SALES_KEY WHERE B.SALES_KEY IS NULL"
        )
        missing_bridge_rows = int(cursor.fetchone()[0])
        cursor.execute(
            "SELECT COUNT(*) FROM (SELECT SALES_KEY FROM CORE.BRIDGE_SALES_PROMOTION "
            "GROUP BY SALES_KEY HAVING ABS(SUM(ALLOCATION_WEIGHT)-1)>0.000001)"
        )
        invalid_weights = int(cursor.fetchone()[0])
        return [
            Check("Live Snowflake tables", "PASS" if not missing else "FAIL",
                  "16/16 tables exist" if not missing else f"Missing: {missing}"),
            Check("Live Snowflake constraint metadata", "PASS" if constraint_count == 65 else "FAIL",
                  f"PK/UNIQUE/FK constraints: {constraint_count}/65"),
            Check("Live promotion bridge", "PASS" if missing_bridge_rows == 0 and invalid_weights == 0 else "FAIL",
                  f"missing_sales={missing_bridge_rows}; invalid_weights={invalid_weights}"),
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
    parser = argparse.ArgumentParser(description="Validate the Snowflake Star Schema before deployment.")
    parser.add_argument("--schema", type=Path, default=root / "sql" / "star_schema.sql")
    parser.add_argument("--connection-name", default=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME"))
    parser.add_argument("--report", type=Path, default=root / "output" / "model_validation_report.md")
    args = parser.parse_args()

    checks = validate_static(args.schema)
    if args.connection_name:
        checks.extend(validate_live(args.connection_name))
    write_report(args.report, args.schema, checks, bool(args.connection_name))

    failed = [check for check in checks if check.status == "FAIL"]
    print(f"star_schema_checks={len(checks)}")
    print(f"failed_star_schema_checks={len(failed)}")
    print(f"live_validation={'executed' if args.connection_name else 'skipped'}")
    print(f"report={args.report}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
