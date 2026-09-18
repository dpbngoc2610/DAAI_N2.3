"""
Xu ly du lieu co ban (Bronze -> Silver) cho file: products.csv

Cac buoc kiem tra:
    1. Kiem tra gia tri am o cot 'price', 'cogs'
    2. Kiem tra cot 'category' xem co nhung gia tri nao
    3. Kiem tra cot 'product_name' co bao nhieu gia tri (unique)
    4. Kiem tra cac gia tri rieng biet cua cac cot dinh danh (category, segment, size, color)
    5. Kiem tra cot 'price' co du lieu thieu (missing) hay khong
    6. Kiem tra cot 'product_id' co bao nhieu gia tri, co bi trung (duplicate) hay khong
    7. Xu ly xong thi luu ra thu muc "silver_data"
"""

import os
import pandas as pd

RAW_DIR = "/home/claude/extracted/student_data"
OUT_DIR = "/home/claude/work/silver_data"
os.makedirs(OUT_DIR, exist_ok=True)

FILE_NAME = "products.csv"

print("=" * 70)
print(f"XU LY FILE: {FILE_NAME}")
print("=" * 70)

df = pd.read_csv(f"{RAW_DIR}/{FILE_NAME}")
print(f"Shape ban dau: {df.shape}")

# [6] Kiem tra cot product_id
print("\n[6] Kiem tra cot 'product_id'")
print(f"    - Tong so dong: {len(df)}")
print(f"    - So gia tri rieng biet: {df['product_id'].nunique(dropna=True)}")
print(f"    - So dong co product_id bi trung: {df['product_id'].duplicated(keep=False).sum()}")

# Kiem tra trung lap hoan toan
n_dup_rows = df.duplicated().sum()
print(f"    - So dong trung lap hoan toan: {n_dup_rows}")

# [2] Kiem tra cot category
print("\n[2] Kiem tra cot 'category'")
print(f"    - Cac gia tri hien co: {sorted(df['category'].dropna().unique().tolist())}")

# [3] Kiem tra cot product_name
print("\n[3] Kiem tra cot 'product_name'")
print(f"    - So gia tri (unique) trong 'product_name': {df['product_name'].nunique()}")
print(f"    - So dong: {len(df)}")

# [4] Kiem tra cac gia tri rieng biet cua cac cot dinh danh
print("\n[4] Kiem tra gia tri rieng biet (unique values)")
for col in ["category", "segment", "size", "color"]:
    print(f"    - Cot '{col}': {df[col].nunique(dropna=True)} gia tri rieng biet")

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
for col in ["price", "cogs"]:
    n_neg = (df[col] < 0).sum()
    print(f"    - Cot '{col}': {n_neg} gia tri am")

# --------------------- XU LY / LAM SACH ---------------------
before = len(df)
df_clean = df.drop_duplicates(subset=["product_id"], keep="first").copy()
df_clean = df_clean.dropna(subset=["price"])          # price la cot bat buoc
df_clean = df_clean[df_clean["price"] >= 0]
df_clean = df_clean[df_clean["cogs"] >= 0]
after = len(df_clean)

print(f"\n>> Da loai bo {before - after} dong (trung product_id / thieu price / gia tri am).")
print(f">> So dong con lai: {after}")

out_path = f"{OUT_DIR}/products.csv"
df_clean.to_csv(out_path, index=False)
print(f"\nDa luu file sach vao: {out_path}")
