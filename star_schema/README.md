# Snowflake Star Schema cho Student Sales

Thư mục này chứa thiết kế dimensional model hoàn chỉnh, được kiểm tra trước khi Data Warehouse Snowflake được triển khai.

## Phạm vi mô hình

- 7 conformed dimensions.
- 8 fact tables với grain được khai báo rõ.
- 1 bridge xử lý nhiều khuyến mãi trên một sales line.
- 33 quan hệ khóa ngoại từ fact/bridge đến dimension hoặc fact trung tâm.
- 65 PK, FK và UNIQUE metadata constraints.
- Dimension Type 1 phù hợp với Silver snapshot và cơ chế full refresh.
- Unknown member có surrogate key `0`.

## File chính

- `sql/star_schema.sql`: DDL Snowflake cho dimension, fact và bridge.
- `docs/dimensional_model.md`: quyết định thiết kế, grain và sơ đồ quan hệ.
- `docs/source_to_target_mapping.md`: ánh xạ Silver sang CORE.
- `docs/Huong_dan_Star_Schema.docx`: tài liệu Word thô mô tả quy trình và thiết kế cuối cùng.
- `validate_model.py`: kiểm tra DDL và kiểm tra live khi có connection.
- `output/model_validation_report.md`: báo cáo kiểm tra gần nhất.

## Kiểm tra

```powershell
.\data_warehouse\.venv\Scripts\python.exe .\star_schema\validate_model.py
```

Khi đã cấu hình Snowflake connection:

```powershell
.\data_warehouse\.venv\Scripts\python.exe .\star_schema\validate_model.py --connection-name student_sales
```

Trình tự bắt buộc: kiểm tra lineage file gốc → Silver canonical, kiểm tra Silver, kiểm tra Star Schema, tạo mô hình CORE, nạp Data Warehouse, chạy quality gate và đối soát Silver-Gold.

Mô hình chỉ dùng `products`, `promotions` và `web_traffic` làm nguồn nghiệp vụ canonical. `epd`, `eprom` và `tf` được giữ ở lớp kiểm thử lineage để phát hiện xung đột hoặc đếm trùng, không được union trực tiếp vào dimension/fact.
