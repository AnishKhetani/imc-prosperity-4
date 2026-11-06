"""
Round 2: Test refined strategy variants based on Round 1 findings.
Key findings: WIDTH=6 dominates, adaptive_w6_11 best (7823, 90% stable),
simpler > complex, mid-price as good as EMA.
"""
import sys
from pathlib import Path

BACKTESTER_DIR = Path(__file__).parent.parent / "backtester"
sys.path.insert(0, str(BACKTESTER_DIR))

from prosperity3bt.file_reader import FileSystemReader
from prosperity3bt.models import TradeMatchingMode, BacktestResult
from prosperity3bt.runner import run_backtest
from prosperity3bt.data import LIMITS

LIMITS["EMERALDS"] = 80
LIMITS["TOMATOES"] = 80

DATA_DIR = BACKTESTER_DIR / "data" / "tutorial"

from datamodel import Order, OrderDepth, TradingState


class TomatoesVariant:
    def __init__(self, name):
        self.name = name
        self.symbol = "TOMATOES"
        self.position_limit = 80
        self.price_history = []
        self.ema = 0.0
        self.fill_count = 0

    def get_position(self, state):
        return state.position.get(self.symbol, 0)

    def get_order_depth(self, state):
        return state.order_depths.get(self.symbol, OrderDepth())

    def mid_price(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        return (max(od.buy_orders.keys()) + min(od.sell_orders.keys())) / 2.0

    def spread(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        return min(od.sell_orders.keys()) - max(od.buy_orders.keys())

    def weighted_mid(self, state):
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return None
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        total = bv + av
        if total == 0:
            return (bb + ba) / 2.0
        return (bb * av + ba * bv) / total

    def buy(self, price, qty, position):
        clipped = min(qty, self.position_limit - position)
        return Order(self.symbol, price, clipped) if clipped > 0 else None

    def sell(self, price, qty, position):
        clipped = min(qty, self.position_limit + position)
        return Order(self.symbol, price, -clipped) if clipped > 0 else None

    def max_buy_qty(self, pos): return self.position_limit - pos
    def max_sell_qty(self, pos): return self.position_limit + pos


# ==================== STRATEGY VARIANTS ====================

def adaptive_w6_11(v, state):
    """BEST: adaptive WIDTH=6 when spread>=11, else WIDTH=4."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 11 else 4
    orders = []
    b = v.buy(fair - width, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(fair + width, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def adaptive_w6_11_softskew(v, state):
    """Adaptive WIDTH=6/4 + soft position skew at 50%."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 11 else 4
    bid = fair - width
    ask = fair + width
    pr = pos / v.position_limit
    if abs(pr) > 0.5:
        skew = 1 if pr > 0 else -1
        bid -= skew
        ask -= skew
    orders = []
    b = v.buy(bid, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(ask, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def adaptive_w6_13(v, state):
    """WIDTH=6 when spread>=13, WIDTH=5 otherwise."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 13 else 5
    orders = []
    b = v.buy(fair - width, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(fair + width, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def adaptive_w6_13_softskew(v, state):
    """WIDTH=6 when spread>=13, WIDTH=5 otherwise + soft skew."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 13 else 5
    bid = fair - width
    ask = fair + width
    pr = pos / v.position_limit
    if abs(pr) > 0.5:
        skew = 1 if pr > 0 else -1
        bid -= skew; ask -= skew
    orders = []
    b = v.buy(bid, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(ask, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def wmid_adaptive_w6_11(v, state):
    """Weighted mid + adaptive WIDTH=6/4."""
    pos = v.get_position(state)
    wmid = v.weighted_mid(state)
    if wmid is None: return []
    fair = round(wmid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 11 else 4
    orders = []
    b = v.buy(fair - width, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(fair + width, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def wmid_adaptive_w6_11_softskew(v, state):
    """Weighted mid + adaptive WIDTH=6/4 + soft skew."""
    pos = v.get_position(state)
    wmid = v.weighted_mid(state)
    if wmid is None: return []
    fair = round(wmid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 11 else 4
    bid = fair - width
    ask = fair + width
    pr = pos / v.position_limit
    if abs(pr) > 0.5:
        skew = 1 if pr > 0 else -1
        bid -= skew; ask -= skew
    orders = []
    b = v.buy(bid, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(ask, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def two_level_w5_w6(v, state):
    """Two-level: small tier at WIDTH=5, rest at WIDTH=6."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    orders = []
    
    # Level 1: WIDTH=5, 30% of available size
    remaining_buy = v.max_buy_qty(pos)
    remaining_sell = v.max_sell_qty(pos)
    l1_buy = max(1, int(remaining_buy * 0.3))
    l1_sell = max(1, int(remaining_sell * 0.3))
    
    b1 = v.buy(fair - 5, l1_buy, pos)
    if b1: orders.append(b1); pos += b1.quantity
    s1 = v.sell(fair + 5, l1_sell, pos)
    if s1: orders.append(s1); pos += s1.quantity
    
    # Level 2: WIDTH=6, rest
    remaining_buy = v.max_buy_qty(pos)
    remaining_sell = v.max_sell_qty(pos)
    b2 = v.buy(fair - 6, remaining_buy, pos)
    if b2: orders.append(b2)
    s2 = v.sell(fair + 6, remaining_sell, pos)
    if s2: orders.append(s2)
    
    return orders


def adaptive_pos_width(v, state):
    """Position-dependent width: W=6 at flat, W=5 at |pos|>30, W=4 at |pos|>50."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    
    abs_pos = abs(pos)
    if abs_pos > 50:
        width = 4
    elif abs_pos > 30:
        width = 5
    else:
        width = 6
    
    orders = []
    b = v.buy(fair - width, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(fair + width, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


def adaptive_w6_cancelextend(v, state):
    """WIDTH=6, but cancel extending side when |pos|>60."""
    pos = v.get_position(state)
    mid = v.mid_price(state)
    if mid is None: return []
    fair = round(mid)
    sp = v.spread(state)
    width = 6 if sp and sp >= 11 else 4
    
    orders = []
    pr = pos / v.position_limit
    
    # Cancel extending side at extreme position
    if pr < 0.75:  # not heavily long, quote bid
        b = v.buy(fair - width, v.max_buy_qty(pos), pos)
        if b: orders.append(b)
    if pr > -0.75:  # not heavily short, quote ask
        s = v.sell(fair + width, v.max_sell_qty(pos), pos)
        if s: orders.append(s)
    
    return orders


def microprice_w6(v, state):
    """Microprice fair value + WIDTH=6.
    Microprice = bid*ask_vol + ask*bid_vol / (bid_vol + ask_vol)
    (same as weighted mid but explicitly named)."""
    pos = v.get_position(state)
    od = v.get_order_depth(state)
    if not od.buy_orders or not od.sell_orders:
        return []
    
    bb = max(od.buy_orders.keys())
    ba = min(od.sell_orders.keys())
    bv = od.buy_orders[bb]
    av = abs(od.sell_orders[ba])
    sp = ba - bb
    
    # Microprice
    total = bv + av
    if total > 0:
        fair = round((bb * av + ba * bv) / total)
    else:
        fair = round((bb + ba) / 2)
    
    width = 6 if sp >= 11 else 4
    
    orders = []
    b = v.buy(fair - width, v.max_buy_qty(pos), pos)
    if b: orders.append(b)
    s = v.sell(fair + width, v.max_sell_qty(pos), pos)
    if s: orders.append(s)
    return orders


# ==================== RUNNER ====================

def create_trader_class(strategy_func, strategy_name):
    class TestTrader:
        def __init__(self):
            self.tomatoes = TomatoesVariant(strategy_name)
        def run(self, state):
            all_orders = {}
            if "EMERALDS" in state.order_depths:
                position = state.position.get("EMERALDS", 0)
                em_orders = []
                max_buy = 80 - position
                max_sell = 80 + position
                if max_buy > 0:
                    em_orders.append(Order("EMERALDS", 9993, max_buy))
                if max_sell > 0:
                    em_orders.append(Order("EMERALDS", 10007, -max_sell))
                all_orders["EMERALDS"] = em_orders
            if "TOMATOES" in state.order_depths:
                all_orders["TOMATOES"] = strategy_func(self.tomatoes, state)
            return all_orders, 0, ""
    return TestTrader


def run_test(strategy_func, strategy_name, day, round_num=0):
    file_reader = FileSystemReader(DATA_DIR)
    trader = create_trader_class(strategy_func, strategy_name)()
    result = run_backtest(
        trader=trader, file_reader=file_reader,
        round_num=round_num, day_num=day,
        trade_matching_mode=TradeMatchingMode.all,
        print_output=False, no_names=True, show_progress_bar=False,
    )
    tom_pnl = em_pnl = 0
    for row in reversed(result.activity_logs):
        cols = row.columns
        if cols[2] == 'TOMATOES' and tom_pnl == 0:
            tom_pnl = float(cols[-1])
        elif cols[2] == 'EMERALDS' and em_pnl == 0:
            em_pnl = float(cols[-1])
        if tom_pnl != 0 and em_pnl != 0:
            break
    return tom_pnl, em_pnl, tom_pnl + em_pnl


STRATEGIES = [
    ("adaptive_w6_11 (best)", adaptive_w6_11),
    ("adaptive_w6_11+skew", adaptive_w6_11_softskew),
    ("adaptive_w6_13", adaptive_w6_13),
    ("adaptive_w6_13+skew", adaptive_w6_13_softskew),
    ("wmid_adaptive_w6_11", wmid_adaptive_w6_11),
    ("wmid_adapt_w6_11+sk", wmid_adaptive_w6_11_softskew),
    ("two_level_w5_w6", two_level_w5_w6),
    ("adaptive_pos_width", adaptive_pos_width),
    ("adapt_w6_cancelext", adaptive_w6_cancelextend),
    ("microprice_w6", microprice_w6),
]

print(f"{'Strategy':<25} {'D-2 TOM':>10} {'D-1 TOM':>10} {'Avg TOM':>10} {'Diff%':>8}")
print("-" * 60)

results = []
for name, func in STRATEGIES:
    t2, _, _ = run_test(func, name, -2)
    t1, _, _ = run_test(func, name, -1)
    avg = (t2 + t1) / 2
    diff = abs(t2 - t1) / max(avg, 1) * 100
    print(f"{name:<25} {t2:>10.1f} {t1:>10.1f} {avg:>10.1f} {diff:>7.1f}%")
    results.append((name, t2, t1, avg, diff))

print("\nRANKED BY AVERAGE:")
for name, d2, d1, avg, diff in sorted(results, key=lambda x: -x[3]):
    print(f"  {name:<25} avg={avg:>8.1f}  D-2={d2:>8.1f}  D-1={d1:>8.1f}  stab={100-diff:.0f}%")
