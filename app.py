import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# =====================================
# 🔧 KONFIGURASI DASAR
# =====================================
st.set_page_config(page_title="Infografis Prakiraan Cuaca - BMKG", layout="wide")
API_BASE = "https://cuaca.bmkg.go.id/api/df/v1/forecast/adm"

@st.cache_data(ttl=300)
def fetch_forecast(adm1: str):
    """Fetch forecast JSON dari BMKG API berdasarkan kode ADM1."""
    params = {"adm1": adm1}
    resp = requests.get(API_BASE, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def flatten_cuaca_entry(entry):
    """Ubah data cuaca nested menjadi DataFrame datar dengan metadata lokasi."""
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
                "timezone": lokasi.get("timezone", "+0700"),
                "type": lokasi.get("type"),
            })
            try:
                r["utc_datetime_dt"] = pd.to_datetime(r.get("utc_datetime"))
                r["local_datetime_dt"] = pd.to_datetime(r.get("local_datetime"))
            except Exception:
                r["utc_datetime_dt"], r["local_datetime_dt"] = pd.NaT, pd.NaT
            rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    numeric_cols = ["t", "tcc", "tp", "wd_deg", "ws", "hu", "vs"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

# =====================================
# 🧭 SIDEBAR
# =====================================
st.sidebar.title("Kontrol Infografis")
adm1 = st.sidebar.text_input("Kode ADM1 (provinsi)", value="32")
refresh = st.sidebar.button("Ambil ulang data")

st.sidebar.markdown("---")
show_map = st.sidebar.checkbox("Tampilkan peta lokasi", value=True)
show_table = st.sidebar.checkbox("Tampilkan tabel data", value=False)

# =====================================
# 🛰️ AMBIL DATA
# =====================================
st.title("Infografis Prakiraan Cuaca (BMKG)")
st.markdown("Sumber: `https://cuaca.bmkg.go.id/api/df/v1/forecast/adm?adm1=<kode>`")

with st.spinner("Mengambil data..."):
    try:
        raw = fetch_forecast(adm1)
    except Exception as e:
        st.error(f"Gagal mengambil data: {e}")
        st.stop()

lokasi_meta = raw.get("lokasi", {})
entries = raw.get("data", [])
if not entries:
    st.warning("Tidak ada data untuk ADM1 ini.")
    st.stop()

mapping = {}
for e in entries:
    lok = e.get("lokasi", {})
    label = lok.get("kotkab") or lok.get("adm2") or f"Lokasi {len(mapping)+1}"
    key = lok.get("adm2") or lok.get("kotkab") or str(len(mapping)+1)
    mapping[label] = {"key": key, "entry": e}

col1, col2 = st.columns([2, 1])
with col1:
    prov_name = lokasi_meta.get("provinsi", "—")
    st.subheader(f"Provinsi: {prov_name}")
    loc_choice = st.selectbox("Pilih lokasi (Kabupaten/Kota)", options=list(mapping.keys()))
with col2:
    st.metric("Jumlah lokasi tersedia", len(mapping))

selected_entry = mapping[loc_choice]["entry"]
df = flatten_cuaca_entry(selected_entry)
if df.empty:
    st.warning("Data cuaca kosong untuk lokasi ini.")
    st.stop()

# =====================================
# ⏰ RENTANG WAKTU
# =====================================
df = df.sort_values(by="utc_datetime_dt")
min_dt, max_dt = df["local_datetime_dt"].min(), df["local_datetime_dt"].max()
if hasattr(min_dt, "to_pydatetime"): min_dt = min_dt.to_pydatetime()
if hasattr(max_dt, "to_pydatetime"): max_dt = max_dt.to_pydatetime()

st.sidebar.markdown("---")
start_dt = st.sidebar.slider(
    "Rentang waktu (lokal)",
    min_value=min_dt, max_value=max_dt,
    value=(min_dt, max_dt), format="DD-MM-YYYY HH:mm"
)
mask = (df["local_datetime_dt"] >= pd.to_datetime(start_dt[0])) & \
       (df["local_datetime_dt"] <= pd.to_datetime(start_dt[1]))
df_sel = df.loc[mask].copy()

# =====================================
# 📈 METRIK UTAMA
# =====================================
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
now_row = df_sel.iloc[0] if not df_sel.empty else df.iloc[0]
with r1c1: st.metric("Suhu (°C)", f"{now_row.get('t', '—')}°C")
with r1c2: st.metric("Kelembaban (%)", f"{now_row.get('hu', '—')}%")
with r1c3: st.metric("Kecepatan Angin (m/s)", f"{now_row.get('ws', '—')} m/s")
with r1c4:
    tcc, tp = now_row.get('tcc', '—'), now_row.get('tp', '—')
    st.metric("Awan & Curah Hujan", f"TP: {tp} mm", f"Cloud: {tcc}%")

# =====================================
# 📊 GRAFIK TREN
# =====================================
st.markdown("---")
st.header("Grafik Tren — Parameter Utama")

if not df_sel.empty:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="t", markers=True, title="Suhu (°C)"), use_container_width=True)
        st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="hu", markers=True, title="Kelembaban (%)"), use_container_width=True)
    with c2:
        st.plotly_chart(px.line(df_sel, x="local_datetime_dt", y="ws", markers=True, title="Kecepatan Angin (m/s)"), use_container_width=True)
        st.plotly_chart(px.bar(df_sel, x="local_datetime_dt", y="tp", title="Curah Hujan (mm)"), use_container_width=True)

# =====================================
# 🌬️ WINDROSE CHART (ENGLISH + KONTRAS)
# =====================================
st.markdown("---")
st.header("Windrose Diagram — Wind Direction & Speed Distribution")

try:
    if "wd_deg" in df_sel.columns and "ws" in df_sel.columns:
        df_wr = df_sel.dropna(subset=["wd_deg", "ws"]).copy()
        if not df_wr.empty:
            # 16 sektor arah (Inggris)
            bins_dir = np.arange(-11.25, 360, 22.5)
            labels_dir_en = [
                "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
            ]
            df_wr["dir_sector"] = pd.cut(
                df_wr["wd_deg"] % 360, bins=bins_dir,
                labels=labels_dir_en, include_lowest=True, right=False
            )

            # Kelas kecepatan (semakin tinggi → warna makin panas)
            speed_bins = [0, 2, 5, 10, 20, 100]
            speed_labels = ["<2", "2–5", "5–10", "10–20", ">20"]
            df_wr["speed_class"] = pd.cut(df_wr["ws"], bins=speed_bins, labels=speed_labels, include_lowest=True)

            # Hitung frekuensi tiap kombinasi arah-kecepatan
            freq = df_wr.groupby(["dir_sector", "speed_class"]).size().reset_index(name="count")
            freq["percent"] = freq["count"] / freq["count"].sum() * 100

            # Azimuth arah (°)
            azimuth_map = {
                "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90, "ESE": 112.5,
                "SE": 135, "SSE": 157.5, "S": 180, "SSW": 202.5, "SW": 225,
                "WSW": 247.5, "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5
            }
            freq["theta"] = freq["dir_sector"].map(azimuth_map)

            # Gradasi warna kontras (biru → hijau → kuning → oranye → merah)
            colors = ["#1E90FF", "#00FA9A", "#FFD700", "#FF8C00", "#FF0000"]

            # Plot Windrose
            fig_wr = go.Figure()
            for i, sc in enumerate(speed_labels):
                subset = freq[freq["speed_class"] == sc]
                fig_wr.add_trace(go.Barpolar(
                    r=subset["percent"], theta=subset["theta"],
                    name=f"{sc} m/s", marker_color=colors[i], opacity=0.9
                ))

            fig_wr.update_layout(
                title="Windrose — Wind Direction and Speed (%)",
                polar=dict(
                    angularaxis=dict(
                        direction="clockwise", rotation=90,
                        tickmode="array",
                        tickvals=list(range(0, 360, 45)),
                        ticktext=["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                    ),
                    radialaxis=dict(
                        ticksuffix="%", angle=45,
                        showline=True, gridcolor="lightgray"
                    )
                ),
                legend_title="Speed Class (m/s)",
                template="plotly_white",
                margin=dict(t=60, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_wr, use_container_width=True)
        else:
            st.info("Data arah atau kecepatan angin tidak tersedia.")
    else:
        st.info("Kolom 'wd_deg' dan 'ws' tidak ditemukan dalam data.")
except Exception as e:
    st.warning(f"Gagal membuat windrose: {e}")

# =====================================
# 🗺️ PETA
# =====================================
if show_map:
    st.markdown("---")
    st.header("Peta Lokasi")
    try:
        lat = float(selected_entry.get("lokasi", {}).get("lat", 0))
        lon = float(selected_entry.get("lokasi", {}).get("lon", 0))
        st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))
    except Exception as e:
        st.warning(f"Peta tidak tersedia: {e}")

# =====================================
# 📋 TABEL DATA & EKSPOR
# =====================================
if show_table:
    st.markdown("---")
    st.header("Tabel Data (Mentah)")
    st.dataframe(df_sel)

st.markdown("---")
st.header("Ekspor Data")
csv = df_sel.to_csv(index=False)
json_text = df_sel.to_json(orient="records", force_ascii=False, date_format="iso")
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button("Unduh CSV", data=csv,
                       file_name=f"forecast_adm1_{adm1}_{loc_choice}.csv",
                       mime="text/csv")
with col_dl2:
    st.download_button("Unduh JSON", data=json_text,
                       file_name=f"forecast_adm1_{adm1}_{loc_choice}.json",
                       mime="application/json")

# =====================================
# 📝 FOOTER
# =====================================
st.markdown("""
---
**Catatan:**
- Windrose menampilkan distribusi arah & kecepatan angin (dalam bahasa Inggris).  
- Semakin tinggi kecepatan angin, warna semakin "panas" (biru → merah).  
- Gunakan mode layar penuh (F11) untuk tampilan optimal.
""")
st.caption("Aplikasi demo infografis prakiraan cuaca — data BMKG © 2025")
