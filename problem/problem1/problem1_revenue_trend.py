"""
Problem 1: Hieu suat Doanh thu theo Dong thoi gian
"""

import os
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")

ORDER_ITEMS_CSV = "order_items.csv"
ORDERS_CSV = "orders_enriched.csv"
PRODUCTS_CSV = "products.csv"
OUT_DIR = "output_problem1"

INVALID_STATUSES = {"cancelled", "created"}  # don chua hop le, khong tinh doanh thu

os.makedirs(OUT_DIR, exist_ok=True)


def load_fact_sales() -> pd.DataFrame:
    """Ghep order_items + orders_enriched + products thanh 1 bang fact.

    NetRevenue = quantity*unit_price - discount_amount
    (discount_amount la SO TIEN chiet khau tuyet doi cua CA DONG hang,
    da xac minh bang cach doi chieu voi payments.csv)
    """
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
    fact["month"] = fact.order_date.dt.to_period("M").dt.to_timestamp()

    return fact[~fact.order_status.isin(INVALID_STATUSES)].copy()


def ps1_ps2_monthly_and_category(fact: pd.DataFrame):
    """PS1: tong doanh thu thuc te theo thang.
    PS2: bien dong ty trong dong gop cua tung CategoryName theo thang."""
    monthly = fact.groupby("month").agg(
        NetRevenue=("NetRevenue", "sum"),
        Orders=("order_id", "nunique"),
        Qty=("quantity", "sum"),
    ).reset_index()
    monthly["AOV"] = monthly.NetRevenue / monthly.Orders
    monthly["MoM_%"] = (monthly.NetRevenue.pct_change() * 100).round(2)
    monthly["RollingAvg3"] = monthly.NetRevenue.rolling(3).mean()
    monthly.to_csv(f"{OUT_DIR}/monthly_revenue.csv", index=False)

    cat_month = fact.groupby(["month", "category"]).NetRevenue.sum().reset_index()
    total_month = cat_month.groupby("month").NetRevenue.sum().rename("total_month")
    cat_month = cat_month.merge(total_month, on="month")
    cat_month["share_%"] = (cat_month.NetRevenue / cat_month.total_month * 100).round(2)
    cat_month.to_csv(f"{OUT_DIR}/category_monthly_share.csv", index=False)

    plt.figure(figsize=(11, 4))
    plt.plot(monthly.month, monthly.NetRevenue, label="NetRevenue")
    plt.plot(monthly.month, monthly.RollingAvg3, label="Rolling avg (3 thang)", linestyle="--")
    plt.title("Doanh thu thuan theo thang")
    plt.ylabel("VND")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/chart_monthly_revenue.png", dpi=120)
    plt.close()

    return monthly, cat_month


def ps3_growth_decline_alerts(monthly: pd.DataFrame):
    """PS3: MoM growth, thang tang/giam manh nhat, canh bao giam lien tiep."""
    monthly.nlargest(5, "MoM_%")[["month", "NetRevenue", "MoM_%"]].to_csv(
        f"{OUT_DIR}/top5_growth_months.csv", index=False)
    monthly.nsmallest(5, "MoM_%")[["month", "NetRevenue", "MoM_%"]].to_csv(
        f"{OUT_DIR}/top5_decline_months.csv", index=False)

    m = monthly.copy()
    m["decline"] = m["MoM_%"] < 0
    m["streak_id"] = (m.decline != m.decline.shift()).cumsum()
    streaks = m[m.decline].groupby("streak_id").agg(
        start=("month", "min"), end=("month", "max"), n_months=("month", "count")
    )
    alerts = streaks[streaks.n_months >= 2]
    alerts.to_csv(f"{OUT_DIR}/decline_streak_alerts.csv")
    print(f"[PS3] So chuoi suy giam lien tiep >=2 thang: {len(alerts)}")


def ps4_category_stability(cat_month: pd.DataFrame):
    """PS4: CV va xu huong (slope) theo category -> phan loai 4 nhom."""
    stats = cat_month.groupby("category").NetRevenue.agg(["mean", "std"])
    stats["CV"] = stats["std"] / stats["mean"]

    slopes = {}
    for cat, g in cat_month.groupby("category"):
        g = g.sort_values("month")
        x = np.arange(len(g))
        slopes[cat] = np.polyfit(x, g.NetRevenue.values, 1)[0]
    stats["slope"] = pd.Series(slopes)
    stats["avg_share_%"] = cat_month.groupby("category")["share_%"].mean()

    def classify(row):
        if row.slope > 0 and row.CV < 0.6:
            return "Tang truong"
        if row.CV >= 0.6:
            return "Bien dong manh"
        if row.slope < -50000:
            return "Suy giam"
        return "On dinh"

    stats["classification"] = stats.apply(classify, axis=1)
    stats.round(3).to_csv(f"{OUT_DIR}/category_stability.csv")
    print("[PS4] category_stability.csv da tao")


def ps5_forecast(monthly: pd.DataFrame):
    """PS5: du bao 3-6 thang bang SARIMA, kiem dinh do chinh xac tren
    holdout truoc khi du bao thuc te."""
    y = monthly.set_index("month").NetRevenue
    n_test = 6 if len(y) > 24 else 3  # can >=2 nam du lieu de bat mua vu 12 thang

    train, test = y.iloc[:-n_test], y.iloc[-n_test:]
    model = SARIMAX(train, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12),
                     enforce_stationarity=False, enforce_invertibility=False)
    fit = model.fit(disp=False)
    pred = fit.get_forecast(n_test).predicted_mean

    err = pred.values - test.values
    mape = float(np.mean(np.abs(err) / test.values) * 100)
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(np.mean(np.abs(err)))

    pd.DataFrame({"Actual": test.values, "Forecast": pred.values.round(0)}, index=test.index).to_csv(
        f"{OUT_DIR}/forecast_validation.csv")
    print(f"[PS5] Kiem dinh holdout {n_test} thang: MAE={mae:,.0f} RMSE={rmse:,.0f} MAPE={mape:.1f}%")

    model_full = SARIMAX(y, order=(1, 1, 1), seasonal_order=(1, 1, 1, 12),
                          enforce_stationarity=False, enforce_invertibility=False)
    fit_full = model_full.fit(disp=False)
    fc = fit_full.get_forecast(6)
    future = pd.DataFrame({
        "Forecast": fc.predicted_mean.round(0),
        "Low_80%": fc.conf_int(alpha=0.2).iloc[:, 0].round(0),
        "High_80%": fc.conf_int(alpha=0.2).iloc[:, 1].round(0),
    })
    future.to_csv(f"{OUT_DIR}/forecast_next_6_months.csv")
    print("[PS5] forecast_next_6_months.csv da tao")

    plt.figure(figsize=(11, 4))
    plt.plot(y.index, y.values, label="Thuc te")
    plt.plot(future.index, future.Forecast, label="Du bao", linestyle="--", marker="o")
    plt.fill_between(future.index, future["Low_80%"], future["High_80%"], alpha=0.2, label="Khoang tin cay 80%")
    plt.title("Doanh thu thuc te va du bao 6 thang tiep theo")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUT_DIR}/chart_forecast.png", dpi=120)
    plt.close()


def main():
    fact = load_fact_sales()
    monthly, cat_month = ps1_ps2_monthly_and_category(fact)
    ps3_growth_decline_alerts(monthly)
    ps4_category_stability(cat_month)
    ps5_forecast(monthly)
    print(f"\nHoan tat Problem 1. Ket qua trong: {os.path.abspath(OUT_DIR)}")


if __name__ == "__main__":
    main()
