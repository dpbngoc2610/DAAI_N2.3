"""
BRONZE -> SILVER cleaning pipeline
Môn: Nhập môn phân tích dữ liệu và AI

"""

import pandas as pd
import numpy as np
import os

RAW_DIR = "."
OUT_DIR = "./silver_output"
os.makedirs(OUT_DIR, exist_ok=True)

log = []  # ghi lại các thay đổi để làm báo cáo data quality


def note(msg):
    print(msg)
    log.append(msg)


# ============================================================
# 1. CUSTOMERS 
# ============================================================
customers = pd.read_csv(f"{RAW_DIR}/customers.csv")

before = len(customers)
customers["signup_date"] = pd.to_datetime(customers["signup_date"], errors="coerce")
customers = customers.drop_duplicates(subset="customer_id")
# chuẩn hóa text: bỏ khoảng trắng dư, đồng bộ hoa/thường ở các cột phân loại
for col in ["city", "gender", "age_group", "acquisition_channel"]:
    customers[col] = customers[col].str.strip()

note(f"[customers] {before} -> {len(customers)} dòng sau khi loại trùng + parse ngày. "
     f"Ngày lỗi (NaT): {customers['signup_date'].isna().sum()}")

customers.to_csv(f"{OUT_DIR}/customers_silver.csv", index=False)


# ============================================================
# 2. GEOGRAPHY 
# ============================================================
geography = pd.read_csv(f"{RAW_DIR}/geography.csv")
for col in ["city", "region", "district"]:
    geography[col] = geography[col].str.strip()
geography = geography.drop_duplicates(subset="zip")
note(f"[geography] {len(geography)} dòng, không có lỗi đáng kể.")
geography.to_csv(f"{OUT_DIR}/geography_silver.csv", index=False)


# ============================================================
# 3. EPD (product master) — 4 lỗi cụ thể 
# ============================================================
epd = pd.read_csv(f"{RAW_DIR}/epd.csv", encoding="utf-8-sig")  # utf-8-sig bỏ BOM ở đầu file

# 3a. Giá âm -> không có ý nghĩa kinh doanh, coi là lỗi nhập liệu -> chuyển về NaN để impute
neg_price_mask = epd["price"] < 0
note(f"[epd] Giá âm: {neg_price_mask.sum()} dòng -> set về NaN để impute lại")
epd.loc[neg_price_mask, "price"] = np.nan

# 3b. category = "Unknown_999" là placeholder giả -> coi như thiếu (NaN)
placeholder_mask = epd["category"] == "Unknown_999"
note(f"[epd] category placeholder 'Unknown_999': {placeholder_mask.sum()} dòng -> set về NaN")
epd.loc[placeholder_mask, "category"] = np.nan

# 3c. Impute price thiếu bằng median của CÙNG category (hợp lý hơn median toàn bảng)
epd["price"] = epd.groupby("category")["price"].transform(lambda s: s.fillna(s.median()))
# nếu category cũng NaN thì impute bằng median toàn bảng (fallback)
epd["price"] = epd["price"].fillna(epd["price"].median())

# 3d. category còn thiếu -> gán "Unknown" (giữ lại dòng, không xóa, vì các cột khác vẫn dùng được)
epd["category"] = epd["category"].fillna("Unknown")

# 3e. cogs > price (bán dưới giá vốn) -> không xóa, chỉ FLAG để phân tích/gold layer biết
epd["flag_loss_margin"] = epd["cogs"] > epd["price"]
note(f"[epd] Sản phẩm có cogs > price (bán lỗ): {epd['flag_loss_margin'].sum()} dòng -> giữ lại, gắn cờ")

epd = epd.drop_duplicates(subset="product_id")
epd.to_csv(f"{OUT_DIR}/epd_silver.csv", index=False)
note(f"[epd] Hoàn tất: {len(epd)} dòng")


# ============================================================
# 4. EPROM (promotions) — nhiều lỗi nhỏ
# ============================================================
eprom = pd.read_csv(f"{RAW_DIR}/eprom.csv", encoding="utf-8-sig")

eprom["start_date"] = pd.to_datetime(eprom["start_date"], errors="coerce")
eprom["end_date"] = pd.to_datetime(eprom["end_date"], errors="coerce")

# 4a. discount_value âm -> lỗi nhập liệu, lấy trị tuyệt đối
neg_disc = eprom["discount_value"] < 0
note(f"[eprom] discount_value âm: {neg_disc.sum()} dòng -> lấy abs()")
eprom.loc[neg_disc, "discount_value"] = eprom.loc[neg_disc, "discount_value"].abs()

# 4b. discount_value > 100 khi promo_type = percentage -> vô lý (giảm >100%) -> cap về 100
bad_pct = (eprom["promo_type"] == "percentage") & (eprom["discount_value"] > 100)
note(f"[eprom] % giảm giá > 100%: {bad_pct.sum()} dòng -> cap về 100")
eprom.loc[bad_pct, "discount_value"] = 100

# 4c. start_date > end_date -> hoán đổi 2 ngày (giả định người nhập liệu nhập ngược)
swap_mask = eprom["start_date"] > eprom["end_date"]
note(f"[eprom] start_date > end_date: {swap_mask.sum()} dòng -> hoán đổi lại 2 cột")
eprom.loc[swap_mask, ["start_date", "end_date"]] = eprom.loc[swap_mask, ["end_date", "start_date"]].values

# 4d. applicable_category thiếu (783 dòng) -> đây không phải "lỗi", nghĩa là áp dụng
#     cho MỌI category -> điền rõ nghĩa "all" thay vì để trống, để khi phân tích không bị hiểu lầm
eprom["applicable_category"] = eprom["applicable_category"].fillna("all")

# 4e. promo_name / promo_channel thiếu (vài dòng) -> điền "Unknown" (không đủ dữ liệu để suy luận)
eprom["promo_name"] = eprom["promo_name"].fillna("Unknown")
eprom["promo_channel"] = eprom["promo_channel"].fillna("Unknown")

eprom = eprom.drop_duplicates(subset="promo_id")
eprom.to_csv(f"{OUT_DIR}/eprom_silver.csv", index=False)
note(f"[eprom] Hoàn tất: {len(eprom)} dòng")


# ============================================================
# 5. INVENTORY — vấn đề referential integrity với epd
# ============================================================
inventory = pd.read_csv(f"{RAW_DIR}/inventory.csv")
inventory["snapshot_date"] = pd.to_datetime(inventory["snapshot_date"], errors="coerce")

# 961 product_id trong inventory không có trong epd (bảng sản phẩm hiện tại chỉ có id 1-1000).
# Đây nhiều khả năng là sản phẩm CŨ/đã ngừng bán. Ta KHÔNG xóa các dòng này (mất dữ liệu tồn kho
# lịch sử), mà gắn cờ để phân biệt rõ khi phân tích ở bước Gold.
orphan_mask = ~inventory["product_id"].isin(epd["product_id"])
note(f"[inventory] product_id không khớp với epd (sản phẩm cũ/ngừng bán): {orphan_mask.sum()} dòng -> gắn cờ 'is_legacy_product'")
inventory["is_legacy_product"] = orphan_mask

inventory = inventory.drop_duplicates(subset=["snapshot_date", "product_id"])
inventory.to_csv(f"{OUT_DIR}/inventory_silver.csv", index=False)
note(f"[inventory] Hoàn tất: {len(inventory)} dòng")


# ============================================================
# 6. VALIDATION 
# ============================================================
note("\n===== KIỂM TRA CHẤT LƯỢNG DỮ LIỆU (epd_silver) =====")

note(f"1. Giá trị âm: price={( epd['price']<0 ).sum()} dòng, cogs={( epd['cogs']<0 ).sum()} dòng")

note(f"2. Category — các giá trị hiện có:\n{epd['category'].value_counts(dropna=False).to_string()}")

note(f"3. Product_name — số giá trị: {epd['product_name'].notna().sum()}, "
     f"số giá trị DUY NHẤT: {epd['product_name'].nunique()}, "
     f"số dòng trùng tên: {epd['product_name'].duplicated().sum()}")

note(f"4. Price — số dòng thiếu (NaN): {epd['price'].isna().sum()}")

note(f"5. Product_id — tổng số: {epd['product_id'].count()}, "
     f"số giá trị DUY NHẤT: {epd['product_id'].nunique()}, "
     f"số dòng trùng: {epd['product_id'].duplicated().sum()}")


# ============================================================
# log data-quality report
# ============================================================
with open(f"{OUT_DIR}/data_quality_log.txt", "w", encoding="utf-8") as f:
    f.write("BRONZE -> SILVER: LOG XỬ LÝ DỮ LIỆU\n")
    f.write("=" * 50 + "\n")
    for line in log:
        f.write(line + "\n")

print("\nXong. Các file silver đã lưu tại:", OUT_DIR)
