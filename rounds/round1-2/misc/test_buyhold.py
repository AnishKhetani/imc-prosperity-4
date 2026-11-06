"""Test: ACO unchanged, IPR = pure buy-and-hold to measure drift capture ceiling."""
import json
from typing import Any, Dict, List, Optional, Tuple
from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

MAX_LOG_LENGTH = 3750

class Logger:
    def __init__(self):
        self._logs = ""
    def print(self, *args: Any, **kwargs: Any) -> None:
        self._logs += " ".join(str(a) for a in args) + "\n"
    def flush(self, state, orders, conversions, trader_data):
        output = json.dumps([
            self._compress_state(state),
            self._compress_orders(orders),
            conversions,
            trader_data[:500] if trader_data else "",
            self._logs.rstrip(),
        ], separators=(",", ":"))
        if len(output) > MAX_LOG_LENGTH:
            half = (MAX_LOG_LENGTH - 3) // 2
            output = output[:half] + "..." + output[-half:]
        print(output)
        self._logs = ""
    def _compress_state(self, state):
        return [state.timestamp, "", {}, {}, {}, {}, state.position, {}]
    def _compress_orders(self, orders):
        return {sym: [[o.symbol, o.price, o.quantity] for o in ol] for sym, ol in orders.items()}

logger = Logger()

TIER_NORMAL = 50
TIER_AGGRESSIVE = 70

class Strategy:
    def __init__(self, symbol, position_limit, soft_limit=50):
        self.symbol = symbol
        self.position_limit = position_limit
        self.soft_limit = soft_limit
    def act(self, state): raise NotImplementedError
    def get_position(self, state): return state.position.get(self.symbol, 0)
    def max_buy_qty(self, pos): return self.position_limit - pos
    def max_sell_qty(self, pos): return self.position_limit + pos
    def soft_buy_qty(self, pos): return max(0, self.soft_limit - pos)
    def soft_sell_qty(self, pos): return max(0, self.soft_limit + pos)
    def soft_buy(self, price, qty, pos):
        cap = self.soft_limit - pos
        c = min(qty, cap)
        return Order(self.symbol, price, c) if c > 0 else None
    def soft_sell(self, price, qty, pos):
        cap = self.soft_limit + pos
        c = min(qty, cap)
        return Order(self.symbol, price, -c) if c > 0 else None
    def buy(self, price, qty, pos):
        c = min(qty, self.position_limit - pos)
        return Order(self.symbol, price, c) if c > 0 else None
    def sell(self, price, qty, pos):
        c = min(qty, self.position_limit + pos)
        return Order(self.symbol, price, -c) if c > 0 else None
    def get_order_depth(self, state): return state.order_depths.get(self.symbol, OrderDepth())
    def best_bid(self, od): return max(od.buy_orders.keys()) if od.buy_orders else None
    def best_ask(self, od): return min(od.sell_orders.keys()) if od.sell_orders else None
    def inventory_tier(self, pos):
        a = abs(pos)
        if a >= self.position_limit: return 4
        elif a >= TIER_AGGRESSIVE: return 3
        elif a >= TIER_NORMAL: return 2
        return 1
    def save(self): return {}
    def load(self, data): pass


# ACO: exact copy from submission.py
class ACOStrategy(Strategy):
    EMA_ALPHA = 2.0 / 16
    SPREAD_ALPHA = 2.0 / 20
    def __init__(self, symbol, position_limit, soft_limit=70):
        super().__init__(symbol, position_limit, soft_limit)
        self.ema_fair = None
        self.ema_spread = None
        self.last_bid_price = None
        self.last_ask_price = None

    def act(self, state):
        position = self.get_position(state)
        orders = []
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return orders
        bb = self.best_bid(od)
        ba = self.best_ask(od)
        mid = (bb + ba) / 2.0
        spread = ba - bb
        if self.ema_spread is None:
            self.ema_spread = float(spread)
        else:
            self.ema_spread = self.SPREAD_ALPHA * spread + (1 - self.SPREAD_ALPHA) * self.ema_spread
        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        total = bv + av
        if self.ema_fair is None:
            self.ema_fair = mid
        else:
            self.ema_fair = self.EMA_ALPHA * mid + (1 - self.EMA_ALPHA) * self.ema_fair
        imb = (bv - av) / total if total > 0 else 0.0
        fair = round(self.ema_fair + imb * 1.0)
        for ask_p in sorted(od.sell_orders.keys()):
            ask_v = abs(od.sell_orders[ask_p])
            if ask_p <= fair - 1:
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity
            elif ask_p <= fair and position < 0:
                o = self.soft_buy(ask_p, min(ask_v, abs(position)), position)
                if o:
                    orders.append(o)
                    position += o.quantity
        for bid_p in sorted(od.buy_orders.keys(), reverse=True):
            bid_v = od.buy_orders[bid_p]
            if bid_p >= fair + 1:
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity
            elif bid_p >= fair and position > 0:
                o = self.soft_sell(bid_p, min(bid_v, position), position)
                if o:
                    orders.append(o)
                    position += o.quantity
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())
        make_offset = max(1, int(self.ema_spread * 0.08))
        bid_price = int(bid_wall + 1)
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp == self.last_bid_price and od.buy_orders[bp] >= 25:
                continue
            if od.buy_orders[bp] > 1 and bp + make_offset < fair:
                bid_price = max(bid_price, bp + make_offset)
                break
        bid_price = min(bid_price, int(fair) - 1)
        ask_price = int(ask_wall - 1)
        for ap in sorted(od.sell_orders.keys()):
            if ap == self.last_ask_price and abs(od.sell_orders[ap]) >= 25:
                continue
            if abs(od.sell_orders[ap]) > 1 and ap - make_offset > fair:
                ask_price = min(ask_price, ap - make_offset)
                break
        ask_price = max(ask_price, int(fair) + 1)
        max_buy = self.soft_buy_qty(position)
        max_sell = self.soft_sell_qty(position)
        if max_buy > 0:
            tight_buy = max(1, int(max_buy * 0.1))
            wide_buy = max_buy - tight_buy
            orders.append(Order(self.symbol, bid_price, tight_buy))
            if wide_buy > 0 and bid_price - 1 >= int(bid_wall + 1):
                orders.append(Order(self.symbol, bid_price - 1, wide_buy))
            elif wide_buy > 0:
                orders.append(Order(self.symbol, bid_price, wide_buy))
        if max_sell > 0:
            tight_sell = max(1, int(max_sell * 0.1))
            wide_sell = max_sell - tight_sell
            orders.append(Order(self.symbol, ask_price, -tight_sell))
            if wide_sell > 0 and ask_price + 1 <= int(ask_wall - 1):
                orders.append(Order(self.symbol, ask_price + 1, -wide_sell))
            elif wide_sell > 0:
                orders.append(Order(self.symbol, ask_price, -wide_sell))
        self.last_bid_price = bid_price if max_buy > 0 else None
        self.last_ask_price = ask_price if max_sell > 0 else None
        return orders

    def save(self):
        return {"ef": self.ema_fair, "es": self.ema_spread, "bp": self.last_bid_price, "ap": self.last_ask_price}
    def load(self, data):
        self.ema_fair = data.get("ef")
        self.ema_spread = data.get("es")
        self.last_bid_price = data.get("bp")
        self.last_ask_price = data.get("ap")


# IPR: Buy-and-hold only — take all asks up to position limit, never sell
class IPRBuyHoldStrategy(Strategy):
    def act(self, state):
        position = self.get_position(state)
        orders = []
        od = self.get_order_depth(state)
        if not od.sell_orders:
            return orders
        # Buy everything we can
        for ask_p in sorted(od.sell_orders.keys()):
            ask_v = abs(od.sell_orders[ask_p])
            remaining = self.position_limit - position
            if remaining <= 0:
                break
            qty = min(ask_v, remaining)
            orders.append(Order(self.symbol, ask_p, qty))
            position += qty
        return orders


class Trader:
    def __init__(self):
        self.strategies = [
            ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=70),
            IPRBuyHoldStrategy("INTARIAN_PEPPER_ROOT", position_limit=80),
        ]

    def run(self, state):
        try:
            saved = {}
            if state.traderData and state.traderData.strip():
                try:
                    saved = json.loads(state.traderData)
                except (json.JSONDecodeError, ValueError):
                    saved = {}
            all_orders = {}
            conversions = 0
            for strategy in self.strategies:
                symbol = strategy.symbol
                strategy.load(saved.get(symbol, {}))
                if symbol in state.order_depths:
                    orders = strategy.act(state)
                    if orders:
                        all_orders[symbol] = orders
                saved[symbol] = strategy.save()
            trader_data = json.dumps(saved, separators=(",", ":"))
            logger.flush(state, all_orders, conversions, trader_data)
            return all_orders, conversions, trader_data
        except Exception:
            try:
                logger.flush(state, {}, 0, state.traderData or "")
            except Exception:
                pass
            return {}, 0, state.traderData or ""

    def bid(self, state):
        return 2000
