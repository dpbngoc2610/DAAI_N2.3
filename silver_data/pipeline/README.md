# Silver data pipeline

Pipeline này tái tạo 15 workbook Silver độc lập từ `excel.rar`.

Mỗi workbook gồm:

- `Silver`: dữ liệu hợp lệ, kiểu dữ liệu Excel chuẩn, metadata truy vết, `data_quality_status` và `warning_codes`.
- `Quality`: số dòng nguồn/Silver/Quarantine/cảnh báo và các quy tắc đã áp dụng.
- `Quarantine`: bản ghi không đạt quy tắc bắt buộc, kèm mã lỗi và dữ liệu nguồn.

Chạy bằng Python đã cài `pandas`, `numpy`, `xlsxwriter` và `openpyxl`:

```powershell
python .\pipeline\run_silver_pipeline.py --output-dir .\outputs\silver_final
```

Cảnh báo nghiệp vụ không bị tự động sửa hoặc loại bỏ. Chúng được giữ trong Silver và gắn mã cảnh báo theo từng dòng để không làm mất dữ liệu nguồn.
