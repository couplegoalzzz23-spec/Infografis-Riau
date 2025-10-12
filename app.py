import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

# --- KONFIGURASI UTAMA ---
st.set_page_config(page_title="Infografis Prakiraan Cuaca - BMKG", layout="wide")
API_BASE = "https://cuaca.bmkg.go.id/api/df/v1/forecast/adm"

# ==============================
# 🚀 BAGIAN 1 — UTILITAS DASAR
# ==============================

@st.cache_data(ttl=3600)
def fetch_adm_mapping():
    """Ambil daftar ADM1 (provinsi) dari API BMKG."""
    url = "https://cuaca.bmkg.go.id/api/df/v1/adm"
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    data = r.json().get("data", [])
    df = pd.DataFrame(data)
    df["provinsi_lower"] = df["provinsi"].str.lower()
    return df

def resolve_adm1(input_text: str):
    """Konversi input (nama provinsi atau kode) menjadi kode ADM1 valid."""
    if input_text.isdigit():
        return input_text  # langsung return jika user masukkan kode angka
    df = fetch_adm_mapping()
    input_clean = input_text.strip().lower()
    match = df[df["provinsi_lower"].str.contains(input_clean)]
    if not match.empty:
        return match.iloc[0]["adm1"]
    return None

@st.cache_data(ttl=300)
def fetch_forecast(adm1: str):
    """Ambil data prakiraan cuaca BMKG berdasarkan kode ADM1."""
    params = {"adm1": adm1}
    resp = requests.get(API_BASE, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def flatten_cuaca_entry(entry):
    """Ubah struktur nested JSON BMKG ke DataFrame datar."""
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

# ==============================
# ⚙️ BAGIAN 2 — KONTROL SIDEBAR
# ==============================
st.sidebar.title("Kontrol Infografis")

user_input = st.sidebar.text_input("Nama Provinsi atau Kode ADM1", value="Jawa Timur")
refresh = st.sidebar.button("Ambil ulang data")

st.sidebar.markdown("---")
show_map = st.sidebar.checkbox("Tampilkan peta lokasi", value=True)
show_table = st.sidebar.checkbox("Tampilkan tabel data mentah", value=False)

# ==============================
# 🌤️ BAGIAN 3 — AMBIL DATA API
# ==============================
adm1 = resolve_adm1(user_input)
if adm1 is None:
    st.error(f"❌ Provinsi '{user_input}' tidak ditemukan di data BMKG.")
    st.stop()

st.title("Infografis Prakiraan Cuaca (BMKG)")
st.caption("Sumber data: https://cuaca.bmkg.go.id/api/df/v1/forecast/adm")

with st.spinner(f"Mengambil data prakiraan untuk ADM1 {adm1}..."):
    try:
        raw = fetch_forecast(adm1)
    except Exception as e:
        st.error(f"Gagal mengambil data dari BMKG: {e}")
        st.stop()

lokasi_meta = raw.get("lokasi", {})
entries = raw.get("data", [])
if not entries:
    st.warning("Tidak ada data untuk ADM1 ini.")
    st.stop()

# ==============================
# 📍 BAGIAN 4 — PILIH KOTA/KAB
# ==============================
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

# ==============================
# 🕓 BAGIAN 5 — FILTER WAKTU
# ==============================
df = df.sort_values(by="utc_datetime_dt")
min_dt = df["local_datetime_dt"].min()
max_dt = df["local_datetime_dt"].max()

if hasattr(min_dt, "to_pydatetime"): min_dt = min_dt.to_pydatetime()
if hasattr(max_dt, "to_pydatetime"): max_dt = max_dt.to_pydatetime()

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

# ==============================
# 📊 BAGIAN 6 — INFOGRAFIS
# ==============================
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
    st.metric(label=f"Cloud cover", value=f"{now_row.get('tcc', '—')}% / TP: {now_row.get('tp', '—')} mm")

# Grafik tren
st.markdown("---")
st.header("Grafik Tren — Parameter Utama")

if df_sel.empty:
    st.warning("Tidak ada data di rentang waktu yang dipilih.")
else:
    fig_t = px.line(df_sel, x="local_datetime_dt", y="t", markers=True, title="Suhu (°C)")
    fig_hu = px.line(df_sel, x="local_datetime_dt", y="hu", markers=True, title="Kelembaban (%)")
    fig_ws = px.line(df_sel, x="local_datetime_dt", y="ws", markers=True, title="Kecepatan Angin (m/s)")
    fig_tp = px.bar(df_sel, x="local_datetime_dt", y="tp", title="Curah Hujan (mm)")

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_t, use_container_width=True)
        st.plotly_chart(fig_hu, use_container_width=True)
    with c2:
        st.plotly_chart(fig_ws, use_container_width=True)
        st.plotly_chart(fig_tp, use_container_width=True)

# ==============================
# 🧾 BAGIAN 7 — TABEL CUACA
# ==============================
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
<thead><tr>""" + "".join([f"<th>{c}</th>" for c in cols_show]) + "</tr></thead><tbody>"

for _, r in timeline_show.iterrows():
    table_html += "<tr>" + "".join([f"<td>{r[c]}</td>" for c in cols_show]) + "</tr>"

table_html += "</tbody></table>"
st.markdown(table_html, unsafe_allow_html=True)

# ==============================
# 🗺️ BAGIAN 8 — PETA & EKSPOR
# ==============================
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

    # 🌪️ BAGIAN TAMBAHAN — WINDROSE
    st.markdown("### 🌪️ Distribusi Arah & Kecepatan Angin (Windrose)")
    try:
        if "wd_deg" in df_sel.columns and "ws" in df_sel.columns:
            fig_windrose = px.bar_polar(
                df_sel,
                r="ws",
                theta="wd_deg",
                color="ws",
                color_continuous_scale="blues",
                title="Windrose — Arah (°) vs Kecepatan (m/s)"
            )
            fig_windrose.update_traces(opacity=0.8)
            fig_windrose.update_layout(polar=dict(radialaxis=dict(showticklabels=True, ticks="")),
                                       showlegend=False)
            st.plotly_chart(fig_windrose, use_container_width=True)
        else:
            st.info("Data arah dan kecepatan angin tidak tersedia untuk lokasi ini.")
    except Exception as e:
        st.warning(f"Gagal menampilkan windrose: {e}")

if show_table:
    st.markdown("---")
    st.header("Tabel Data Mentah")
    st.dataframe(df_sel)

# Ekspor data
st.markdown("---")
st.header("Ekspor Data")

csv = df_sel.to_csv(index=False)
json_text = df_sel.to_json(orient="records", force_ascii=False, date_format="iso")

col_dl1, col_dl2 = st.columns(2)
with col_dl1:
    st.download_button("Unduh CSV", data=csv, file_name=f"forecast_adm1_{adm1}_{loc_choice}.csv", mime="text/csv")
with col_dl2:
    st.download_button("Unduh JSON", data=json_text, file_name=f"forecast_adm1_{adm1}_{loc_choice}.json", mime="application/json")

# ==============================
# 📋 BAGIAN 9 — FOOTER
# ==============================
st.markdown("""
---
**Catatan:**
- Input bisa berupa *nama provinsi* (misal: `Jawa Timur`, `DKI Jakarta`) atau langsung *kode ADM1* (misal: `35`).
- Data bersumber langsung dari API resmi BMKG.
- Gunakan mode layar penuh (F11) untuk tampilan optimal.
""")

st.caption("Aplikasi demo infografis prakiraan cuaca — data BMKG")
