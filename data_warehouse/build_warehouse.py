from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def relaunch_in_project_venv() -> None:
    """Use the project interpreter even when the file is run with system Python."""
    script = Path(__file__).resolve()
    venv_python = script.parent / ".venv" / "Scripts" / "python.exe"
    if Path(sys.executable).resolve() == venv_python.resolve():
        return

    if not venv_python.exists():
        installer = script.parent / "install_snowflake_tools.ps1"
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if os.name != "nt" or powershell is None or not installer.exists():
            raise RuntimeError(
                "Project environment is missing. Run "
                "'.\\data_warehouse\\install_snowflake_tools.ps1' first."
            )
        print("Project environment is missing; installing dependencies...", flush=True)
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(installer)],
            check=False,
        )
        if completed.returncode != 0 or not venv_python.exists():
            raise RuntimeError("Could not create the project Snowflake environment.")

    if Path(sys.executable).resolve() != venv_python.resolve():
        print(f"Restarting with project Python: {venv_python}", flush=True)
        completed = subprocess.run(
            [str(venv_python), str(script), *sys.argv[1:]],
            check=False,
        )
        raise SystemExit(completed.returncode)


relaunch_in_project_venv()

from snowflake_connection import connect
from validate_source import CANONICAL_DATASETS, find_latest_prepared_dir


DATABASE = "STUDENT_SALES_DW"
WAREHOUSE = "STUDENT_SALES_ETL_WH"
STAGE = f"{DATABASE}.STAGE.SILVER_INTERNAL_STAGE"
FILE_FORMAT = f"{DATABASE}.STAGE.SILVER_CSV_FORMAT"

STAGE_TABLES = {
    "customers": "STG_CUSTOMERS",
    "geography": "STG_GEOGRAPHY",
    "products": "STG_PRODUCTS",
    "promotions": "STG_PROMOTIONS",
    "orders_enriched": "STG_ORDERS_ENRICHED",
    "order_items": "STG_ORDER_ITEMS",
    "payments": "STG_PAYMENTS",
    "returns": "STG_RETURNS",
    "reviews": "STG_REVIEWS",
    "shipments": "STG_SHIPMENTS",
    "inventory": "STG_INVENTORY",
    "web_traffic": "STG_WEB_TRAFFIC",
}

SOURCE_TARGETS = {
    "customers": ("CORE.DIM_CUSTOMER", "SELECT COUNT(*) FROM CORE.DIM_CUSTOMER WHERE CUSTOMER_KEY <> 0"),
    "geography": ("CORE.DIM_GEOGRAPHY", "SELECT COUNT(*) FROM CORE.DIM_GEOGRAPHY WHERE GEOGRAPHY_KEY <> 0"),
    "products": ("CORE.DIM_PRODUCT", "SELECT COUNT(*) FROM CORE.DIM_PRODUCT WHERE PRODUCT_KEY <> 0"),
    "promotions": ("CORE.DIM_PROMOTION", "SELECT COUNT(*) FROM CORE.DIM_PROMOTION WHERE PROMOTION_KEY <> 0"),
    "orders_enriched": ("CORE.FACT_ORDERS", "SELECT COUNT(*) FROM CORE.FACT_ORDERS"),
    "order_items": ("CORE.FACT_SALES", "SELECT COUNT(*) FROM CORE.FACT_SALES"),
    "payments": ("CORE.FACT_PAYMENTS", "SELECT COUNT(*) FROM CORE.FACT_PAYMENTS"),
    "returns": ("CORE.FACT_RETURNS", "SELECT COUNT(*) FROM CORE.FACT_RETURNS"),
    "reviews": ("CORE.FACT_REVIEWS", "SELECT COUNT(*) FROM CORE.FACT_REVIEWS"),
    "shipments": ("CORE.FACT_SHIPMENTS", "SELECT COUNT(*) FROM CORE.FACT_SHIPMENTS"),
    "inventory": ("CORE.FACT_INVENTORY_SNAPSHOT", "SELECT COUNT(*) FROM CORE.FACT_INVENTORY_SNAPSHOT"),
    "web_traffic": ("CORE.FACT_WEB_TRAFFIC", "SELECT COUNT(*) FROM CORE.FACT_WEB_TRAFFIC"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="Deploy the Student Sales Star Schema and Data Warehouse to Snowflake.")
    parser.add_argument("--project-root", type=Path, default=root)
    parser.add_argument("--prepared-dir", type=Path)
    parser.add_argument(
        "--connection-name",
        default=os.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME", "student_sales"),
        help="Connection name from Snowflake connections.toml.",
    )
    parser.add_argument("--skip-bootstrap", action="store_true", help="Skip warehouse/database/schema creation.")
    parser.add_argument("--keep-stage-files", action="store_true", help="Keep uploaded files after a successful load.")
    return parser.parse_args()


def execute_sql_file(cursor, path: Path) -> None:
    try:
        import sqlparse
    except ImportError as exc:
        raise RuntimeError("Missing sqlparse. Install data_warehouse/requirements.txt") from exc
    source = path.read_text(encoding="utf-8")
    statements = [statement.strip() for statement in sqlparse.split(source) if statement.strip()]
    for index, statement in enumerate(statements, start=1):
        try:
            cursor.execute(statement)
        except Exception as exc:
            raise RuntimeError(f"{path.name}: statement {index} failed") from exc


def scalar(cursor, sql: str):
    cursor.execute(sql)
    return cursor.fetchone()[0]


def file_uri(path: Path) -> str:
    return "file://" + path.resolve().as_posix()


def upload_and_copy(cursor, prepared_dir: Path, manifest_rows: dict[str, int]) -> dict[str, int]:
    loaded_counts: dict[str, int] = {}
    cursor.execute(f"USE WAREHOUSE {WAREHOUSE}")
    cursor.execute(f"USE DATABASE {DATABASE}")
    for dataset in CANONICAL_DATASETS:
        table = STAGE_TABLES[dataset]
        source = prepared_dir / f"{dataset}_silver.csv"
        if not source.exists():
            raise FileNotFoundError(source)
        stage_path = f"@{STAGE}/{dataset}"
        print(f"Uploading {dataset}...", flush=True)
        cursor.execute(f"REMOVE {stage_path}")
        cursor.execute(
            f"PUT '{file_uri(source)}' {stage_path} "
            "AUTO_COMPRESS=TRUE OVERWRITE=TRUE PARALLEL=4"
        )
        cursor.execute(f"TRUNCATE TABLE STAGE.{table}")
        cursor.execute(
            f"COPY INTO STAGE.{table} FROM {stage_path} "
            f"FILE_FORMAT=(FORMAT_NAME='{FILE_FORMAT}') "
            f"PATTERN='.*{dataset}_silver[.]csv([.]gz)?' "
            "FORCE=TRUE ON_ERROR='ABORT_STATEMENT'"
        )
        loaded = int(scalar(cursor, f"SELECT COUNT(*) FROM STAGE.{table}"))
        expected = manifest_rows[dataset]
        if loaded != expected:
            raise ValueError(f"{dataset}: Snowflake loaded {loaded:,}, expected {expected:,}")
        loaded_counts[dataset] = loaded
        print(f"  loaded {loaded:,} rows", flush=True)
    return loaded_counts


def populate_dataset_log(cursor, loaded_counts: dict[str, int], batch_run_id: int) -> None:
    for dataset, source_count in loaded_counts.items():
        target_table, count_sql = SOURCE_TARGETS[dataset]
        target_count = int(scalar(cursor, count_sql))
        status = "PASS" if source_count == target_count else "FAIL"
        cursor.execute(
            """
            INSERT INTO CONTROL.ETL_DATASET_LOG (
                BATCH_RUN_ID, DATASET_NAME, SOURCE_ROW_COUNT, TARGET_TABLE,
                TARGET_ROW_COUNT, STATUS
            ) SELECT %s, %s, %s, %s, %s, %s
            """,
            (batch_run_id, dataset, source_count, target_table, target_count, status),
        )


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    data_warehouse_root = Path(__file__).resolve().parent
    prepared_dir = args.prepared_dir.resolve() if args.prepared_dir else find_latest_prepared_dir(project_root)
    manifest = json.loads((prepared_dir / "manifest.json").read_text(encoding="utf-8"))
    metadata = {item["name"]: item for item in manifest["datasets"]}
    manifest_rows = {name: int(metadata[name]["silver_rows"]) for name in CANONICAL_DATASETS}
    source_batch_id = manifest.get("batch_id")

    sql_root = data_warehouse_root / "sql"
    star_schema_sql = project_root / "star_schema" / "sql" / "star_schema.sql"
    connection = connect(args.connection_name)
    cursor = connection.cursor()
    started_at = utc_now()
    loaded_counts: dict[str, int] = {}
    batch_run_id: int | None = None
    try:
        if not args.skip_bootstrap:
            print("Creating Snowflake warehouse, database and schemas...")
            execute_sql_file(cursor, sql_root / "00_bootstrap.sql")
        cursor.execute(f"USE WAREHOUSE {WAREHOUSE}")
        cursor.execute(f"USE DATABASE {DATABASE}")

        print("Creating control tables...")
        execute_sql_file(cursor, sql_root / "01_control_schema.sql")
        batch_run_id = int(scalar(cursor, "SELECT COALESCE(MAX(BATCH_RUN_ID), 0) + 1 FROM CONTROL.ETL_BATCH_LOG"))
        cursor.execute(f"SET BATCH_RUN_ID = {batch_run_id}")
        cursor.execute(
            """
            INSERT INTO CONTROL.ETL_BATCH_LOG (
                BATCH_RUN_ID, SOURCE_BATCH_ID, SOURCE_MODE, STARTED_AT_UTC,
                STATUS, SOURCE_PATH
            ) SELECT %s, %s, 'PREPARED_CSV', %s, 'RUNNING', %s
            """,
            (batch_run_id, source_batch_id, started_at, str(prepared_dir)),
        )

        print("Creating Star Schema before loading the Data Warehouse...")
        execute_sql_file(cursor, star_schema_sql)

        print("Creating Snowflake staging tables...")
        execute_sql_file(cursor, sql_root / "02_stage_schema.sql")
        loaded_counts = upload_and_copy(cursor, prepared_dir, manifest_rows)

        print("Transforming Silver staging data into dimensions and facts...")
        execute_sql_file(cursor, sql_root / "03_transform.sql")
        populate_dataset_log(cursor, loaded_counts, batch_run_id)

        print("Creating analytical views...")
        execute_sql_file(cursor, sql_root / "04_analytics_views.sql")
        print("Running the Snowflake quality gate...")
        execute_sql_file(cursor, sql_root / "05_quality_checks.sql")

        failed_checks = int(scalar(
            cursor,
            f"SELECT COUNT(*) FROM CONTROL.DQ_RESULTS WHERE BATCH_RUN_ID={batch_run_id} AND STATUS='FAIL'",
        ))
        failed_sync = int(scalar(
            cursor,
            f"SELECT COUNT(*) FROM CONTROL.ETL_DATASET_LOG WHERE BATCH_RUN_ID={batch_run_id} AND STATUS='FAIL'",
        ))
        status = "SUCCESS" if failed_checks == 0 and failed_sync == 0 else "FAILED_DQ"
        cursor.execute(
            """
            UPDATE CONTROL.ETL_BATCH_LOG
            SET COMPLETED_AT_UTC=%s, STATUS=%s, MESSAGE=%s
            WHERE BATCH_RUN_ID=%s
            """,
            (utc_now(), status, f"failed_checks={failed_checks}; failed_sync={failed_sync}", batch_run_id),
        )
        if status != "SUCCESS":
            raise RuntimeError(f"Snowflake quality gate failed: checks={failed_checks}, sync={failed_sync}")

        if not args.keep_stage_files:
            for dataset in CANONICAL_DATASETS:
                cursor.execute(f"REMOVE @{STAGE}/{dataset}")
        print(f"Snowflake deployment completed: {DATABASE}")
        return 0
    except Exception as exc:
        try:
            if batch_run_id is None:
                raise RuntimeError("Batch log was not initialized")
            cursor.execute(
                """
                UPDATE CONTROL.ETL_BATCH_LOG
                SET COMPLETED_AT_UTC=%s, STATUS='FAILED', MESSAGE=%s
                WHERE BATCH_RUN_ID=%s
                """,
                (utc_now(), str(exc)[:3900], batch_run_id),
            )
        except Exception:
            pass
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
