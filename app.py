import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import numpy as np

st.set_page_config(page_title="Infografis Prakiraan Cuaca - BMKG", layout="wide")

API_BASE = "https://cuaca.bmkg.go.id/api/df/v1/forecast/adm"

@st.cache_data(ttl=300)
def fetch_forecast(adm1: str):
    """Fetch forecast JSON from BMKG API for given adm1 code."""
    params = {"adm1": adm1}
    resp = requests.get(API_BASE, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def flatten_cuaca_entry(entry):
    """Convert cuaca nested lists into a flat DataFrame with metadata columns from entry['lokasi']"""
    rows = []
    lokasi = entry.get("lokasi", {})
    for group in entry.get("cuaca", []):
        for obs in group:
            r = obs.copy()
            # Tambahkan metadata lokasi
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
            # Parse datetime
            try:
                r["utc_datetime_dt"] = pd.to_datetime(r.get("utc_datetime"))
            except Exception:
                r["utc_datetime_dt"] = pd.NaT
            try:
                r["local_datetime_dt"] = pd.to_datetime(r.get("local_datetime"))
            except Exception:
                r["local_datetime_dt"] = pd.NaT
            rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    numeric_cols = ["t", "tcc", "tp", "wd_deg", "ws", "hu", "vs"]
    for c in numeric_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

# Sidebar controls
st.sidebar.title("Kontrol Infografis")
adm1 = st.sidebar.text_input("Kode ADM1 (provinsi)", value="32")
refresh = st.sidebar.button("Ambil ulang data")

st.sidebar.markdown("---")
show_map = st.sidebar.checkbox("Tampilkan peta lokasi", value=True)
show_table = st.sidebar.checkbox("Tampilkan tabel data", value=False)

# Main
st.title("Infografis Prakiraan Cuaca (BMKG)")
st.markdown("Sumber: `https://cuaca.bmkg.go.id/api/df/v1/forecast/adm?adm1=<kode>`")

# Fetch data
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

# Bangun mapping lokasi
mapping = {}
for e in entries:
    lok = e.get("lokasi", {})
    label = lok.get("kotkab") or lok.get("adm2") or f"Lokasi {len(mapping)+1}"
    key = lok.get("adm2") or lok.get("kotkab") or str(len(mapping)+1)
    mapping[label] = {"key": key, "entry": e}

# Pilih lokasi
col1, col2 = st.columns([2, 1])
with col1:
    prov_name = lokasi_meta.get("provinsi", "—")
    st.subheader(f"Provinsi: {prov_name}")
    loc_choice = st.selectbox("Pilih lokasi (Kabupaten/Kota)", options=list(mapping.keys()))
with col2:
    st.metric("Jumlah lokasi tersedia", len(mapping))

# Ambil data entry
selected_entry = mapping[loc_choice]["entry"]
df = flatten_cuaca_entry(selected_entry)
if df.empty:
    st.warning("Data cuaca kosong untuk lokasi ini.")
    st.stop()

df = df.sort_values(by="utc_datetime_dt")
min_dt = df["local_datetime_dt"].min()
max_dt = df["local_datetime_dt"].max()
if hasattr(min_dt, "to_pydatetime"):
    min_dt = min_dt.to_pydatetime()
if hasattr(max_dt, "to_pydatetime"):
    max_dt = max_dt.to_pydatetime()

# Sidebar rentang waktu
st.sidebar.markdown("---")
start_dt = st.sidebar.slider(
    "Rentang waktu (lokal)",
    min_value=min_dt,
    max_value=max_dt,
    value=(min_dt, max_dt),
    format="DD-MM-YYYY HH:mm"
)
mask = (df["local_datetime_dt"] >= pd.to_datetime(start_dt[0])) & (df["local_datetime_dt"] <= pd.to_datetime(start_dt[1]))
df_sel = df.loc[mask].copy()

# Top metrics
r1c1, r1c2, r1c3, r1c4 = st.columns(4)
now_row = df_sel.iloc[0] if not df_sel.empty else df.iloc[0]
with r1c1:
    st.markdown("**Suhu**")
    st.metric(label="°C", value=f"{now_row.get('t', '—')}°C")
with r1c2:
    st.markdown("**Kelembaban**")
    st.metric(label="RH (%)", value=f"{now_row.get('hu', '—')} %")
with r1c3:
    st.markdown("**Kecepatan Angin**")
    st.metric(label="m/s", value=f"{now_row.get('ws', '—')} m/s")
with r1c4:
    st.markdown("**Awan & Curah Hujan**")
    tcc = now_row.get('tcc', '—')
    tp = now_row.get('tp', '—')
    st.metric(label=f"Cloud cover: {tcc}%", value=f"TP: {tp} mm")

# Charts
st.markdown("---")
st.header("Grafik Tren — Parameter Utama")

if df_sel.empty:
    st.warning("Tidak ada data di rentang waktu yang dipilih.")
else:
    fig_t = px.line(df_sel, x="local_datetime_dt", y="t", markers=True, title="Suhu (°C)")
    fig_t.update_layout(yaxis_title="Temperature (°C)", xaxis_title="Waktu (Lokal)")

    fig_hu = px.line(df_sel, x="local_datetime_dt", y="hu", markers=True, title="Kelembaban (%)")
    fig_hu.update_layout(yaxis_title="Relative Humidity (%)", xaxis_title="Waktu (Lokal)")

    fig_ws = px.line(df_sel, x="local_datetime_dt", y="ws", markers=True, title="Kecepatan Angin (m/s)")
    fig_ws.update_layout(yaxis_title="Wind Speed (m/s)", xaxis_title="Waktu (Lokal)")

    fig_tp = px.bar(df_sel, x="local_datetime_dt", y="tp", title="Curah Hujan (mm)")
    fig_tp.update_layout(yaxis_title="Rainfall (mm)", xaxis_title="Waktu (Lokal)")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_t, use_container_width=True)
        st.plotly_chart(fig_hu, use_container_width=True)
    with c2:
        st.plotly_chart(fig_ws, use_container_width=True)
        st.plotly_chart(fig_tp, use_container_width=True)

# === Timeline Cuaca (Tabel Ringkas) ===
st.markdown("---")
st.header("Tabel Cuaca (Ringkas)")

timeline = df_sel.sort_values(by="local_datetime_dt")[
    ["local_datetime_dt", "weather_desc", "t", "hu", "ws", "tp", "image"]
].copy()
timeline["Waktu (Lokal)"] = timeline["local_datetime_dt"].dt.strftime("%d %b %Y %H:%M")
timeline["Suhu (°C)"] = timeline["t"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
timeline["Kelembaban (%)"] = timeline["hu"].apply(lambda x: f"{x:.0f}" if pd.notna(x) else "—")
timeline["Kecepatan Angin (m/s)"] = timeline["ws"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
timeline["Curah Hujan (mm)"] = timeline["tp"].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "—")
timeline["Cuaca"] = timeline.apply(
    lambda r: f"<img src='{r['image']}' width='36' height='36' style='vertical-align:middle;margin-right:6px;'/> {r['weather_desc']}",
    axis=1
)
cols_show = ["Waktu (Lokal)", "Cuaca", "Suhu (°C)", "Kelembaban (%)", "Kecepatan Angin (m/s)", "Curah Hujan (mm)"]
timeline_show = timeline[cols_show]

table_html = """
<style>
table.weather-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 14px;
}
table.weather-table th {
  background-color: #1e88e5;
  color: white;
  text-align: center;
  padding: 8px;
}
table.weather-table td {
  border-bottom: 1px solid #ddd;
  padding: 6px 8px;
  text-align: center;
}
table.weather-table tr:hover {
  background-color: #f1f5fb;
}
</style>
<table class='weather-table'>
<thead><tr>""" + "".join([f"<th>{c}</th>" for c in cols_show]) + "</tr></thead><tbody>"""

for _, r in timeline_show.iterrows():
    table_html += "<tr>" + "".join([f"<td>{r[c]}</td>" for c in cols_show]) + "</tr>"

table_html += "</tbody></table>"
st.markdown(table_html, unsafe_allow_html=True)

# === 🌬️ WINDROSE CHART (Profesional Style) ===
st.markdown("---")
st.header("Diagram Mawar Angin (Windrose)")

try:
    if "wd_deg" in df_sel.columns and "ws" in df_sel.columns:
        df_wr = df_sel.dropna(subset=["wd_deg", "ws"]).copy()
        if not df_wr.empty:
            # Bagi arah angin ke 16 sektor
            bins_dir = np.arange(-11.25, 360+22.5, 22.5)
            labels_dir = [
                "U", "UT", "UTL", "TL", "TLT", "T", "TGS", "TG", 
                "TGB", "S", "SBD", "BD", "BDB", "B", "BUL", "UL"
            ]
            df_wr["dir_sector"] = pd.cut(df_wr["wd_deg"] % 360, bins=bins_dir, labels=labels_dir, include_lowest=True)

            # Kelompokkan kecepatan angin
            speed_bins = [0, 2, 5, 10, 20, 100]
            speed_labels = ["<2", "2–5", "5–10", "10–20", ">20"]
            df_wr["speed_class"] = pd.cut(df_wr["ws"], bins=speed_bins, labels=speed_labels, include_lowest=True)

            # Hitung frekuensi (%) per sektor & kelas
            freq = (
                df_wr.groupby(["dir_sector", "speed_class"])
                .size()
                .reset_index(name="count")
            )
            freq["percent"] = freq["count"] / freq["count"].sum() * 100

            # Urutkan arah sesuai urutan azimut
            freq["theta"] = freq["dir_sector"].map({
                "U":0,"UT":22.5,"UTL":45,"TL":67.5,"TLT":90,"T":112.5,"TGS":135,"TG":157.5,
                "TGB":180,"S":202.5,"SBD":225,"BD":247.5,"BDB":270,"B":292.5,"BUL":315,"UL":337.5
            })

            # Buat windrose plot
            fig_wr = go.Figure()
            colors = px.colors.sequential.Blues[::-1][:len(speed_labels)]

            for i, sc in enumerate(speed_labels):
                subset = freq[freq["speed_class"] == sc]
                fig_wr.add_trace(go.Barpolar(
                    r=subset["percent"],
                    theta=subset["theta"],
                    name=f"{sc} m/s",
                    marker_color=colors[i],
                    opacity=0.9
                ))

            fig_wr.update_layout(
                title="Distribusi Arah & Kecepatan Angin (%)",
                polar=dict(
                    angularaxis=dict(
                        direction="clockwise",
                        rotation=90,
                        tickmode="array",
                        tickvals=list(range(0, 360, 45)),
                        ticktext=["U", "TL", "T", "TG", "S", "BD", "B", "BL"]
                    ),
                    radialaxis=dict(
                        ticksuffix="%",
                        angle=45,
                        showline=True,
                        linewidth=1,
                        gridcolor="lightgray"
                    )
                ),
                legend_title="Kelas Kecepatan",
                template="plotly_white",
                margin=dict(t=60, b=20, l=20, r=20)
            )
            st.plotly_chart(fig_wr, use_container_width=True)
        else:
            st.info("Data arah atau kecepatan angin tidak tersedia untuk periode ini.")
    else:
        st.info("Kolom 'wd_deg' dan 'ws' tidak ditemukan dalam data.")
except Exception as e:
    st.warning(f"Gagal membuat windrose: {e}")

# === PETA LOKASI ===
if show_map:
    st.markdown("---")
    st.header("Peta Lokasi")
    try:
        lat = float(selected_entry.get("lokasi", {}).get("lat", 0))
        lon = float(selected_entry.get("lokasi", {}).get("lon", 0))
        map_df = pd.DataFrame({"lat": [lat], "lon": [lon]})
        st.map(map_df)
    except Exception as e:
        st.warning(f"Peta tidak tersedia: {e}")

# === TABEL DATA MENTAH ===
if show_table:
    st.markdown("---")
    st.header("Tabel Data (Mentah)")
    st.dataframe(df_sel)

# === EKSPOR DATA ===
st.markdown("---")
st.header("Ekspor Data")
csv = df_sel.to_csv(index=False)
json_text = df_sel.to_json(orient="records", force_ascii=False, date_format="iso")
col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button("Unduh CSV", data=csv, file_name=f"forecast_adm1_{adm1}_{loc_choice}.csv", mime="text/csv")
with col_dl2:
    st.download_button("Unduh JSON", data=json_text, file_name=f"forecast_adm1_{adm1}_{loc_choice}.json", mime="application/json")

# === FOOTER ===
st.markdown("""
---
**Catatan:**
- Waktu lokal diambil dari field `local_datetime` di API.
- Jika ikon tidak tampil, jalankan aplikasi di lingkungan dengan akses internet.
- Gunakan mode layar penuh (F11) untuk tampilan optimal.
""")
st.caption("Aplikasi demo infografis prakiraan cuaca — data BMKG")
