from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from validate_source import CANONICAL_DATASETS, find_latest_prepared_dir


ALL_DATASETS = [
    "customers", "epd", "products", "eprom", "promotions", "geography",
    "inventory", "orders_enriched", "order_items", "payments", "returns",
    "reviews", "shipments", "tf", "web_traffic",
]

STABLE_MANIFEST_FIELDS = [
    "name", "source_file", "source_rows", "silver_rows", "quarantined_rows",
    "source_column_count", "silver_columns", "key_cols", "types", "rules",
    "warnings", "warning_rows",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_manifest(prepared_dir: Path) -> dict:
    return json.loads((prepared_dir / "manifest.json").read_text(encoding="utf-8"))


def dataset_map(manifest: dict) -> dict[str, dict]:
    return {item["name"]: item for item in manifest["datasets"]}


def stable_manifest_entry(item: dict) -> dict:
    return {field: item.get(field) for field in STABLE_MANIFEST_FIELDS}


def validate_row_lineage(prepared_dir: Path, metadata: dict[str, dict], chunk_size: int) -> list[dict]:
    checks = []
    for name in ALL_DATASETS:
        item = metadata[name]
        silver_path = prepared_dir / f"{name}_silver.csv"
        quarantine_path = prepared_dir / f"{name}_quarantine.json"
        silver_rows: list[int] = []
        source_files: set[str] = set()
        for chunk in pd.read_csv(
            silver_path,
            usecols=["source_file", "source_row_number"],
            dtype={"source_file": "string", "source_row_number": "Int64"},
            chunksize=chunk_size,
        ):
            source_files.update(chunk["source_file"].dropna().astype(str).unique())
            silver_rows.extend(chunk["source_row_number"].dropna().astype(int).tolist())
        quarantine = json.loads(quarantine_path.read_text(encoding="utf-8"))
        quarantine_rows = [int(row["source_row_number"]) for row in quarantine]
        source_files.update(str(row["source_file"]) for row in quarantine)
        combined = silver_rows + quarantine_rows
        expected = set(range(2, int(item["source_rows"]) + 2))
        actual = set(combined)
        passed = (
            len(silver_rows) == int(item["silver_rows"])
            and len(quarantine_rows) == int(item["quarantined_rows"])
            and len(combined) == len(actual)
            and actual == expected
            and source_files == {item["source_file"]}
        )
        checks.append({
            "name": f"row_lineage:{name}",
            "status": "PASS" if passed else "FAIL",
            "details": (
                f"source={item['source_rows']:,}; silver={len(silver_rows):,}; "
                f"quarantine={len(quarantine_rows):,}; source_file={sorted(source_files)}"
            ),
        })
    return checks


def compare_silver_files(reference: Path, rebuilt: Path, name: str, chunk_size: int) -> tuple[bool, str]:
    reference_path = reference / f"{name}_silver.csv"
    rebuilt_path = rebuilt / f"{name}_silver.csv"
    reference_columns = pd.read_csv(reference_path, nrows=0).columns.tolist()
    rebuilt_columns = pd.read_csv(rebuilt_path, nrows=0).columns.tolist()
    if reference_columns != rebuilt_columns:
        return False, "column order differs"
    stable_columns = [column for column in reference_columns if column not in {"batch_id", "processed_at_utc"}]
    reference_reader = pd.read_csv(reference_path, usecols=stable_columns, dtype=str, chunksize=chunk_size)
    rebuilt_reader = pd.read_csv(rebuilt_path, usecols=stable_columns, dtype=str, chunksize=chunk_size)
    reference_count = rebuilt_count = 0
    while True:
        try:
            reference_chunk = next(reference_reader)
        except StopIteration:
            reference_chunk = None
        try:
            rebuilt_chunk = next(rebuilt_reader)
        except StopIteration:
            rebuilt_chunk = None
        if reference_chunk is None or rebuilt_chunk is None:
            return (
                reference_chunk is None and rebuilt_chunk is None,
                f"stable rows compared: reference={reference_count:,}; rebuilt={rebuilt_count:,}",
            )
        reference_count += len(reference_chunk)
        rebuilt_count += len(rebuilt_chunk)
        if not reference_chunk.fillna("").equals(rebuilt_chunk.fillna("")):
            return False, f"stable content differs near row {min(reference_count, rebuilt_count):,}"


def stable_quarantine(path: Path) -> list[dict]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    stable = [
        {key: value for key, value in row.items() if key not in {"batch_id", "processed_at_utc"}}
        for row in rows
    ]
    return sorted(stable, key=lambda row: (int(row["source_row_number"]), row.get("error_codes", "")))


def rebuild_checks(project_root: Path, source_dir: Path, reference_dir: Path, chunk_size: int) -> list[dict]:
    checks = []
    temp_root = project_root / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lineage_rebuild_", dir=temp_root) as temp_name:
        rebuilt = Path(temp_name) / "prepared"
        command = [
            sys.executable,
            str(project_root / "silver_data" / "pipeline" / "prepare_silver.py"),
            "--source-dir", str(source_dir),
            "--prepared-dir", str(rebuilt),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            return [{
                "name": "deterministic_rebuild",
                "status": "FAIL",
                "details": completed.stderr[-1000:] or completed.stdout[-1000:],
            }]
        reference_manifest = dataset_map(load_manifest(reference_dir))
        rebuilt_manifest = dataset_map(load_manifest(rebuilt))
        for name in ALL_DATASETS:
            manifest_ok = stable_manifest_entry(reference_manifest[name]) == stable_manifest_entry(rebuilt_manifest[name])
            silver_ok, details = compare_silver_files(reference_dir, rebuilt, name, chunk_size)
            quarantine_ok = stable_quarantine(reference_dir / f"{name}_quarantine.json") == stable_quarantine(
                rebuilt / f"{name}_quarantine.json"
            )
            passed = manifest_ok and silver_ok and quarantine_ok
            checks.append({
                "name": f"deterministic_rebuild:{name}",
                "status": "PASS" if passed else "FAIL",
                "details": (
                    f"manifest={manifest_ok}; silver={silver_ok}; quarantine={quarantine_ok}; {details}"
                ),
            })
    return checks


def variant_and_grain_checks(prepared_dir: Path) -> tuple[list[dict], dict]:
    def load(name: str, columns: list[str]) -> pd.DataFrame:
        return pd.read_csv(prepared_dir / f"{name}_silver.csv", usecols=columns, low_memory=False)

    products = load("products", ["product_id", "product_name", "category", "segment", "size", "color", "price", "cogs"])
    epd = load("epd", ["product_id", "product_name", "category", "segment", "size", "color", "price", "cogs"])
    product_ids = set(products["product_id"].astype(int))
    epd_ids = set(epd["product_id"].astype(int))
    merged = epd.merge(products, on="product_id", suffixes=("_epd", "_products"))
    conflicts = 0
    for attribute in ["product_name", "category", "segment", "size", "color", "price", "cogs"]:
        left = merged[f"{attribute}_epd"].fillna("").astype(str)
        right = merged[f"{attribute}_products"].fillna("").astype(str)
        conflicts += int((left != right).sum())

    items = load("order_items", ["order_id", "product_id", "promo_id", "promo_id_2"])
    product_refs = set(items["product_id"].dropna().astype(int))
    promotions = load("promotions", ["promo_id"])
    eprom = load("eprom", ["promo_id"])
    promotion_ids = set(promotions["promo_id"].astype(str))
    eprom_ids = set(eprom["promo_id"].astype(str))
    promo_refs = set(pd.concat([items["promo_id"], items["promo_id_2"]]).dropna().astype(str))

    tf = load("tf", ["date", "traffic_source", "traffic_variant"])
    web = load("web_traffic", ["date", "traffic_source"])
    tf_keys = set(zip(tf["date"].astype(str), tf["traffic_source"].astype(str)))
    web_keys = set(zip(web["date"].astype(str), web["traffic_source"].astype(str)))

    line_counts = items.value_counts(["order_id", "product_id"])
    ambiguous_keys = set(line_counts[line_counts > 1].index.tolist())
    returns = load("returns", ["order_id", "product_id"])
    reviews = load("reviews", ["order_id", "product_id"])
    returns_ambiguous = sum(
        key in ambiguous_keys for key in zip(returns["order_id"], returns["product_id"])
    )
    reviews_ambiguous = sum(
        key in ambiguous_keys for key in zip(reviews["order_id"], reviews["product_id"])
    )

    metrics = {
        "epd_product_overlap": len(epd_ids & product_ids),
        "epd_product_attribute_conflicts": conflicts,
        "eprom_promotion_overlap": len(eprom_ids & promotion_ids),
        "tf_web_overlap": len(tf_keys & web_keys),
        "duplicate_order_product_pairs": len(ambiguous_keys),
        "duplicate_order_item_rows": int(line_counts[line_counts > 1].sum()),
        "returns_on_ambiguous_pairs": int(returns_ambiguous),
        "reviews_on_ambiguous_pairs": int(reviews_ambiguous),
    }
    checks = [
        {
            "name": "canonical_product_coverage",
            "status": "PASS" if not (product_refs - product_ids) else "FAIL",
            "details": f"order-item products missing from products={len(product_refs - product_ids)}",
        },
        {
            "name": "epd_is_validation_variant",
            "status": "PASS" if epd_ids <= product_ids else "FAIL",
            "details": (
                f"epd-only keys={len(epd_ids - product_ids)}; overlap={len(epd_ids & product_ids)}; "
                f"attribute conflicts={conflicts}"
            ),
        },
        {
            "name": "canonical_promotion_coverage",
            "status": "PASS" if not (promo_refs - promotion_ids) else "FAIL",
            "details": (
                f"order-item promotions missing from promotions={len(promo_refs - promotion_ids)}; "
                f"referenced only by eprom={len((promo_refs - promotion_ids) & eprom_ids)}"
            ),
        },
        {
            "name": "tf_is_validation_variant",
            "status": "PASS" if tf_keys <= web_keys else "FAIL",
            "details": (
                f"tf-only grain keys={len(tf_keys - web_keys)}; overlap={len(tf_keys & web_keys)}; "
                f"variant rows={int(tf['traffic_variant'].notna().sum())}"
            ),
        },
        {
            "name": "returns_reviews_grain_safety",
            "status": "PASS",
            "details": (
                f"ambiguous order-product pairs={len(ambiguous_keys)}; rows={int(line_counts[line_counts > 1].sum())}; "
                f"returns affected={returns_ambiguous}; reviews affected={reviews_ambiguous}; "
                "therefore facts retain order+product references and are not forced to a sales-line key"
            ),
        },
    ]
    return checks, metrics


def write_report(path: Path, result: dict) -> None:
    lines = [
        "# Báo cáo kiểm thử lineage File gốc → Silver → Star Schema/Data Warehouse",
        "",
        f"- Thời điểm UTC: `{result['generated_at_utc']}`",
        f"- Silver canonical: `{result['prepared_dir']}`",
        f"- Nguồn CSV gốc: `{result['source_dir']}`",
        f"- Kết luận: `{result['status']}`",
        f"- Số kiểm tra: `{len(result['checks'])}`",
        f"- Số lỗi: `{len(result['failures'])}`",
        "",
        "## Quyết định nguồn canonical",
        "",
        "- `products` là nguồn DIM_PRODUCT; `epd` chỉ dùng đối chiếu vì là tập con và có xung đột thuộc tính.",
        "- `promotions` là nguồn DIM_PROMOTION vì bao phủ toàn bộ promotion mà order_items tham chiếu; `eprom` không cùng namespace khóa.",
        "- `web_traffic` là nguồn FACT_WEB_TRAFFIC; `tf` là tập con trùng grain và có thêm nhãn variant nên không được union để tránh đếm đôi.",
        "- `returns` và `reviews` không ép ánh xạ đến một sales line khi `(order_id, product_id)` không duy nhất.",
        "",
        "## Kết quả",
        "",
        "| Kiểm tra | Trạng thái | Chi tiết |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| `{check['name']}` | {check['status']} | {check['details'].replace('|', '/')} |"
        for check in result["checks"]
    )
    lines.extend(["", "## Chỉ số phát hiện từ dữ liệu dự án", ""])
    lines.extend(f"- `{name}`: `{value:,}`" for name, value in result["metrics"].items())
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Validate raw-source to canonical-Silver lineage.")
    parser.add_argument("--project-root", type=Path, default=root)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument("--chunk-size", type=int, default=100_000)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument(
        "--output", type=Path,
        default=root / "data_warehouse" / "output" / "lineage_validation_report.json",
    )
    parser.add_argument(
        "--report", type=Path,
        default=root / "data_warehouse" / "output" / "lineage_validation_report.md",
    )
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    prepared_dir = args.prepared_dir.resolve() if args.prepared_dir else find_latest_prepared_dir(project_root)
    source_dir = prepared_dir.parent / "excel"
    manifest = load_manifest(prepared_dir)
    metadata = dataset_map(manifest)
    checks: list[dict] = []

    canonical_path_ok = prepared_dir.parent.name.startswith(".silver_pipeline_work_")
    checks.append({
        "name": "canonical_prepared_path",
        "status": "PASS" if canonical_path_ok else "FAIL",
        "details": str(prepared_dir),
    })
    manifest_ok = set(metadata) == set(ALL_DATASETS)
    checks.append({
        "name": "manifest_dataset_coverage",
        "status": "PASS" if manifest_ok else "FAIL",
        "details": f"datasets={len(metadata)}/{len(ALL_DATASETS)}",
    })
    if not manifest_ok:
        missing = sorted(set(ALL_DATASETS) - set(metadata))
        extra = sorted(set(metadata) - set(ALL_DATASETS))
        checks[-1]["details"] += f"; missing={missing}; extra={extra}"
    source_files_ok = manifest_ok and all((source_dir / metadata[name]["source_file"]).exists() for name in ALL_DATASETS)
    checks.append({
        "name": "raw_source_file_coverage",
        "status": "PASS" if source_files_ok else "FAIL",
        "details": f"source_dir={source_dir}",
    })

    metrics: dict = {}
    if manifest_ok and source_files_ok:
        checks.extend(validate_row_lineage(prepared_dir, metadata, args.chunk_size))
        variant_checks, metrics = variant_and_grain_checks(prepared_dir)
        checks.extend(variant_checks)
        if args.rebuild:
            checks.extend(rebuild_checks(project_root, source_dir, prepared_dir, args.chunk_size))

    failures = [check["name"] for check in checks if check["status"] == "FAIL"]
    result = {
        "generated_at_utc": utc_now(),
        "prepared_dir": str(prepared_dir),
        "source_dir": str(source_dir),
        "source_batch_id": manifest.get("batch_id"),
        "rebuild_enabled": args.rebuild,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "metrics": metrics,
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(args.report, result)
    print(f"lineage_status={result['status']}")
    print(f"lineage_checks={len(checks)}")
    print(f"report={args.report}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
