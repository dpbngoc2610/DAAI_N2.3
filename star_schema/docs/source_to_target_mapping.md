# Ánh xạ Silver → Snowflake Star Schema

Đích triển khai là `STUDENT_SALES_DW.CORE`; dữ liệu trung gian được nạp vào `STUDENT_SALES_DW.STAGE` bằng named internal stage, `PUT` và `COPY INTO`.

## Ánh xạ bảng

| Silver canonical | Gold target | Loại | Grain/Business key | Quy tắc chính |
| --- | --- | --- | --- | --- |
| `customers` | `dim_customer` | Dimension | `customer_id` | Gắn geography bằng `zip`; đổi `signup_date` thành `signup_date_key` |
| `geography` | `dim_geography` | Dimension | `zip` | Một geography hiện hành cho mỗi ZIP |
| `products` | `dim_product` | Dimension | `product_id` | `price` → `list_price`; `cogs` → `standard_cogs` |
| `promotions` | `dim_promotion` | Dimension | `promo_id` | Ngày bắt đầu/kết thúc đổi thành date key |
| `orders_enriched` | `dim_sales_employee` | Dimension | `sales_employee_id` | Chọn thuộc tính mới nhất theo order date |
| `shipments` | `dim_shipper` | Dimension | `shipper_id` | Chọn thuộc tính mới nhất theo delivery date |
| `order_items` + `orders_enriched` | `fact_sales` | Fact | `order_id`, `source_row_number` | Ghép ngữ cảnh đơn hàng và tính measure ở cấp dòng |
| `orders_enriched` + các fact chi tiết | `fact_orders` | Fact tổng hợp | `order_id` | Tổng hợp sales, payment, shipment và return về một đơn |
| `payments` | `fact_payments` | Fact | `order_id` | Ánh xạ order date/customer từ đơn hàng; một thanh toán cho một đơn trong batch hiện tại |
| `returns` | `fact_returns` | Fact | `return_id` | Ánh xạ product/customer/return date và giữ thông tin hoàn tiền |
| `reviews` | `fact_reviews` | Fact | `review_id` | Ánh xạ customer/product/date |
| `shipments` | `fact_shipments` | Fact | `order_id` | Ánh xạ shipper/date; tính `days_to_deliver` |
| `inventory` | `fact_inventory_snapshot` | Fact snapshot | `snapshot_date`, `product_id` | Một sản phẩm tại một ngày snapshot |
| `web_traffic` | `fact_web_traffic` | Fact | `date`, `traffic_source` | Một nguồn traffic tại một ngày |

## Measure bán hàng

| Measure | Công thức |
| --- | --- |
| `gross_sales_amount` | `quantity * unit_price` |
| `discount_amount` | Giá trị giảm giá từ Silver |
| `net_sales_amount` | `gross_sales_amount - discount_amount` |
| `cogs_amount` | `quantity * dim_product.standard_cogs` |
| `gross_profit_amount` | `net_sales_amount - cogs_amount` |
| `net_revenue_after_returns` | `fact_orders.net_sales_amount - fact_orders.refund_amount` |

## Nguồn bị loại khỏi canonical Gold

| Nguồn | Nguồn canonical thay thế | Lý do |
| --- | --- | --- |
| `epd` | `products` | Biến thể sản phẩm; có nguy cơ nhân đôi dimension |
| `eprom` | `promotions` | Biến thể khuyến mãi; có nguy cơ nhân đôi dimension |
| `tf` | `web_traffic` | Biến thể traffic; có nguy cơ nhân đôi fact |

Các nguồn trên không bị xóa khỏi Silver. Chúng chỉ chưa tham gia Gold cho đến khi có quy tắc hợp nhất và ưu tiên nguồn được phê duyệt.
