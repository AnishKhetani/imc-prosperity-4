"""
Systematic test of multiple TOMATOES strategies using the prosperity3bt backtester.
Tests various approaches side-by-side on both training days.

Key insight from analysis:
- Mid-price is as good as EMA for fair value prediction
- Variance ratios 0.15-0.31 → strong mean-reversion (bid-ask bounce)
- All platform fills are makes (passive)
- Bot spread ~13 (offset ~6.5 each side)
- WIDTH=6 barely drops fills vs WIDTH=5 in backtester
- Simpler strategies outperform complex ones on platform
"""
import sys
import os
import json
import importlib
from pathlib import Path

# Add backtester dir to path
BACKTESTER_DIR = Path(__file__).parent.parent / "backtester"
sys.path.insert(0, str(BACKTESTER_DIR))

from prosperity3bt.file_reader import FileSystemReader
from prosperity3bt.models import TradeMatchingMode
from prosperity3bt.runner import run_backtest
from prosperity3bt.data import LIMITS

LIMITS["EMERALDS"] = 80
LIMITS["TOMATOES"] = 80

DATA_DIR = BACKTESTER_DIR / "data" / "tutorial"

# We need to create variant trader modules dynamically.
# Instead, we use a parametric approach: modify the strategy in trader.py to accept params.

# Import the datamodel
sys.path.insert(0, str(BACKTESTER_DIR))
from datamodel import Order, OrderDepth, TradingState


class TomatoesVariant:
    """Parametric TOMATOES strategy for testing."""
    def __init__(self, name, params):
        self.name = name
        self.params = params
        self.symbol = "TOMATOES"
        self.position_limit = 80
        self.price_history = []
        self.ema = 0.0

    def get_position(self, state):
        return state.position.get(self.symbol, 0)

    def get_order_depth(self, state):
        return state.order_depths.get(self.symbol, OrderDepth())

    def mid_price(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        return (bb + ba) / 2.0

    def spread(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        return ba - bb

    def l1_imbalance(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return 0.0
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        bid_vol = od.buy_orders[bb]
        ask_vol = abs(od.sell_orders[ba])
        total = bid_vol + ask_vol
        if total == 0:
            return 0.0
        return (bid_vol - ask_vol) / total

    def weighted_mid(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        bid_vol = od.buy_orders[bb]
        ask_vol = abs(od.sell_orders[ba])
        total = bid_vol + ask_vol
        if total == 0:
            return (bb + ba) / 2.0
        return (bb * ask_vol + ba * bid_vol) / total

    def buy(self, price, qty, position):
        max_buy = self.position_limit - position
        clipped = min(qty, max_buy)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, clipped)

    def sell(self, price, qty, position):
        max_sell = self.position_limit + position
        clipped = min(qty, max_sell)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, -clipped)

    def max_buy_qty(self, position):
        return self.position_limit - position

    def max_sell_qty(self, position):
        return self.position_limit + position


def strategy_current(variant, state):
    """Current strategy: EMA(5) + IMB + DEPTH_CONTRARIAN, WIDTH=5"""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    variant.price_history.append(mid)
    if len(variant.price_history) <= 1:
        variant.ema = mid
    else:
        alpha = 2.0 / (5 + 1)
        variant.ema = alpha * mid + (1 - alpha) * variant.ema

    imb = variant.l1_imbalance(state)
    adjusted_fair = variant.ema + imb * 0.5 - position * 0.05
    fair = round(adjusted_fair)

    # Take (TAKE_EDGE=0, so no takes)
    # Make
    bid = fair - 5
    ask = fair + 5

    pos_ratio = position / variant.position_limit
    if pos_ratio > 0.6:
        bid -= 1; ask -= 1
    elif pos_ratio > 0.15:
        ask -= 1
    elif pos_ratio < -0.6:
        bid += 1; ask += 1
    elif pos_ratio < -0.15:
        bid += 1

    # Depth contrarian
    od = variant.get_order_depth(state)
    bid_depth = sum(od.buy_orders.values()) if od.buy_orders else 0
    ask_depth = sum(abs(v) for v in od.sell_orders.values()) if od.sell_orders else 0
    total_depth = bid_depth + ask_depth
    depth_imb = (bid_depth - ask_depth) / total_depth if total_depth > 0 else 0
    if depth_imb > 0.1:
        ask -= 1
    elif depth_imb < -0.1:
        bid += 1

    # Asymmetric sizing
    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)
    if abs(pos_ratio) >= 0.15:
        if pos_ratio > 0:
            remaining_buy = max(1, int(remaining_buy * 0.5))
        else:
            remaining_sell = max(1, int(remaining_sell * 0.5))

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w5(variant, state):
    """Simple: raw mid, WIDTH=5, no adjustments, full size."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 5
    ask = fair + 5

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w6(variant, state):
    """Simple: raw mid, WIDTH=6, no adjustments."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 6
    ask = fair + 6

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_adaptive_width(variant, state):
    """Adaptive: WIDTH=6 when spread>=11, WIDTH=4 otherwise."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    spread = variant.spread(state)

    if spread is not None and spread >= 11:
        width = 6
    else:
        width = 4

    bid = fair - width
    ask = fair + width

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_wmid_w5(variant, state):
    """Weighted mid for fair value, WIDTH=5."""
    position = variant.get_position(state)
    orders = []
    wmid = variant.weighted_mid(state)
    if wmid is None:
        return []

    fair = round(wmid)
    bid = fair - 5
    ask = fair + 5

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_wmid_w6(variant, state):
    """Weighted mid for fair value, WIDTH=6."""
    position = variant.get_position(state)
    orders = []
    wmid = variant.weighted_mid(state)
    if wmid is None:
        return []

    fair = round(wmid)
    bid = fair - 6
    ask = fair + 6

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w5_softskew(variant, state):
    """Mid + WIDTH=5 with soft position skew (only at extreme positions)."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 5
    ask = fair + 5

    # Soft continuous skew based on position
    # At position 40 (50% of limit), shift quotes by 1
    pos_ratio = position / variant.position_limit
    if abs(pos_ratio) > 0.5:
        skew = 1 if pos_ratio > 0 else -1
        bid -= skew
        ask -= skew

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w6_softskew(variant, state):
    """Mid + WIDTH=6 with soft position skew only at extreme."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 6
    ask = fair + 6

    pos_ratio = position / variant.position_limit
    if abs(pos_ratio) > 0.5:
        skew = 1 if pos_ratio > 0 else -1
        bid -= skew
        ask -= skew

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_adaptive_w6_tight(variant, state):
    """WIDTH=6 when spread>=13, WIDTH=5 when 9-12, WIDTH=3 when <9."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    spread = variant.spread(state)

    if spread is not None and spread >= 13:
        width = 6
    elif spread is not None and spread >= 9:
        width = 5
    else:
        width = 3

    bid = fair - width
    ask = fair + width

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w3(variant, state):
    """Simple: raw mid, WIDTH=3 (backtester optimal)."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 3
    ask = fair + 3

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_simple_mid_w4(variant, state):
    """Simple: raw mid, WIDTH=4."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    fair = round(mid)
    bid = fair - 4
    ask = fair + 4

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_imb_skew_w5(variant, state):
    """Mid + L1 imbalance for fair (no EMA), WIDTH=5."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    imb = variant.l1_imbalance(state)
    adjusted_fair = mid + imb * 0.5
    fair = round(adjusted_fair)
    bid = fair - 5
    ask = fair + 5

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


def strategy_imb_skew_w6(variant, state):
    """Mid + L1 imbalance for fair (no EMA), WIDTH=6."""
    position = variant.get_position(state)
    orders = []
    mid = variant.mid_price(state)
    if mid is None:
        return []

    imb = variant.l1_imbalance(state)
    adjusted_fair = mid + imb * 0.5
    fair = round(adjusted_fair)
    bid = fair - 6
    ask = fair + 6

    remaining_buy = variant.max_buy_qty(position)
    remaining_sell = variant.max_sell_qty(position)

    buy_order = variant.buy(bid, remaining_buy, position)
    if buy_order:
        orders.append(buy_order)
    sell_order = variant.sell(ask, remaining_sell, position)
    if sell_order:
        orders.append(sell_order)

    return orders


# ==================== RUNNER ====================

def create_trader_class(strategy_func, strategy_name):
    """Create a Trader class that uses the given strategy function for TOMATOES."""
    
    class TestTrader:
        def __init__(self):
            self.tomatoes = TomatoesVariant(strategy_name, {})
            self.emeralds_fair = 10000
            
        def run(self, state):
            all_orders = {}
            conversions = 0
            trader_data = ""
            
            # EMERALDS: fixed strategy (keep same for comparison)
            if "EMERALDS" in state.order_depths:
                position = state.position.get("EMERALDS", 0)
                em_orders = []
                bid_price = 9993
                ask_price = 10007
                max_buy = 80 - position
                max_sell = 80 + position
                if max_buy > 0:
                    em_orders.append(Order("EMERALDS", bid_price, max_buy))
                if max_sell > 0:
                    em_orders.append(Order("EMERALDS", ask_price, -max_sell))
                all_orders["EMERALDS"] = em_orders
            
            # TOMATOES: variable strategy
            if "TOMATOES" in state.order_depths:
                tom_orders = strategy_func(self.tomatoes, state)
                all_orders["TOMATOES"] = tom_orders
            
            return all_orders, conversions, trader_data
    
    return TestTrader


def run_test(strategy_func, strategy_name, day, round_num=0):
    """Run a single backtest and return PnL."""
    file_reader = FileSystemReader(DATA_DIR)
    TraderClass = create_trader_class(strategy_func, strategy_name)
    trader = TraderClass()
    
    result = run_backtest(
        trader=trader,
        file_reader=file_reader,
        round_num=round_num,
        day_num=day,
        trade_matching_mode=TradeMatchingMode.all,
        print_output=False,
        no_names=True,
        show_progress_bar=False,
    )
    
    # Extract PnL from activity_logs
    # ActivityLogRow has .columns which is: [day, timestamp, product, bid1, bvol1, bid2, bvol2, bid3, bvol3, ask1, avol1, ask2, avol2, ask3, avol3, mid_price, pnl]
    tom_pnl = 0
    em_pnl = 0
    for row in reversed(result.activity_logs):
        cols = row.columns
        product = cols[2]
        pnl = cols[-1]
        if product == 'TOMATOES' and tom_pnl == 0:
            tom_pnl = float(pnl)
        elif product == 'EMERALDS' and em_pnl == 0:
            em_pnl = float(pnl)
        if tom_pnl != 0 and em_pnl != 0:
            break
    
    total_pnl = tom_pnl + em_pnl
    return tom_pnl, em_pnl, total_pnl, result


# ==================== MAIN ====================

STRATEGIES = [
    ("adaptive_w6_11", strategy_adaptive_width),
    ("adaptive_w6_tight", strategy_adaptive_w6_tight),
    ("imb_w5", strategy_imb_skew_w5),
    ("imb_w6", strategy_imb_skew_w6),
    ("mid_w5_softskew", strategy_simple_mid_w5_softskew),
    ("mid_w6_softskew", strategy_simple_mid_w6_softskew),
]

print(f"{'Strategy':<25} {'D-2 TOM':>10} {'D-1 TOM':>10} {'Avg TOM':>10} {'Diff%':>8} {'D-2 Total':>10} {'D-1 Total':>10}")
print("-" * 95)

results = []
for name, func in STRATEGIES:
    tom_d2, em_d2, total_d2, _ = run_test(func, name, -2)
    tom_d1, em_d1, total_d1, _ = run_test(func, name, -1)
    
    avg_tom = (tom_d2 + tom_d1) / 2
    diff_pct = abs(tom_d2 - tom_d1) / max(avg_tom, 1) * 100
    
    print(f"{name:<25} {tom_d2:>10.1f} {tom_d1:>10.1f} {avg_tom:>10.1f} {diff_pct:>7.1f}% {total_d2:>10.1f} {total_d1:>10.1f}")
    results.append((name, tom_d2, tom_d1, avg_tom, diff_pct))

print("\n" + "=" * 95)
print("RANKED BY AVERAGE TOMATOES PnL:")
print("=" * 95)
for name, d2, d1, avg, diff in sorted(results, key=lambda x: -x[3]):
    print(f"  {name:<25} avg={avg:>10.1f}  D-2={d2:>10.1f}  D-1={d1:>10.1f}  stability={100-diff:.0f}%")
