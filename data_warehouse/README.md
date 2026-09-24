# Snowflake Data Warehouse — Student Sales

Thư mục này chứa pipeline triển khai Data Warehouse trên Snowflake sau khi Star Schema trong `../star_schema` đã được kiểm tra.

## Kiến trúc Snowflake

| Đối tượng | Tên | Vai trò |
| --- | --- | --- |
| Virtual warehouse | `STUDENT_SALES_ETL_WH` | Compute X-Small, auto-suspend 60 giây |
| Database | `STUDENT_SALES_DW` | Database Data Warehouse |
| Schema | `CONTROL` | Batch log, dataset log, data-quality results |
| Schema | `STAGE` | Silver staging tables và named internal stage |
| Schema | `CORE` | Star Schema dimension và fact |
| Schema | `ANALYTICS` | View phục vụ BI và phân tích |

## Thứ tự triển khai

1. Kiểm tra toàn bộ Silver và tạo baseline.
2. Kiểm tra DDL Star Schema.
3. Tạo Snowflake warehouse, database và schemas.
4. Tạo Star Schema trong `CORE` trước khi nạp dữ liệu.
5. Tạo staging tables.
6. Dùng `PUT` để tải CSV lên named internal stage.
7. Dùng `COPY INTO` để nạp Silver vào `STAGE`.
8. Chuyển đổi dữ liệu sang dimension và fact.
9. Tạo analytical views.
10. Chạy 31 data-quality checks.
11. Đối soát số dòng và tài chính với baseline Silver.
12. Xóa file khỏi internal stage sau khi nạp thành công.

## File chính

- `build_warehouse.py`: triển khai Snowflake theo đúng thứ tự trên.
- `validate_source.py`: kiểm tra Silver và tạo `expected_metrics.json`.
- `validate_warehouse.py`: kiểm thử database Snowflake live.
- `run_snowflake_deploy.ps1`: chạy toàn bộ quy trình.
- `connections.toml.example`: mẫu cấu hình connection, không chứa credential thật.
- `requirements.txt`: Snowflake Python Connector và thư viện cần thiết.
- `sql/00_bootstrap.sql`: warehouse, database, schemas, file format và stage.
- `sql/01_control_schema.sql`: bảng kiểm soát ETL và DQ.
- `sql/02_stage_schema.sql`: 12 staging tables.
- `sql/03_transform.sql`: Silver → dimensions/facts.
- `sql/04_analytics_views.sql`: 6 analytical views.
- `sql/05_quality_checks.sql`: 31 kiểm tra dữ liệu.

## Cài Snowflake CLI và Python Connector

Chạy script cài đặt từ thư mục gốc dự án. Công cụ được cài cô lập tại `data_warehouse/.venv`, không thay đổi Python toàn hệ thống:

```powershell
.\data_warehouse\install_snowflake_tools.ps1
```

Kiểm tra sau khi cài:

```powershell
.\data_warehouse\.venv\Scripts\snow.exe --version
.\data_warehouse\.venv\Scripts\python.exe -c "import snowflake.connector; print(snowflake.connector.__version__)"
```

## Chuẩn bị connection

Sao chép nội dung từ `connections.toml.example` vào file `connections.toml` của Snowflake và đặt tên connection là `student_sales`. Không lưu mật khẩu thật trong project.

## Chạy triển khai

```powershell
.\data_warehouse\run_snowflake_deploy.ps1 -ConnectionName student_sales
```

## Kiểm tra ngoại tuyến không cần Snowflake account

```powershell
python .\data_warehouse\validate_source.py
python .\star_schema\validate_model.py
```

Kết quả ngoại tuyến nằm tại:

- `output/offline_validation_report.md`
- `output/expected_metrics.json`
- `../star_schema/output/model_validation_report.md`

Sau khi triển khai live, báo cáo Snowflake được ghi tại `output/snowflake_validation_report.md`.

## Canonical sources

Gold sử dụng `products`, `promotions` và `web_traffic`. Các biến thể `epd`, `eprom` và `tf` chưa được hợp nhất để tránh đếm trùng.
