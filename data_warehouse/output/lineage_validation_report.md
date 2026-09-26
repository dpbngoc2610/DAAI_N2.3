# Báo cáo kiểm thử lineage File gốc → Silver → Star Schema/Data Warehouse

- Thời điểm UTC: `2026-09-26T02:58:11Z`
- Silver canonical: `C:\dpbngoc\DA & AI\DAAI_N2.3\silver_data\.silver_pipeline_work_01a0c3da\prepared`
- Nguồn CSV gốc: `C:\dpbngoc\DA & AI\DAAI_N2.3\silver_data\.silver_pipeline_work_01a0c3da\excel`
- Kết luận: `PASS`
- Số kiểm tra: `38`
- Số lỗi: `0`

## Quyết định nguồn canonical

- `products` là nguồn DIM_PRODUCT; `epd` chỉ dùng đối chiếu vì là tập con và có xung đột thuộc tính.
- `promotions` là nguồn DIM_PROMOTION vì bao phủ toàn bộ promotion mà order_items tham chiếu; `eprom` không cùng namespace khóa.
- `web_traffic` là nguồn FACT_WEB_TRAFFIC; `tf` là tập con trùng grain và có thêm nhãn variant nên không được union để tránh đếm đôi.
- `returns` và `reviews` không ép ánh xạ đến một sales line khi `(order_id, product_id)` không duy nhất.

## Kết quả

| Kiểm tra | Trạng thái | Chi tiết |
| --- | --- | --- |
| `canonical_prepared_path` | PASS | C:\dpbngoc\DA & AI\DAAI_N2.3\silver_data\.silver_pipeline_work_01a0c3da\prepared |
| `manifest_dataset_coverage` | PASS | datasets=15/15 |
| `raw_source_file_coverage` | PASS | source_dir=C:\dpbngoc\DA & AI\DAAI_N2.3\silver_data\.silver_pipeline_work_01a0c3da\excel |
| `row_lineage:customers` | PASS | source=121,930; silver=121,930; quarantine=0; source_file=['customers.csv'] |
| `row_lineage:epd` | PASS | source=1,000; silver=995; quarantine=5; source_file=['epd.csv'] |
| `row_lineage:products` | PASS | source=2,412; silver=2,412; quarantine=0; source_file=['products.csv'] |
| `row_lineage:eprom` | PASS | source=1,000; silver=994; quarantine=6; source_file=['eprom.csv'] |
| `row_lineage:promotions` | PASS | source=50; silver=50; quarantine=0; source_file=['promotions.csv'] |
| `row_lineage:geography` | PASS | source=39,948; silver=39,948; quarantine=0; source_file=['geography.csv'] |
| `row_lineage:inventory` | PASS | source=60,247; silver=60,247; quarantine=0; source_file=['inventory.csv'] |
| `row_lineage:orders_enriched` | PASS | source=646,945; silver=646,945; quarantine=0; source_file=['orders_enriched.csv'] |
| `row_lineage:order_items` | PASS | source=714,669; silver=714,669; quarantine=0; source_file=['order_items.csv'] |
| `row_lineage:payments` | PASS | source=646,945; silver=646,945; quarantine=0; source_file=['payments.csv'] |
| `row_lineage:returns` | PASS | source=39,939; silver=39,939; quarantine=0; source_file=['returns.csv'] |
| `row_lineage:reviews` | PASS | source=113,551; silver=113,551; quarantine=0; source_file=['reviews.csv'] |
| `row_lineage:shipments` | PASS | source=566,067; silver=566,067; quarantine=0; source_file=['shipments_realistic.csv'] |
| `row_lineage:tf` | PASS | source=1,000; silver=990; quarantine=10; source_file=['tf.csv'] |
| `row_lineage:web_traffic` | PASS | source=3,652; silver=3,652; quarantine=0; source_file=['web_traffic.csv'] |
| `canonical_product_coverage` | PASS | order-item products missing from products=0 |
| `epd_is_validation_variant` | PASS | epd-only keys=0; overlap=995; attribute conflicts=6013 |
| `canonical_promotion_coverage` | PASS | order-item promotions missing from promotions=0; referenced only by eprom=0 |
| `tf_is_validation_variant` | PASS | tf-only grain keys=0; overlap=990; variant rows=990 |
| `returns_reviews_grain_safety` | PASS | ambiguous order-product pairs=16; rows=32; returns affected=4; reviews affected=2; therefore facts retain order+product references and are not forced to a sales-line key |
| `deterministic_rebuild:customers` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=121,930; rebuilt=121,930 |
| `deterministic_rebuild:epd` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=995; rebuilt=995 |
| `deterministic_rebuild:products` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=2,412; rebuilt=2,412 |
| `deterministic_rebuild:eprom` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=994; rebuilt=994 |
| `deterministic_rebuild:promotions` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=50; rebuilt=50 |
| `deterministic_rebuild:geography` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=39,948; rebuilt=39,948 |
| `deterministic_rebuild:inventory` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=60,247; rebuilt=60,247 |
| `deterministic_rebuild:orders_enriched` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=646,945; rebuilt=646,945 |
| `deterministic_rebuild:order_items` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=714,669; rebuilt=714,669 |
| `deterministic_rebuild:payments` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=646,945; rebuilt=646,945 |
| `deterministic_rebuild:returns` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=39,939; rebuilt=39,939 |
| `deterministic_rebuild:reviews` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=113,551; rebuilt=113,551 |
| `deterministic_rebuild:shipments` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=566,067; rebuilt=566,067 |
| `deterministic_rebuild:tf` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=990; rebuilt=990 |
| `deterministic_rebuild:web_traffic` | PASS | manifest=True; silver=True; quarantine=True; stable rows compared: reference=3,652; rebuilt=3,652 |

## Chỉ số phát hiện từ dữ liệu dự án

- `epd_product_overlap`: `995`
- `epd_product_attribute_conflicts`: `6,013`
- `eprom_promotion_overlap`: `0`
- `tf_web_overlap`: `990`
- `duplicate_order_product_pairs`: `16`
- `duplicate_order_item_rows`: `32`
- `returns_on_ambiguous_pairs`: `4`
- `reviews_on_ambiguous_pairs`: `2`
