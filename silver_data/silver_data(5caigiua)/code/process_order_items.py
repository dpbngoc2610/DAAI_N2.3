"""
Xu ly du lieu co ban (Bronze -> Silver) cho file: order_items.csv

Cac buoc kiem tra:
    1. Kiem tra gia tri am o cot 'quantity', 'unit_price', 'discount_amount'
    4. Kiem tra cac gia tri rieng biet cua cot 'product_id'
    5. Kiem tra du lieu thieu (missing values), dac biet cot promo_id, promo_id_2
    6. Kiem tra product_id co ton tai trong bang products.csv hay khong (doi chieu khoa ngoai)
    7. Xu ly xong thi luu ra thu muc "silver_data"

Luu y: script nay can file products.csv (silver) da duoc xu ly truoc
(chay process_products.py truoc) de doi chieu product_id.
Neu chua co, script se tu doc truc tiep tu file goc.
"""

import os
import pandas as pd

RAW_DIR = "/home/claude/extracted/student_data"
OUT_DIR = "/home/claude/work/silver_data"
os.makedirs(OUT_DIR, exist_ok=True)

FILE_NAME = "order_items.csv"

print("=" * 70)
print(f"XU LY FILE: {FILE_NAME}")
print("=" * 70)

df = pd.read_csv(f"{RAW_DIR}/{FILE_NAME}", low_memory=False)
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
for col in ["quantity", "unit_price", "discount_amount"]:
    n_neg = (df[col] < 0).sum()
    print(f"    - Cot '{col}': {n_neg} gia tri am")

# [4] Kiem tra gia tri rieng biet cua product_id
print("\n[4] Kiem tra gia tri rieng biet (unique values)")
print(f"    - Cot 'product_id': {df['product_id'].nunique(dropna=True)} gia tri rieng biet")

# [6] Doi chieu product_id voi bang products
print("\n[6] Doi chieu 'product_id' voi products.csv")
products_silver_path = f"{OUT_DIR}/products.csv"
if os.path.exists(products_silver_path):
    df_products = pd.read_csv(products_silver_path)
else:
    df_products = pd.read_csv(f"{RAW_DIR}/products.csv")
valid_product_ids = set(df_products["product_id"])
n_orphan = (~df["product_id"].isin(valid_product_ids)).sum()
print(f"    - So dong co product_id KHONG ton tai trong products.csv: {n_orphan}")

# --------------------- XU LY / LAM SACH ---------------------
before = len(df)
df_clean = df.drop_duplicates().copy()
df_clean = df_clean.dropna(subset=["order_id", "product_id", "quantity", "unit_price"])
df_clean = df_clean[(df_clean["quantity"] >= 0) & (df_clean["unit_price"] >= 0)]
# chuan hoa discount_amount am (neu co) ve 0
df_clean.loc[df_clean["discount_amount"] < 0, "discount_amount"] = 0
after = len(df_clean)

print(f"\n>> Da loai bo {before - after} dong (trung / thieu du lieu bat buoc / gia tri am).")
print(f">> So dong con lai: {after}")

out_path = f"{OUT_DIR}/order_items.csv"
df_clean.to_csv(out_path, index=False)
print(f"\nDa luu file sach vao: {out_path}")
