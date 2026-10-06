"""
Forward MAL Dashboard — Streamlit version
Deploy free at streamlit.io/cloud
"""
import os, glob, warnings
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

warnings.filterwarnings("ignore")

# ── Page config ─────────────────────────────────────────────
st.set_page_config(
    page_title="Forward MAL Dashboard",
    page_icon="🔴",
    layout="wide",
)

st.markdown("""
<style>
[data-testid="stSidebar"]{background:#1A5276}
[data-testid="stSidebar"] *{color:#fff !important}
[data-testid="stSidebar"] .stMultiSelect label{color:#fff !important}
[data-testid="stSidebar"] .stSelectbox label{color:#fff !important}
.kpi-card{background:#fff;border-radius:8px;padding:14px 16px;
          border-left:4px solid #ccc;box-shadow:0 2px 6px rgba(0,0,0,.08);text-align:center}
</style>
""", unsafe_allow_html=True)

COLS = ["origin_party_id","destination_party_id","external_id",
        "updated_at","fsn","add_excess_variance_id",
        "Qty","Value","cms_vertical","DS City","Zone","Store Name","Remark"]

TOP_N = 15

# ── Load data ────────────────────────────────────────────────
@st.cache_data(show_spinner="Loading files...")
def load_data():
    # Works both locally and on Streamlit Cloud (data folder beside app.py)
    base = os.path.dirname(__file__)
    folder = os.path.join(base, "csv_files")

    files = glob.glob(os.path.join(folder, "**", "*.csv"),  recursive=True)
    if not files:
        files = glob.glob(os.path.join(folder, "**", "*.xlsx"), recursive=True)
    if not files:
        st.error(f"No CSV/XLSX files found in: {folder}")
        st.stop()

    dfs = []
    for f in files:
        try:
            ext = os.path.splitext(f)[1].lower()
            if ext == ".xlsx":
                tmp = pd.read_excel(f, engine="openpyxl")
            else:
                try:    tmp = pd.read_csv(f, encoding="utf-8",   low_memory=False)
                except: tmp = pd.read_csv(f, encoding="latin1", low_memory=False)
            existing = [c for c in COLS if c in tmp.columns]
            dfs.append(tmp[existing])
        except Exception as e:
            st.warning(f"Skipped {os.path.basename(f)}: {e}")

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

    return df, len(files)

DF, n_files = load_data()

# ── Sidebar filters ──────────────────────────────────────────
st.sidebar.title("🔴 Forward MAL")
st.sidebar.markdown(f"**{n_files} file(s) · {len(DF):,} records**")
st.sidebar.markdown("---")

def ms(label, col, df=DF):
    opts = sorted(df[col].dropna().unique().tolist())
    return st.sidebar.multiselect(label, opts, default=[])

month_opts = sorted(DF["Month"].dropna().unique().tolist())
month_labels = {m: DF[DF["Month"]==m]["MonthLabel"].iloc[0] for m in month_opts}
sel_months = st.sidebar.multiselect("Month", options=month_opts,
                                    format_func=lambda x: month_labels.get(x, x))

week_opts = (DF.groupby(["YearWeek","WeekLabel"]).size()
               .reset_index().sort_values("YearWeek")["WeekLabel"].tolist())
sel_weeks   = st.sidebar.multiselect("Week",         week_opts)
sel_origin  = ms("Origin Party",  "origin_party_id")
sel_dest    = ms("Dest Party",    "destination_party_id")
sel_vert    = ms("Vertical",      "cms_vertical")
sel_city    = ms("DS City",       "DS City")
sel_zone    = ms("Zone",          "Zone")
sel_store   = ms("Store Name",    "Store Name")
sel_remark  = ms("Remark",        "Remark")

st.sidebar.markdown("---")
apply = st.sidebar.button("▶ Apply Filters", use_container_width=True, type="primary")
reset = st.sidebar.button("✕ Reset All",     use_container_width=True)

# ── Filter logic ─────────────────────────────────────────────
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

if reset:
    st.rerun()

df = filter_df(
    tuple(sel_months), tuple(sel_weeks), tuple(sel_origin),
    tuple(sel_dest), tuple(sel_vert), tuple(sel_city),
    tuple(sel_zone), tuple(sel_store), tuple(sel_remark)
)

# ── Header ───────────────────────────────────────────────────
st.title("🔴 Forward MAL Dashboard")
st.caption(f"{n_files} file(s) loaded · {len(df):,} records shown")

# ── KPIs ─────────────────────────────────────────────────────
k1,k2,k3,k4,k5,k6 = st.columns(6)
def kpi(col, label, value, color):
    col.markdown(f"""
    <div class="kpi-card" style="border-left-color:{color}">
      <div style="font-size:10px;color:#95A5A6;text-transform:uppercase">{label}</div>
      <div style="font-size:18px;font-weight:700;color:{color}">{value}</div>
    </div>""", unsafe_allow_html=True)

kpi(k1, "Total MAL Value",  f"Rs.{df['Value'].sum():,.0f}",        "#E74C3C")
kpi(k2, "Total MAL Qty",    f"{df['Qty'].sum():,.0f}",             "#E67E22")
kpi(k3, "Unique SKUs",      f"{df['fsn'].nunique() if 'fsn' in df.columns else 0:,}", "#2980B9")
kpi(k4, "Stores Affected",  f"{df['Store Name'].nunique():,}",     "#1ABC9C")
kpi(k5, "Origin Parties",   f"{df['origin_party_id'].nunique():,}","#1A5276")
kpi(k6, "Dest Parties",     f"{df['destination_party_id'].nunique():,}","#8E44AD")

st.markdown("<br>", unsafe_allow_html=True)

# ── Chart helpers ─────────────────────────────────────────────
def topn_val(col, n=TOP_N):
    return df.groupby(col)["Value"].sum().nlargest(n).reset_index()

def topn_qty(col, n=TOP_N):
    return df.groupby(col)["Qty"].sum().nlargest(n).reset_index()

def hbar_val(col, title, color):
    t = topn_val(col)
    if t.empty: return go.Figure()
    t = t.sort_values("Value")
    fig = px.bar(t, x="Value", y=col, orientation="h", title=title,
                 text=t["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, margin=dict(l=10,r=60,t=40,b=10),
                      plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                      yaxis_title="", xaxis_title="Value (Rs.)")
    return fig

def hbar_qty(col, title, color):
    t = topn_qty(col)
    if t.empty: return go.Figure()
    t = t.sort_values("Qty")
    fig = px.bar(t, x="Qty", y=col, orientation="h", title=title,
                 text=t["Qty"].apply(lambda v: f"{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, margin=dict(l=10,r=60,t=40,b=10),
                      plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                      yaxis_title="", xaxis_title="Qty")
    return fig

def vbar(groupcol, sortcol, xlabel, title, color):
    t = df.groupby([sortcol, groupcol])["Value"].sum().reset_index().sort_values(sortcol)
    if t.empty: return go.Figure()
    fig = px.bar(t, x=groupcol, y="Value", title=title,
                 text=t["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
                 color_discrete_sequence=[color])
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, margin=dict(l=10,r=10,t=40,b=80),
                      plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                      xaxis_title=xlabel, yaxis_title="Value (Rs.)",
                      xaxis_tickangle=-45)
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
trend_month = df.groupby(["Month","MonthLabel"])["Value"].sum().reset_index().sort_values("Month")
fig_month = px.bar(trend_month, x="MonthLabel", y="Value", title="Monthly MAL Value (Rs.)",
                   text=trend_month["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
                   color_discrete_sequence=["#1ABC9C"])
fig_month.update_traces(textposition="outside")
fig_month.update_layout(plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                        xaxis_title="", yaxis_title="Value (Rs.)",
                        margin=dict(t=40,b=40), showlegend=False)
st.plotly_chart(fig_month, use_container_width=True)

c1, c2 = st.columns(2)
trend_week = df.groupby(["YearWeek","WeekLabel"])["Value"].sum().reset_index().sort_values("YearWeek")
fig_week = px.bar(trend_week, x="WeekLabel", y="Value", title="Week-wise MAL Value (Rs.)",
                  text=trend_week["Value"].apply(lambda v: f"Rs.{v:,.0f}"),
                  color_discrete_sequence=["#3498DB"])
fig_week.update_traces(textposition="outside")
fig_week.update_layout(plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                       xaxis_title="", yaxis_title="Value (Rs.)",
                       xaxis_tickangle=-45, margin=dict(t=40,b=60), showlegend=False)
c1.plotly_chart(fig_week, use_container_width=True)

trend_day = df.groupby("Date")["Value"].sum().reset_index().sort_values("Date")
fig_day = px.bar(trend_day, x="Date", y="Value", title="Day-wise MAL Value (Rs.)",
                 color_discrete_sequence=["#E74C3C"])
fig_day.update_layout(plot_bgcolor="#FAFAFA", paper_bgcolor="#fff",
                      xaxis_title="", yaxis_title="Value (Rs.)",
                      xaxis_tickangle=-45, margin=dict(t=40,b=60), showlegend=False)
c2.plotly_chart(fig_day, use_container_width=True)

# ── Party View ────────────────────────────────────────────────
st.subheader("🏢 Party View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_val("origin_party_id", "Origin Party by Value", "#E74C3C"), use_container_width=True)
c2.plotly_chart(hbar_val("destination_party_id", "Destination Party by Value", "#E67E22"), use_container_width=True)

# ── Product View ───────────────────────────────────────────────
st.subheader("📦 Product View")
c1, c2 = st.columns(2)
c1.plotly_chart(hbar_val("cms_vertical", "Vertical by Value (Rs.)", "#3498DB"), use_container_width=True)
c2.plotly_chart(hbar_qty("cms_vertical", "Vertical by Qty",         "#2ECC71"), use_container_width=True)

# ── Location View ──────────────────────────────────────────────
st.subheader("📍 Location View")
c1, c2, c3 = st.columns(3)
c1.plotly_chart(hbar_val("DS City",     "DS City by Value",    "#8E44AD"), use_container_width=True)
c2.plotly_chart(hbar_val("Zone",        "Zone by Value",       "#1ABC9C"), use_container_width=True)
c3.plotly_chart(hbar_val("Store Name",  "Store by Value",      "#F39C12"), use_container_width=True)

# ── Remark Split ───────────────────────────────────────────────
st.subheader("🏷️ Remark Split")
st.plotly_chart(pie_chart("Remark", "MAL by Remark Type"), use_container_width=True)

st.caption(f"Forward MAL Dashboard · Streamlit · {len(df):,} records")
