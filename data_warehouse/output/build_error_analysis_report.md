# Báo cáo phân tích và kiểm thử lỗi Data Warehouse

- Ngày kiểm tra: `2026-09-26`
- Database: `STUDENT_SALES_DW`
- Batch kiểm thử cuối: `7`
- Kết luận: `PASS`
- Lỗi còn lại sau kiểm thử: `0`

## 1. Sai Python interpreter và thiếu Snowflake Connector

- Triệu chứng: `ModuleNotFoundError: No module named 'snowflake'` khi chạy `python data_warehouse\build_warehouse.py`.
- Nguyên nhân gốc: lệnh `python` trỏ đến Python 3.13 toàn hệ thống, trong khi dependency được cài trong `data_warehouse/.venv`.
- Sửa lỗi: `build_warehouse.py` tự phát hiện interpreter, tự tạo `.venv` nếu thiếu và khởi chạy lại bằng Python của dự án.
- Kết quả: lệnh `python .\data_warehouse\build_warehouse.py --help` và lệnh build trực tiếp đều chạy thành công.

## 2. Đường dẫn dự án có ký tự `&`

- Triệu chứng: interpreter nhận sai đường dẫn và cố mở file tại đoạn kết thúc bằng `\&`.
- Nguyên nhân gốc: cơ chế chuyển process bằng `os.execv` không tương thích ổn định với launcher Windows trong đường dẫn `C:\dpbngoc\DA & AI\...`.
- Sửa lỗi: thay bằng `subprocess.run` với danh sách tham số, không dùng shell và truyền nguyên vẹn đường dẫn.
- Kết quả: file tự chuyển sang `.venv\Scripts\python.exe` và trả đúng exit code.

## 3. Connection mặc định không đúng

- Triệu chứng: chạy file không truyền tham số có thể tìm connection tên `default` thay vì connection dự án.
- Nguyên nhân gốc: giá trị mặc định cũ không đồng bộ với cấu hình `student_sales`.
- Sửa lỗi: connection mặc định đổi thành `student_sales`; vẫn cho phép ghi đè bằng biến môi trường hoặc `--connection-name`.
- Kết quả: build trực tiếp không cần truyền tên connection vẫn kết nối đúng account/user/role.

## 4. Chuỗi chứng chỉ TLS trên Windows

- Triệu chứng: Snowflake Connector không xác minh được certificate chain bằng bundle certifi mặc định.
- Nguyên nhân gốc: certificate cần thiết nằm trong Windows trust store nhưng không có trong certifi.
- Sửa lỗi: hợp nhất certifi với kho `ROOT`/`CA` của Windows và thiết lập `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`; không tắt SSL verification.
- Kết quả: kết nối Snowflake qua HTTPS thành công với 65 certificate bổ sung.

## 5. Phiên kiểm thử không có current database

- Triệu chứng: `Cannot perform SELECT. This session does not have a current database`.
- Nguyên nhân gốc: PAT connection không bảo đảm kế thừa database mặc định trong mọi phiên.
- Sửa lỗi: `validate_model.py` thực thi `USE DATABASE STUDENT_SALES_DW` trước các truy vấn `CORE`.
- Kết quả: kiểm thử Star Schema live đạt 14/14.

## 6. Sai lệch 0,02 ở view khuyến mãi

- Triệu chứng: tổng doanh thu promotion view là `15,680,869,265.45`, trong khi fact là `15,680,869,265.43`.
- Nguyên nhân gốc: view làm tròn từng nhóm promotion trước khi cộng tổng.
- Sửa lỗi: giữ độ chính xác đầy đủ trong các phép `SUM` tiền; chỉ định dạng/làm tròn ở lớp trình bày.
- Kết quả: Fact Sales, Fact Orders, Product View và Promotion View đều bằng `15,680,869,265.43`.

## 7. Installer và cấu hình mẫu chưa portable

- Triệu chứng: installer cũ gắn cứng đường dẫn Python của một tài khoản Windows; file mẫu hướng dẫn password không khớp PAT đang dùng.
- Nguyên nhân gốc: cấu hình phụ thuộc máy phát triển.
- Sửa lỗi: installer tự tìm `python`, bắt buộc Python 3.10+; mẫu connection chuyển sang `PROGRAMMATIC_ACCESS_TOKEN` và `token_file_path` ngoài project.
- Kết quả: PowerShell parse PASS, dependency health PASS và không lưu token trong repository.

## 8. VS Code không tìm thấy named connection

- Triệu chứng: `Invalid connection_name 'student_sales', known ones are []` trong VS Code Debugger.
- Nguyên nhân gốc: process do VS Code tạo không luôn dùng cùng thư mục cấu hình Snowflake với terminal; Connector vì vậy đọc một config location rỗng.
- Sửa lỗi: thêm `snowflake_connection.py` để tìm profile theo `SNOWFLAKE_CONFIG_FILE`, `SNOWFLAKE_HOME`, `%LOCALAPPDATA%\snowflake` và user profile, sau đó truyền trực tiếp các tham số profile vào Connector. Token chỉ được đọc từ file bên ngoài project và không được log.
- Kết quả: mô phỏng Connector có danh sách profile rỗng vẫn kết nối thành công; build trực tiếp hoàn tất với exit code 0.

## Kết quả kiểm thử cuối

| Hạng mục | Kết quả |
| --- | --- |
| Dependency (`pip check`) | PASS — không có dependency hỏng |
| Python compile | PASS |
| PowerShell parse | PASS |
| Lineage nguồn → Silver | PASS — 38 checks |
| Silver offline validation | PASS |
| Star Schema tĩnh | PASS — 11/11 |
| Pipeline SQL | PASS — 10/10 |
| Snowflake deployment | PASS — batch 7 SUCCESS |
| Silver → Gold synchronization | PASS — 12/12 datasets |
| Snowflake DQ gate | PASS — 35/35 |
| Star Schema live | PASS — 14/14 |
| Data Warehouse live | PASS — 14/14 |

## Lưu ý vận hành

- PAT hiện là credential tạm thời và có ngày hết hạn; lỗi xác thực sau khi PAT hết hạn là vấn đề credential bên ngoài code.
- Nếu account không có network policy, Snowflake có thể yêu cầu cấp lại temporary network-policy bypass cho PAT.
- Pipeline đang dùng chiến lược full refresh cho `STAGE` và `CORE`; không chạy đồng thời hai batch trên cùng database.
