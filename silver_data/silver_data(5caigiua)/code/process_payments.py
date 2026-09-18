"""
Xu ly du lieu co ban (Bronze -> Silver) cho file: payments.csv

Cac buoc kiem tra:
    1. Kiem tra gia tri am o cot 'payment_value', 'installments'
    4. Kiem tra gia tri rieng biet cua cot 'payment_method'
    5. Kiem tra du lieu thieu (missing values)
    7. Xu ly xong thi luu ra thu muc "silver_data"
"""

import os
import pandas as pd

RAW_DIR = "/home/claude/extracted/student_data"
OUT_DIR = "/home/claude/work/silver_data"
os.makedirs(OUT_DIR, exist_ok=True)

FILE_NAME = "payments.csv"

print("=" * 70)
print(f"XU LY FILE: {FILE_NAME}")
print("=" * 70)

df = pd.read_csv(f"{RAW_DIR}/{FILE_NAME}")
print(f"Shape ban dau: {df.shape}")

# Kiem tra trung lap hoan toan
n_dup_rows = df.duplicated().sum()
print(f"\n    - So dong trung lap hoan toan: {n_dup_rows}")

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
for col in ["payment_value", "installments"]:
    n_neg = (df[col] < 0).sum()
    print(f"    - Cot '{col}': {n_neg} gia tri am")

# [4] Kiem tra gia tri rieng biet
print("\n[4] Kiem tra gia tri rieng biet (unique values)")
print(f"    - Cot 'payment_method': {df['payment_method'].nunique(dropna=True)} gia tri rieng biet")
print(f"      Danh sach: {sorted(df['payment_method'].dropna().unique().tolist())}")

# --------------------- XU LY / LAM SACH ---------------------
before = len(df)
df_clean = df.drop_duplicates().copy()
df_clean = df_clean.dropna(subset=["order_id", "payment_value"])
df_clean = df_clean[df_clean["payment_value"] >= 0]
df_clean = df_clean[df_clean["installments"] >= 1]
after = len(df_clean)

print(f"\n>> Da loai bo {before - after} dong (trung / thieu du lieu / gia tri am hoac installments < 1).")
print(f">> So dong con lai: {after}")

out_path = f"{OUT_DIR}/payments.csv"
df_clean.to_csv(out_path, index=False)
print(f"\nDa luu file sach vao: {out_path}")
