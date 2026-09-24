from __future__ import annotations

import argparse
import csv
import json
import os
from datetime import datetime
from pathlib import Path

import xlsxwriter


def width_for(name: str, dtype: str) -> int:
    if name in {"comment", "raw_record_json", "error_details"}:
        return 48
    if name in {"product_name", "promo_name", "review_title", "sales_employee_name", "shipper_name"}:
        return 28
    if name in {"batch_id", "processed_at_utc", "source_file"}:
        return 24
    if name == "record_hash":
        return 19
    if name == "data_quality_status":
        return 19
    if name == "warning_codes":
        return 42
    if dtype == "date":
        return 13
    if dtype == "datetime":
        return 21
    if dtype in {"integer", "money", "decimal", "rate", "percent_points"}:
        return max(12, min(18, len(name) + 3))
    return max(14, min(26, len(name) + 4))


def make_formats(workbook: xlsxwriter.Workbook):
    base = {"font_name": "Arial", "font_size": 10, "font_color": "#1F2937", "valign": "vcenter"}
    return {
        "header": workbook.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#1F4E78", "align": "center", "valign": "vcenter", "text_wrap": True, "bottom": 1, "bottom_color": "#AFC4D6"}),
        "text": workbook.add_format({**base}),
        "integer": workbook.add_format({**base, "num_format": "#,##0"}),
        "id": workbook.add_format({**base, "num_format": "0"}),
        "money": workbook.add_format({**base, "num_format": "#,##0.00"}),
        "decimal": workbook.add_format({**base, "num_format": "#,##0.00"}),
        "rate": workbook.add_format({**base, "num_format": "0.00%"}),
        "percent_points": workbook.add_format({**base, "num_format": "0.0"}),
        "boolean": workbook.add_format({**base, "align": "center"}),
        "date": workbook.add_format({**base, "num_format": "yyyy-mm-dd"}),
        "datetime": workbook.add_format({**base, "num_format": "yyyy-mm-dd hh:mm:ss"}),
        "title": workbook.add_format({"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#1F2937", "bottom": 1, "bottom_color": "#4472C4"}),
        "label": workbook.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#1F2937"}),
        "section": workbook.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#4472C4"}),
        "warning_section": workbook.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#7F6000", "bg_color": "#FFF2CC"}),
        "wrap": workbook.add_format({"font_name": "Arial", "font_size": 10, "font_color": "#1F2937", "valign": "top", "text_wrap": True}),
        "q_header": workbook.add_format({"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#FFFFFF", "bg_color": "#C00000", "align": "center", "valign": "vcenter", "text_wrap": True}),
    }


def parse_datetime(value: str, date_only: bool = False) -> datetime | None:
    if not value:
        return None
    try:
        if date_only:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def write_typed(ws, row: int, col: int, value: str | None, dtype: str, name: str, formats) -> None:
    fmt = formats["id"] if dtype == "integer" and (name.endswith("_id") or name == "source_row_number") else formats.get(dtype, formats["text"])
    if value is None or value == "":
        ws.write_blank(row, col, None, fmt)
    elif dtype == "integer":
        ws.write_number(row, col, int(float(value)), fmt)
    elif dtype in {"money", "decimal", "rate", "percent_points"}:
        ws.write_number(row, col, float(value), fmt)
    elif dtype == "boolean":
        ws.write_boolean(row, col, str(value).strip().lower() in {"true", "1", "yes"}, fmt)
    elif dtype == "date":
        parsed = parse_datetime(str(value), date_only=True)
        ws.write_datetime(row, col, parsed, fmt) if parsed else ws.write_blank(row, col, None, fmt)
    elif dtype == "datetime":
        parsed = parse_datetime(str(value))
        ws.write_datetime(row, col, parsed, fmt) if parsed else ws.write_blank(row, col, None, fmt)
    else:
        ws.write_string(row, col, str(value), fmt)


def build(dataset_name: str, manifest_path: Path, output_dir: Path) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = next(d for d in manifest["datasets"] if d["name"] == dataset_name)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{dataset_name}_silver.xlsx"
    temp_path = output_dir / f".{dataset_name}_silver.tmp.xlsx"
    if temp_path.exists():
        temp_path.unlink()

    workbook = xlsxwriter.Workbook(temp_path, {"constant_memory": True})
    workbook.set_properties({"title": f"Silver data - {dataset_name}", "subject": "Standardized Silver dataset", "author": "Codex"})
    formats = make_formats(workbook)

    silver = workbook.add_worksheet("Silver")
    silver.hide_gridlines(2)
    silver.set_tab_color("#1F4E78")
    silver.freeze_panes(1, min(2, len(meta["silver_columns"])))
    silver.set_row(0, 32)
    for col_idx, col_name in enumerate(meta["silver_columns"]):
        silver.write(0, col_idx, col_name, formats["header"])
        silver.set_column(col_idx, col_idx, width_for(col_name, meta["types"].get(col_name, "text")))

    with Path(meta["silver_csv"]).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row_idx, record in enumerate(reader, start=1):
            for col_idx, col_name in enumerate(meta["silver_columns"]):
                write_typed(silver, row_idx, col_idx, record.get(col_name), meta["types"].get(col_name, "text"), col_name, formats)
            if row_idx % 100000 == 0:
                print(f"[{dataset_name}] wrote {row_idx:,} rows", flush=True)
    silver.autofilter(0, 0, meta["silver_rows"], len(meta["silver_columns"]) - 1)

    quality = workbook.add_worksheet("Quality")
    quality.hide_gridlines(2)
    quality.set_tab_color("#4472C4")
    quality.set_column("A:A", 34)
    quality.set_column("B:B", 72)
    quality.write(1, 0, f"Tóm tắt chất lượng dữ liệu: {dataset_name}", formats["title"])
    quality.write_blank(1, 1, None, formats["title"])
    summary = [
        ("Tệp nguồn", meta["source_file"], "text"),
        ("Mã batch", manifest["batch_id"], "text"),
        ("Thời điểm xử lý UTC", manifest["processed_at_utc"], "datetime"),
        ("Số dòng nguồn", meta["source_rows"], "integer"),
        ("Số dòng Silver", meta["silver_rows"], "integer"),
        ("Số dòng Quarantine", meta["quarantined_rows"], "integer"),
        ("Số dòng có cảnh báo", meta.get("warning_rows", 0), "integer"),
        ("Tỷ lệ giữ lại", meta["silver_rows"] / meta["source_rows"] if meta["source_rows"] else None, "rate"),
        ("Khóa kiểm tra", " + ".join(meta["key_cols"]), "text"),
        ("Số cột nguồn", meta["source_column_count"], "integer"),
        ("Số cột Silver", len(meta["silver_columns"]), "integer"),
    ]
    for i, (label, value, dtype) in enumerate(summary, start=3):
        quality.write(i, 0, label, formats["label"])
        write_typed(quality, i, 1, value, dtype, label, formats)

    rule_header = 14
    quality.write(rule_header, 0, "Quy tắc đã áp dụng", formats["section"])
    quality.write(rule_header, 1, "Mô tả", formats["section"])
    for i, rule in enumerate(meta["rules"], start=rule_header + 1):
        quality.write(i, 0, f"Quy tắc {i - rule_header}", formats["text"])
        quality.write(i, 1, rule, formats["wrap"])
        quality.set_row(i, 24)

    warning_row = rule_header + 1 + len(meta["rules"]) + 1
    if meta.get("warnings"):
        quality.write(warning_row, 0, "Cảnh báo không loại dòng", formats["warning_section"])
        quality.write(warning_row, 1, "Số dòng/giá trị", formats["warning_section"])
        for offset, (key, value) in enumerate(meta["warnings"].items(), start=1):
            quality.write(warning_row + offset, 0, key.replace("_", " "), formats["text"])
            quality.write_number(warning_row + offset, 1, value, formats["integer"])

    quarantine = workbook.add_worksheet("Quarantine")
    quarantine.hide_gridlines(2)
    quarantine.set_tab_color("#C00000")
    quarantine.freeze_panes(1, 0)
    q_columns = ["source_file", "source_row_number", "error_codes", "error_details", "raw_record_json", "batch_id", "processed_at_utc"]
    q_widths = [24, 18, 36, 40, 55, 24, 22]
    for c, (name, width) in enumerate(zip(q_columns, q_widths)):
        quarantine.write(0, c, name, formats["q_header"])
        quarantine.set_column(c, c, width)
    q_records = json.loads(Path(meta["quarantine_json"]).read_text(encoding="utf-8"))
    for r, record in enumerate(q_records, start=1):
        quarantine.set_row(r, 36)
        for c, name in enumerate(q_columns):
            if name == "source_row_number":
                quarantine.write_number(r, c, int(record[name]), formats["id"])
            elif name == "processed_at_utc":
                parsed = parse_datetime(record[name])
                quarantine.write_datetime(r, c, parsed, formats["datetime"])
            elif name in {"error_codes", "error_details", "raw_record_json"}:
                quarantine.write_string(r, c, str(record.get(name, "")), formats["wrap"])
            else:
                quarantine.write_string(r, c, str(record.get(name, "")), formats["text"])

    workbook.close()
    os.replace(temp_path, output_path)
    print(json.dumps({"dataset": dataset_name, "path": str(output_path), "bytes": output_path.stat().st_size, "silver_rows": meta["silver_rows"], "quarantined_rows": meta["quarantined_rows"]}, ensure_ascii=False), flush=True)
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build one Silver workbook from a prepared manifest.")
    parser.add_argument("dataset_name")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    build(args.dataset_name, args.manifest.resolve(), args.output_dir.resolve())
