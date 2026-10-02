
import os
import requests
import streamlit as st
import pandas as pd
from datetime import date, datetime

# ============================================
# PORTFOLIO DASHBOARD | ZAPI IDX
# ============================================
st.set_page_config(
    page_title="Portfolio Leo",
    page_icon="📈",
    layout="wide"
)

st.title("📈 Portfolio Dashboard")
st.caption("ZAPI IDX | ADRO • ADMR • ESSA • MEDC")

# PORTFOLIO SNAPSHOT
HOLDINGS = {
    "ADRO": {"lots": 261, "avg": 2066.36},
    "ADMR": {"lots": 355, "avg": 1589.32},
    "ESSA": {"lots": 1000, "avg": 612.68},
    "MEDC": {"lots": 82, "avg": 1471.10},
}
CASH = 20027683

# API CONFIG
try:
    API_KEY = st.secrets["ZAPI_API_KEY"]
except Exception:
    API_KEY = os.getenv("ZAPI_API_KEY", "")

URL = "https://api.zapi.ink/v1/finance:idx/stock-history"
HEADERS = {
    "x-api-key": API_KEY,
    "accept": "application/json"
}

# RESPONSE PARSER
def extract_rows(obj):
    if isinstance(obj, list):
        if not obj:
            return []
        if all(isinstance(x, dict) for x in obj):
            return obj
        for item in obj:
            rows = extract_rows(item)
            if rows:
                return rows
    elif isinstance(obj, dict):
        for key in (
            "data", "results", "result", "items",
            "rows", "stock_history"
        ):
            if key in obj:
                rows = extract_rows(obj[key])
                if rows:
                    return rows
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock(code, start_date, end_date):
    params = {
        "code": code,
        "from": start_date,
        "to": end_date,
        "length": 2000
    }
    response = requests.get(
        URL,
        headers=HEADERS,
        params=params,
        timeout=(20, 60)
    )
    response.raise_for_status()
    rows = extract_rows(response.json())
    if not rows:
        raise ValueError("Respons API tidak berisi data historis")

    df = pd.DataFrame(rows)
    df.columns = [str(c).lower().strip() for c in df.columns]

    aliases = {
        "date": ["date", "datetime", "timestamp",
                 "trading_date", "trade_date"],
        "open": ["open", "o"],
        "high": ["high", "h"],
        "low": ["low", "l"],
        "close": ["close", "c", "price", "last"],
        "volume": ["volume", "vol", "v"],
        "value": ["value", "turnover"]
    }

    rename = {}
    for target, names in aliases.items():
        for col in df.columns:
            if col in names:
                rename[col] = target
                break
    df = df.rename(columns=rename)

    if "close" not in df.columns:
        raise ValueError(
            "Kolom close tidak ditemukan: "
            + ", ".join(df.columns)
        )

    if "date" in df.columns:
        df["date"] = pd.to_datetime(
            df["date"], errors="coerce", utc=True
        ).dt.tz_convert("Asia/Jakarta").dt.tz_localize(None)
        df = df.dropna(subset=["date"])

    for col in ["open", "high", "low", "close",
                "volume", "value"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["close"])
    if "date" in df.columns:
        df = df.sort_values("date")
    return df.reset_index(drop=True)

# SIDEBAR
with st.sidebar:
    st.header("Pengaturan")
    start = st.date_input(
        "Mulai data",
        value=date(2024, 1, 1)
    )
    end = st.date_input(
        "Akhir data",
        value=date.today()
    )
    if st.button("🔄 Refresh data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.caption("Cache data: 5 menit")

if not API_KEY:
    st.error(
        "API key belum ditemukan. Atur ZAPI_API_KEY "
        "di Streamlit Cloud → Settings → Secrets."
    )
    st.stop()

if start > end:
    st.error("Tanggal mulai harus sebelum tanggal akhir.")
    st.stop()

# FETCH DATA
prices = {}
history = {}
errors = {}

with st.spinner("Mengambil data saham dari ZAPI..."):
    for code in HOLDINGS:
        try:
            df = fetch_stock(
                code, start.isoformat(), end.isoformat()
            )
            history[code] = df
            prices[code] = float(df.iloc[-1]["close"])
        except Exception as e:
            errors[code] = str(e)

for code, err in errors.items():
    st.warning(f"{code}: {err}")

# PORTFOLIO SUMMARY
st.subheader("Ringkasan Portofolio")

rows = []
for code, info in HOLDINGS.items():
    qty = info["lots"] * 100
    avg = info["avg"]
    price = prices.get(code)

    cost = qty * avg
    market = qty * price if price is not None else None
    pnl = market - cost if market is not None else None
    pct = pnl / cost * 100 if pnl is not None and cost else None

    rows.append({
        "Kode": code,
        "Lot": info["lots"],
        "Saham": qty,
        "Avg (Rp)": avg,
        "Harga (Rp)": price,
        "Modal (Rp)": cost,
        "Nilai Pasar (Rp)": market,
        "P&L (Rp)": pnl,
        "P&L (%)": pct
    })

table = pd.DataFrame(rows)
valid_table = table.dropna(subset=["Nilai Pasar (Rp)"])

invested = table["Modal (Rp)"].sum()
market_value = valid_table["Nilai Pasar (Rp)"].sum()
pnl_total = valid_table["P&L (Rp)"].sum()
equity = CASH + market_value
known_cost = valid_table["Modal (Rp)"].sum()
pnl_pct = pnl_total / known_cost * 100 if known_cost else 0

c1, c2 = st.columns(2)
c1.metric("Total Ekuitas", f"Rp {equity:,.0f}")
c2.metric("Cash", f"Rp {CASH:,.0f}")

c3, c4 = st.columns(2)
c3.metric("Nilai Pasar Saham", f"Rp {market_value:,.0f}")
c4.metric(
    "Floating P&L",
    f"Rp {pnl_total:,.0f}",
    f"{pnl_pct:+.2f}%"
)

if len(valid_table) < len(HOLDINGS):
    st.info(
        "Sebagian saham belum memiliki data harga. "
        "Total ekuitas dan P&L hanya menghitung saham "
        "yang berhasil diambil dari ZAPI."
    )

# HOLDINGS TABLE
st.subheader("Detail Kepemilikan")
display_table = table.copy()
for col in ["Avg (Rp)", "Harga (Rp)", "Modal (Rp)",
            "Nilai Pasar (Rp)", "P&L (Rp)"]:
    display_table[col] = display_table[col].map(
        lambda x: f"Rp {x:,.0f}" if pd.notna(x) else "N/A"
    )
display_table["P&L (%)"] = display_table["P&L (%)"].map(
    lambda x: f"{x:+.2f}%" if pd.notna(x) else "N/A"
)
st.dataframe(
    display_table,
    use_container_width=True,
    hide_index=True
)

# PRICE CHART
st.subheader("Grafik Harga")
available = list(history.keys())

if available:
    selected = st.selectbox("Pilih saham", available)
    df = history[selected]

    if "date" in df.columns:
        chart = df.set_index("date")[["close"]].rename(
            columns={"close": selected}
        )
        st.line_chart(chart)
    else:
        st.warning("Data tanggal tidak tersedia untuk grafik.")

    st.caption(
        f"Data terakhir {selected}: "
        + (
            df.iloc[-1]["date"].strftime("%d-%m-%Y")
            if "date" in df.columns else "tanggal tidak diketahui"
        )
        + ". Harga mengikuti respons terbaru dari ZAPI."
    )

    with st.expander("Lihat data historis"):
        st.dataframe(
            df.sort_values("date", ascending=False)
            if "date" in df.columns else df,
            use_container_width=True,
            hide_index=True
        )
else:
    st.error(
        "Tidak ada data yang berhasil diambil. "
        "Periksa Secrets, koneksi, dan format respons ZAPI."
    )

st.divider()
st.caption(
    "Dashboard portofolio | Harga dari ZAPI. "
    "P&L dihitung berdasarkan jumlah saham dan harga rata-rata "
    "yang diatur pada kode. Belum termasuk biaya transaksi, "
    "pajak, dan dividen."
)
