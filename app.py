import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# =====================================
# ⚙️ KONFIGURASI DASAR
# =====================================
st.set_page_config(page_title="Tactical Weather Ops — BMKG", layout="wide")

# 🌑 CSS — MILITARY STYLE + RADAR ANIMATION
st.markdown("""
<style>
body {
    background-color: #0b0c0c;
    color: #cfd2c3;
    font-family: "Consolas", "Roboto Mono", monospace;
}

/* --- Judul dan warna aksen --- */
h1, h2, h3, h4 {
    color: #a9df52;
    text-transform: uppercase;
    letter-spacing: 1px;
}

/* --- Sidebar --- */
section[data-testid="stSidebar"] {
    background-color: #111;
    color: #d0d3ca;
}

/* --- Tombol --- */
.stButton>button {
    background-color: #1a2a1f;
    color: #a9df52;
    border: 1px solid #3f4f3f;
    border-radius: 8px;
    font-weight: bold;
}
.stButton>button:hover {
    background-color: #2b3b2b;
    border-color: #a9df52;
}

/* --- Metric hijau --- */
div[data-testid="stMetricValue"] {
    color: #a9df52 !important;
}

/* --- Radar animation --- */
.radar {
  position: relative;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(20,255,50,0.05) 20%, transparent 21%),
              radial-gradient(circle, rgba(20,255,50,0.1) 10%, transparent 11%);
  background-size: 20px 20px;
  border: 2px solid #33ff55;
  overflow: hidden;
  margin: auto;
  box-shadow: 0 0 20px #33ff55;
}
.radar:before {
  content: "";
  position: absolute;
  top: 0; left: 0;
  width: 50%; height: 2px;
  background: linear-gradient(90deg, #33ff55, transparent);
  transform-origin: 100% 50%;
  animation: sweep 2.5s linear infinite;
}
@keyframes sweep {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* --- Footer --- */
hr, .stDivider {
    border-top: 1px solid #2f3a2f;
}
</style>
""", unsafe_allow_html=True)

# =====================================
# 📡 KONFIGURASI API
# =====================================
API_BASE = "https://cuaca.bmkg.go.id/api/df/v1/forecast/adm"
MS_TO_KT = 1.94384  # konversi ke knot

# =====================================
# 🧰 UTILITAS
# =====================================
@st.cache_data(ttl=300)
def fetch_forecast(adm1: str):
    params = {"adm1": adm1}
    resp = requests.get(API_BASE, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def flatten_cuaca_entry(entry):
    rows = []
    lokasi = entry.get("lokasi", {})
    for group in entry.get("cuaca", []):
        for obs in group:
            r = obs.copy()
            r.update({
                "adm1": lokasi.get("adm1"),
                "adm2": lokasi.get("adm2"),
                "provinsi": lokasi.get("provinsi"),
                "kotkab": lokasi.get("kotkab"),
                "lon": lokasi.get("lon"),
                "lat": lokasi.get("lat"),
            })
            try:
                r["utc_datetime_dt"] = pd.to_datetime(r.get("utc_datetime"))
                r["local_datetime_dt"] = pd.to_datetime(r.get("local_datetime"))
            except Exception:
                r["utc_datetime_dt"], r["local_datetime_dt"] = pd.NaT, pd.NaT
            rows.append(r)
    df = pd.DataFrame(rows)
    for c in ["t", "tcc", "tp", "wd_deg", "ws", "hu", "vs"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

# =====================================
# 🎚️ SIDEBAR
# =====================================
with st.sidebar:
    st.title("🛰️ Tactical Controls")
    adm1 = st.text_input("Province Code (ADM1)", value="32")
    st.markdown("<div class='radar'></div>", unsafe_allow_html=True)
    st.markdown("<p style='text-align:center; color:#5f5;'>Scanning Weather...</p>", unsafe_allow_html=True)
    refresh = st.button("🔄 Fetch Data")
    st.markdown("---")
    show_map = st.checkbox("Show Map", value=True)
    show_table = st.checkbox("Show Table", value=False)
    st.markdown("---")
    st.caption("Data Source: BMKG API\nTheme: Military Ops v1.0")

# =====================================
# 📡 PENGAMBILAN DATA
# =====================================
st.title("Tactical Weather Operations Dashboard")
st.markdown("*Source: BMKG Forecast API — Live Data*")

with st.spinner("🛰️ Acquiring weather intelligence..."):
    try:
        raw = fetch_forecast(adm1)
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        st.stop()

entries = raw.get("data", [])
if not entries:
    st.warning("No forecast data available.")
    st.stop()

mapping = {}
for e in entries:
    lok = e.get("lokasi", {})
    label = lok.get("kotkab") or lok.get("adm2") or f"Location {len(mapping)+1}"
    mapping[label] = {"entry": e}

col1, col2 = st.columns([2, 1])
with col1:
    loc_choice = st.selectbox("🎯 Select Location", options=list(mapping.keys()))
with col2:
    st.metric("📍 Locations", len(mapping))

selected_entry = mapping[loc_choice]["entry"]
df = flatten_cuaca_entry(selected_entry)
if df.empty:
    st.warning("No valid weather data found.")
    st.stop()

df["ws_kt"] = df["ws"] * MS_TO_KT

# =====================================
# 🕓 SLIDER WAKTU TANPA ERROR
# =====================================
df = df.sort_values("utc_datetime_dt")

if df["local_datetime_dt"].isna().all():
    st.error("No valid datetime available in dataset.")
    st.stop()

min_dt = df["local_datetime_dt"].dropna().min().to_pydatetime()
max_dt = df["local_datetime_dt"].dropna().max().to_pydatetime()

start_dt = st.sidebar.slider(
    "Time Range (Local)",
    min_value=min_dt,
    max_value=max_dt,
    value=(min_dt, max_dt),
    step=pd.Timedelta(hours=3)
)

mask = (df["local_datetime_dt"] >= pd.to_datetime(start_dt[0])) & \
       (df["local_datetime_dt"] <= pd.to_datetime(start_dt[1]))
df_sel = df.loc[mask].copy()

# =====================================
# ⚡ METRIC PANEL
# =====================================
st.markdown("---")
st.subheader("⚡ Tactical Weather Status")

now = df_sel.iloc[0]
c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("TEMP (°C)", f"{now.get('t', '—')}°C")
with c2: st.metric("HUMIDITY", f"{now.get('hu', '—')}%")
with c3: st.metric("WIND (KT)", f"{now.get('ws_kt', 0):.1f}")
with c4: st.metric("RAIN (mm)", f"{now.get('tp', '—')}")

# =====================================
# 📈 TREND GRAFIK
# =====================================
st.markdown("---")
st.subheader("📊 Parameter Trends")

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="t",
        title="Temperature (°C)", markers=True,
        color_discrete_sequence=["#a9df52"]), use_container_width=True)
    st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="hu",
        title="Humidity (%)", markers=True,
        color_discrete_sequence=["#00ffbf"]), use_container_width=True)
with c2:
    st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="ws_kt",
        title="Wind Speed (KT)", markers=True,
        color_discrete_sequence=["#00ffbf"]), use_container_width=True)
    st.plotly_chart(px.bar(df_sel, x="local_datetime_dt", y="tp",
        title="Rainfall (mm)",
        color_discrete_sequence=["#ffbf00"]), use_container_width=True)

# =====================================
# 🌪️ WINDROSE
# =====================================
st.markdown("---")
st.subheader("🌪️ Windrose — Direction & Speed")

if "wd_deg" in df_sel.columns and "ws_kt" in df_sel.columns:
    df_wr = df_sel.dropna(subset=["wd_deg", "ws_kt"])
    if not df_wr.empty:
        bins_dir = np.arange(-11.25, 360, 22.5)
        labels_dir = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]
        df_wr["dir_sector"] = pd.cut(df_wr["wd_deg"] % 360, bins=bins_dir, labels=labels_dir, include_lowest=True)
        speed_bins = [0,5,10,20,30,50,100]
        speed_labels = ["<5","5–10","10–20","20–30","30–50",">50"]
        df_wr["speed_class"] = pd.cut(df_wr["ws_kt"], bins=speed_bins, labels=speed_labels, include_lowest=True)
        freq = df_wr.groupby(["dir_sector","speed_class"]).size().reset_index(name="count")
        freq["percent"] = freq["count"]/freq["count"].sum()*100
        az_map = {"N":0,"NNE":22.5,"NE":45,"ENE":67.5,"E":90,"ESE":112.5,"SE":135,"SSE":157.5,
                  "S":180,"SSW":202.5,"SW":225,"WSW":247.5,"W":270,"WNW":292.5,"NW":315,"NNW":337.5}
        freq["theta"] = freq["dir_sector"].map(az_map)
        colors = ["#00ffbf","#80ff00","#d0ff00","#ffb300","#ff6600","#ff0033"]
        fig_wr = go.Figure()
        for i, sc in enumerate(speed_labels):
            subset = freq[freq["speed_class"]==sc]
            fig_wr.add_trace(go.Barpolar(
                r=subset["percent"], theta=subset["theta"],
                name=f"{sc} KT", marker_color=colors[i], opacity=0.85
            ))
        fig_wr.update_layout(
            title="Windrose (KT)",
            polar=dict(
                angularaxis=dict(direction="clockwise", rotation=90, tickvals=list(range(0,360,45))),
                radialaxis=dict(ticksuffix="%", showline=True, gridcolor="#333")
            ),
            legend_title="Wind Speed Class",
            template="plotly_dark"
        )
        st.plotly_chart(fig_wr, use_container_width=True)

# =====================================
# 🗺️ PETA
# =====================================
if show_map:
    st.markdown("---")
    st.subheader("🗺️ Tactical Map")
    try:
        lat = float(selected_entry.get("lokasi", {}).get("lat", 0))
        lon = float(selected_entry.get("lokasi", {}).get("lon", 0))
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))
    except Exception as e:
        st.warning(f"Map unavailable: {e}")

# =====================================
# 📋 TABEL
# =====================================
if show_table:
    st.markdown("---")
    st.subheader("📋 Forecast Table")
    st.dataframe(df_sel)

# =====================================
# 💾 EKSPOR
# =====================================
st.markdown("---")
st.subheader("💾 Export Data")

csv = df_sel.to_csv(index=False)
json_text = df_sel.to_json(orient="records", force_ascii=False, date_format="iso")
c1, c2 = st.columns(2)
with c1:
    st.download_button("⬇️ Download CSV", data=csv, file_name=f"{adm1}_{loc_choice}.csv", mime="text/csv")
with c2:
    st.download_button("⬇️ Download JSON", data=json_text, file_name=f"{adm1}_{loc_choice}.json", mime="application/json")

# =====================================
# ⚓ FOOTER
# =====================================
st.markdown("""
---
<div style="text-align:center; color:#7a7; font-size:0.9rem;">
Tactical Weather Ops Dashboard — BMKG Data © 2025<br>
Designed with Military Precision | Powered by Streamlit + Plotly
</div>
""", unsafe_allow_html=True)
