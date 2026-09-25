"""
Problem 2: Dinh bien va Phan loai San pham Kinh doanh

"""

import os

import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

ORDER_ITEMS_CSV = "order_items.csv"
ORDERS_CSV = "orders_enriched.csv"
PRODUCTS_CSV = "products.csv"
INVENTORY_CSV = "inventory.csv"
OUT_DIR = "output_problem2"


INVALID_STATUSES = {"cancelled", "created"}
MIN_DAYS_WITH_SALES = 30  # loai san pham qua moi khi xet Bottom 5

os.makedirs(OUT_DIR, exist_ok=True)


def load_fact_sales() -> pd.DataFrame:
    """NetRevenue = quantity*unit_price - discount_amount
    (discount_amount la SO TIEN chiet khau tuyet doi cua CA DONG hang)."""
    order_items = pd.read_csv(ORDER_ITEMS_CSV, low_memory=False)
    orders = pd.read_csv(ORDERS_CSV, parse_dates=["order_date"])
    products = pd.read_csv(PRODUCTS_CSV)

    fact = order_items.merge(
        orders[["order_id", "order_date", "order_status", "region", "customer_id"]],
        on="order_id", how="left",
    )
    fact = fact.merge(
        products[["product_id", "product_name", "category", "segment", "cogs", "price"]],
        on="product_id", how="left",
    )
    fact["line_gross"] = fact.quantity * fact.unit_price
    fact["NetRevenue"] = fact.line_gross - fact.discount_amount

    return fact[~fact.order_status.isin(INVALID_STATUSES)].copy()


def build_product_table(fact: pd.DataFrame) -> pd.DataFrame:
    prod = fact.groupby(["product_id", "product_name", "category", "segment"]).agg(
        NetRevenue=("NetRevenue", "sum"),
        Qty=("quantity", "sum"),
        Orders=("order_id", "nunique"),
        Customers=("customer_id", "nunique"),
        AvgDiscount=("discount_amount", "mean"),
        COGS_unit=("cogs", "first"),
    ).reset_index()

    prod["GrossProfit"] = prod.NetRevenue - prod.Qty * prod.COGS_unit
    prod["GrossMargin"] = prod.GrossProfit / prod.NetRevenue

    days = fact.groupby("product_id").order_date.apply(lambda s: s.dt.date.nunique())
    prod = prod.merge(days.rename("DaysWithSales"), on="product_id")
    return prod


def ps1_ranking(prod: pd.DataFrame):
    """PS1: Top5 ban chay nhat / Top5 ton kho-kem hieu qua nhat.
    Xep hang tren toan bo ky du lieu co san (sua filter theo thang o
    load_fact_sales() truoc khi goi ham nay neu de bai yeu cau 1 khoang
    thoi gian cu the)."""
    top5 = prod.sort_values("NetRevenue", ascending=False).head(5)
    bottom5 = (
        prod[prod.DaysWithSales >= MIN_DAYS_WITH_SALES]
        .sort_values("NetRevenue", ascending=True)
        .head(5)
    )
    top5.to_csv(f"{OUT_DIR}/top5_products.csv", index=False)
    bottom5.to_csv(f"{OUT_DIR}/bottom5_products.csv", index=False)
    print("[PS1] top5_products.csv, bottom5_products.csv da tao")


def ps2_quantity_vs_margin(prod: pd.DataFrame):
    """PS2: tuong quan Quantity vs Revenue, tim san pham SL cao / bien loi nhuan thap."""
    q75 = prod.Qty.quantile(0.75)
    flagged = prod[(prod.Qty >= q75) & (prod.GrossMargin < 0.05)].sort_values("Qty", ascending=False)
    flagged.to_csv(f"{OUT_DIR}/high_qty_low_margin_products.csv", index=False)
    print(f"[PS2] San pham SL cao nhung margin<5%: {len(flagged)}")

    plt.figure(figsize=(7, 6))
    colors = prod.category.astype("category").cat.codes
    plt.scatter(prod.Qty, prod.NetRevenue, c=colors, s=18, alpha=0.6, cmap="tab10")
    plt.axvline(q75, color="gray", linestyle="--", linewidth=0.8)
    plt.xlabel("Quantity")
    plt.ylabel("NetRevenue")
    plt.title("Quantity vs NetRevenue theo san pham (mau = category)")
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/chart_quantity_vs_revenue.png", dpi=120)
    plt.close()


def ps3_class_effect(fact: pd.DataFrame):
    """PS3: anh huong cua Class (segment) den hieu suat tieu thu - ANOVA."""
    groups_rev = [g.NetRevenue.values for _, g in fact.groupby("segment")]
    f_rev, p_rev = stats.f_oneway(*groups_rev)

    groups_qty = [g.quantity.values for _, g in fact.groupby("segment")]
    f_qty, p_qty = stats.f_oneway(*groups_qty)

    with open(f"{OUT_DIR}/class_effect_anova.txt", "w", encoding="utf-8") as f:
        f.write("ANOVA: NetRevenue theo Class (segment)\n")
        f.write(f"  F = {f_rev:.2f}, p-value = {p_rev:.4g}\n\n")
        f.write("ANOVA: Quantity theo Class (segment)\n")
        f.write(f"  F = {f_qty:.2f}, p-value = {p_qty:.4g}\n")
    print(f"[PS3] ANOVA: F(revenue)={f_rev:.1f} p={p_rev:.3g} | F(qty)={f_qty:.1f} p={p_qty:.3g}")

    seg_summary = fact.groupby("segment").agg(
        NetRevenue=("NetRevenue", "sum"), Qty=("quantity", "sum"), Orders=("order_id", "nunique")
    )
    seg_summary["AOV"] = seg_summary.NetRevenue / seg_summary.Orders
    seg_summary.to_csv(f"{OUT_DIR}/class_summary.csv")


def ps4_turnover(inv: pd.DataFrame):
    """PS4: luan chuyen hang hoa theo Category & Class."""
    n_months = inv.snapshot_date.nunique()
    cs = inv.groupby(["category", "segment"]).agg(
        UnitsSold=("units_sold", "sum"), AvgStock=("stock_on_hand", "mean")
    ).reset_index()

    total_units = cs.UnitsSold.sum()
    cs["ContribShare_%"] = (cs.UnitsSold / total_units * 100).round(2)
    cs["Turnover_Annual"] = ((cs.UnitsSold / n_months * 12) / cs.AvgStock).round(1)

    def tier(t):
        if t > 150:
            return "Cao"
        if t > 50:
            return "Trung binh"
        return "Thap"

    cs["TurnoverTier"] = cs.Turnover_Annual.apply(tier)
    cs = cs.sort_values("UnitsSold", ascending=False)
    cs.to_csv(f"{OUT_DIR}/turnover_by_category_class.csv", index=False)
    print("[PS4] turnover_by_category_class.csv da tao")


def ps5_abc(prod: pd.DataFrame):
    """PS5: phan loai ABC theo doanh thu tich luy."""
    p = prod.sort_values("NetRevenue", ascending=False).copy()
    p["cum_pct"] = p.NetRevenue.cumsum() / p.NetRevenue.sum()
    p["ABC"] = p.cum_pct.apply(lambda x: "A" if x <= 0.8 else ("B" if x <= 0.95 else "C"))
    p.to_csv(f"{OUT_DIR}/product_abc_full.csv", index=False)

    summary = p.groupby("ABC").agg(NumSKU=("product_id", "count"), Revenue=("NetRevenue", "sum"), Qty=("Qty", "sum"))
    summary["RevShare_%"] = (summary.Revenue / summary.Revenue.sum() * 100).round(1)
    summary["QtyShare_%"] = (summary.Qty / summary.Qty.sum() * 100).round(1)
    summary["SKUShare_%"] = (summary.NumSKU / summary.NumSKU.sum() * 100).round(1)
    summary.to_csv(f"{OUT_DIR}/abc_summary.csv")
    print("[PS5] product_abc_full.csv, abc_summary.csv da tao")

    plt.figure(figsize=(6, 4))
    plt.bar(summary.index, summary["RevShare_%"])
    plt.ylabel("% Doanh thu")
    plt.title("Ty trong doanh thu theo nhom ABC")
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/chart_abc.png", dpi=120)
    plt.close()


def main():
    fact = load_fact_sales()
    inv = pd.read_csv(INVENTORY_CSV)
    prod = build_product_table(fact)

    ps1_ranking(prod)
    ps2_quantity_vs_margin(prod)
    ps3_class_effect(fact)
    ps4_turnover(inv)
    ps5_abc(prod)

    print(f"\nHoan tat Problem 2. Ket qua trong: {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
