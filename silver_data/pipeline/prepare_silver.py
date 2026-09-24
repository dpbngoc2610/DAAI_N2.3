from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd


PARSER = argparse.ArgumentParser(description="Prepare standardized Silver datasets from extracted CSV sources.")
PARSER.add_argument("--source-dir", type=Path, required=True)
PARSER.add_argument("--prepared-dir", type=Path, required=True)
ARGS = PARSER.parse_args()

SOURCE_DIR = ARGS.source_dir.resolve()
PREP_DIR = ARGS.prepared_dir.resolve()
PREP_DIR.mkdir(parents=True, exist_ok=True)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
PROCESSED_AT = NOW.isoformat().replace("+00:00", "Z")
BATCH_ID = f"SILVER_{NOW.strftime('%Y%m%d_%H%M%S')}"
TODAY = pd.Timestamp(NOW.date())

VALID_CATEGORIES = {"Streetwear", "Outdoor", "GenZ", "Casual"}
VALID_CHANNELS = {"organic_search", "paid_search", "social_media", "email_campaign", "referral", "direct"}
VALID_PROMO_CHANNELS = {"all_channels", "email", "online", "social_media", "in_store"}
VALID_PAYMENT_METHODS = {"credit_card", "paypal", "cod", "apple_pay", "bank_transfer"}


def snake(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "_", value.strip().lower()).strip("_")


def read_source(name: str) -> pd.DataFrame:
    df = pd.read_csv(SOURCE_DIR / name, dtype=str, keep_default_na=True, encoding="utf-8-sig")
    df.columns = [snake(c) for c in df.columns]
    for c in df.columns:
        df[c] = df[c].astype("string").str.strip()
        lower = df[c].str.lower()
        df.loc[lower.isin({"", "null", "n/a", "nan", "none"}), c] = pd.NA
    df.insert(0, "source_row_number", np.arange(2, len(df) + 2, dtype=np.int64))
    return df


def to_int(df: pd.DataFrame, columns: list[str]) -> None:
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")


def to_float(df: pd.DataFrame, columns: list[str]) -> None:
    for c in columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Float64")


def to_date(df: pd.DataFrame, columns: list[str]) -> None:
    for c in columns:
        df[c] = pd.to_datetime(df[c], errors="coerce")


def append_error(errors: pd.Series, mask: pd.Series, code: str) -> None:
    mask = mask.fillna(True)
    errors.loc[mask] = errors.loc[mask].map(lambda items: items + [code])


def append_warning(warnings: pd.Series, mask: pd.Series, code: str) -> None:
    mask = mask.fillna(False)
    warnings.loc[mask] = warnings.loc[mask].map(lambda items: items + [code])


def add_common_metadata(df: pd.DataFrame, source_file: str, data_cols: list[str]) -> pd.DataFrame:
    canonical = df[data_cols].copy()
    for c in canonical.columns:
        if pd.api.types.is_datetime64_any_dtype(canonical[c]):
            canonical[c] = canonical[c].dt.strftime("%Y-%m-%d")
        else:
            canonical[c] = canonical[c].astype("string").fillna("")
    hashes = pd.util.hash_pandas_object(canonical, index=False).map(lambda x: f"{int(x):016x}")
    df["source_file"] = source_file
    df["batch_id"] = BATCH_ID
    df["processed_at_utc"] = PROCESSED_AT
    df["record_hash"] = hashes.values
    return df


def write_dataset(
    name: str,
    source_file: str,
    df: pd.DataFrame,
    errors: pd.Series,
    key_cols: list[str],
    rules: list[str],
    types: dict[str, str],
    warnings: dict[str, int] | None = None,
    row_warnings: pd.Series | None = None,
) -> dict:
    source_rows = len(df)
    source_columns = [c for c in df.columns if c != "source_row_number"]
    bad = errors.map(bool)

    quarantine_rows = []
    if bad.any():
        raw_cols = [c for c in df.columns if c != "source_row_number"]
        for idx, row in df.loc[bad].iterrows():
            raw = {}
            for c in raw_cols:
                v = row[c]
                if pd.isna(v):
                    raw[c] = None
                elif isinstance(v, pd.Timestamp):
                    raw[c] = v.isoformat()
                elif hasattr(v, "item"):
                    raw[c] = v.item()
                else:
                    raw[c] = v
            quarantine_rows.append({
                "source_file": source_file,
                "source_row_number": int(row["source_row_number"]),
                "error_codes": "|".join(errors.loc[idx]),
                "error_details": "; ".join(errors.loc[idx]),
                "raw_record_json": json.dumps(raw, ensure_ascii=False, default=str),
                "batch_id": BATCH_ID,
                "processed_at_utc": PROCESSED_AT,
            })

    if row_warnings is None:
        row_warnings = pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)

    silver = df.loc[~bad].copy()
    data_cols = [c for c in silver.columns if c != "source_row_number"]
    silver = add_common_metadata(silver, source_file, data_cols)
    silver_warning_codes = row_warnings.loc[~bad].map(lambda items: "|".join(items))
    silver["data_quality_status"] = np.where(silver_warning_codes.map(bool), "warning", "valid")
    silver["warning_codes"] = silver_warning_codes.values

    ordered_cols = data_cols + [
        "data_quality_status", "warning_codes", "source_file", "source_row_number",
        "batch_id", "processed_at_utc", "record_hash",
    ]
    silver = silver[ordered_cols]
    for c in silver.columns:
        if pd.api.types.is_datetime64_any_dtype(silver[c]):
            silver[c] = silver[c].dt.strftime("%Y-%m-%d")

    quarantine = pd.DataFrame(quarantine_rows, columns=[
        "source_file", "source_row_number", "error_codes", "error_details",
        "raw_record_json", "batch_id", "processed_at_utc",
    ])

    silver_path = PREP_DIR / f"{name}_silver.csv"
    quarantine_path = PREP_DIR / f"{name}_quarantine.json"
    silver.to_csv(silver_path, index=False, encoding="utf-8", lineterminator="\n")
    quarantine_path.write_text(quarantine.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")

    final_types = {c: types.get(c, "text") for c in data_cols}
    final_types.update({
        "data_quality_status": "text", "warning_codes": "text",
        "source_file": "text", "source_row_number": "integer", "batch_id": "text",
        "processed_at_utc": "datetime", "record_hash": "text",
    })

    return {
        "name": name,
        "source_file": source_file,
        "silver_csv": str(silver_path),
        "quarantine_json": str(quarantine_path),
        "source_rows": source_rows,
        "silver_rows": len(silver),
        "quarantined_rows": len(quarantine),
        "source_column_count": len(source_columns),
        "silver_columns": ordered_cols,
        "key_cols": key_cols,
        "types": final_types,
        "rules": rules,
        "warnings": warnings or {},
        "warning_rows": int(silver["data_quality_status"].eq("warning").sum()),
    }


# Reference data for cross-file validation.
geo_ref = read_source("geography.csv")
geo_ref["zip"] = geo_ref["zip"].str.replace(r"\.0$", "", regex=True).str.zfill(5)
geo_map = geo_ref.set_index("zip")[["city", "region", "district"]]
valid_zips = set(geo_ref["zip"].dropna())

customers_ref = read_source("customers.csv")
valid_customer_ids = set(pd.to_numeric(customers_ref["customer_id"], errors="coerce").dropna().astype(int))

products_ref = read_source("products.csv")
valid_product_ids = set(pd.to_numeric(products_ref["product_id"], errors="coerce").dropna().astype(int))
product_map = products_ref.assign(product_id_num=pd.to_numeric(products_ref["product_id"], errors="coerce")).set_index("product_id_num")[["product_name", "category", "segment"]]

promotions_ref = read_source("promotions.csv")
valid_promo_ids = set(promotions_ref["promo_id"].dropna())

orders_ref = read_source("orders_enriched.csv")
orders_ref["order_id_num"] = pd.to_numeric(orders_ref["order_id"], errors="coerce")
orders_ref["customer_id_num"] = pd.to_numeric(orders_ref["customer_id"], errors="coerce")
orders_ref["order_date_parsed"] = pd.to_datetime(orders_ref["order_date"], errors="coerce")
valid_order_ids = set(orders_ref["order_id_num"].dropna().astype(int))
order_customer_map = orders_ref.set_index("order_id_num")["customer_id_num"]
order_date_map = orders_ref.set_index("order_id_num")["order_date_parsed"]
order_payment_map = orders_ref.set_index("order_id_num")["payment_method"]

items_ref = pd.read_csv(
    SOURCE_DIR / "order_items.csv",
    usecols=["order_id", "product_id", "quantity", "unit_price", "discount_amount"],
)
valid_order_product = set(zip(items_ref["order_id"].astype(int), items_ref["product_id"].astype(int)))
item_net = ((items_ref["quantity"] * items_ref["unit_price"]) - items_ref["discount_amount"]).groupby(
    [items_ref["order_id"], items_ref["product_id"]]
).sum()

manifest = []


def base_errors(df: pd.DataFrame) -> pd.Series:
    return pd.Series([[] for _ in range(len(df))], index=df.index, dtype=object)


# customers
df = read_source("customers.csv")
df["zip"] = df["zip"].str.replace(r"\.0$", "", regex=True).str.zfill(5)
to_int(df, ["customer_id"]); to_date(df, ["signup_date"])
errors = base_errors(df)
append_error(errors, df["customer_id"].isna() | (df["customer_id"] <= 0), "INVALID_CUSTOMER_ID")
append_error(errors, df.duplicated(["customer_id"], keep="first"), "DUPLICATE_CUSTOMER_ID")
append_error(errors, ~df["zip"].fillna("").str.fullmatch(r"\d{5}"), "INVALID_ZIP")
append_error(errors, ~df["zip"].isin(valid_zips), "ZIP_NOT_IN_GEOGRAPHY")
append_error(errors, df["signup_date"].isna() | (df["signup_date"] < "2000-01-01") | (df["signup_date"] > TODAY), "INVALID_SIGNUP_DATE")
append_error(errors, ~df["gender"].isin({"Female", "Male", "Non-binary"}), "INVALID_GENDER")
append_error(errors, ~df["age_group"].isin({"18-24", "25-34", "35-44", "45-54", "55+"}), "INVALID_AGE_GROUP")
append_error(errors, ~df["acquisition_channel"].isin(VALID_CHANNELS), "INVALID_ACQUISITION_CHANNEL")
append_error(errors, df[["city"]].isna().any(axis=1), "MISSING_REQUIRED_TEXT")
manifest.append(write_dataset("customers", "customers.csv", df, errors, ["customer_id"], [
    "Khóa customer_id duy nhất và dương", "ZIP chuẩn 5 ký tự và tồn tại trong geography",
    "Ngày đăng ký hợp lệ từ 2000 đến ngày xử lý", "Miền gender, age_group và acquisition_channel hợp lệ",
], {"customer_id": "integer", "zip": "text", "city": "text", "signup_date": "date", "gender": "text", "age_group": "text", "acquisition_channel": "text"}))


def prepare_product_file(name: str, source_file: str):
    df = read_source(source_file)
    to_int(df, ["product_id"]); to_float(df, ["price", "cogs"])
    df.loc[df["category"].eq("Unknown_999"), "category"] = pd.NA
    errors = base_errors(df)
    append_error(errors, df["product_id"].isna() | (df["product_id"] <= 0), "INVALID_PRODUCT_ID")
    append_error(errors, df.duplicated(["product_id"], keep="first"), "DUPLICATE_PRODUCT_ID")
    append_error(errors, ~df["category"].isin(VALID_CATEGORIES), "INVALID_CATEGORY")
    append_error(errors, df["product_name"].isna(), "MISSING_PRODUCT_NAME")
    append_error(errors, df["price"].isna() | (df["price"] <= 0), "INVALID_PRICE")
    append_error(errors, df["cogs"].isna() | (df["cogs"] <= 0), "INVALID_COGS")
    append_error(errors, df["price"] > 100_000, "PRICE_OUTLIER_OVER_100000")
    append_error(errors, (df["price"] / df["cogs"]) > 100, "PRICE_COGS_RATIO_OUTLIER")
    duplicate_names = df["product_name"].notna() & df["product_name"].duplicated(keep=False)
    row_warnings = base_errors(df)
    append_warning(row_warnings, duplicate_names, "DUPLICATE_PRODUCT_NAME_ALLOWED")
    warnings = {"duplicate_product_names_allowed": int(duplicate_names.sum())}
    return write_dataset(name, source_file, df, errors, ["product_id"], [
        "Khóa product_id duy nhất và dương", "Category thuộc danh mục chuẩn",
        "Price và COGS dương", "Quarantine giá trên 100.000 hoặc tỷ lệ price/COGS trên 100",
        "Tên sản phẩm trùng được giữ vì product_id mới là khóa",
    ], {"product_id": "integer", "product_name": "text", "category": "text", "segment": "text", "size": "text", "color": "text", "price": "money", "cogs": "money"}, warnings, row_warnings)


manifest.append(prepare_product_file("epd", "epd.csv"))
manifest.append(prepare_product_file("products", "products.csv"))


def prepare_promo_file(name: str, source_file: str, pattern: str):
    df = read_source(source_file)
    to_float(df, ["discount_value", "min_order_value"]); to_int(df, ["stackable_flag"])
    to_date(df, ["start_date", "end_date"])
    df["applicable_category"] = df["applicable_category"].fillna("ALL")
    df["stackable_flag"] = df["stackable_flag"].map({0: False, 1: True}).astype("boolean")
    errors = base_errors(df)
    append_error(errors, ~df["promo_id"].fillna("").str.fullmatch(pattern), "INVALID_PROMO_ID")
    append_error(errors, df.duplicated(["promo_id"], keep="first"), "DUPLICATE_PROMO_ID")
    append_error(errors, df["promo_name"].isna(), "MISSING_PROMO_NAME")
    append_error(errors, ~df["promo_type"].isin({"percentage", "fixed"}), "INVALID_PROMO_TYPE")
    append_error(errors, ~df["promo_channel"].isin(VALID_PROMO_CHANNELS), "INVALID_PROMO_CHANNEL")
    append_error(errors, ~df["applicable_category"].isin(VALID_CATEGORIES | {"ALL"}), "INVALID_APPLICABLE_CATEGORY")
    append_error(errors, df["discount_value"].isna() | ((df["promo_type"] == "percentage") & ~df["discount_value"].between(0, 100)) | ((df["promo_type"] == "fixed") & (df["discount_value"] <= 0)), "INVALID_DISCOUNT")
    append_error(errors, df["min_order_value"].isna() | (df["min_order_value"] < 0), "INVALID_MIN_ORDER_VALUE")
    append_error(errors, df["start_date"].isna() | df["end_date"].isna() | (df["end_date"] < df["start_date"]), "INVALID_PROMO_DATES")
    append_error(errors, df["stackable_flag"].isna(), "INVALID_STACKABLE_FLAG")
    return write_dataset(name, source_file, df, errors, ["promo_id"], [
        "Khóa promo_id duy nhất và đúng định dạng", "Miền promo_type, promo_channel và category hợp lệ",
        "Discount hợp lệ theo loại chương trình", "Ngày kết thúc không trước ngày bắt đầu",
        "applicable_category rỗng được chuẩn hóa thành ALL",
    ], {"promo_id": "text", "promo_name": "text", "promo_type": "text", "discount_value": "money", "start_date": "date", "end_date": "date", "applicable_category": "text", "promo_channel": "text", "stackable_flag": "boolean", "min_order_value": "money"})


manifest.append(prepare_promo_file("eprom", "eprom.csv", r"PROMO-\d{4}-\d{4}"))
manifest.append(prepare_promo_file("promotions", "promotions.csv", r"PROMO-\d{4}"))


# geography
df = geo_ref.copy(); to_int(df, [])
errors = base_errors(df)
append_error(errors, ~df["zip"].fillna("").str.fullmatch(r"\d{5}"), "INVALID_ZIP")
append_error(errors, df.duplicated(["zip"], keep="first"), "DUPLICATE_ZIP")
append_error(errors, ~df["region"].isin({"East", "Central", "West"}), "INVALID_REGION")
append_error(errors, df["district"].isna() | ~df["district"].fillna("").str.contains(r"\d", regex=True), "INVALID_DISTRICT")
append_error(errors, df["city"].isna(), "MISSING_CITY")
manifest.append(write_dataset("geography", "geography.csv", df, errors, ["zip"], [
    "ZIP được giữ dạng text 5 ký tự", "Mỗi ZIP ánh xạ một city, region và district",
    "Region thuộc East, Central hoặc West",
], {"zip": "text", "city": "text", "region": "text", "district": "text"}))


# inventory
df = read_source("inventory.csv")
to_date(df, ["snapshot_date"])
to_int(df, ["product_id", "stock_on_hand", "units_received", "units_sold", "stockout_days", "year", "month"])
to_float(df, ["days_of_supply", "fill_rate", "sell_through_rate"])
for c in ["stockout_flag", "overstock_flag", "reorder_flag"]:
    raw = pd.to_numeric(df[c], errors="coerce")
    df[c] = raw.map({0: False, 1: True}).astype("boolean")
errors = base_errors(df)
append_error(errors, df[["snapshot_date", "product_id"]].isna().any(axis=1), "MISSING_INVENTORY_KEY")
append_error(errors, df.duplicated(["snapshot_date", "product_id"], keep="first"), "DUPLICATE_INVENTORY_KEY")
append_error(errors, ~df["product_id"].isin(valid_product_ids), "PRODUCT_NOT_FOUND")
for c in ["stock_on_hand", "units_received", "units_sold", "stockout_days", "days_of_supply"]:
    append_error(errors, df[c].isna() | (df[c] < 0), f"INVALID_{c.upper()}")
for c in ["fill_rate", "sell_through_rate"]:
    append_error(errors, df[c].isna() | ~df[c].between(0, 1), f"INVALID_{c.upper()}")
append_error(errors, (df["year"] != df["snapshot_date"].dt.year) | (df["month"] != df["snapshot_date"].dt.month), "YEAR_MONTH_MISMATCH")
append_error(errors, (df["stockout_flag"].eq(True) & df["stockout_days"].eq(0)) | (df["stockout_flag"].eq(False) & df["stockout_days"].gt(0)), "STOCKOUT_FLAG_MISMATCH")
append_error(errors, df[["stockout_flag", "overstock_flag", "reorder_flag"]].isna().any(axis=1), "INVALID_BOOLEAN_FLAG")
attrs = df.join(product_map, on="product_id", rsuffix="_product")
append_error(errors, (attrs["product_name"] != attrs["product_name_product"]) | (attrs["category"] != attrs["category_product"]) | (attrs["segment"] != attrs["segment_product"]), "PRODUCT_ATTRIBUTES_MISMATCH")
inventory_warnings = base_errors(df)
append_warning(inventory_warnings, df["days_of_supply"] > 10_000, "DAYS_OF_SUPPLY_GT_10000")
manifest.append(write_dataset("inventory", "inventory.csv", df, errors, ["snapshot_date", "product_id"], [
    "Khóa snapshot_date + product_id duy nhất", "Số lượng không âm; các rate nằm trong 0–1",
    "year/month khớp snapshot_date", "Cờ stockout nhất quán với stockout_days",
    "product_id và thuộc tính sản phẩm khớp bảng products",
], {"snapshot_date": "date", "product_id": "integer", "stock_on_hand": "integer", "units_received": "integer", "units_sold": "integer", "stockout_days": "integer", "days_of_supply": "decimal", "fill_rate": "rate", "stockout_flag": "boolean", "overstock_flag": "boolean", "reorder_flag": "boolean", "sell_through_rate": "rate", "product_name": "text", "category": "text", "segment": "text", "year": "integer", "month": "integer"}, {"days_of_supply_over_10000": int((df["days_of_supply"] > 10_000).sum())}, inventory_warnings))


# orders_enriched
df = read_source("orders_enriched.csv")
to_int(df, ["order_id", "customer_id", "years_experience"]); to_date(df, ["order_date"])
df["zip"] = df["zip"].str.replace(r"\.0$", "", regex=True).str.zfill(5)
errors = base_errors(df)
append_error(errors, df["order_id"].isna() | (df["order_id"] <= 0), "INVALID_ORDER_ID")
append_error(errors, df.duplicated(["order_id"], keep="first"), "DUPLICATE_ORDER_ID")
append_error(errors, df["order_date"].isna() | (df["order_date"] > TODAY), "INVALID_ORDER_DATE")
append_error(errors, ~df["customer_id"].isin(valid_customer_ids), "CUSTOMER_NOT_FOUND")
append_error(errors, ~df["zip"].isin(valid_zips), "ZIP_NOT_FOUND")
for c, vals in {"order_status": {"delivered", "cancelled", "returned", "shipped", "paid", "created"}, "payment_method": VALID_PAYMENT_METHODS, "device_type": {"mobile", "desktop", "tablet"}, "order_source": VALID_CHANNELS, "region": {"East", "Central", "West"}}.items():
    append_error(errors, ~df[c].isin(vals), f"INVALID_{c.upper()}")
append_error(errors, df["years_experience"].isna() | (df["years_experience"] < 0), "INVALID_YEARS_EXPERIENCE")
joined = df.join(geo_map, on="zip", rsuffix="_geo")
append_error(errors, (joined["city"] != joined["city_geo"]) | (joined["region"] != joined["region_geo"]) | (joined["district"] != joined["district_geo"]), "GEOGRAPHY_ATTRIBUTES_MISMATCH")
manifest.append(write_dataset("orders_enriched", "orders_enriched.csv", df, errors, ["order_id"], [
    "Khóa order_id duy nhất", "Ngày đặt hàng hợp lệ", "customer_id và ZIP tồn tại trong bảng chuẩn",
    "Miền trạng thái, thanh toán, thiết bị, nguồn đơn và vùng hợp lệ", "Thuộc tính địa lý khớp geography",
], {"order_id": "integer", "order_date": "date", "customer_id": "integer", "zip": "text", "city": "text", "region": "text", "district": "text", "order_status": "text", "payment_method": "text", "device_type": "text", "order_source": "text", "sales_employee_id": "text", "sales_employee_name": "text", "marital_status": "text", "education_level": "text", "years_experience": "integer", "comment": "text"}))


# order_items
df = read_source("order_items.csv")
to_int(df, ["order_id", "product_id", "quantity"]); to_float(df, ["unit_price", "discount_amount"])
errors = base_errors(df)
append_error(errors, df[["order_id", "product_id", "quantity", "unit_price"]].isna().any(axis=1), "MISSING_REQUIRED_ORDER_ITEM_FIELD")
append_error(errors, ~df["order_id"].isin(valid_order_ids), "ORDER_NOT_FOUND")
append_error(errors, ~df["product_id"].isin(valid_product_ids), "PRODUCT_NOT_FOUND")
append_error(errors, df["quantity"].isna() | (df["quantity"] <= 0), "INVALID_QUANTITY")
append_error(errors, df["unit_price"].isna() | (df["unit_price"] < 0), "INVALID_UNIT_PRICE")
append_error(errors, df["discount_amount"].isna() | (df["discount_amount"] < 0), "INVALID_DISCOUNT_AMOUNT")
append_error(errors, df["discount_amount"] > (df["quantity"] * df["unit_price"]), "DISCOUNT_EXCEEDS_LINE_GROSS")
for c in ["promo_id", "promo_id_2"]:
    append_error(errors, df[c].notna() & ~df[c].isin(valid_promo_ids), f"{c.upper()}_NOT_FOUND")
manifest.append(write_dataset("order_items", "order_items.csv", df, errors, ["order_id", "product_id", "source_row_number"], [
    "order_id và product_id tồn tại", "Quantity dương; giá và giảm giá không âm",
    "Giảm giá không vượt giá trị gộp của dòng", "Mã khuyến mãi tùy chọn phải tồn tại trong promotions",
], {"order_id": "integer", "product_id": "integer", "quantity": "integer", "unit_price": "money", "discount_amount": "money", "promo_id": "text", "promo_id_2": "text"}))


# payments
df = read_source("payments.csv")
to_int(df, ["order_id", "installments"]); to_float(df, ["payment_value"])
errors = base_errors(df)
append_error(errors, df["order_id"].isna() | ~df["order_id"].isin(valid_order_ids), "ORDER_NOT_FOUND")
append_error(errors, df.duplicated(["order_id"], keep="first"), "DUPLICATE_PAYMENT_ORDER")
append_error(errors, ~df["payment_method"].isin(VALID_PAYMENT_METHODS), "INVALID_PAYMENT_METHOD")
append_error(errors, df["payment_value"].isna() | (df["payment_value"] < 0), "INVALID_PAYMENT_VALUE")
append_error(errors, df["installments"].isna() | (df["installments"] < 1), "INVALID_INSTALLMENTS")
append_error(errors, df["payment_method"] != df["order_id"].map(order_payment_map), "PAYMENT_METHOD_MISMATCH_ORDER")
manifest.append(write_dataset("payments", "payments.csv", df, errors, ["order_id"], [
    "Một bản ghi thanh toán cho mỗi order_id", "Order tồn tại và payment_method khớp đơn hàng",
    "payment_value không âm; installments từ 1 trở lên",
], {"order_id": "integer", "payment_method": "text", "payment_value": "money", "installments": "integer"}))


# returns
df = read_source("returns.csv")
to_int(df, ["order_id", "product_id", "return_quantity"]); to_float(df, ["refund_amount"]); to_date(df, ["return_date"])
errors = base_errors(df)
append_error(errors, df["return_id"].isna(), "MISSING_RETURN_ID")
append_error(errors, df.duplicated(["return_id"], keep="first"), "DUPLICATE_RETURN_ID")
append_error(errors, ~df["order_id"].isin(valid_order_ids), "ORDER_NOT_FOUND")
append_error(errors, ~df["product_id"].isin(valid_product_ids), "PRODUCT_NOT_FOUND")
pair_valid = pd.Series([(o, p) in valid_order_product if pd.notna(o) and pd.notna(p) else False for o, p in zip(df["order_id"], df["product_id"])], index=df.index)
append_error(errors, ~pair_valid, "ORDER_PRODUCT_NOT_FOUND")
append_error(errors, df["return_date"].isna() | (df["return_date"] < df["order_id"].map(order_date_map)), "INVALID_RETURN_DATE")
append_error(errors, df["return_quantity"].isna() | (df["return_quantity"] <= 0), "INVALID_RETURN_QUANTITY")
append_error(errors, df["refund_amount"].isna() | (df["refund_amount"] < 0), "INVALID_REFUND_AMOUNT")
append_error(errors, ~df["return_reason"].isin({"wrong_size", "defective", "not_as_described", "changed_mind", "late_delivery"}), "INVALID_RETURN_REASON")
refund_by_pair = df.groupby(["order_id", "product_id"])["refund_amount"].transform("sum")
net_for_row = pd.Series([item_net.get((o, p), np.nan) for o, p in zip(df["order_id"], df["product_id"])], index=df.index)
refund_warning = refund_by_pair > (net_for_row + 0.01)
return_warnings = base_errors(df)
append_warning(return_warnings, refund_warning, "REFUND_PAIR_TOTAL_EXCEEDS_ITEM_NET")
manifest.append(write_dataset("returns", "returns.csv", df, errors, ["return_id"], [
    "Khóa return_id duy nhất", "Order-product tồn tại trong order_items", "Ngày trả không trước ngày đặt",
    "Số lượng trả dương; refund không âm", "Lý do trả thuộc danh mục chuẩn",
], {"return_id": "text", "order_id": "integer", "product_id": "integer", "return_date": "date", "return_reason": "text", "return_quantity": "integer", "refund_amount": "money"}, {"refund_rows_where_pair_total_exceeds_item_net": int(refund_warning.sum())}, return_warnings))


# reviews
df = read_source("reviews.csv")
to_int(df, ["order_id", "product_id", "customer_id", "rating"]); to_date(df, ["review_date"])
errors = base_errors(df)
append_error(errors, df["review_id"].isna(), "MISSING_REVIEW_ID")
append_error(errors, df.duplicated(["review_id"], keep="first"), "DUPLICATE_REVIEW_ID")
append_error(errors, ~df["order_id"].isin(valid_order_ids), "ORDER_NOT_FOUND")
append_error(errors, ~df["product_id"].isin(valid_product_ids), "PRODUCT_NOT_FOUND")
append_error(errors, ~df["customer_id"].isin(valid_customer_ids), "CUSTOMER_NOT_FOUND")
pair_valid = pd.Series([(o, p) in valid_order_product if pd.notna(o) and pd.notna(p) else False for o, p in zip(df["order_id"], df["product_id"])], index=df.index)
append_error(errors, ~pair_valid, "ORDER_PRODUCT_NOT_FOUND")
append_error(errors, df["customer_id"] != df["order_id"].map(order_customer_map), "CUSTOMER_MISMATCH_ORDER")
append_error(errors, df["review_date"].isna() | (df["review_date"] < df["order_id"].map(order_date_map)), "INVALID_REVIEW_DATE")
append_error(errors, df["rating"].isna() | ~df["rating"].between(1, 5), "INVALID_RATING")
manifest.append(write_dataset("reviews", "reviews.csv", df, errors, ["review_id"], [
    "Khóa review_id duy nhất", "Order-product và customer tồn tại, customer khớp order",
    "Ngày review không trước ngày đặt", "Rating nằm trong 1–5",
], {"review_id": "text", "order_id": "integer", "product_id": "integer", "customer_id": "integer", "review_date": "date", "rating": "integer", "review_title": "text"}))


# shipments
df = read_source("shipments_realistic.csv")
to_int(df, ["order_id", "shipper_experience_years", "average_delivery_time", "shipper_age"])
to_float(df, ["shipping_fee", "shipper_rating", "delivery_success_rate"])
to_date(df, ["ship_date", "delivery_date", "join_date"])
df["shipper_phone"] = df["shipper_phone"].str.replace(r"\.0$", "", regex=True).str.zfill(10)
errors = base_errors(df)
append_error(errors, df["order_id"].isna() | ~df["order_id"].isin(valid_order_ids), "ORDER_NOT_FOUND")
append_error(errors, df.duplicated(["order_id"], keep="first"), "DUPLICATE_SHIPMENT_ORDER")
append_error(errors, df["ship_date"].isna() | (df["ship_date"] < df["order_id"].map(order_date_map)), "INVALID_SHIP_DATE")
append_error(errors, df["delivery_date"].isna() | (df["delivery_date"] < df["ship_date"]), "INVALID_DELIVERY_DATE")
append_error(errors, df["shipping_fee"].isna() | (df["shipping_fee"] < 0), "INVALID_SHIPPING_FEE")
append_error(errors, ~df["shipper_id"].fillna("").str.fullmatch(r"SHP\d+"), "INVALID_SHIPPER_ID")
append_error(errors, df["shipper_rating"].isna() | ~df["shipper_rating"].between(0, 5), "INVALID_SHIPPER_RATING")
append_error(errors, df["delivery_success_rate"].isna() | ~df["delivery_success_rate"].between(0, 100), "INVALID_DELIVERY_SUCCESS_RATE")
append_error(errors, ~df["shipper_phone"].fillna("").str.fullmatch(r"\d{10}"), "INVALID_SHIPPER_PHONE")
shipment_warnings = base_errors(df)
append_warning(shipment_warnings, df["ship_date"] < df["join_date"], "SHIP_DATE_BEFORE_SHIPPER_JOIN_DATE")
manifest.append(write_dataset("shipments", "shipments_realistic.csv", df, errors, ["order_id"], [
    "Một shipment cho mỗi order_id", "Order tồn tại; ngày ship không trước ngày đặt; ngày giao không trước ngày ship",
    "Phí ship không âm; shipper_id và số điện thoại đúng định dạng", "Giữ đủ 22 cột nguồn, không lược bỏ thuộc tính shipper",
], {"shipper_id": "text", "order_id": "integer", "ship_date": "date", "delivery_date": "date", "shipping_fee": "money", "shipper_company": "text", "shipper_vehicle": "text", "shipper_experience_years": "integer", "shipper_rating": "decimal", "delivery_success_rate": "percent_points", "average_delivery_time": "integer", "working_shift": "text", "join_date": "date", "shipper_name": "text", "shipper_phone": "text", "shipper_gender": "text", "shipper_age": "integer", "shipper_marital_status": "text", "shipper_education": "text", "city": "text", "region": "text", "district": "text"}, {"shipments_before_shipper_join_date": int((df["ship_date"] < df["join_date"]).sum())}, shipment_warnings))


def prepare_traffic(name: str, source_file: str, split_variant: bool):
    df = read_source(source_file)
    to_date(df, ["date"]); to_int(df, ["sessions", "unique_visitors", "page_views"]); to_float(df, ["bounce_rate", "avg_session_duration_sec"])
    if split_variant:
        parsed = df["traffic_source"].fillna("").str.extract(r"^(.*?)(?:\s+(Variant\s+\d+))?$")
        df["traffic_source"] = parsed[0].str.strip()
        df["traffic_variant"] = parsed[1]
    else:
        df["traffic_source"] = df["traffic_source"].str.lower()
    df.insert(df.columns.get_loc("traffic_source"), "reporting_period", df["date"].dt.strftime("%Y-%m"))
    errors = base_errors(df)
    append_error(errors, df["date"].isna() | (df["date"] < "2000-01-01") | (df["date"] > TODAY), "INVALID_DATE")
    append_error(errors, df["sessions"].isna() | (df["sessions"] < 0) | (df["sessions"] > 10_000_000), "INVALID_SESSIONS")
    append_error(errors, df["unique_visitors"].isna() | (df["unique_visitors"] < 0), "INVALID_UNIQUE_VISITORS")
    append_error(errors, df["unique_visitors"] > df["sessions"], "UNIQUE_VISITORS_EXCEED_SESSIONS")
    append_error(errors, df["page_views"].isna() | (df["page_views"] < 0), "INVALID_PAGE_VIEWS")
    append_error(errors, df["bounce_rate"].isna() | ~df["bounce_rate"].between(0, 1), "INVALID_BOUNCE_RATE")
    append_error(errors, df["avg_session_duration_sec"].isna() | (df["avg_session_duration_sec"] < 0), "INVALID_AVG_SESSION_DURATION")
    append_error(errors, ~df["traffic_source"].isin(VALID_CHANNELS), "INVALID_TRAFFIC_SOURCE")
    append_error(errors, df.duplicated(["date", "traffic_source"], keep="first"), "DUPLICATE_TRAFFIC_KEY")
    types = {"date": "date", "reporting_period": "text", "sessions": "integer", "unique_visitors": "integer", "page_views": "integer", "bounce_rate": "rate", "avg_session_duration_sec": "decimal", "traffic_source": "text"}
    if split_variant:
        types["traffic_variant"] = "text"
    return write_dataset(name, source_file, df, errors, ["date", "traffic_source"], [
        "Khóa date + traffic_source duy nhất", "Ngày hợp lệ; các chỉ số đếm không âm",
        "unique_visitors không vượt sessions", "Bounce rate nằm trong 0–1; thời lượng không âm",
        "Traffic source thuộc danh mục chuẩn" + (" và variant được tách riêng" if split_variant else ""),
    ], types)


manifest.append(prepare_traffic("tf", "tf.csv", True))
manifest.append(prepare_traffic("web_traffic", "web_traffic.csv", False))


manifest_path = PREP_DIR / "manifest.json"
manifest_path.write_text(json.dumps({"batch_id": BATCH_ID, "processed_at_utc": PROCESSED_AT, "datasets": manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps([{k: d[k] for k in ["name", "source_rows", "silver_rows", "quarantined_rows"]} for d in manifest], ensure_ascii=False, indent=2))
print(f"Manifest: {manifest_path}")
