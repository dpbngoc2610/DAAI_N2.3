# Snowflake Star Schema — Student Sales

Thư mục này là sản phẩm **thiết kế mô hình**, được hoàn thiện và kiểm tra trước khi pipeline Data Warehouse được triển khai.

## Phạm vi

- Database đích: `STUDENT_SALES_DW`.
- Schema mô hình: `CORE`.
- 7 dimension và 8 fact.
- 33 quan hệ khóa ngoại.
- SCD Type 2 columns cho 6 dimension nghiệp vụ.
- Unknown member có surrogate key `0`.
- 8 ràng buộc grain tương ứng 8 fact.

Vì Snowflake standard tables không thực thi PK, FK và UNIQUE, các constraint trong DDL là metadata mô hình. Pipeline Data Warehouse kiểm tra chúng bằng các truy vấn quality gate sau khi nạp dữ liệu.

## Thành phần được giữ lại

- `sql/star_schema.sql`: DDL Snowflake cho dimension và fact.
- `docs/dimensional_model.md`: grain, quan hệ và phạm vi mô hình.
- `docs/source_to_target_mapping.md`: ánh xạ Silver → Snowflake CORE.
- `validate_model.py`: kiểm tra DDL trước khi triển khai và kiểm tra live khi có Snowflake connection.
- `output/model_validation_report.md`: kết quả kiểm tra gần nhất.

## Kiểm tra trước khi triển khai

```powershell
python .\star_schema\validate_model.py
```

## Kiểm tra trên Snowflake sau khi triển khai

```powershell
python .\star_schema\validate_model.py --connection-name student_sales
```

Quy trình bắt buộc là:

```text
Thiết kế Star Schema
    → kiểm tra DDL và grain
    → tạo Star Schema trên Snowflake
    → nạp Data Warehouse
    → kiểm thử live và đối soát Silver–Gold
```
