# Báo cáo kiểm tra Silver trước khi nạp Snowflake

- Batch: `SILVER_20260921_122904`
- Kết luận: `PASS`
- Số lỗi: `0`

## Số dòng và grain

| Dataset | Manifest | Thực tế | Grain trùng | Thiếu key | Rule lỗi | Warning | Status |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `customers` | 121,930 | 121,930 | 0 | 0 | 0 | 0 | PASS |
| `geography` | 39,948 | 39,948 | 0 | 0 | 0 | 0 | PASS |
| `products` | 2,412 | 2,412 | 0 | 0 | 0 | 426 | PASS |
| `promotions` | 50 | 50 | 0 | 0 | 0 | 0 | PASS |
| `orders_enriched` | 646,945 | 646,945 | 0 | 0 | 0 | 0 | PASS |
| `order_items` | 714,669 | 714,669 | 0 | 0 | 0 | 0 | PASS |
| `payments` | 646,945 | 646,945 | 0 | 0 | 0 | 0 | PASS |
| `returns` | 39,939 | 39,939 | 0 | 0 | 0 | 4,423 | PASS |
| `reviews` | 113,551 | 113,551 | 0 | 0 | 0 | 0 | PASS |
| `shipments` | 566,067 | 566,067 | 0 | 0 | 0 | 519,276 | PASS |
| `inventory` | 60,247 | 60,247 | 0 | 0 | 0 | 782 | PASS |
| `web_traffic` | 3,652 | 3,652 | 0 | 0 | 0 | 0 | PASS |

## Referential integrity giữa các nguồn Silver

| Quan hệ | Bản ghi không khớp | Status |
| --- | ---: | --- |
| `order_items.order_id->orders_enriched.order_id` | 0 | PASS |
| `order_items.product_id->products.product_id` | 0 | PASS |
| `order_items.promo_id->promotions.promo_id` | 0 | PASS |
| `order_items.promo_id_2->promotions.promo_id` | 0 | PASS |
| `orders_enriched.customer_id->customers.customer_id` | 0 | PASS |
| `orders_enriched.zip->geography.zip` | 0 | PASS |
| `payments.order_id->orders_enriched.order_id` | 0 | PASS |
| `returns.order_id->orders_enriched.order_id` | 0 | PASS |
| `returns.product_id->products.product_id` | 0 | PASS |
| `reviews.order_id->orders_enriched.order_id` | 0 | PASS |
| `reviews.product_id->products.product_id` | 0 | PASS |
| `reviews.customer_id->customers.customer_id` | 0 | PASS |
| `shipments.order_id->orders_enriched.order_id` | 0 | PASS |
| `inventory.product_id->products.product_id` | 0 | PASS |

## Đồng bộ thuộc tính giữa các nguồn

| Quy tắc | Bản ghi không khớp | Status |
| --- | ---: | --- |
| `payments.payment_method=orders_enriched.payment_method` | 0 | PASS |
| `reviews.customer_id=orders_enriched.customer_id` | 0 | PASS |

## Đồng bộ thứ tự cột CSV → Snowflake staging

| Dataset | Stage table | Silver columns | Stage columns | Status |
| --- | --- | ---: | ---: | --- |
| `customers` | `STG_CUSTOMERS` | 14 | 14 | PASS |
| `geography` | `STG_GEOGRAPHY` | 11 | 11 | PASS |
| `products` | `STG_PRODUCTS` | 15 | 15 | PASS |
| `promotions` | `STG_PROMOTIONS` | 17 | 17 | PASS |
| `orders_enriched` | `STG_ORDERS_ENRICHED` | 24 | 24 | PASS |
| `order_items` | `STG_ORDER_ITEMS` | 14 | 14 | PASS |
| `payments` | `STG_PAYMENTS` | 11 | 11 | PASS |
| `returns` | `STG_RETURNS` | 14 | 14 | PASS |
| `reviews` | `STG_REVIEWS` | 14 | 14 | PASS |
| `shipments` | `STG_SHIPMENTS` | 29 | 29 | PASS |
| `inventory` | `STG_INVENTORY` | 24 | 24 | PASS |
| `web_traffic` | `STG_WEB_TRAFFIC` | 15 | 15 | PASS |

## Baseline tài chính dùng để đối soát Snowflake

- `gross_sales`: `16,430,476,585.53`
- `discount_amount`: `749,607,320.10`
- `net_sales`: `15,680,869,265.43`
- `payment_value`: `15,680,869,265.43`
- `refund_amount`: `510,598,506.55`
- `shipping_fee`: `2,809,309.66`

## Baseline bridge khuyến mãi

- Liên kết promotion từ Silver: `276,522`
- Sales line có promotion thứ hai: `206`
- Số dòng bridge kỳ vọng, gồm NO_PROMO: `714,875`
