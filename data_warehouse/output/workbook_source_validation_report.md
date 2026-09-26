# Báo cáo xác minh workbook nguồn Silver

- Kết luận nguồn canonical: `silver_data/outputs/Original_file`
- Kết quả: `15/15 workbook PASS` khi đối chiếu với manifest Silver canonical.
- Các tiêu chí: tên cột, quality columns, số cột, số dòng, kiểu dữ liệu đại diện, warning count và tính nhất quán warning.

| Dataset | Source rows | Silver rows | Quarantine | Warning | Kết quả |
| --- | ---: | ---: | ---: | ---: | --- |
| customers | 121,930 | 121,930 | 0 | 0 | PASS |
| epd | 1,000 | 995 | 5 | 79 | PASS |
| products | 2,412 | 2,412 | 0 | 426 | PASS |
| eprom | 1,000 | 994 | 6 | 0 | PASS |
| promotions | 50 | 50 | 0 | 0 | PASS |
| geography | 39,948 | 39,948 | 0 | 0 | PASS |
| inventory | 60,247 | 60,247 | 0 | 782 | PASS |
| orders_enriched | 646,945 | 646,945 | 0 | 0 | PASS |
| order_items | 714,669 | 714,669 | 0 | 0 | PASS |
| payments | 646,945 | 646,945 | 0 | 0 | PASS |
| returns | 39,939 | 39,939 | 0 | 4,423 | PASS |
| reviews | 113,551 | 113,551 | 0 | 0 | PASS |
| shipments | 566,067 | 566,067 | 0 | 519,276 | PASS |
| tf | 1,000 | 990 | 10 | 0 | PASS |
| web_traffic | 3,652 | 3,652 | 0 | 0 | PASS |

## Loại bỏ `silver_nomalized` khỏi nguồn warehouse

Kiểm tra cấu trúc dừng sớm sau khi 7 dataset đầu tiên (`customers`, `epd`, `products`, `eprom`, `promotions`, `geography`, `inventory`) đều FAIL. Số dòng khớp, nhưng header, quality columns, số cột, kiểu dữ liệu đại diện và quality counts không khớp manifest canonical. Chỉ một lỗi cấu trúc đã đủ chặn nạp warehouse; vì vậy thư mục này không được dùng để tự động triển khai.

Pipeline chỉ tự động chọn `.silver_pipeline_work_*/prepared`. Có thể truyền `--prepared-dir` để kiểm tra một nguồn khác một cách chủ động, nhưng nguồn đó vẫn phải vượt qua toàn bộ quality gate.
