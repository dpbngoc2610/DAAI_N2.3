# Báo cáo kiểm thử Data Warehouse trên Snowflake

- Database: `STUDENT_SALES_DW`
- Thời điểm UTC: `2026-09-26T03:48:25Z`
- Kết luận: `PASS`
- Số kiểm tra thất bại: `0`

| Kiểm tra | Nhóm | Trạng thái | Chi tiết |
| --- | --- | --- | --- |
| Core Star Schema tables | model | PASS | 7 dimensions, 8 facts and 1 bridge exist |
| Analytical views | model | PASS | All 7 analytical views exist |
| Analytical views executable | model | PASS | All views execute |
| Latest ETL batch | pipeline | PASS | run=7, source_batch=SILVER_20260921_122904, status=SUCCESS, mode=PREPARED_CSV |
| Silver-to-Gold row synchronization | completeness | PASS | 12/12 canonical datasets match |
| Snowflake data-quality gate | quality | PASS | checks=35/35; failed=0 |
| net_sales reconciliation | financial | PASS | expected=15,680,869,265.43; Snowflake=15,680,869,265.43 |
| payment_value reconciliation | financial | PASS | expected=15,680,869,265.43; Snowflake=15,680,869,265.43 |
| refund_amount reconciliation | financial | PASS | expected=510,598,506.55; Snowflake=510,598,506.55 |
| shipping_fee reconciliation | financial | PASS | expected=2,809,309.66; Snowflake=2,809,309.66 |
| Net sales across Snowflake layers | cross_layer_consistency | PASS | sales=15,680,869,265.43; orders=15,680,869,265.43; product_view=15,680,869,265.43; promotion_view=15,680,869,265.43 |
| Fact grain uniqueness | model | PASS | All 8 fact grains are unique |
| Promotion bridge integrity | model | PASS | duplicate_sequences=0; invalid_weight_sums=0 |
| Promotion bridge completeness | completeness | PASS | expected=714,875; Snowflake=714,875 |

## Đồng bộ Silver → Snowflake Gold

| Dataset | Source rows | Target table | Target rows | Status |
| --- | ---: | --- | ---: | --- |
| `customers` | 121,930 | `CORE.DIM_CUSTOMER` | 121,930 | PASS |
| `geography` | 39,948 | `CORE.DIM_GEOGRAPHY` | 39,948 | PASS |
| `inventory` | 60,247 | `CORE.FACT_INVENTORY_SNAPSHOT` | 60,247 | PASS |
| `order_items` | 714,669 | `CORE.FACT_SALES` | 714,669 | PASS |
| `orders_enriched` | 646,945 | `CORE.FACT_ORDERS` | 646,945 | PASS |
| `payments` | 646,945 | `CORE.FACT_PAYMENTS` | 646,945 | PASS |
| `products` | 2,412 | `CORE.DIM_PRODUCT` | 2,412 | PASS |
| `promotions` | 50 | `CORE.DIM_PROMOTION` | 50 | PASS |
| `returns` | 39,939 | `CORE.FACT_RETURNS` | 39,939 | PASS |
| `reviews` | 113,551 | `CORE.FACT_REVIEWS` | 113,551 | PASS |
| `shipments` | 566,067 | `CORE.FACT_SHIPMENTS` | 566,067 | PASS |
| `web_traffic` | 3,652 | `CORE.FACT_WEB_TRAFFIC` | 3,652 | PASS |
