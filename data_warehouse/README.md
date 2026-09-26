# Snowflake Data Warehouse — Student Sales

Thư mục này chứa pipeline triển khai Data Warehouse trên Snowflake sau khi Star Schema trong `../star_schema` đã được kiểm tra.

## Kiến trúc Snowflake

| Đối tượng | Tên | Vai trò |
| --- | --- | --- |
| Virtual warehouse | `STUDENT_SALES_ETL_WH` | Compute X-Small, auto-suspend 60 giây |
| Database | `STUDENT_SALES_DW` | Database Data Warehouse |
| Schema | `CONTROL` | Batch log, dataset log, data-quality results |
| Schema | `STAGE` | Silver staging tables và named internal stage |
| Schema | `CORE` | 7 dimension, 8 fact và promotion bridge |
| Schema | `ANALYTICS` | View phục vụ BI và phân tích |

## Thứ tự triển khai

1. Kiểm tra lineage từ 15 file CSV gốc đến Silver canonical; dựng lại Silver để chứng minh kết quả tái lập.
2. Kiểm tra 12 Silver canonical dùng cho warehouse và tạo baseline.
3. Kiểm tra DDL Star Schema.
4. Tạo Snowflake warehouse, database và schemas.
5. Tạo Star Schema trong `CORE` trước khi nạp dữ liệu.
6. Tạo 12 staging tables.
7. Dùng `PUT` để tải CSV lên named internal stage.
8. Dùng `COPY INTO` để nạp Silver vào `STAGE`.
9. Chuyển đổi dữ liệu sang dimension, fact và promotion bridge.
10. Tạo 7 analytical views.
11. Chạy 35 data-quality checks.
12. Đối soát số dòng và tài chính với baseline Silver.
13. Xóa file khỏi internal stage sau khi nạp thành công.

## File chính

- `build_warehouse.py`: triển khai Snowflake theo đúng thứ tự trên.
- `snowflake_connection.py`: tìm profile Snowflake ổn định giữa terminal/VS Code và cấu hình TLS dùng chung.
- `build_windows_ca_bundle.py`: dùng kho chứng chỉ Windows cho kết nối TLS, không tắt SSL verification.
- `validate_lineage.py`: kiểm tra file gốc → Silver, quyết định nguồn canonical và khả năng tái lập.
- `validate_source.py`: kiểm tra Silver và tạo `expected_metrics.json`.
- `validate_pipeline.py`: kiểm tra tĩnh toàn bộ SQL bundle và thứ tự triển khai.
- `validate_warehouse.py`: kiểm thử database Snowflake live.
- `run_snowflake_deploy.ps1`: chạy toàn bộ quy trình.
- `connections.toml.example`: mẫu cấu hình connection, không chứa credential thật.
- `requirements.txt`: Snowflake Python Connector và thư viện cần thiết.
- `docs/Huong_dan_Data_Warehouse_Snowflake.docx`: tài liệu Word thô về quy trình, kết quả đối soát và cách triển khai.
- `sql/00_bootstrap.sql`: warehouse, database, schemas, file format và stage.
- `sql/01_control_schema.sql`: bảng kiểm soát ETL và DQ.
- `sql/02_stage_schema.sql`: 12 staging tables.
- `sql/03_transform.sql`: Silver → dimensions/facts.
- `sql/04_analytics_views.sql`: 7 analytical views, gồm phân bổ hiệu quả promotion.
- `sql/05_quality_checks.sql`: 35 kiểm tra grain, khóa, bridge, business rules và tài chính.

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

Sao chép nội dung từ `connections.toml.example` vào file `connections.toml` của Snowflake và đặt tên connection là `student_sales`. Dùng PAT lưu ngoài project; không lưu password hoặc nội dung token trong repository.

Khi chạy từ VS Code, code tự tìm `config.toml`/`connections.toml` ở `SNOWFLAKE_CONFIG_FILE`, `SNOWFLAKE_HOME`, `%LOCALAPPDATA%\snowflake` và thư mục Snowflake trong user profile. Vì vậy debugger không còn phụ thuộc vào việc kế thừa đúng biến môi trường từ terminal.

## Chạy triển khai

Lệnh khuyến nghị bên dưới sẽ tự tạo lại `.venv` và cài dependency nếu môi trường chưa tồn tại:

```powershell
.\data_warehouse\run_snowflake_deploy.ps1 -ConnectionName student_sales
```

Nếu chỉ muốn chạy trực tiếp file build, dùng đúng Python trong môi trường dự án. Connection mặc định là `student_sales` và chứng chỉ TLS Windows được cấu hình tự động:

```powershell
.\data_warehouse\.venv\Scripts\python.exe .\data_warehouse\build_warehouse.py
```

## Kiểm tra ngoại tuyến không cần Snowflake account

```powershell
python .\data_warehouse\validate_source.py
python .\data_warehouse\validate_lineage.py --rebuild
python .\star_schema\validate_model.py
```

Kết quả ngoại tuyến nằm tại:

- `output/offline_validation_report.md`
- `output/lineage_validation_report.md`
- `output/workbook_source_validation_report.md`
- `output/pipeline_validation_report.md`
- `output/expected_metrics.json`
- `../star_schema/output/model_validation_report.md`

Sau khi triển khai live, báo cáo Snowflake được ghi tại `output/snowflake_validation_report.md`.

## Chiến lược nạp

- CORE và STAGE dùng full refresh cho mỗi batch canonical.
- Business dimensions dùng Type 1 vì Silver chỉ có một trạng thái hiện hành cho mỗi natural key.
- `CONTROL.ETL_BATCH_LOG`, `ETL_DATASET_LOG` và `DQ_RESULTS` giữ lịch sử theo `BATCH_RUN_ID` qua nhiều lần chạy.
- `BRIDGE_SALES_PROMOTION` tách `promo_id` và `promo_id_2`; allocation weight của mỗi sales line luôn tổng bằng 1.

## Canonical sources

Gold sử dụng `products`, `promotions` và `web_traffic` theo dependency thực tế của dữ liệu dự án:

- `products` bao phủ toàn bộ `product_id` trong `order_items`; `epd` là tập con 995 khóa nhưng có 6.013 xung đột thuộc tính, nên chỉ dùng đối chiếu.
- `promotions` bao phủ toàn bộ 50 promotion được `order_items` tham chiếu; 994 khóa `eprom` không giao với namespace khóa này, nên không tự ý hợp nhất.
- 990 grain `(date, traffic_source)` của `tf` đều đã có trong `web_traffic`; union sẽ đếm đôi, nên `tf` chỉ dùng kiểm tra biến thể.
- Có 16 cặp `(order_id, product_id)` bị lặp trên 32 sales line; 4 return và 2 review nằm trên các cặp mơ hồ. Vì vậy return/review giữ khóa order + product và không bị gán sai vào một sales line cụ thể.

Mặc định pipeline chỉ tự động chọn thư mục `.silver_pipeline_work_*/prepared`. Nguồn khác chỉ được dùng khi người vận hành truyền rõ `--prepared-dir`.
