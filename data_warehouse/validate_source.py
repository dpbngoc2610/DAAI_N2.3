from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


CANONICAL_DATASETS = [
    "customers", "geography", "products", "promotions", "orders_enriched",
    "order_items", "payments", "returns", "reviews", "shipments", "inventory",
    "web_traffic",
]

GRAINS = {
    "customers": ["customer_id"],
    "geography": ["zip"],
    "products": ["product_id"],
    "promotions": ["promo_id"],
    "orders_enriched": ["order_id"],
    "order_items": ["order_id", "source_row_number"],
    "payments": ["order_id"],
    "returns": ["return_id"],
    "reviews": ["review_id"],
    "shipments": ["order_id"],
    "inventory": ["snapshot_date", "product_id"],
    "web_traffic": ["date", "traffic_source"],
}

REQUIRED_KEYS = {
    "customers": ["customer_id", "zip"],
    "geography": ["zip"],
    "products": ["product_id"],
    "promotions": ["promo_id"],
    "orders_enriched": ["order_id", "customer_id", "zip", "sales_employee_id"],
    "order_items": ["order_id", "product_id", "source_row_number"],
    "payments": ["order_id"],
    "returns": ["return_id", "order_id", "product_id"],
    "reviews": ["review_id", "order_id", "product_id", "customer_id"],
    "shipments": ["order_id", "shipper_id"],
    "inventory": ["snapshot_date", "product_id"],
    "web_traffic": ["date", "traffic_source"],
}

STAGE_TABLES = {
    "customers": "STG_CUSTOMERS", "geography": "STG_GEOGRAPHY",
    "products": "STG_PRODUCTS", "promotions": "STG_PROMOTIONS",
    "orders_enriched": "STG_ORDERS_ENRICHED", "order_items": "STG_ORDER_ITEMS",
    "payments": "STG_PAYMENTS", "returns": "STG_RETURNS", "reviews": "STG_REVIEWS",
    "shipments": "STG_SHIPMENTS", "inventory": "STG_INVENTORY",
    "web_traffic": "STG_WEB_TRAFFIC",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_latest_prepared_dir(project_root: Path) -> Path:
    candidates = []
    silver_root = project_root / "silver_data"
    for pattern in (".silver_pipeline_work_*/prepared", ".tmp_silver_normalize/prepared"):
        for path in silver_root.glob(pattern):
            if (path / "manifest.json").exists() and all(
                (path / f"{name}_silver.csv").exists() for name in CANONICAL_DATASETS
            ):
                candidates.append(path)
    if not candidates:
        raise FileNotFoundError("No complete prepared Silver directory was found")
    return max(candidates, key=lambda path: (path / "manifest.json").stat().st_mtime)


def key_series(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    return frame[columns].fillna("").astype(str).agg("\x1f".join, axis=1)


def scan_dataset(path: Path, dataset: str, chunk_size: int) -> dict:
    seen: set[str] = set()
    duplicate_count = 0
    missing_required = 0
    row_count = 0
    warning_count = 0
    metric_sums = {
        "gross_sales": 0.0,
        "discount_amount": 0.0,
        "net_sales": 0.0,
        "payment_value": 0.0,
        "refund_amount": 0.0,
        "shipping_fee": 0.0,
    }

    for frame in pd.read_csv(path, dtype=str, keep_default_na=False, chunksize=chunk_size, low_memory=False):
        row_count += len(frame)
        keys = key_series(frame, GRAINS[dataset])
        duplicate_count += int(keys.duplicated().sum())
        unique_keys = set(keys.unique())
        duplicate_count += len(unique_keys & seen)
        seen.update(unique_keys)

        required = frame[REQUIRED_KEYS[dataset]].fillna("").astype(str)
        missing_required += int((required.apply(lambda column: column.str.strip().eq(""))).any(axis=1).sum())
        if "data_quality_status" in frame:
            warning_count += int(frame["data_quality_status"].str.lower().eq("warning").sum())

        if dataset == "order_items":
            quantity = pd.to_numeric(frame["quantity"], errors="coerce").fillna(0)
            unit_price = pd.to_numeric(frame["unit_price"], errors="coerce").fillna(0)
            discount = pd.to_numeric(frame["discount_amount"], errors="coerce").fillna(0)
            gross = quantity * unit_price
            metric_sums["gross_sales"] += float(gross.sum())
            metric_sums["discount_amount"] += float(discount.sum())
            metric_sums["net_sales"] += float((gross - discount).sum())
        elif dataset == "payments":
            metric_sums["payment_value"] += float(pd.to_numeric(frame["payment_value"], errors="coerce").fillna(0).sum())
        elif dataset == "returns":
            metric_sums["refund_amount"] += float(pd.to_numeric(frame["refund_amount"], errors="coerce").fillna(0).sum())
        elif dataset == "shipments":
            metric_sums["shipping_fee"] += float(pd.to_numeric(frame["shipping_fee"], errors="coerce").fillna(0).sum())

    return {
        "row_count": row_count,
        "duplicate_grain_count": duplicate_count,
        "missing_required_key_count": missing_required,
        "warning_count": warning_count,
        "key_values": seen,
        "metric_sums": metric_sums,
    }


def foreign_key_checks(prepared_dir: Path, key_sets: dict[str, set[str]], chunk_size: int) -> dict[str, int]:
    relationships = [
        ("order_items", "order_id", "orders_enriched"),
        ("order_items", "product_id", "products"),
        ("orders_enriched", "customer_id", "customers"),
        ("orders_enriched", "zip", "geography"),
        ("payments", "order_id", "orders_enriched"),
        ("returns", "order_id", "orders_enriched"),
        ("returns", "product_id", "products"),
        ("reviews", "order_id", "orders_enriched"),
        ("reviews", "product_id", "products"),
        ("reviews", "customer_id", "customers"),
        ("shipments", "order_id", "orders_enriched"),
        ("inventory", "product_id", "products"),
    ]
    results: dict[str, int] = {}
    natural_keys = {
        "orders_enriched": "order_id", "products": "product_id",
        "customers": "customer_id", "geography": "zip",
    }
    parent_values = {
        parent: {value.split("\x1f", 1)[0] for value in key_sets[parent]}
        for parent in natural_keys
    }
    for child, column, parent in relationships:
        missing = 0
        path = prepared_dir / f"{child}_silver.csv"
        for frame in pd.read_csv(path, dtype=str, keep_default_na=False, usecols=[column], chunksize=chunk_size):
            values = frame[column].fillna("").astype(str).str.strip()
            missing += int((~values.isin(parent_values[parent])).sum())
        results[f"{child}.{column}->{parent}.{natural_keys[parent]}"] = missing
    return results


def split_top_level_columns(body: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(body):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(body[start:index].strip())
            start = index + 1
    parts.append(body[start:].strip())
    return [part for part in parts if part]


def validate_stage_column_order(stage_schema_path: Path, manifest: dict) -> dict[str, dict]:
    source = stage_schema_path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"CREATE\s+OR\s+REPLACE\s+TRANSIENT\s+TABLE\s+(STG_\w+)\s*\((.*?)\)\s*;",
        re.I | re.S,
    )
    definitions = {}
    for table, body in pattern.findall(source):
        definitions[table.upper()] = [part.split()[0].upper() for part in split_top_level_columns(body)]
    metadata = {item["name"]: item for item in manifest["datasets"]}
    results = {}
    for dataset, table in STAGE_TABLES.items():
        expected = [column.upper() for column in metadata[dataset]["silver_columns"]]
        actual = definitions.get(table, [])
        results[dataset] = {
            "table": table,
            "expected_columns": len(expected),
            "actual_columns": len(actual),
            "status": "PASS" if actual == expected else "FAIL",
            "first_mismatch": next(
                (index + 1 for index, (left, right) in enumerate(zip(expected, actual)) if left != right),
                None if len(expected) == len(actual) else min(len(expected), len(actual)) + 1,
            ),
        }
    return results


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Validate canonical Silver data and write Snowflake comparison metrics.")
    parser.add_argument("--project-root", type=Path, default=root)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--output", type=Path, default=root / "data_warehouse" / "output" / "expected_metrics.json")
    parser.add_argument("--report", type=Path, default=root / "data_warehouse" / "output" / "offline_validation_report.md")
    args = parser.parse_args()

    prepared_dir = args.prepared_dir.resolve() if args.prepared_dir else find_latest_prepared_dir(args.project_root.resolve())
    manifest = json.loads((prepared_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_rows = {item["name"]: int(item["silver_rows"]) for item in manifest["datasets"]}

    scans: dict[str, dict] = {}
    for dataset in CANONICAL_DATASETS:
        print(f"Validating {dataset}...", flush=True)
        scans[dataset] = scan_dataset(prepared_dir / f"{dataset}_silver.csv", dataset, args.chunk_size)

    key_sets = {name: result.pop("key_values") for name, result in scans.items()}
    fk_results = foreign_key_checks(prepared_dir, key_sets, args.chunk_size)
    stage_schema_path = args.project_root.resolve() / "data_warehouse" / "sql" / "02_stage_schema.sql"
    stage_column_checks = validate_stage_column_order(stage_schema_path, manifest)

    row_counts = {name: result["row_count"] for name, result in scans.items()}
    measures = {
        "gross_sales": round(scans["order_items"]["metric_sums"]["gross_sales"], 2),
        "discount_amount": round(scans["order_items"]["metric_sums"]["discount_amount"], 2),
        "net_sales": round(scans["order_items"]["metric_sums"]["net_sales"], 2),
        "payment_value": round(scans["payments"]["metric_sums"]["payment_value"], 2),
        "refund_amount": round(scans["returns"]["metric_sums"]["refund_amount"], 2),
        "shipping_fee": round(scans["shipments"]["metric_sums"]["shipping_fee"], 2),
    }
    results = {
        "generated_at_utc": utc_now(),
        "source_batch_id": manifest.get("batch_id"),
        "prepared_dir": str(prepared_dir),
        "row_counts": row_counts,
        "manifest_row_counts": {name: manifest_rows[name] for name in CANONICAL_DATASETS},
        "duplicate_grain_counts": {name: result["duplicate_grain_count"] for name, result in scans.items()},
        "missing_required_key_counts": {name: result["missing_required_key_count"] for name, result in scans.items()},
        "foreign_key_missing_counts": fk_results,
        "stage_column_checks": stage_column_checks,
        "warning_counts": {name: result["warning_count"] for name, result in scans.items()},
        "measures": measures,
    }

    failures = []
    for dataset in CANONICAL_DATASETS:
        if row_counts[dataset] != manifest_rows[dataset]:
            failures.append(f"{dataset}: actual rows differ from manifest")
        if results["duplicate_grain_counts"][dataset] != 0:
            failures.append(f"{dataset}: duplicated grain")
        if results["missing_required_key_counts"][dataset] != 0:
            failures.append(f"{dataset}: missing required key")
    failures.extend(name for name, count in fk_results.items() if count != 0)
    failures.extend(
        f"{dataset}: staging column order does not match Silver CSV"
        for dataset, result in stage_column_checks.items() if result["status"] != "PASS"
    )
    results["status"] = "PASS" if not failures else "FAIL"
    results["failures"] = failures

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Báo cáo kiểm tra Silver trước khi nạp Snowflake", "",
        f"- Batch: `{results['source_batch_id']}`",
        f"- Kết luận: `{results['status']}`",
        f"- Số lỗi: `{len(failures)}`", "",
        "## Số dòng và grain", "",
        "| Dataset | Manifest | Thực tế | Grain trùng | Thiếu key | Warning | Status |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for dataset in CANONICAL_DATASETS:
        ok = (row_counts[dataset] == manifest_rows[dataset]
              and results["duplicate_grain_counts"][dataset] == 0
              and results["missing_required_key_counts"][dataset] == 0)
        lines.append(
            f"| `{dataset}` | {manifest_rows[dataset]:,} | {row_counts[dataset]:,} | "
            f"{results['duplicate_grain_counts'][dataset]:,} | "
            f"{results['missing_required_key_counts'][dataset]:,} | "
            f"{results['warning_counts'][dataset]:,} | {'PASS' if ok else 'FAIL'} |"
        )
    lines.extend(["", "## Referential integrity giữa các nguồn Silver", "",
                  "| Quan hệ | Bản ghi không khớp | Status |", "| --- | ---: | --- |"]) 
    for name, count in fk_results.items():
        lines.append(f"| `{name}` | {count:,} | {'PASS' if count == 0 else 'FAIL'} |")
    lines.extend(["", "## Đồng bộ thứ tự cột CSV → Snowflake staging", "",
                  "| Dataset | Stage table | Silver columns | Stage columns | Status |",
                  "| --- | --- | ---: | ---: | --- |"]) 
    for dataset, result in stage_column_checks.items():
        lines.append(
            f"| `{dataset}` | `{result['table']}` | {result['expected_columns']} | "
            f"{result['actual_columns']} | {result['status']} |"
        )
    lines.extend(["", "## Baseline tài chính dùng để đối soát Snowflake", ""])
    for name, value in measures.items():
        lines.append(f"- `{name}`: `{value:,.2f}`")
    if failures:
        lines.extend(["", "## Lỗi", ""] + [f"- {failure}" for failure in failures])
    lines.append("")
    args.report.write_text("\n".join(lines), encoding="utf-8")

    print(f"offline_status={results['status']}")
    print(f"expected_metrics={args.output}")
    print(f"report={args.report}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
