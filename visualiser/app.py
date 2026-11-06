"""
IMC Prosperity 4 — Dashboard Visualiser
Inspired by Frankfurt Hedgehogs' Prosperity 3 dashboard.

Features:
- Order book scatter plot (red asks, blue bids) with trade markers
- PnL panel over time
- Position panel over time
- Log viewer synced to hovered timestamp
- Product selector, indicator overlays, normalization
- Trade filtering by trader type and quantity range
- Performance downsampling for large datasets

Usage:
    cd visualiser
    pip install -r requirements.txt
    streamlit run app.py
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ─── Constants ───────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "backtester" / "data"

COLORS = {
    "bid": "#4A90D9",       # Blue for bids
    "ask": "#D94A4A",       # Red for asks
    "mid": "#888888",       # Grey for mid
    "own_trade": "#FF8C00", # Orange crosses for own trades
    "buy_trade": "#2196F3", # Blue squares for maker buys
    "sell_trade": "#F44336",# Red triangles for taker sells
    "pnl": "#4CAF50",      # Green for PnL
    "position": "#9C27B0", # Purple for position
    "bg": "#0E1117",       # Dark background
    "grid": "#1E2530",     # Grid lines
    "text": "#FAFAFA",     # Text color
}


# ─── Data Loading ────────────────────────────────────────────────────────────

@st.cache_data
def load_prices_csv(path: str) -> pd.DataFrame:
    """Load a prices CSV (semicolon-delimited) into a DataFrame."""
    df = pd.read_csv(path, sep=";")
    return df


@st.cache_data
def load_trades_csv(path: str) -> pd.DataFrame:
    """Load a trades CSV (semicolon-delimited) into a DataFrame."""
    df = pd.read_csv(path, sep=";")
    return df


def discover_data_files() -> Dict[str, Dict[str, List[Tuple[str, Path]]]]:
    """Scan DATA_DIR for available round/day combinations.
    Also scan tutorial-round/data for additional data.
    Returns: {round_label: {"prices": [(day_label, path)], "trades": [(day_label, path)]}}
    """
    result = {}

    search_dirs = []

    # backtester/data has structure: data/tutorial/round0/*.csv
    # Add each subdirectory (e.g. "tutorial") so round dirs inside are found
    if DATA_DIR.is_dir():
        for sub in DATA_DIR.iterdir():
            if sub.is_dir() and not sub.name.startswith("_"):
                search_dirs.append(sub)

    # tutorial-round/data has structure: data/TUTORIAL_ROUND_1/*.csv
    # Add data/ itself so TUTORIAL_ROUND_1 is found as a round dir
    tutorial_dir = ROOT / "tutorial-round" / "data"
    if tutorial_dir.is_dir():
        search_dirs.append(tutorial_dir)

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for round_dir in sorted(search_dir.iterdir()):
            if not round_dir.is_dir():
                continue
            round_label = round_dir.name
            if round_label.startswith("_"):
                continue

            prices = []
            trades = []
            for f in sorted(round_dir.iterdir()):
                if f.name.startswith("_"):
                    continue
                if f.suffix == ".csv":
                    if "prices" in f.name.lower():
                        # Extract day from filename
                        m = re.search(r"day_(-?\d+)", f.name)
                        day = m.group(1) if m else f.stem
                        prices.append((f"Day {day}", f))
                    elif "trades" in f.name.lower():
                        m = re.search(r"day_(-?\d+)", f.name)
                        day = m.group(1) if m else f.stem
                        trades.append((f"Day {day}", f))

            if prices:
                key = f"{search_dir.name}/{round_label}" if search_dir != DATA_DIR else round_label
                result[key] = {"prices": prices, "trades": trades}

    return result


def parse_backtest_log(log_text: str) -> List[dict]:
    """Parse prosperity3bt JSON log output into structured records.

    Each line of the log is a JSON array:
    [state_array, orders_dict, conversions, traderData, logs_string]

    state_array = [timestamp, traderData, listings, order_depths,
                   own_trades, market_trades, position, observations]
    """
    records = []
    for line in log_text.strip().split("\n"):
        line = line.strip()
        if not line or not line.startswith("["):
            continue
        try:
            parsed = json.loads(line)
            state = parsed[0]
            orders = parsed[1]
            conversions = parsed[2]
            trader_data = parsed[3]
            logs = parsed[4] if len(parsed) > 4 else ""

            record = {
                "timestamp": state[0],
                "listings": state[2],
                "order_depths": state[3],
                "own_trades": state[4],
                "market_trades": state[5],
                "position": state[6],
                "observations": state[7] if len(state) > 7 else {},
                "orders": orders,
                "conversions": conversions,
                "logs": logs,
            }
            records.append(record)
        except (json.JSONDecodeError, IndexError, TypeError):
            continue
    return records


def log_records_to_dataframes(records: List[dict]) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convert parsed log records into prices_df, trades_df, and logs_df.

    Returns:
        prices_df: columns like the prices CSV
        trades_df: columns like the trades CSV
        logs_df: timestamp, log_text
    """
    price_rows = []
    trade_rows = []
    log_rows = []

    for rec in records:
        ts = rec["timestamp"]

        # Prices from order depths
        for sym, (buys, sells) in rec.get("order_depths", {}).items():
            row = {"timestamp": ts, "product": sym, "mid_price": 0.0}

            # Sort buys descending, sells ascending
            buy_prices = sorted(buys.keys(), key=lambda x: -int(x)) if buys else []
            sell_prices = sorted(sells.keys(), key=lambda x: int(x)) if sells else []

            for i, p in enumerate(buy_prices[:3], 1):
                row[f"bid_price_{i}"] = int(p)
                row[f"bid_volume_{i}"] = abs(int(buys[p]))
            for i, p in enumerate(sell_prices[:3], 1):
                row[f"ask_price_{i}"] = int(p)
                row[f"ask_volume_{i}"] = abs(int(sells[p]))

            # Compute mid
            best_bid = int(buy_prices[0]) if buy_prices else None
            best_ask = int(sell_prices[0]) if sell_prices else None
            if best_bid is not None and best_ask is not None:
                row["mid_price"] = (best_bid + best_ask) / 2.0
            elif best_bid is not None:
                row["mid_price"] = best_bid
            elif best_ask is not None:
                row["mid_price"] = best_ask

            # PnL from position (placeholder — real PnL requires trade tracking)
            row["profit_and_loss"] = 0.0

            price_rows.append(row)

        # Market trades
        for sym, trades_list in rec.get("market_trades", {}).items():
            for t in trades_list:
                trade_rows.append({
                    "timestamp": t[5] if len(t) > 5 else ts,
                    "buyer": t[3] if len(t) > 3 else "",
                    "seller": t[4] if len(t) > 4 else "",
                    "symbol": t[0],
                    "price": t[1],
                    "quantity": t[2],
                    "is_own": False,
                })

        # Own trades
        for sym, trades_list in rec.get("own_trades", {}).items():
            for t in trades_list:
                trade_rows.append({
                    "timestamp": t[5] if len(t) > 5 else ts,
                    "buyer": t[3] if len(t) > 3 else "",
                    "seller": t[4] if len(t) > 4 else "",
                    "symbol": t[0],
                    "price": t[1],
                    "quantity": t[2],
                    "is_own": True,
                })

        # Logs
        if rec.get("logs"):
            log_rows.append({"timestamp": ts, "log_text": rec["logs"]})

    prices_df = pd.DataFrame(price_rows) if price_rows else pd.DataFrame()
    trades_df = pd.DataFrame(trade_rows) if trade_rows else pd.DataFrame()
    logs_df = pd.DataFrame(log_rows) if log_rows else pd.DataFrame()

    return prices_df, trades_df, logs_df


# ─── Order Book Plot (Main Scatter) ─────────────────────────────────────────

def build_orderbook_chart(
    prices_df: pd.DataFrame,
    trades_df: pd.DataFrame,
    product: str,
    show_levels: int = 3,
    show_trades: bool = True,
    show_own_trades: bool = True,
    qty_min: int = 0,
    qty_max: int = 999,
    normalize_col: Optional[str] = None,
    downsample: int = 1,
) -> go.Figure:
    """Build the main order-book scatter plot like Frankfurt Hedgehogs."""

    pdf = prices_df[prices_df["product"] == product].copy()
    if pdf.empty:
        return go.Figure().update_layout(title="No data for selected product")

    if downsample > 1:
        pdf = pdf.iloc[::downsample].reset_index(drop=True)

    ts = pdf["timestamp"]

    # Normalization offset
    norm_offset = pd.Series(0.0, index=pdf.index)
    if normalize_col and normalize_col in pdf.columns:
        norm_offset = pdf[normalize_col].fillna(0)
    elif normalize_col == "mid_price":
        norm_offset = pdf["mid_price"].fillna(0)

    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.6, 0.2, 0.2],
        subplot_titles=("Order Book", "Profit & Loss", "Position"),
    )

    # ── Ask levels (red dots) ──
    for level in range(1, show_levels + 1):
        ask_col = f"ask_price_{level}"
        vol_col = f"ask_volume_{level}"
        if ask_col not in pdf.columns:
            continue
        mask = pdf[ask_col].notna()
        if not mask.any():
            continue
        y_vals = pdf.loc[mask, ask_col] - norm_offset[mask]
        sizes = pdf.loc[mask, vol_col].fillna(1).clip(lower=1)
        # Small dots — volume shown via hover, not size
        size_scaled = 2 + (sizes / sizes.max()) * 2 if sizes.max() > 0 else sizes * 0 + 2

        fig.add_trace(go.Scattergl(
            x=ts[mask], y=y_vals,
            mode="markers",
            marker=dict(
                size=size_scaled,
                color=COLORS["ask"],
                opacity=0.3 + 0.1 * (show_levels - level),
            ),
            name=f"Ask L{level}",
            hovertemplate=f"Ask L{level}<br>Price: %{{y:.0f}}<br>Vol: %{{customdata}}<br>t=%{{x}}<extra></extra>",
            customdata=sizes,
            legendgroup="asks",
            showlegend=(level == 1),
        ), row=1, col=1)

    # ── Bid levels (blue dots) ──
    for level in range(1, show_levels + 1):
        bid_col = f"bid_price_{level}"
        vol_col = f"bid_volume_{level}"
        if bid_col not in pdf.columns:
            continue
        mask = pdf[bid_col].notna()
        if not mask.any():
            continue
        y_vals = pdf.loc[mask, bid_col] - norm_offset[mask]
        sizes = pdf.loc[mask, vol_col].fillna(1).clip(lower=1)
        size_scaled = 2 + (sizes / sizes.max()) * 2 if sizes.max() > 0 else sizes * 0 + 2

        fig.add_trace(go.Scattergl(
            x=ts[mask], y=y_vals,
            mode="markers",
            marker=dict(
                size=size_scaled,
                color=COLORS["bid"],
                opacity=0.3 + 0.1 * (show_levels - level),
            ),
            name=f"Bid L{level}",
            hovertemplate=f"Bid L{level}<br>Price: %{{y:.0f}}<br>Vol: %{{customdata}}<br>t=%{{x}}<extra></extra>",
            customdata=sizes,
            legendgroup="bids",
            showlegend=(level == 1),
        ), row=1, col=1)

    # ── Mid price line ──
    if "mid_price" in pdf.columns:
        mid_vals = pdf["mid_price"] - norm_offset
        fig.add_trace(go.Scattergl(
            x=ts, y=mid_vals,
            mode="lines",
            line=dict(color="#FFFFFF", width=2),
            name="Mid",
            hovertemplate="Mid: %{y:.1f}<br>t=%{x}<extra></extra>",
            opacity=0.9,
        ), row=1, col=1)

    # ── Trades ──
    if show_trades and not trades_df.empty:
        tdf = trades_df[trades_df["symbol"] == product].copy()
        if qty_min > 0:
            tdf = tdf[tdf["quantity"] >= qty_min]
        if qty_max < 999:
            tdf = tdf[tdf["quantity"] <= qty_max]

        if downsample > 1:
            # Filter trades to only those at visible timestamps
            visible_ts = set(ts.values)
            tdf = tdf[tdf["timestamp"].isin(visible_ts)]

        # Apply normalization to trades
        if normalize_col:
            # Merge nearest norm_offset for each trade timestamp
            norm_lookup = pd.DataFrame({"timestamp": ts, "norm": norm_offset.values})
            tdf = tdf.merge(norm_lookup, on="timestamp", how="left")
            tdf["norm"] = tdf["norm"].fillna(0)
        else:
            tdf["norm"] = 0

        # Split own vs market trades
        is_own = tdf.get("is_own", pd.Series(False, index=tdf.index))

        if show_own_trades and is_own.any():
            own = tdf[is_own]
            fig.add_trace(go.Scattergl(
                x=own["timestamp"], y=own["price"] - own["norm"],
                mode="markers",
                marker=dict(
                    symbol="x",
                    size=10,
                    color=COLORS["own_trade"],
                    line=dict(width=2, color=COLORS["own_trade"]),
                ),
                name="Own Trades",
                hovertemplate="OWN %{customdata[0]} @ %{y:.0f}<br>qty=%{customdata[1]}<br>t=%{x}<extra></extra>",
                customdata=list(zip(
                    ["BUY" if b else "SELL" for b in (own.get("buyer", "") == "SUBMISSION")],
                    own["quantity"],
                )),
            ), row=1, col=1)

        market = tdf[~is_own] if "is_own" in tdf.columns else tdf
        if not market.empty:
            # Squares for makers (buyer side), triangles for sellers
            fig.add_trace(go.Scattergl(
                x=market["timestamp"], y=market["price"] - market["norm"],
                mode="markers",
                marker=dict(
                    symbol="square",
                    size=6,
                    color="#AAAAAA",
                    opacity=0.7,
                ),
                name="Market Trades",
                hovertemplate="Trade @ %{y:.0f}<br>qty=%{customdata[0]}<br>buyer=%{customdata[1]}<br>seller=%{customdata[2]}<br>t=%{x}<extra></extra>",
                customdata=list(zip(
                    market["quantity"],
                    market.get("buyer", ""),
                    market.get("seller", ""),
                )),
            ), row=1, col=1)

    # ── PnL subplot ──
    if "profit_and_loss" in pdf.columns:
        fig.add_trace(go.Scattergl(
            x=ts, y=pdf["profit_and_loss"],
            mode="lines",
            line=dict(color=COLORS["pnl"], width=1.5),
            name="PnL",
            hovertemplate="PnL: %{y:.0f}<br>t=%{x}<extra></extra>",
            showlegend=True,
        ), row=2, col=1)

        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="#555", row=2, col=1)

    # ── Position subplot ──
    # Position is not in the prices CSV, so we'll add a placeholder
    # It will be populated from backtest logs when available

    # Style
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["bg"],
        plot_bgcolor=COLORS["bg"],
        height=800,
        margin=dict(l=60, r=20, t=40, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=10),
        ),
        hovermode="x unified",
    )

    fig.update_xaxes(gridcolor=COLORS["grid"], showgrid=True)
    fig.update_yaxes(gridcolor=COLORS["grid"], showgrid=True)
    fig.update_xaxes(title_text="Timestamp", row=3, col=1)
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="PnL", row=2, col=1)
    fig.update_yaxes(title_text="Position", row=3, col=1)

    return fig


# ─── Streamlit App ───────────────────────────────────────────────────────────

def main():
    st.set_page_config(
        page_title="P4 Dashboard",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown("""
    <style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    footer { visibility: hidden; }
    .stPlotlyChart { margin-top: -0.5rem; }
    div[data-testid="stSidebarContent"] { padding-top: 1rem; }
    .stDeployButton { display: none !important; }
    [data-testid="stStatusWidget"] { display: none !important; }
    #MainMenu { visibility: hidden; }
    button[kind="header"] { display: none !important; }
    div[data-testid="stDecoration"] { display: none !important; }
    </style>
    """, unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════
    # TOP BAR — Data source, round/day, product selection
    # ══════════════════════════════════════════════════════════════════
    prices_df = pd.DataFrame()
    trades_df = pd.DataFrame()
    logs_df = pd.DataFrame()
    position_data = {}
    product = None

    # Data source selector in sidebar
    data_source = st.sidebar.radio("Data Source", ["📁 CSV Files", "📋 Paste Log"], index=0)

    if data_source == "📁 CSV Files":
        available = discover_data_files()
        if not available:
            st.warning("No data files found. Run the backtester first or add CSVs to backtester/data/ or tutorial-round/data/.")
            st.stop()

        top_row = st.columns([2, 2, 2])
        with top_row[0]:
            round_key = st.selectbox("Round", list(available.keys()), key="csv_round")
        round_data = available[round_key]

        price_options = round_data.get("prices", [])
        trade_options = round_data.get("trades", [])

        with top_row[1]:
            if price_options:
                day_label = st.selectbox(
                    "Day",
                    [label for label, _ in price_options],
                    key="csv_day",
                )
                price_path = next(p for l, p in price_options if l == day_label)
                prices_df = load_prices_csv(str(price_path))

                # Auto-match trades day
                if trade_options:
                    matching_trade = next((p for l, p in trade_options if l == day_label), None)
                    if matching_trade:
                        trades_df = load_trades_csv(str(matching_trade))
                        if "is_own" not in trades_df.columns:
                            trades_df["is_own"] = False

        with top_row[2]:
            if not prices_df.empty:
                products = sorted(prices_df["product"].unique())
                product = st.selectbox("Product", products, key="csv_product")
            else:
                st.info("No data")
                st.stop()

    else:  # Paste Log
        log_text = st.text_area(
            "Paste backtest log output (JSON lines from prosperity3bt)",
            height=150,
            placeholder='[[[0,"",{},...],...],...]',
            key="log_input",
        )
        if log_text.strip():
            records = parse_backtest_log(log_text)
            if records:
                prices_df, trades_df, logs_df = log_records_to_dataframes(records)
                for rec in records:
                    position_data[rec["timestamp"]] = rec.get("position", {})
                st.success(f"Parsed {len(records)} timesteps")
                products = sorted(prices_df["product"].unique())
                product = st.selectbox("Product", products, key="log_product")
            else:
                st.error("Could not parse log. Expected JSON array lines.")
                st.stop()
        else:
            st.info("Paste prosperity3bt stdout here to visualize.")
            st.stop()

    if prices_df.empty or product is None:
        st.warning("No price data loaded.")
        st.stop()

    # ══════════════════════════════════════════════════════════════════
    # SIDEBAR — Display controls (filters, normalization, etc.)
    # ══════════════════════════════════════════════════════════════════
    st.sidebar.markdown("### ⚙️ Controls")

    # Order book levels
    show_levels = st.sidebar.slider("Order Book Levels", 1, 3, 3)

    # Trade visibility
    st.sidebar.markdown("**Trades**")
    show_trades = st.sidebar.checkbox("Show Market Trades", value=True)
    show_own_trades = st.sidebar.checkbox("Show Own Trades", value=True)

    # Quantity filter
    col_qmin, col_qmax = st.sidebar.columns(2)
    qty_min = col_qmin.number_input("Min Qty", min_value=0, value=0, step=1)
    qty_max = col_qmax.number_input("Max Qty", min_value=1, value=999, step=1)

    # Normalization
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Normalization**")
    norm_options = ["None", "mid_price"]
    for col in prices_df.columns:
        if col not in ["timestamp", "product", "day", "mid_price", "profit_and_loss"] and prices_df[col].dtype in ["float64", "int64"]:
            if col not in norm_options:
                norm_options.append(col)
    normalize_col = st.sidebar.selectbox("Normalize by", norm_options)
    if normalize_col == "None":
        normalize_col = None

    # Downsampling
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Performance**")
    n_points = len(prices_df[prices_df["product"] == product])
    max_ds = max(2, n_points // 100)
    downsample = st.sidebar.slider(
        f"Downsample ({n_points:,} pts)",
        min_value=1,
        max_value=max_ds,
        value=1,
    )

    # Timestamp range filter
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Time Range**")
    product_df = prices_df[prices_df["product"] == product]
    ts_min = int(product_df["timestamp"].min())
    ts_max = int(product_df["timestamp"].max())
    ts_range = st.sidebar.slider(
        "Timestamp",
        min_value=ts_min,
        max_value=ts_max,
        value=(ts_min, ts_max),
        step=100,
    )
    # Filter to selected range
    prices_df = prices_df[
        (prices_df["timestamp"] >= ts_range[0]) &
        (prices_df["timestamp"] <= ts_range[1])
    ]
    if not trades_df.empty:
        trades_df = trades_df[
            (trades_df["timestamp"] >= ts_range[0]) &
            (trades_df["timestamp"] <= ts_range[1])
        ]

    # ── Main Chart ──
    fig = build_orderbook_chart(
        prices_df=prices_df,
        trades_df=trades_df,
        product=product,
        show_levels=show_levels,
        show_trades=show_trades,
        show_own_trades=show_own_trades,
        qty_min=qty_min,
        qty_max=qty_max,
        normalize_col=normalize_col,
        downsample=downsample,
    )

    # Add position data to subplot 3 if available
    if position_data:
        pos_ts = sorted(position_data.keys())
        pos_vals = [position_data[t].get(product, 0) for t in pos_ts]
        fig.add_trace(go.Scattergl(
            x=pos_ts, y=pos_vals,
            mode="lines",
            line=dict(color=COLORS["position"], width=1.5),
            name="Position",
            hovertemplate="Pos: %{y}<br>t=%{x}<extra></extra>",
        ), row=3, col=1)
        fig.add_hline(y=0, line_dash="dash", line_color="#555", row=3, col=1)

    st.plotly_chart(fig, width="stretch", config={"scrollZoom": True})

    # ── Stats Row ──
    col1, col2, col3, col4 = st.columns(4)
    pdf = prices_df[prices_df["product"] == product]

    with col1:
        if "mid_price" in pdf.columns:
            current = pdf["mid_price"].iloc[-1] if not pdf.empty else 0
            st.metric("Current Mid", f"{current:,.0f}")

    with col2:
        if "profit_and_loss" in pdf.columns:
            pnl = pdf["profit_and_loss"].iloc[-1] if not pdf.empty else 0
            st.metric("Final PnL", f"{pnl:,.0f}")

    with col3:
        if not trades_df.empty:
            tdf = trades_df[trades_df["symbol"] == product]
            st.metric("Trades", f"{len(tdf)}")
        else:
            st.metric("Trades", "0")

    with col4:
        st.metric("Timestamps", f"{len(pdf)}")

    # ── Log Viewer ──
    if not logs_df.empty:
        st.markdown("---")
        st.subheader("Log Viewer")

        # Timestamp selector for logs
        log_timestamps = logs_df["timestamp"].unique()
        if len(log_timestamps) > 0:
            selected_ts = st.select_slider(
                "Select Timestamp",
                options=sorted(log_timestamps),
                value=sorted(log_timestamps)[0],
            )
            log_entry = logs_df[logs_df["timestamp"] == selected_ts]
            if not log_entry.empty:
                st.code(log_entry.iloc[0]["log_text"], language="text")

    # ── Trade Details Table ──
    if not trades_df.empty:
        st.markdown("---")
        with st.expander("Trade Details", expanded=False):
            tdf = trades_df[trades_df["symbol"] == product].copy()
            if not tdf.empty:
                display_cols = ["timestamp", "price", "quantity"]
                if "buyer" in tdf.columns:
                    display_cols.append("buyer")
                if "seller" in tdf.columns:
                    display_cols.append("seller")
                if "is_own" in tdf.columns:
                    display_cols.append("is_own")
                st.dataframe(
                    tdf[display_cols].sort_values("timestamp"),
                    width="stretch",
                    hide_index=True,
                )

    # ── Raw Data Explorer ──
    with st.expander("Raw Price Data", expanded=False):
        st.dataframe(
            pdf.head(200),
            width="stretch",
            hide_index=True,
        )


if __name__ == "__main__":
    main()
