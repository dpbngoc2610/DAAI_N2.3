from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent
SILVER_DIR = PIPELINE_DIR.parent


def run(command: list[str]) -> None:
    print("RUN", " ".join(command), flush=True)
    subprocess.run(command, check=True)


def safe_reset_work_dir(work_dir: Path) -> None:
    resolved = work_dir.resolve()
    root = SILVER_DIR.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"Work directory must be inside {root}: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild and verify all 15 standardized Silver workbooks.")
    parser.add_argument("--archive", type=Path, default=SILVER_DIR / "excel.rar")
    parser.add_argument("--work-dir", type=Path, default=SILVER_DIR / ".silver_pipeline_work")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--keep-work", action="store_true")
    args = parser.parse_args()

    archive = args.archive.resolve()
    work_dir = args.work_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive)

    safe_reset_work_dir(work_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run(["tar", "-xf", str(archive), "-C", str(work_dir)])

    source_dir = work_dir / "excel"
    prepared_dir = work_dir / "prepared"
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Archive did not contain expected excel directory: {source_dir}")

    run([
        sys.executable,
        str(PIPELINE_DIR / "prepare_silver.py"),
        "--source-dir", str(source_dir),
        "--prepared-dir", str(prepared_dir),
    ])

    manifest_path = prepared_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for dataset in manifest["datasets"]:
        run([
            sys.executable,
            str(PIPELINE_DIR / "build_silver_workbook.py"),
            dataset["name"],
            "--manifest", str(manifest_path),
            "--output-dir", str(output_dir),
        ])

    report_path = output_dir / "verification_report.json"
    run([
        sys.executable,
        str(PIPELINE_DIR / "verify_silver_outputs.py"),
        "--manifest", str(manifest_path),
        "--output-dir", str(output_dir),
        "--report", str(report_path),
    ])

    print(json.dumps({
        "status": "complete",
        "dataset_count": len(manifest["datasets"]),
        "output_dir": str(output_dir),
        "verification_report": str(report_path),
    }, ensure_ascii=False, indent=2), flush=True)

    if not args.keep_work:
        shutil.rmtree(work_dir)


if __name__ == "__main__":
    main()
