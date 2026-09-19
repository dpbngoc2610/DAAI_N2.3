"""
Xu ly du lieu co ban (Bronze -> Silver) cho file: promotions.csv

Cac buoc kiem tra:
    1. Kiem tra gia tri am o cot 'discount_value', 'min_order_value'
    4. Kiem tra gia tri rieng biet cua 'promo_type', 'promo_channel', 'applicable_category'
    5. Kiem tra du lieu thieu (missing values)
    6. Kiem tra cot 'promo_id' co bao nhieu gia tri, co bi trung hay khong
    7. Xu ly xong thi luu ra thu muc "silver_data"
"""

import os
import pandas as pd

RAW_DIR = "/home/claude/extracted/student_data"
OUT_DIR = "/home/claude/work/silver_data"
os.makedirs(OUT_DIR, exist_ok=True)

FILE_NAME = "promotions.csv"

print("=" * 70)
print(f"XU LY FILE: {FILE_NAME}")
print("=" * 70)

df = pd.read_csv(f"{RAW_DIR}/{FILE_NAME}")
print(f"Shape ban dau: {df.shape}")

# [6] Kiem tra cot promo_id
print("\n[6] Kiem tra cot 'promo_id'")
print(f"    - Tong so dong: {len(df)}")
print(f"    - So gia tri rieng biet: {df['promo_id'].nunique(dropna=True)}")
print(f"    - So dong co promo_id bi trung: {df['promo_id'].duplicated(keep=False).sum()}")

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
for col in ["discount_value", "min_order_value"]:
    n_neg = (df[col] < 0).sum()
    print(f"    - Cot '{col}': {n_neg} gia tri am")

# [4] Kiem tra gia tri rieng biet
print("\n[4] Kiem tra gia tri rieng biet (unique values)")
for col in ["promo_type", "promo_channel", "applicable_category"]:
    print(f"    - Cot '{col}': {df[col].nunique(dropna=True)} gia tri rieng biet -> "
          f"{sorted(df[col].dropna().unique().tolist())}")

# --------------------- XU LY / LAM SACH ---------------------
before = len(df)
df_clean = df.drop_duplicates(subset=["promo_id"], keep="first").copy()
df_clean = df_clean[df_clean["discount_value"] >= 0]
df_clean = df_clean[df_clean["min_order_value"] >= 0]

# Chuan hoa ngay thang va kiem tra tinh hop le
df_clean["start_date"] = pd.to_datetime(df_clean["start_date"], errors="coerce")
df_clean["end_date"] = pd.to_datetime(df_clean["end_date"], errors="coerce")
n_bad_dates = (df_clean["end_date"] < df_clean["start_date"]).sum()
print(f"\n>> So dong co end_date truoc start_date (bat thuong): {n_bad_dates}")

after = len(df_clean)
print(f">> Da loai bo {before - after} dong (trung promo_id / gia tri am).")
print(f">> So dong con lai: {after}")

out_path = f"{OUT_DIR}/promotions.csv"
df_clean.to_csv(out_path, index=False)
print(f"\nDa luu file sach vao: {out_path}")
