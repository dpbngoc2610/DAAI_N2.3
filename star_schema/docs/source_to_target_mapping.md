# Ánh xạ Silver sang Snowflake Star Schema

Đích triển khai là `STUDENT_SALES_DW.CORE`. Dữ liệu canonical được đưa qua `STUDENT_SALES_DW.STAGE` trước khi chuyển thành dimension, fact và bridge.

## Ánh xạ bảng

| Silver canonical | Gold target | Loại | Grain hoặc business key | Quy tắc chính |
| --- | --- | --- | --- | --- |
| `customers` | `dim_customer` | Dimension Type 1 | `customer_id` | Giữ home ZIP/city và signup date như thuộc tính |
| `geography` | `dim_geography` | Dimension Type 1 | `zip` | Một bản ghi cho mỗi ZIP |
| `products` | `dim_product` | Dimension Type 1 | `product_id` | `price` thành `list_price`; `cogs` thành `standard_cogs`, giữ 6 số lẻ |
| `promotions` | `dim_promotion` | Dimension Type 1 | `promo_id` | Giữ start/end date như thuộc tính dimension |
| `orders_enriched` | `dim_sales_employee` | Dimension Type 1 | `sales_employee_id` | Chọn bản ghi mới nhất; dữ liệu nguồn không có thay đổi thuộc tính theo ID |
| `shipments` | `dim_shipper` | Dimension Type 1 | `shipper_id` | Chọn bản ghi mới nhất và giữ cả số điện thoại |
| `order_items + orders_enriched` | `fact_sales` | Transaction fact | `order_id + source_row_number` | Ghép context đơn hàng và tính measure dòng bán hàng |
| `order_items + fact_sales` | `bridge_sales_promotion` | Bridge | `sales_key + promotion_sequence` | Tách promo 1/2 thành dòng; thêm `NO_PROMO`; phân bổ đều khi có hai promotion |
| `orders_enriched + fact chi tiết` | `fact_orders` | Order aggregate fact | `order_id` | Tổng hợp sales, payment, shipment và refund về một đơn |
| `payments + orders_enriched` | `fact_payments` | Transaction fact | `order_id` | Gắn order date và customer |
| `returns + orders_enriched` | `fact_returns` | Event fact | `return_id` | Gắn order date, return date, product và customer |
| `reviews + orders_enriched` | `fact_reviews` | Event fact | `review_id` | Gắn order date, review date, product và customer |
| `shipments + orders_enriched` | `fact_shipments` | Event fact | `order_id` | Gắn ba date roles, customer, geography, shipper; tính thời gian giao |
| `inventory` | `fact_inventory_snapshot` | Periodic snapshot | `snapshot_date + product_id` | Không nạp lại mô tả product/year/month dẫn xuất |
| `web_traffic` | `fact_web_traffic` | Periodic fact | `date + traffic_source` | Một nguồn traffic tại một ngày |

## Measure và công thức

| Measure | Công thức |
| --- | --- |
| `gross_sales_amount` | `quantity * unit_price` |
| `net_sales_amount` | `gross_sales_amount - discount_amount` |
| `cogs_amount` | `quantity * dim_product.standard_cogs`, làm tròn ở fact |
| `gross_profit_amount` | `net_sales_amount - cogs_amount` |
| `net_revenue_after_returns` | `fact_orders.net_sales_amount - fact_orders.refund_amount` |
| `allocation_weight` | `1 / số promotion trên sales line`; `NO_PROMO = 1` |

## Canonical source policy

| Nguồn biến thể | Nguồn canonical | Trạng thái |
| --- | --- | --- |
| `epd` | `products` | Không nạp Gold để tránh trùng product |
| `eprom` | `promotions` | Không nạp Gold để tránh trùng promotion |
| `tf` | `web_traffic` | Không nạp Gold để tránh trùng traffic |

Các file biến thể vẫn nằm tại Silver và chỉ được dùng khi có quy tắc hợp nhất nguồn rõ ràng.
