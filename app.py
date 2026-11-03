"""Nifty 500 Oversold-at-Support Scanner. UI only; logic lives in scanner/."""
from __future__ import annotations

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from scanner.config import CHART_BARS, HTF_OPTIONS, LTF_OPTIONS, ScanParams
from scanner.data import load_universe
from scanner.engine import ScanResult, run_scan
from scanner.utils import market_status

st.set_page_config(page_title="Nifty 500 Support Scanner", page_icon="📉", layout="wide",
                   initial_sidebar_state="expanded")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,600;12..96,800&family=Instrument+Sans:wght@400;500;600&display=swap');
html, body, [class*="css"], .stMarkdown, button, input { font-family: 'Instrument Sans', sans-serif; }
.block-container { padding-top: 1.4rem; max-width: 1480px; }
header[data-testid="stHeader"] { background: transparent; }
section[data-testid="stSidebar"] { background: #0b0f1c; border-right: 1px solid #262d47; }
.hero { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap;
        padding: 1.6rem 0 1.3rem; border-bottom: 1px solid #262d47; margin-bottom: 1.1rem; }
.hero .title { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: clamp(2rem, 4.4vw, 3.4rem);
               line-height: 1.02; letter-spacing: -0.035em; color: #f4f1ea; }
.hero .sub { color: #8a93ad; margin-top: .6rem; max-width: 46rem; font-size: 1.02rem; line-height: 1.5; }
.status { display: flex; align-items: center; gap: .55rem; padding: .45rem .8rem; border: 1px solid #262d47;
          border-radius: 999px; color: #c9cee0; font-size: .9rem; white-space: nowrap; }
.status .dot { width: .55rem; height: .55rem; border-radius: 50%; background: #6b7390; }
.status.open .dot { background: #34d399; box-shadow: 0 0 0 4px rgba(52,211,153,.18); }
.ribbon { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); border: 1px solid #262d47;
          border-radius: 10px; background: #121729; margin: .4rem 0 1.3rem; overflow: hidden; }
.ribbon .cell { padding: .95rem 1.1rem; border-right: 1px solid #262d47; }
.ribbon .cell:last-child { border-right: none; }
.ribbon .v { font-family: 'Bricolage Grotesque', sans-serif; font-weight: 800; font-size: 1.9rem; line-height: 1.1;
             font-variant-numeric: tabular-nums; color: #f4f1ea; }
.ribbon .l { color: #8a93ad; font-size: .85rem; margin-top: .2rem; }
.ribbon .good .v { color: #34d399; } .ribbon .bad .v { color: #fb7185; } .ribbon .key .v { color: #f2a63b; }
@media (max-width: 900px) { .ribbon { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ribbon .cell { border-bottom: 1px solid #262d47; } }
.empty { border: 1px dashed #343c5c; border-radius: 10px; padding: 1.6rem 1.4rem; color: #aab1c9; line-height: 1.6; }
.empty b { color: #f4f1ea; }
div[data-testid="stFormSubmitButton"] button { width: 100%; font-weight: 600; }
button[data-baseweb="tab"] { font-weight: 600; }
.foot { color: #6b7390; font-size: .82rem; margin-top: 2.2rem; border-top: 1px solid #262d47; padding-top: .9rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

BADGE = {"At Support": "🟢 At support", "Below Support": "🔴 Below support"}
ss = st.session_state

# ------------------------------------------------------------------ sidebar
universe, source = load_universe()
with st.sidebar:
    st.markdown("### Scan settings")
    with st.form("settings"):
        st.markdown("**Oversold on the lower timeframe**")
        ltf = st.selectbox("Lower timeframe", list(LTF_OPTIONS), index=1)
        rsi_period = st.slider("RSI period", 5, 30, 14)
        rsi_thr = st.slider("Oversold when RSI is below", 10, 45, 30)
        include_live = st.checkbox("Include the candle still forming", value=False)

        st.markdown("**Support on the higher timeframe**")
        htf = st.radio("Higher timeframe", list(HTF_OPTIONS), horizontal=True)
        lookback = st.slider("Swing lookback (bars each side)", 2, 15, 5)
        cluster = st.slider("Merge swing lows within (%)", 0.5, 3.0, 1.5, 0.1)
        touches = st.slider("Minimum touches for a swing zone", 1, 6, 2)
        near = st.slider("Count as 'at support' up to (% above zone)", 0.5, 5.0, 2.0, 0.1)
        below = st.slider("Still list when up to (% below zone)", 0.5, 10.0, 3.0, 0.5)
        c1, c2, c3 = st.columns(3)
        use_swing = c1.checkbox("Swing", True)
        use_52w = c2.checkbox("52W low", True)
        use_ema = c3.checkbox("200 EMA", False)

        st.markdown("**Liquidity filters**")
        min_price = st.number_input("Minimum price (Rs)", 0.0, 100000.0, 20.0, 10.0)
        min_vol = st.number_input("Minimum average daily volume", 0, 100_000_000, 100_000, 50_000)
        max_stocks = st.number_input("Limit to first N stocks (0 = all)", 0, 600, 0, 50)
        submitted = st.form_submit_button("Run scan", type="primary")

    auto = st.toggle("Auto-refresh results", value=False)
    every = st.select_slider("Refresh every (minutes)", [1, 2, 5, 10, 15], value=5, disabled=not auto)
    st.caption(f"{len(universe)} stocks loaded from the {source}.")
    if source == "fallback file":
        st.warning("NSE did not respond, so the short built-in list is in use. "
                   "Replace data/nifty500.csv with the full NSE file (see README).")

# ------------------------------------------------------------------ header
is_open, stamp = market_status()
st.markdown(
    f"""<div class="hero"><div>
    <div class="title">Oversold now,<br>sitting on support.</div>
    <div class="sub">Nifty 500 stocks where RSI is low on a short timeframe while price is at, or just under,
    a daily or weekly support zone.</div></div>
    <div class="status {'open' if is_open else ''}"><span class="dot"></span>NSE {'open' if is_open else 'closed'} &nbsp;{stamp}</div></div>""",
    unsafe_allow_html=True)

# ------------------------------------------------------------------ run scan
if submitted or ss.pop("auto_trigger", False):
    params = ScanParams(ltf=ltf, rsi_period=rsi_period, rsi_threshold=float(rsi_thr), include_live=include_live,
                        htf=htf, swing_lookback=lookback, cluster_tol=cluster, min_touches=touches,
                        near_tol=near, below_tol=below, use_swing=use_swing, use_52w=use_52w, use_ema=use_ema,
                        min_price=float(min_price), min_volume=int(min_vol), max_stocks=int(max_stocks))
    bar = st.progress(0.0, text="Starting scan")
    try:
        ss["res"] = run_scan(params, universe, lambda p, m: bar.progress(min(max(p, 0.0), 1.0), text=m))
        ss["last_scan"] = time.time()
    except Exception as exc:  # network or parsing failure: say what to do next
        st.error(f"The scan stopped: {exc}. Check your connection and run it again.")
    bar.empty()

res: ScanResult | None = ss.get("res")


def ribbon(items: list[tuple[str, str, str]]) -> str:
    cells = "".join(f'<div class="cell {t}"><div class="v">{v}</div><div class="l">{l}</div></div>' for l, v, t in items)
    return f'<div class="ribbon">{cells}</div>'


def build_chart(r: ScanResult, sym: str) -> go.Figure:
    p, h = r.params, r.htf[sym].tail(CHART_BARS[r.params.htf])
    near = r.nearest[sym]
    fig = make_subplots(rows=2, cols=1, row_heights=[0.72, 0.28], vertical_spacing=0.1,
                        subplot_titles=(f"{sym} on the {p.htf.lower()} chart", f"RSI {p.rsi_period} on {p.ltf}"))
    fig.add_trace(go.Candlestick(x=h.index, open=h["Open"], high=h["High"], low=h["Low"], close=h["Close"],
                                 increasing_line_color="#34d399", decreasing_line_color="#fb7185", name=sym), row=1, col=1)
    lo, hi = h["Low"].min() * 0.97, h["High"].max() * 1.03
    for z in r.zones[sym]:
        if z.high < lo or z.low > hi:
            continue
        is_near = z == near
        color = "#f2a63b" if is_near else "#6b7390"
        fig.add_hrect(y0=z.low, y1=z.high, fillcolor=color, opacity=0.30 if is_near else 0.14, line_width=0,
                      row=1, col=1, annotation_text=f"{z.kind} ({z.touches}x)" if z.touches > 1 else z.kind,
                      annotation_position="top left", annotation_font_size=11, annotation_font_color=color)
    fig.add_hline(y=float(r.table.loc[r.table["Symbol"] == sym, "LTP"].iloc[0]), line_dash="dot",
                  line_color="#e8eaf3", line_width=1, row=1, col=1)
    s = r.rsi_ltf[sym]
    fig.add_trace(go.Scatter(x=s.index, y=s.values, mode="lines", line=dict(color="#7dd3fc", width=1.6), name="RSI"), row=2, col=1)
    fig.add_hline(y=p.rsi_threshold, line_dash="dash", line_color="#34d399", row=2, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#fb7185", row=2, col=1)
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    if p.htf == "Daily":
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])], row=1, col=1)
    fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"]), dict(bounds=[15.5, 9.25], pattern="hour")], row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False, gridcolor="#1c2238")
    fig.update_yaxes(gridcolor="#1c2238")
    fig.update_layout(template="plotly_dark", height=720, showlegend=False, paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", margin=dict(l=10, r=10, t=40, b=10))
    return fig


# ------------------------------------------------------------------ tabs
tab_scan, tab_chart, tab_how = st.tabs(["Scanner", "Chart view", "How it works"])

with tab_scan:
    if res is None:
        st.markdown('<div class="empty"><b>Choose your timeframes, then select Run scan.</b><br>'
                    'The first scan downloads fresh candles; repeat scans reuse them for a few minutes, '
                    'so changing support settings afterwards is much quicker.</div>', unsafe_allow_html=True)
    else:
        s = res.stats
        st.markdown(ribbon([("Stocks scanned", f"{s['scanned']}", ""), (f"RSI below {res.params.rsi_threshold:.0f}", f"{s['oversold']}", ""),
                            ("Matches", f"{s['matches']}", "key"), ("At support", f"{s['at']}", "good"),
                            ("Below support", f"{s['below']}", "bad"), ("Scan time", f"{s['seconds']:.1f}s", "")]),
                    unsafe_allow_html=True)
        if res.skipped:
            with st.expander(f"{len(res.skipped)} symbols returned no data and were skipped"):
                st.write(", ".join(res.skipped))
        if res.table.empty:
            st.info("No stock matches right now. Raise the RSI threshold, widen the support tolerances, "
                    "or lower the minimum touches, then run the scan again.")
        else:
            f1, f2 = st.columns([1, 2])
            status_pick = f1.radio("Show", ["All", "At Support", "Below Support"], horizontal=True, label_visibility="collapsed")
            query = f2.text_input("Search", placeholder="Search by symbol or company", label_visibility="collapsed")
            view = res.table
            if status_pick != "All":
                view = view[view["Status"] == status_pick]
            if query:
                view = view[view["Symbol"].str.contains(query, case=False) | view["Company"].str.contains(query, case=False)]
            view = view.reset_index(drop=True)
            shown = view.assign(Status=view["Status"].map(BADGE))[
                ["Symbol", "Company", "LTP", "LTF RSI", "HTF RSI", "Support Type", "Support Level", "Zone Low", "Zone High",
                 "Touches", "Distance %", "Distance Rs", "Status", "Avg Volume"]]
            cc = st.column_config
            event = st.dataframe(
                shown, hide_index=True, on_select="rerun", selection_mode="single-row", key="results_table",
                height=min(640, 42 + 35 * max(len(shown), 1)),
                column_config={
                    "LTP": cc.NumberColumn("LTP (Rs)", format="%.2f"),
                    "LTF RSI": cc.ProgressColumn(f"RSI {res.params.ltf}", min_value=0, max_value=100, format="%.1f"),
                    "HTF RSI": cc.ProgressColumn(f"RSI {res.params.htf.lower()}", min_value=0, max_value=100, format="%.1f"),
                    "Support Level": cc.NumberColumn("Support (Rs)", format="%.2f"),
                    "Zone Low": cc.NumberColumn("Zone low", format="%.2f"),
                    "Zone High": cc.NumberColumn("Zone high", format="%.2f"),
                    "Distance %": cc.NumberColumn("Distance (%)", format="%+.2f", help="Above the zone is positive, below is negative, 0 is inside it."),
                    "Distance Rs": cc.NumberColumn("Distance (Rs)", format="%+.2f"),
                    "Avg Volume": cc.NumberColumn("Avg volume", format="%d"),
                })
            rows = event.selection.rows if event and event.selection else []
            if rows and rows[0] < len(view):
                picked = view.iloc[rows[0]]["Symbol"]
                if ss.get("_last_pick") != picked:          # only react to a new click
                    ss["_last_pick"], ss["chart_symbol"] = picked, picked
                st.caption(f"{picked} selected. Open the Chart view tab to see its support zones.")
            st.download_button("Download CSV", res.table.to_csv(index=False).encode(),
                               file_name=f"nifty500_scan_{pd.Timestamp.now():%Y%m%d_%H%M}.csv", mime="text/csv")

with tab_chart:
    if res is None or res.table.empty:
        st.info("Run a scan with at least one match to see charts here.")
    else:
        syms = list(res.table["Symbol"])
        if ss.get("chart_symbol") not in syms:
            ss["chart_symbol"] = syms[0]
        sym = st.selectbox("Stock", syms, key="chart_symbol")
        row = res.table[res.table["Symbol"] == sym].iloc[0]
        m = st.columns(4)
        m[0].metric("Last price", f"Rs {row['LTP']:,.2f}")
        m[1].metric("Support zone", f"{row['Zone Low']:,.2f} to {row['Zone High']:,.2f}", f"{row['Touches']} touch(es), {row['Support Type']}", delta_color="off")
        m[2].metric("Distance", f"{row['Distance %']:+.2f}%", row["Status"], delta_color="off")
        m[3].metric(f"RSI {res.params.ltf}", f"{row['LTF RSI']:.1f}")
        st.plotly_chart(build_chart(res, sym))

with tab_how:
    st.markdown(f"""
**What a match means.** The RSI of the last completed candle on your lower timeframe is below your threshold, and the
last price sits at, or within your tolerance of, a support zone found on the daily or weekly chart.

**How support is found.** Swing lows (the lowest low within N bars on each side) are merged into a zone when they sit within
the merge percentage of each other. More touches means a stronger zone. The 52-week low (taken from before the latest bars) and
the 200 EMA can be added as extra levels. Weekly charts are built from daily data.

**Distance.** Measured from the nearest edge of the zone: positive is above it, 0 is inside it, negative is below it.

**Why it is fast.** Intraday candles are downloaded in batches of 100 and cached for 3 minutes. RSI runs first on all stocks;
daily history is downloaded and support is computed only for the few that are oversold, cached for an hour.

**Limits.** Data comes from Yahoo Finance through yfinance: unofficial, can be delayed, and can be rate limited on shared hosts.
5m and 15m history is limited to about 60 days. Support zones are a mechanical estimate, so check the chart before acting.
""")

st.markdown('<div class="foot">For education only. This is not investment advice, and the data may be delayed or incomplete.</div>',
            unsafe_allow_html=True)

# ------------------------------------------------------------------ auto refresh
if auto and res is not None:
    wait = every * 60 - (time.time() - ss["last_scan"])
    if wait <= 0:
        ss["auto_trigger"] = True
        st.rerun()
    st.sidebar.caption(f"Next refresh in {int(wait)}s")
    time.sleep(min(wait, 5))
    st.rerun()
