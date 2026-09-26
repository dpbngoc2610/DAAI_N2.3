"""Problem 2 - Dinh bien va phan loai san pham kinh doanh.

Tat ca xep hang doanh thu duoc tinh trong bon thang gan nhat va chi tren
don hang da giao. Phan tich ton kho dung cung cua so thoi gian.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent


def show_table(title: str, table: pd.DataFrame, full: bool = True) -> None:
    """Hien thi bang trong terminal, khong tao CSV."""
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    max_rows = None if full else 30
    with pd.option_context("display.max_rows", max_rows, "display.max_columns", None,
                           "display.width", 240, "display.float_format", "{:,.3f}".format):
        print(table.to_string(index=False) if full else table)


def find_data_file(filename: str) -> Path:
    candidates = [SCRIPT_DIR / filename, REPO_ROOT / filename, REPO_ROOT / "silver_data" / filename]
    candidates.extend(sorted((REPO_ROOT / "silver_data").glob(
        f".silver_pipeline_work_*/excel/{filename}"
    ), reverse=True))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Khong tim thay {filename} trong {REPO_ROOT}")


def require_columns(df: pd.DataFrame, columns: set[str], source: str) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(f"{source} thieu cot bat buoc: {missing}")


def last_four_months(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    end_period = df[date_col].dropna().max().to_period("M")
    start_period = end_period - 3
    periods = df[date_col].dt.to_period("M")
    return df[periods.between(start_period, end_period)].copy()


def load_fact_sales() -> pd.DataFrame:
    order_items = pd.read_csv(find_data_file("order_items.csv"), low_memory=False)
    orders = pd.read_csv(find_data_file("orders_enriched.csv"), low_memory=False)
    products = pd.read_csv(find_data_file("products.csv"), low_memory=False)
    require_columns(order_items, {"order_id", "product_id", "quantity", "unit_price", "discount_amount"}, "order_items")
    require_columns(orders, {"order_id", "order_date", "order_status", "customer_id"}, "orders")
    require_columns(products, {"product_id", "product_name", "category", "segment", "cogs"}, "products")
    orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
    orders["order_status"] = orders["order_status"].astype(str).str.lower().str.strip()
    orders = orders[orders["order_status"].eq("delivered")].copy()
    fact = order_items.merge(
        orders[["order_id", "order_date", "order_status", "customer_id"]],
        on="order_id", how="inner", validate="many_to_one",
    ).merge(
        products[["product_id", "product_name", "category", "segment", "cogs"]],
        on="product_id", how="left", validate="many_to_one",
    )
    fact[["quantity", "unit_price", "discount_amount", "cogs"]] = fact[
        ["quantity", "unit_price", "discount_amount", "cogs"]
    ].apply(pd.to_numeric, errors="coerce")
    fact = fact.dropna(subset=["order_date", "product_id", "quantity", "unit_price"])
    fact["GrossRevenue"] = fact["quantity"] * fact["unit_price"]
    fact["NetRevenue"] = (fact["GrossRevenue"] - fact["discount_amount"].fillna(0)).clip(lower=0)
    return last_four_months(fact, "order_date")


def load_inventory() -> pd.DataFrame:
    inv = pd.read_csv(find_data_file("inventory.csv"), low_memory=False)
    require_columns(inv, {
        "snapshot_date", "product_id", "stock_on_hand", "units_sold", "category", "segment"
    }, "inventory")
    inv["snapshot_date"] = pd.to_datetime(inv["snapshot_date"], errors="coerce")
    inv[["stock_on_hand", "units_sold"]] = inv[["stock_on_hand", "units_sold"]].apply(
        pd.to_numeric, errors="coerce"
    ).fillna(0)
    return last_four_months(inv.dropna(subset=["snapshot_date"]), "snapshot_date")


def build_product_table(fact: pd.DataFrame, inv: pd.DataFrame) -> pd.DataFrame:
    prod = fact.groupby(["product_id", "product_name", "category", "segment"], as_index=False).agg(
        NetRevenue=("NetRevenue", "sum"), Qty=("quantity", "sum"),
        Orders=("order_id", "nunique"), Customers=("customer_id", "nunique"),
        AvgDiscount=("discount_amount", "mean"), COGS_unit=("cogs", "first"),
    )
    prod["GrossProfit"] = prod["NetRevenue"] - prod["Qty"] * prod["COGS_unit"].fillna(0)
    prod["GrossMargin"] = prod["GrossProfit"] / prod["NetRevenue"].replace(0, np.nan)
    days = fact.groupby("product_id")["order_date"].apply(lambda s: s.dt.date.nunique())
    prod = prod.merge(days.rename("DaysWithSales"), on="product_id", how="left")
    latest_date = inv["snapshot_date"].max()
    latest = inv[inv["snapshot_date"].eq(latest_date)].groupby("product_id", as_index=False).agg(
        CurrentStock=("stock_on_hand", "sum"),
        DaysOfSupply=("days_of_supply", "mean") if "days_of_supply" in inv.columns else ("stock_on_hand", "mean"),
        OverstockFlag=("overstock_flag", "max") if "overstock_flag" in inv.columns else ("stock_on_hand", lambda s: 0),
    )
    prod = prod.merge(latest, on="product_id", how="left")
    prod[["CurrentStock", "DaysOfSupply", "OverstockFlag"]] = prod[
        ["CurrentStock", "DaysOfSupply", "OverstockFlag"]
    ].fillna(0)
    prod["FourMonthSellThrough"] = prod["Qty"] / (prod["Qty"] + prod["CurrentStock"]).replace(0, np.nan)
    return prod


def ps1_ranking(prod: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Top 5 doanh thu va Top 5 ton kho/kem hieu qua trong bon thang."""
    top5 = prod.sort_values(["NetRevenue", "Qty"], ascending=False).head(5).copy()
    ranked = prod.copy()
    ranked["LowRevenueRank"] = ranked["NetRevenue"].rank(pct=True, ascending=False)
    ranked["HighStockRank"] = ranked["CurrentStock"].rank(pct=True, ascending=True)
    ranked["LowSellThroughRank"] = ranked["FourMonthSellThrough"].rank(pct=True, ascending=False)
    ranked["InventoryRiskScore"] = (
        0.40 * ranked["LowRevenueRank"] + 0.35 * ranked["HighStockRank"] +
        0.25 * ranked["LowSellThroughRank"]
    ) * 100
    bottom5 = ranked.sort_values(
        ["InventoryRiskScore", "CurrentStock"], ascending=False
    ).head(5).copy()
    bottom5["Recommendation"] = "Giam nhap, khuyen mai xa ton hoac tinh gon SKU"
    show_table("PS1 - TOP 5 SAN PHAM THEO DOANH THU 4 THANG", top5)
    show_table("PS1 - TOP 5 SAN PHAM TON KHO/KEM HIEU QUA", bottom5)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    axes[0].barh(top5["product_name"], top5["NetRevenue"])
    axes[0].set_title("Top 5 doanh thu"); axes[0].set_xlabel("NetRevenue")
    axes[1].barh(bottom5["product_name"], bottom5["InventoryRiskScore"], color="tomato")
    axes[1].set_title("Top 5 rui ro ton kho"); axes[1].set_xlabel("InventoryRiskScore")
    plt.tight_layout(); plt.show()
    return top5, bottom5


def ps2_quantity_vs_margin(prod: pd.DataFrame) -> pd.DataFrame:
    q75 = prod["Qty"].quantile(0.75)
    margin_cutoff = min(0.05, prod["GrossMargin"].median())
    flagged = prod[(prod["Qty"] >= q75) & (prod["GrossMargin"] <= margin_cutoff)].copy()
    flagged["Recommendation"] = np.where(
        flagged["GrossMargin"] < 0, "Dung khuyen mai/kiem tra COGS va gia ban",
        "Dam phan COGS hoac tang gia co kiem soat; giu hang vi nhu cau cao",
    )
    flagged = flagged.sort_values("Qty", ascending=False)
    show_table("PS2 - NHU CAU CAO NHUNG BIEN LOI NHUAN THAP", flagged)
    plt.figure(figsize=(8, 6))
    colors = prod["category"].astype("category").cat.codes
    plt.scatter(prod["Qty"], prod["NetRevenue"], c=colors, s=20, alpha=0.6, cmap="tab10")
    plt.axvline(q75, color="gray", linestyle="--", linewidth=0.8)
    plt.xlabel("Quantity - 4 thang"); plt.ylabel("NetRevenue - 4 thang")
    plt.title("Nhu cau va doanh thu san pham")
    plt.tight_layout(); plt.show()
    return flagged


def ps3_class_effect(fact: pd.DataFrame) -> pd.DataFrame:
    """Danh gia anh huong cua Class bang tong hop product-month va eta squared."""
    sample = fact.assign(month=fact["order_date"].dt.to_period("M").dt.to_timestamp()).groupby(
        ["segment", "product_id", "month"], as_index=False
    ).agg(NetRevenue=("NetRevenue", "sum"), Qty=("quantity", "sum"))
    summary = sample.groupby("segment", as_index=False).agg(
        NetRevenue=("NetRevenue", "sum"), Qty=("Qty", "sum"),
        ProductMonths=("product_id", "size"), AvgRevenueProductMonth=("NetRevenue", "mean"),
        AvgQtyProductMonth=("Qty", "mean"),
    )

    def eta_squared(value_col: str) -> float:
        grand = sample[value_col].mean()
        ss_between = sum(len(g) * (g[value_col].mean() - grand) ** 2 for _, g in sample.groupby("segment"))
        ss_total = ((sample[value_col] - grand) ** 2).sum()
        return float(ss_between / ss_total) if ss_total else 0.0

    eta_revenue = eta_squared("NetRevenue"); eta_qty = eta_squared("Qty")
    interpretation = lambda x: "Manh" if x >= 0.14 else ("Vua" if x >= 0.06 else ("Nho" if x >= 0.01 else "Khong dang ke"))
    summary["RevenueEtaSquared"] = eta_revenue
    summary["RevenueEffect"] = interpretation(eta_revenue)
    summary["QuantityEtaSquared"] = eta_qty
    summary["QuantityEffect"] = interpretation(eta_qty)
    summary["AOV"] = summary["NetRevenue"] / fact.groupby("segment")["order_id"].nunique().reindex(summary["segment"]).to_numpy()
    show_table("PS3 - ANH HUONG CUA CLASS/SEGMENT", summary)
    summary.set_index("segment")[["NetRevenue", "Qty"]].plot(
        kind="bar", subplots=True, figsize=(11, 7), title=["Doanh thu theo Class", "So luong theo Class"]
    )
    plt.tight_layout(); plt.show()
    return summary


def ps4_turnover(inv: pd.DataFrame) -> pd.DataFrame:
    n_months = inv["snapshot_date"].dt.to_period("M").nunique()
    result = inv.groupby(["category", "segment"], as_index=False).agg(
        UnitsSold=("units_sold", "sum"), AvgStock=("stock_on_hand", "mean"),
        AvgFillRate=("fill_rate", "mean") if "fill_rate" in inv.columns else ("stock_on_hand", lambda s: np.nan),
        StockoutDays=("stockout_days", "sum") if "stockout_days" in inv.columns else ("stock_on_hand", lambda s: np.nan),
    )
    result["Contribution_%"] = result["UnitsSold"] / result["UnitsSold"].sum() * 100
    result["TurnoverAnnual"] = (result["UnitsSold"] / max(n_months, 1) * 12) / result["AvgStock"].replace(0, np.nan)
    rank = result["TurnoverAnnual"].rank(method="first", pct=True)
    result["TurnoverTier"] = pd.cut(rank, bins=[0, 1/3, 2/3, 1], labels=["Thap", "Trung binh", "Cao"], include_lowest=True)
    result["Recommendation"] = result["TurnoverTier"].map({
        "Cao": "Tang tan suat bo sung; duy tri safety stock va theo doi stockout",
        "Trung binh": "Duy tri muc nhap; toi uu danh muc theo contribution",
        "Thap": "Giam nhap; promotion xa ton va xem xet tinh gon SKU",
    }).astype(str)
    result = result.sort_values("TurnoverAnnual", ascending=False)
    show_table("PS4 - VONG QUAY THEO CATEGORY VA CLASS", result)
    labels = result["category"].astype(str) + " | " + result["segment"].astype(str)
    plt.figure(figsize=(11, 6)); plt.barh(labels, result["TurnoverAnnual"])
    plt.xlabel("Turnover Annual"); plt.title("Vong quay hang hoa theo Category/Class")
    plt.tight_layout(); plt.show()
    return result


def ps5_abc(prod: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = prod.sort_values("NetRevenue", ascending=False).copy()
    total = p["NetRevenue"].sum()
    p["RevenueShare"] = p["NetRevenue"] / total
    p["CumulativeRevenueShare"] = p["RevenueShare"].cumsum()
    p["CumulativeBefore"] = p["CumulativeRevenueShare"] - p["RevenueShare"]
    p["ABC"] = np.select(
        [p["CumulativeBefore"] < 0.80, p["CumulativeBefore"] < 0.95], ["A", "B"], default="C"
    )
    policies = {
        "A": "Kiem soat hang ngay; service level cao; safety stock theo bien dong nhu cau",
        "B": "Kiem soat hang tuan; dat hang dinh ky; toi uu lo dat",
        "C": "Kiem soat hang thang; giam ton; dat theo nhu cau hoac tinh gon SKU",
    }
    p["InventoryPolicy"] = p["ABC"].map(policies)
    show_table("PS5 - PHAN LOAI ABC TOAN BO SAN PHAM", p)
    summary = p.groupby("ABC", as_index=False).agg(
        NumSKU=("product_id", "count"), Revenue=("NetRevenue", "sum"), Qty=("Qty", "sum")
    )
    summary["RevenueShare_%"] = summary["Revenue"] / summary["Revenue"].sum() * 100
    summary["QtyShare_%"] = summary["Qty"] / summary["Qty"].sum() * 100
    summary["SKUShare_%"] = summary["NumSKU"] / summary["NumSKU"].sum() * 100
    summary["Policy"] = summary["ABC"].map(policies)
    show_table("PS5 - TONG HOP ABC VA CHINH SACH TON KHO", summary)
    plt.figure(figsize=(6, 4)); plt.bar(summary["ABC"], summary["RevenueShare_%"])
    plt.ylabel("Ty trong doanh thu (%)"); plt.title("Phan tich ABC - 4 thang")
    plt.tight_layout(); plt.show()
    return p, summary


def main():
    fact = load_fact_sales(); inv = load_inventory(); prod = build_product_table(fact, inv)
    show_table("PHAM VI PHAN TICH", pd.DataFrame([{
        "StartMonth": fact["order_date"].min().to_period("M").strftime("%Y-%m"),
        "EndMonth": fact["order_date"].max().to_period("M").strftime("%Y-%m"),
        "StatusIncluded": "delivered",
    }]))
    show_table("BANG HIEU SUAT SAN PHAM 4 THANG", prod)
    ps1_ranking(prod); ps2_quantity_vs_margin(prod); ps3_class_effect(fact)
    ps4_turnover(inv); ps5_abc(prod)
    print("\nHoan tat Problem 2. Tat ca bang va bieu do da hien thi truc tiep.")


if __name__ == "__main__":
    main()
