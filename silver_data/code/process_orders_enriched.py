"""
Xu ly du lieu co ban (Bronze -> Silver) cho file: orders_enriched.csv

Cac buoc kiem tra:
    1. Kiem tra gia tri am o cot 'years_experience'
    4. Kiem tra gia tri rieng biet cua cac cot phan loai
       (order_status, payment_method, device_type, order_source, region)
    5. Kiem tra du lieu thieu (missing values)
    6. Kiem tra cot 'order_id' co bao nhieu gia tri, co bi trung hay khong
    7. Xu ly xong thi luu ra thu muc "silver_data"
"""

import os
import pandas as pd

RAW_DIR = "/home/claude/extracted/student_data"
OUT_DIR = "/home/claude/work/silver_data"
os.makedirs(OUT_DIR, exist_ok=True)

FILE_NAME = "orders_enriched.csv"

print("=" * 70)
print(f"XU LY FILE: {FILE_NAME}")
print("=" * 70)

# encoding="utf-8-sig" de xu ly dau BOM o dau file (tieng Viet co dau)
df = pd.read_csv(f"{RAW_DIR}/{FILE_NAME}", encoding="utf-8-sig")
print(f"Shape ban dau: {df.shape}")

# [6] Kiem tra cot order_id
print("\n[6] Kiem tra cot 'order_id'")
print(f"    - Tong so dong: {len(df)}")
print(f"    - So gia tri rieng biet: {df['order_id'].nunique(dropna=True)}")
print(f"    - So dong co order_id bi trung: {df['order_id'].duplicated(keep=False).sum()}")

n_dup_rows = df.duplicated().sum()
print(f"    - So dong trung lap hoan toan: {n_dup_rows}")

# [5] Kiem tra missing values
print("\n[5] Kiem tra du lieu thieu (missing values)")
missing = df.isna().sum()
missing = missing[missing > 0]
if missing.empty:
    print("    - Khong co cot nao bi thieu du lieu.")
else:
    for col, cnt in missing.items():
        print(f"    - Cot '{col}': thieu {cnt} dong ({cnt / len(df) * 100:.2f}%)")

# [1] Kiem tra gia tri am
print("\n[1] Kiem tra gia tri am")
n_neg = (df["years_experience"] < 0).sum()
print(f"    - Cot 'years_experience': {n_neg} gia tri am")

# [4] Kiem tra gia tri rieng biet
print("\n[4] Kiem tra gia tri rieng biet (unique values)")
for col in ["order_status", "payment_method", "device_type", "order_source", "region"]:
    print(f"    - Cot '{col}': {df[col].nunique(dropna=True)} gia tri rieng biet")

# --------------------- XU LY / LAM SACH ---------------------
before = len(df)
df_clean = df.drop_duplicates(subset=["order_id"], keep="first").copy()
df_clean = df_clean.dropna(subset=["order_id", "order_date", "customer_id"])
df_clean["order_date"] = pd.to_datetime(df_clean["order_date"], errors="coerce")
n_bad_date = df_clean["order_date"].isna().sum()
print(f"\n>> So dong co order_date khong hop le sau khi convert: {n_bad_date}")
df_clean = df_clean.dropna(subset=["order_date"])
after = len(df_clean)

print(f">> Da loai bo {before - after} dong (trung order_id / thieu du lieu bat buoc / ngay khong hop le).")
print(f">> So dong con lai: {after}")

out_path = f"{OUT_DIR}/orders_enriched.csv"
df_clean.to_csv(out_path, index=False)
print(f"\nDa luu file sach vao: {out_path}")
