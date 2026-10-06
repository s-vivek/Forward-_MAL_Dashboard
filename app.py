"""
Forward MAL Dashboard — Streamlit + Google Drive
Data downloads automatically from Google Drive on startup.
"""
import os, glob, warnings, io, time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import requests

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="Forward MAL Dashboard",
    page_icon="🔴",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebar"]{background:#1A5276}
[data-testid="stSidebar"] *{color:#fff !important}
.kpi-card{background:#fff;border-radius:8px;padding:14px 16px;
          border-left:4px solid #ccc;box-shadow:0 2px 6px rgba(0,0,0,.08);text-align:center}
</style>
""", unsafe_allow_html=True)

FOLDER_ID = "1rYrKfRRO45dbmank4fcHG81CaTS5a9x2"
COLS = ["origin_party_id","destination_party_id","external_id",
        "updated_at","fsn","add_excess_variance_id",
        "Qty","Value","cms_vertical","DS City","Zone","Store Name","Remark"]
TOP_N = 15

# ── Google Drive helpers ─────────────────────────────────────
def gdrive_list(folder_id):
    """List all files recursively in a public Google Drive folder."""
    API = "https://www.googleapis.com/drive/v3/files"
    KEY = st.secrets.get("GDRIVE_API_KEY", "")  # optional API key
    files = []
    queue = [folder_id]
    while queue:
        fid = queue.pop()
        params = {
            "q": f"'{fid}' in parents and trashed=false",
            "fields": "files(id,name,mimeType)",
            "pageSize": 1000,
        }
        if KEY:
            params["key"] = KEY
        try:
            r = requests.get(API, params=params, timeout=30)
            items = r.json().get("files", [])
        except Exception:
            items = []
        for item in items:
            if item["mimeType"] == "application/vnd.google-apps.folder":
                queue.append(item["id"])
            elif item["name"].endswith((".csv", ".xlsx")):
                files.append(item)
    return files

def gdrive_download(file_id):
    """Download a file from Google Drive by file ID."""
    url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
    session = requests.Session()
    r = session.get(url, stream=True, timeout=60)
    # Handle large file warning page
    for key, val in r.cookies.items():
        if "download_warning" in key:
            r = session.get(url, params={"confirm": val}, stream=True, timeout=120)
            break
    content = b""
    for chunk in r.iter_content(chunk_size=1024*1024):
        content += chunk
    return content

# ── Load data ────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_data():
    status = st.empty()
    status.info("🔄 Connecting to Google Drive...")

    files = gdrive_list(FOLDER_ID)
    if not files:
        st.error("No CSV/XLSX files found in Google Drive folder. "
                 "Make sure the folder is shared publicly (Anyone with link).")
        st.stop()

    status.info(f"🔄 Found {len(files)} file(s). Downloading... (this may take a few minutes on first load)")
    dfs = []
    for i, f in enumerate(files, 1):
        status.info(f"🔄 Downloading {i}/{len(files)}: {f['name']}")
        try:
            content = gdrive_download(f["id"])
            ext = os.path.splitext(f["name"])[1].lower()
            if ext == ".xlsx":
                tmp = pd.read_excel(io.BytesIO(content), engine="openpyxl")
            else:
                try:    tmp = pd.read_csv(io.BytesIO(content), encoding="utf-8",   low_memory=False)
                except: tmp = pd.read_csv(io.BytesIO(content), encoding="latin1", low_memory=False)
            existing = [c for c in COLS if c in tmp.columns]
            if existing:
                dfs.append(tmp[existing])
        except Exception as e:
            st.warning(f"Skipped {f['name']}: {e}")

    if not dfs:
        st.error("No data loaded. Check file format and Drive permissions.")
        st.stop()

    df = pd.concat(dfs, ignore_index=True)
    df = df.loc[:, ~df.columns.duplicated()]

    df["Value"] = pd.to_numeric(df["Value"], errors="coerce").fillna(0)
    df["Qty"]   = pd.to_numeric(df["Qty"],   errors="coerce").fillna(0)

    raw = df["updated_at"].astype(str).str.strip()
    raw = raw.str.replace(
        r'(\d{4}-\d{2}-\d{2})[T ](\d{2})\.(\d{2})\.(\d{2})',
        r'\1 \2:\3:\4', regex=True)
    df["updated_at"]  = pd.to_datetime(raw, errors="coerce", dayfirst=False)
    df["Date"]        = df["updated_at"].dt.strftime("%Y-%m-%d")
    df["Month"]       = df["updated_at"].dt.strftime("%Y-%m")
    df["MonthLabel"]  = df["updated_at"].dt.strftime("%b %Y")
    shifted           = df["updated_at"] + pd.Timedelta(days=1)
    df["WeekNum"]     = shifted.dt.isocalendar().week.astype("Int64")
    df["YearWeek"]    = shifted.dt.strftime("%Y-W%V")
    df["WeekLabel"]   = "W" + df["WeekNum"].astype(str)

    for c in ["origin_party_id","destination_party_id","cms_vertical",
              "DS City","Zone","Store Name","Remark"]:
        if c in df.columns:
            df[c] = df[c].fillna("Unknown").astype(str).str.strip()

    status.empty()
    return df, len(files)

DF, n_files = load_data()

# ── Sidebar filters ──────────────────────────────────────────
st.sidebar.title("🔴 Forward MAL")
st.sidebar.markdown(f"**{n_files} file(s) · {len(DF):,} records**")
st.sidebar.markdown("---")

month_opts   = sorted(DF["Month"].dropna().unique().tolist())
month_labels = {m: DF[DF["Month"]==m]["MonthLabel"].iloc[0] for m in month_opts}
sel_months   = st.sidebar.multiselect("Month", options=month_opts,
                                      format_func=lambda x: month_labels.get(x, x))

week_opts  = (DF.groupby(["YearWeek","WeekLabel"]).size()
                .reset_index().sort_values("YearWeek")["WeekLabel"].tolist())

def ms(label, col):
    opts = sorted(DF[col].dropna().unique().tolist())
    return st.sidebar.multiselect(label, opts)

sel_weeks  = st.sidebar.multiselect("Week", week_opts)
sel_origin = ms("Origin Party",  "origin_party_id")
sel_dest   = ms("Dest Party",    "destination_party_id")
sel_vert   = ms("Vertical",      "cms_vertical")
sel_city   = ms("DS City",       "DS City")
sel_zone   = ms("Zone",          "Zone")
sel_store  = ms("Store Name",    "Store Name")
sel_remark = ms("Remark",        "Remark")

st.sidebar.markdown("---")
do_reset = st.sidebar.button("✕ Reset All", use_container_width=True)
if do_reset:
    st.rerun()

# ── Filter ───────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def filter_df(months, weeks, origins, dests, verts, cities, zones, stores, remarks):
    df = DF.copy()
    if months:  df = df[df["Month"].isin(months)]
    if weeks:   df = df[df["WeekLabel"].isin(weeks)]
    if origins: df = df[df["origin_party_id"].isin(origins)]
    if dests:   df = df[df["destination_party_id"].isin(dests)]
    if verts:   df = df[df["cms_vertical"].isin(verts)]
    if cities:  df = df[df["DS City"].isin(cities)]
    if zones:   df = df[df["Zone"].isin(zones)]
    if stores:  df = df[df["Store Name"].isin(stores)]
    if remarks: df = df[df["Remark"].isin(remarks)]
    return df

df = filter_df(
    tuple(sel_months), tuple(sel_weeks), tuple(sel_origin),
    tuple(sel_dest), tuple(sel_vert), tuple(sel_city),
    tuple(sel_zone), tuple(sel_store), tuple(sel_remark)
)

# ── Header ───────────────────────────────────────────────────
st.title("🔴 Forward MAL Dashboard")
st.caption(f"{n_files} file(s) · {len(df):,} records shown")

# ── KPIs ─────────────────────────────────────────────────────
k1,k2,k3,k4,k5,k6 = st.columns(6)
def kpi(col, label, value, color):
    col.markdown(f"""
    <div class="kpi-card" style="border-left-color:{color}">
      <div style="font-size:10px;color:#95A5A6;text-transform:uppercase">{label}</div>
      <div style="font-size:18px;font-weight:700;color:{color}">{value}</div>
    </div>""", unsafe_allow_html=True)

kpi(k1,"Total MAL Value", f"Rs.{df['Value'].sum():,.0f}",                        "#E74C3C")
kpi(k2,"Total MAL Qty",   f"{df['Qty'].sum():,.0f}",                             "#E67E22")
kpi(k3,"Unique SKUs",     f"{df['fsn'].nunique() if 'fsn' in df.columns else 0:,}","#2980B9")
kpi(k4,"Stores Affected", f"{df['Store Name'].nunique():,}",                     "#1ABC9C")
kpi(k5,"Origin Parties",  f"{df['origin_party_id'].nunique():,}",                "#1A5276")
kpi(k6,"Dest Parties",    f"{df['destination_party_id'].nunique():,}",           "#8E44AD")

st.markdown("<br>", unsafe_allow_html=True)

# ── Chart helpers ─────────────────────────────────────────────
LAYOUT = dict(plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
              font=dict(family="Arial", size=11), showlegend=False)

def hbar_val(col, title, color):
    t = df.groupby(col)["Value"].sum().nlargest(TOP_N).reset_index().sort_values("Value")
    if t.empty: return go.Figure()
    fig = px.bar(t, x="Value", y=col, orientation="h", title=title,
                 text=t["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(**LAYOUT, margin=dict(l=10,r=80,t=40,b=10),
                      yaxis_title="", xaxis_title="Value (Rs.)")
    return fig

def hbar_qty(col, title, color):
    t = df.groupby(col)["Qty"].sum().nlargest(TOP_N).reset_index().sort_values("Qty")
    if t.empty: return go.Figure()
    fig = px.bar(t, x="Qty", y=col, orientation="h", title=title,
                 text=t["Qty"].apply(lambda v: f"{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(**LAYOUT, margin=dict(l=10,r=60,t=40,b=10),
                      yaxis_title="", xaxis_title="Qty")
    return fig

def pie_chart(col, title):
    t = df.groupby(col)["Value"].sum().nlargest(10).reset_index()
    if t.empty: return go.Figure()
    fig = px.pie(t, names=col, values="Value", title=title, hole=0.4,
                 color_discrete_sequence=px.colors.qualitative.Set2)
    fig.update_layout(margin=dict(l=10,r=10,t=40,b=10), paper_bgcolor="#fff")
    return fig

# ── Trends ────────────────────────────────────────────────────
st.subheader("📈 Trends")
tm = df.groupby(["Month","MonthLabel"])["Value"].sum().reset_index().sort_values("Month")
fig = px.bar(tm, x="MonthLabel", y="Value", title="Monthly MAL Value (Rs.)",
             text=tm["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
             color_discrete_sequence=["#1ABC9C"])
fig.update_traces(textposition="outside")
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="Value (Rs.)",
                  margin=dict(t=40,b=40))
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
tw = df.groupby(["YearWeek","WeekLabel"])["Value"].sum().reset_index().sort_values("YearWeek")
fig = px.bar(tw, x="WeekLabel", y="Value", title="Week-wise MAL Value (Rs.)",
             text=tw["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
             color_discrete_sequence=["#3498DB"])
fig.update_traces(textposition="outside")
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="Value (Rs.)",
                  xaxis_tickangle=-45, margin=dict(t=40,b=60))
c1.plotly_chart(fig, use_container_width=True)

td = df.groupby("Date")["Value"].sum().reset_index().sort_values("Date")
fig = px.bar(td, x="Date", y="Value", title="Day-wise MAL Value (Rs.)",
             color_discrete_sequence=["#E74C3C"])
fig.update_layout(**LAYOUT, xaxis_title="", yaxis_title="Value (Rs.)",
                  xaxis_tickangle=-45, margin=dict(t=40,b=60))
c2.plotly_chart(fig, use_container_width=True)

# ── Party View ────────────────────────────────────────────────
st.subheader("🏢 Party View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_val("origin_party_id",      "Origin Party by Value", "#E74C3C"), use_container_width=True)
c2.plotly_chart(hbar_val("destination_party_id", "Dest Party by Value",   "#E67E22"), use_container_width=True)

# ── Product View ───────────────────────────────────────────────
st.subheader("📦 Product View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_val("cms_vertical", "Vertical by Value (Rs.)", "#3498DB"), use_container_width=True)
c2.plotly_chart(hbar_qty("cms_vertical", "Vertical by Qty",         "#2ECC71"), use_container_width=True)

# ── Location View ──────────────────────────────────────────────
st.subheader("📍 Location View")
c1, c2, c3 = st.columns(3)
c1.plotly_chart(hbar_val("DS City",    "DS City by Value",   "#8E44AD"), use_container_width=True)
c2.plotly_chart(hbar_val("Zone",       "Zone by Value",      "#1ABC9C"), use_container_width=True)
c3.plotly_chart(hbar_val("Store Name", "Store by Value",     "#F39C12"), use_container_width=True)

# ── Remark Split ───────────────────────────────────────────────
st.subheader("🏷️ Remark Split")
st.plotly_chart(pie_chart("Remark", "MAL by Remark Type"), use_container_width=True)

st.caption(f"Forward MAL Dashboard · Streamlit Cloud · {len(df):,} records")
