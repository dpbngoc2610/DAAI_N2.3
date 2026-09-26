# Báo cáo kiểm tra pipeline Snowflake

- Thời điểm UTC: `2026-09-26T03:48:26Z`
- Kết luận: `PASS`
- Số kiểm tra thất bại: `0`

| Kiểm tra | Trạng thái | Chi tiết |
| --- | --- | --- |
| SQL bundle structure | PASS | Parsed statement counts: {'00_bootstrap.sql': 10, '01_control_schema.sql': 5, '02_stage_schema.sql': 14, '03_transform.sql': 25, '04_analytics_views.sql': 9, '05_quality_checks.sql': 5, 'star_schema.sql': 18} |
| Staging table coverage | PASS | Stage tables: 12/12 |
| Transform target coverage | PASS | All 16 CORE targets are populated |
| Transform-model consistency | PASS | No obsolete SCD2 or dual-promotion columns |
| Analytical view coverage | PASS | All 7 analytical views are defined |
| Quality-gate coverage | PASS | 35 unique checks are defined |
| Batch audit persistence | PASS | Batch, dataset and DQ history are preserved by BATCH_RUN_ID |
| Deployment order | PASS | Control → Star Schema → Stage → Transform → Views → Quality gate |
| Canonical Silver selection | PASS | Automatic discovery is restricted to .silver_pipeline_work_*/prepared |
| End-to-end gate order | PASS | Raw lineage → Silver baseline → Star model → SQL bundle → Snowflake build → live reconciliation |
