"""Problem 1 - Hieu suat doanh thu theo dong thoi gian.

Chay truc tiep voi du lieu Silver cua du an. Doanh thu thuc te chi ghi
nhan cac don co ``order_status == 'delivered'``.
"""

from pathlib import Path
import warnings

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
VALID_REVENUE_STATUSES = {"delivered"}


def show_table(title: str, table: pd.DataFrame) -> None:
    """In day du bang tong hop ra terminal, khong ghi file trung gian."""
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    with pd.option_context("display.max_rows", None, "display.max_columns", None,
                           "display.width", 240, "display.float_format", "{:,.2f}".format):
        print(table.to_string(index=False))


def find_data_file(filename: str) -> Path:
    """Tim CSV Silver ma khong phu thuoc thu muc dang chay."""
    candidates = [SCRIPT_DIR / filename, REPO_ROOT / filename, REPO_ROOT / "silver_data" / filename]
    candidates.extend(sorted((REPO_ROOT / "silver_data").glob(
        f".silver_pipeline_work_*/excel/{filename}"
    ), reverse=True))
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(f"Khong tim thay {filename} trong du an {REPO_ROOT}")


def require_columns(df: pd.DataFrame, columns: set[str], source: str) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(f"{source} thieu cot bat buoc: {missing}")


def safe_divide(numerator, denominator):
    den = pd.Series(denominator).replace(0, np.nan)
    return pd.Series(numerator, index=den.index) / den


def load_fact_sales() -> pd.DataFrame:
    """Tao bang fact va chi giu doanh thu cua don da giao thanh cong."""
    order_items = pd.read_csv(find_data_file("order_items.csv"), low_memory=False)
    orders = pd.read_csv(find_data_file("orders_enriched.csv"), low_memory=False)
    products = pd.read_csv(find_data_file("products.csv"), low_memory=False)
    require_columns(order_items, {
        "order_id", "product_id", "quantity", "unit_price", "discount_amount"
    }, "order_items")
    require_columns(orders, {
        "order_id", "order_date", "order_status", "region", "customer_id"
    }, "orders_enriched")
    require_columns(products, {
        "product_id", "product_name", "category", "segment", "cogs", "price"
    }, "products")

    orders["order_date"] = pd.to_datetime(orders["order_date"], errors="coerce")
    orders["order_status"] = orders["order_status"].astype(str).str.strip().str.lower()
    orders = orders[orders["order_status"].isin(VALID_REVENUE_STATUSES)].copy()
    fact = order_items.merge(
        orders[["order_id", "order_date", "order_status", "region", "customer_id"]],
        on="order_id", how="inner", validate="many_to_one",
    ).merge(
        products[["product_id", "product_name", "category", "segment", "cogs", "price"]],
        on="product_id", how="left", validate="many_to_one",
    )
    numeric = ["quantity", "unit_price", "discount_amount", "cogs", "price"]
    fact[numeric] = fact[numeric].apply(pd.to_numeric, errors="coerce")
    fact = fact.dropna(subset=["order_date", "quantity", "unit_price", "category"])
    fact["GrossRevenue"] = fact["quantity"] * fact["unit_price"]
    fact["NetRevenue"] = (fact["GrossRevenue"] - fact["discount_amount"].fillna(0)).clip(lower=0)
    fact["month"] = fact["order_date"].dt.to_period("M").dt.to_timestamp()
    promo_cols = [c for c in ["promo_id", "promo_id_2"] if c in fact.columns]
    fact["HasPromotion"] = fact[promo_cols].notna().any(axis=1) if promo_cols else False
    return fact


def ps1_ps2_monthly_and_category(fact: pd.DataFrame):
    """Doanh thu thang va co cau doanh thu theo category."""
    monthly = fact.groupby("month").agg(
        GrossRevenue=("GrossRevenue", "sum"), NetRevenue=("NetRevenue", "sum"),
        DiscountAmount=("discount_amount", "sum"), Orders=("order_id", "nunique"),
        Qty=("quantity", "sum"),
        PromoOrders=("order_id", lambda s: s[fact.loc[s.index, "HasPromotion"]].nunique()),
    ).sort_index()
    full_months = pd.date_range(monthly.index.min(), monthly.index.max(), freq="MS")
    monthly = monthly.reindex(full_months, fill_value=0).rename_axis("month").reset_index()
    monthly["AOV"] = safe_divide(monthly["NetRevenue"], monthly["Orders"])
    monthly["QtyPerOrder"] = safe_divide(monthly["Qty"], monthly["Orders"])
    monthly["AvgSellingPrice"] = safe_divide(monthly["GrossRevenue"], monthly["Qty"])
    monthly["DiscountRate_%"] = safe_divide(monthly["DiscountAmount"], monthly["GrossRevenue"]) * 100
    monthly["PromoOrderShare_%"] = safe_divide(monthly["PromoOrders"], monthly["Orders"]) * 100
    monthly["MoM_%"] = monthly["NetRevenue"].pct_change().replace([np.inf, -np.inf], np.nan) * 100
    monthly["RollingAvg3"] = monthly["NetRevenue"].rolling(3, min_periods=1).mean()

    cat_month = fact.groupby(["month", "category"], as_index=False)["NetRevenue"].sum()
    all_idx = pd.MultiIndex.from_product(
        [full_months, sorted(fact["category"].dropna().unique())], names=["month", "category"]
    )
    cat_month = cat_month.set_index(["month", "category"]).reindex(all_idx, fill_value=0).reset_index()
    cat_month["total_month"] = cat_month.groupby("month")["NetRevenue"].transform("sum")
    cat_month["share_%"] = safe_divide(cat_month["NetRevenue"], cat_month["total_month"]) * 100
    show_table("PS1 - DOANH THU THUC TE THEO THANG", monthly)
    show_table("PS2 - TY TRONG DOANH THU CATEGORY THEO THANG", cat_month)

    plt.figure(figsize=(12, 5))
    plt.plot(monthly["month"], monthly["NetRevenue"], label="Doanh thu thuan", linewidth=1.2)
    plt.plot(monthly["month"], monthly["RollingAvg3"], label="Trung binh truot 3 thang", linestyle="--")
    plt.title("Doanh thu thuc te theo thang - don da giao")
    plt.ylabel("VND")
    plt.legend(); plt.tight_layout()
    plt.show()
    cat_month.pivot(index="month", columns="category", values="share_%").plot(figsize=(12, 5))
    plt.title("Bien dong ty trong doanh thu theo category"); plt.ylabel("Ty trong (%)")
    plt.tight_layout(); plt.show()
    return monthly, cat_month


def ps3_growth_decline_alerts(monthly: pd.DataFrame, cat_month: pd.DataFrame):
    """Xac dinh thang bien dong, phan ra driver va canh bao suy giam."""
    analysis = monthly.copy()
    for col in ["Orders", "QtyPerOrder", "AvgSellingPrice", "DiscountRate_%", "PromoOrderShare_%"]:
        analysis[f"{col}_MoM_%"] = analysis[col].pct_change().replace([np.inf, -np.inf], np.nan) * 100
    top_share = cat_month.loc[cat_month.groupby("month")["share_%"].idxmax(),
                              ["month", "category", "share_%"]]
    top_share = top_share.rename(columns={"category": "TopCategory", "share_%": "TopCategoryShare_%"})
    analysis = analysis.merge(top_share, on="month", how="left")
    analysis["TopCategoryShareChange_pp"] = analysis["TopCategoryShare_%"].diff()

    def cause(row):
        drivers = {
            "so don": row.get("Orders_MoM_%"),
            "so luong moi don": row.get("QtyPerOrder_MoM_%"),
            "gia ban binh quan": row.get("AvgSellingPrice_MoM_%"),
            "muc chiet khau": -row.get("DiscountRate_%_MoM_%") if pd.notna(row.get("DiscountRate_%_MoM_%")) else np.nan,
            "ty le khuyen mai": row.get("PromoOrderShare_%_MoM_%"),
            "product mix": row.get("TopCategoryShareChange_pp"),
        }
        valid = {k: v for k, v in drivers.items() if pd.notna(v)}
        return max(valid, key=lambda k: abs(valid[k])) if valid else "khong du du lieu"

    analysis["PrimaryDriver"] = analysis.apply(cause, axis=1)
    analysis["BusinessNote"] = np.where(
        analysis["MoM_%"] < 0,
        "Kiem tra driver am, promotion va mix; lap ke hoach phuc hoi thang tiep theo",
        "Duy tri driver tang truong; kiem tra bien loi nhuan truoc khi mo rong",
    )
    show_table("PS3 - PHAN RA NGUYEN NHAN TANG/GIAM THEO THANG", analysis)
    show_table("PS3 - TOP 5 THANG TANG TRUONG", analysis.nlargest(5, "MoM_%"))
    show_table("PS3 - TOP 5 THANG SUY GIAM", analysis.nsmallest(5, "MoM_%"))
    colors = np.where(analysis["MoM_%"].fillna(0) >= 0, "seagreen", "tomato")
    plt.figure(figsize=(13, 5))
    plt.bar(analysis["month"], analysis["MoM_%"].fillna(0), color=colors, width=20)
    plt.axhline(0, color="black", linewidth=0.8)
    plt.title("Tang truong doanh thu MoM"); plt.ylabel("MoM (%)")
    plt.tight_layout(); plt.show()
    m = analysis[["month", "NetRevenue", "MoM_%"]].copy()
    m["decline"] = m["MoM_%"] < 0
    m["streak_id"] = m["decline"].ne(m["decline"].shift()).cumsum()
    alerts = m[m["decline"]].groupby("streak_id").agg(
        start=("month", "min"), end=("month", "max"), n_months=("month", "count"),
        end_revenue=("NetRevenue", "last"), worst_mom_pct=("MoM_%", "min"),
    )
    alerts = alerts[alerts["n_months"] >= 2]
    alerts["Alert"] = "CANH BAO: doanh thu giam lien tiep tu 2 thang"
    show_table("PS3 - CANH BAO GIAM LIEN TIEP TU 2 THANG", alerts.reset_index())
    print(f"[PS3] So chuoi suy giam lien tiep >=2 thang: {len(alerts)}")
    return analysis, alerts


def ps4_category_stability(cat_month: pd.DataFrame) -> pd.DataFrame:
    """Danh gia on dinh, tang truong, bien dong va suy giam theo category."""
    rows = []
    for category, group in cat_month.groupby("category"):
        group = group.sort_values("month")
        values = group["NetRevenue"].to_numpy(dtype=float)
        mean = values.mean(); std = values.std(ddof=1) if len(values) > 1 else 0.0
        slope = np.polyfit(np.arange(len(values)), values, 1)[0] if len(values) > 1 else 0.0
        rows.append({"category": category, "MeanRevenue": mean, "StdRevenue": std,
                     "CV": std / mean if mean else np.nan, "Slope": slope,
                     "NormalizedSlope": slope / mean if mean else 0.0,
                     "AvgShare_%": group["share_%"].mean()})
    result = pd.DataFrame(rows)

    def classify(row):
        if row["NormalizedSlope"] <= -0.01: return "Suy giam"
        if row["CV"] >= 0.60: return "Bien dong manh"
        if row["NormalizedSlope"] >= 0.01: return "Tang truong"
        return "On dinh"

    recommendations = {
        "Tang truong": "Uu tien dau tu ton kho va marketing; dat muc tieu cao hon du bao co so",
        "On dinh": "Duy tri muc ton kho toi uu; khai thac cross-sell va bao ve thi phan",
        "Bien dong manh": "Giam cam ket ton kho dai han; dung safety stock va chien dich linh hoat",
        "Suy giam": "Ra soat danh muc, gia, promotion va nhu cau; phuc hoi hoac tinh gon SKU",
    }
    result["Classification"] = result.apply(classify, axis=1)
    result["Priority"] = np.where(
        result["Classification"].isin(["Tang truong", "On dinh"]) &
        (result["AvgShare_%"] >= result["AvgShare_%"].median()), "Uu tien dau tu", "Uu tien cai thien"
    )
    result["Recommendation"] = result["Classification"].map(recommendations)
    show_table("PS4 - DO ON DINH, XU HUONG VA UU TIEN CATEGORY", result)
    # Bubble chart: truc X = muc bien dong, truc Y = toc do xu huong,
    # kich thuoc bong bong = ty trong doanh thu binh quan.
    color_map = {
        "Tang truong": "#2E8B57",
        "On dinh": "#2471A3",
        "Bien dong manh": "#F39C12",
        "Suy giam": "#C0392B",
    }
    fig, ax = plt.subplots(figsize=(12, 8))
    y_values = result["NormalizedSlope"] * 100
    x_max = max(0.80, float(result["CV"].max()) * 1.25)
    y_padding = max(float(y_values.max() - y_values.min()) * 0.18, 0.8)
    y_min, y_max = float(y_values.min() - y_padding), float(y_values.max() + y_padding)

    ax.axvspan(0.60, x_max, color="#FDEBD0", alpha=0.55, zorder=0)
    ax.axhspan(1.0, y_max, color="#E8F8F5", alpha=0.45, zorder=0)
    ax.axhspan(y_min, -1.0, color="#FADBD8", alpha=0.40, zorder=0)
    ax.axvline(0.60, color="#B9770E", linestyle="--", linewidth=1.4,
               label="Nguong bien dong CV = 0.60")
    ax.axhline(1.0, color="#1E8449", linestyle="--", linewidth=1.2,
               label="Nguong tang truong = 1%/thang")
    ax.axhline(-1.0, color="#922B21", linestyle="--", linewidth=1.2,
               label="Nguong suy giam = -1%/thang")
    ax.axhline(0, color="#566573", linewidth=0.8)

    offsets = [(12, 14), (12, -22), (-88, 14), (-88, -22)]
    for position, (_, row) in enumerate(result.sort_values("AvgShare_%", ascending=False).iterrows()):
        x_value = float(row["CV"])
        y_value = float(row["NormalizedSlope"] * 100)
        bubble_size = 180 + float(row["AvgShare_%"]) * 32
        ax.scatter(
            x_value, y_value, s=bubble_size,
            color=color_map[row["Classification"]], edgecolor="white",
            linewidth=1.8, alpha=0.88, zorder=3,
        )
        dx, dy = offsets[position % len(offsets)]
        ax.annotate(
            f'{row["category"]}\nShare: {row["AvgShare_%"]:.1f}%',
            xy=(x_value, y_value), xytext=(dx, dy), textcoords="offset points",
            fontsize=9, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="white",
                      edgecolor=color_map[row["Classification"]], alpha=0.92),
            arrowprops=dict(arrowstyle="-", color="#7B7D7D", linewidth=0.8),
            zorder=4,
        )

    legend_items = [
        Line2D([0], [0], marker="o", color="w", label=label,
               markerfacecolor=color, markeredgecolor="white", markersize=10)
        for label, color in color_map.items()
    ]
    threshold_items = [
        Line2D([0], [0], color="#B9770E", linestyle="--", label="CV = 0.60"),
        Line2D([0], [0], color="#1E8449", linestyle="--", label="Tang = 1%/thang"),
        Line2D([0], [0], color="#922B21", linestyle="--", label="Giam = -1%/thang"),
    ]
    ax.legend(handles=legend_items + threshold_items, loc="best", frameon=True,
              title="Phan loai va nguong")
    ax.set_xlim(0, x_max); ax.set_ylim(y_min, y_max)
    ax.set_xlabel("He so bien thien CV - cang sang phai cang bien dong")
    ax.set_ylabel("Xu huong doanh thu (% doanh thu TB moi thang)")
    ax.set_title("Ma tran on dinh - xu huong Category\nKich thuoc bong bong = ty trong doanh thu binh quan")
    ax.grid(True, linestyle=":", alpha=0.35)
    plt.tight_layout(); plt.show()
    return result


def _design_matrix(index: pd.DatetimeIndex, positions: np.ndarray) -> np.ndarray:
    month = index.month.to_numpy()
    seasonal = np.column_stack([(month == value).astype(float) for value in range(2, 13)])
    return np.column_stack([np.ones(len(index)), positions, seasonal])


def seasonal_trend_forecast(series: pd.Series, horizon: int):
    """Hoi quy xu huong + mua vu thang, khong phu thuoc statsmodels."""
    series = series.astype(float).sort_index(); n = len(series)
    x = _design_matrix(pd.DatetimeIndex(series.index), np.arange(n, dtype=float))
    beta = np.linalg.lstsq(x, series.to_numpy(), rcond=None)[0]
    fitted = x @ beta
    future_index = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    xf = _design_matrix(future_index, np.arange(n, n + horizon, dtype=float))
    forecast = np.maximum(xf @ beta, 0)
    residuals = series.to_numpy() - fitted
    sigma = residuals.std(ddof=1) if len(residuals) > 1 else 0.0
    return pd.Series(forecast, index=future_index), float(sigma)


def ps5_forecast(monthly: pd.DataFrame):
    """Kiem dinh holdout va du bao 6 thang kem de xuat kinh doanh."""
    y = monthly.set_index("month")["NetRevenue"].asfreq("MS", fill_value=0)
    if len(y) < 18: raise ValueError("Can toi thieu 18 thang de danh gia xu huong va mua vu")
    n_test = 6 if len(y) >= 30 else 3
    train, test = y.iloc[:-n_test], y.iloc[-n_test:]
    pred, _ = seasonal_trend_forecast(train, n_test); pred.index = test.index
    error = pred - test
    mae = float(error.abs().mean()); rmse = float(np.sqrt(np.mean(error ** 2)))
    smape = float((200 * error.abs() / (test.abs() + pred.abs()).replace(0, np.nan)).mean())
    validation = pd.DataFrame({"Actual": test, "Forecast": pred, "Error": error})
    validation["AbsolutePercentageError_%"] = error.abs() / test.abs().replace(0, np.nan) * 100
    show_table("PS5 - DOI CHIEU THUC TE VA DU BAO HOLDOUT", validation.reset_index(names="month"))

    future, sigma = seasonal_trend_forecast(y, 6); z80 = 1.281551565545
    result = pd.DataFrame({"Forecast": future, "Low_80%": np.maximum(future - z80 * sigma, 0),
                           "High_80%": future + z80 * sigma})
    baseline = y.tail(3).mean()
    result["VsRecent3M_%"] = (result["Forecast"] / baseline - 1) * 100
    result["InventoryAction"] = np.where(
        result["VsRecent3M_%"] >= 5, "Tang safety stock co chon loc",
        np.where(result["VsRecent3M_%"] <= -5, "Giam mua va xa hang cham", "Duy tri ton kho"))
    result["MarketingAction"] = np.where(
        result["VsRecent3M_%"] < 0, "Kich hoat chien dich phuc hoi nhu cau", "Tap trung nhom tang truong")
    result["BudgetGuidance"] = "Lap ngan sach theo Forecast; dung Low/High 80% lam kich ban xau/tot"
    result["TargetRevenue"] = result["Forecast"] * 1.03
    show_table("PS5 - DU BAO 6 THANG VA KHUYEN NGHI", result.reset_index(names="month"))
    metrics = pd.DataFrame([{"MAE": mae, "RMSE": rmse, "sMAPE_%": smape,
                             "HoldoutMonths": n_test}])
    show_table("PS5 - CHI SO SAI SO DU BAO", metrics)
    print(f"[PS5] Holdout {n_test} thang: MAE={mae:,.0f}; RMSE={rmse:,.0f}; sMAPE={smape:.2f}%")
    plt.figure(figsize=(12, 5)); plt.plot(y.index, y.values, label="Thuc te")
    plt.plot(result.index, result["Forecast"], label="Du bao", linestyle="--", marker="o")
    plt.fill_between(result.index, result["Low_80%"], result["High_80%"], alpha=0.2, label="Khoang 80%")
    plt.title("Doanh thu thuc te va du bao 6 thang"); plt.legend(); plt.tight_layout()
    plt.show()
    return result


def main():
    fact = load_fact_sales()
    monthly, cat_month = ps1_ps2_monthly_and_category(fact)
    ps3_growth_decline_alerts(monthly, cat_month)
    ps4_category_stability(cat_month)
    ps5_forecast(monthly)
    print("\nHoan tat Problem 1. Tat ca bang va bieu do da hien thi truc tiep.")


if __name__ == "__main__":
    main()
