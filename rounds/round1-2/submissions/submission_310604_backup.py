"""
IMC Prosperity 4 - Round 2 Submission
Strategy: Independent inventory-penalized market-making

ASH_COATED_OSMIUM: Fixed FV=10000. Take mispriced, make 1-tick inside bot.
  Spread ~16 mean, AC(1)=-0.50, no drift.
INTARIAN_PEPPER_ROOT: EMA(mid) fair value tracker. Take mispriced, make 1-tick inside bot.
  Spread ~14 mean, AC(1)=-0.51, drift +0.1/tick (+1000/day).

Inventory ladder: 4 tiers (normal/aggressive/emergency/hard-stop).
Position limit: 80 for both products.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

# +---------------------------------------------------------------+
# �  LOGGER                                                      �
# +---------------------------------------------------------------+

MAX_LOG_LENGTH = 3750


class Logger:
    def __init__(self):
        self._logs = ""

    def print(self, *args: Any, **kwargs: Any) -> None:
        self._logs += " ".join(str(a) for a in args) + "\n"

    def flush(
        self,
        state: TradingState,
        orders: Dict[str, List[Order]],
        conversions: int,
        trader_data: str,
    ) -> None:
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

    def _compress_state(self, state: TradingState) -> list:
        listings = {}
        for sym, listing in state.listings.items():
            listings[sym] = [listing.symbol, listing.product, listing.denomination]

        order_depths = {}
        for sym, od in state.order_depths.items():
            order_depths[sym] = [od.buy_orders, od.sell_orders]

        own_trades = {}
        for sym, trades in state.own_trades.items():
            own_trades[sym] = [
                [t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp]
                for t in trades
            ]

        market_trades = {}
        for sym, trades in state.market_trades.items():
            market_trades[sym] = [
                [t.symbol, t.price, t.quantity, t.buyer or "", t.seller or "", t.timestamp]
                for t in trades
            ]

        obs = {}
        if state.observations:
            obs["plain"] = state.observations.plainValueObservations
            obs["conv"] = {
                sym: {
                    "bid": co.bidPrice,
                    "ask": co.askPrice,
                    "transport": co.transportFees,
                    "export": co.exportTariff,
                    "import": co.importTariff,
                }
                for sym, co in state.observations.conversionObservations.items()
            }

        return [
            state.timestamp,
            state.traderData[:500] if state.traderData else "",
            listings,
            order_depths,
            own_trades,
            market_trades,
            state.position,
            obs,
        ]

    def _compress_orders(self, orders: Dict[str, List[Order]]) -> dict:
        return {
            sym: [[o.symbol, o.price, o.quantity] for o in order_list]
            for sym, order_list in orders.items()
        }


logger = Logger()


# +---------------------------------------------------------------+
# �  INVENTORY TIER CONSTANTS                                    �
# +---------------------------------------------------------------+

TIER_NORMAL = 50
TIER_AGGRESSIVE = 70


# +---------------------------------------------------------------+
# �  STRATEGY BASE CLASS                                         �
# +---------------------------------------------------------------+


class Strategy:
    def __init__(self, symbol: str, position_limit: int, soft_limit: int = 50):
        self.symbol = symbol
        self.position_limit = position_limit
        self.soft_limit = soft_limit

    def act(self, state: TradingState) -> List[Order]:
        raise NotImplementedError

    def get_position(self, state: TradingState) -> int:
        return state.position.get(self.symbol, 0)

    def max_buy_qty(self, position: int) -> int:
        return self.position_limit - position

    def max_sell_qty(self, position: int) -> int:
        return self.position_limit + position

    def soft_buy_qty(self, position: int) -> int:
        return max(0, self.soft_limit - position)

    def soft_sell_qty(self, position: int) -> int:
        return max(0, self.soft_limit + position)

    def soft_buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        """Buy clipped to soft_limit (not hard limit)."""
        capacity = self.soft_limit - position
        clipped = min(qty, capacity)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, clipped)

    def soft_sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        """Sell clipped to soft_limit (not hard limit)."""
        capacity = self.soft_limit + position
        clipped = min(qty, capacity)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, -clipped)

    def buy(self, price: int, qty: int, position: int) -> Optional[Order]:
        max_buy = self.position_limit - position
        clipped = min(qty, max_buy)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, clipped)

    def sell(self, price: int, qty: int, position: int) -> Optional[Order]:
        max_sell = self.position_limit + position
        clipped = min(qty, max_sell)
        if clipped <= 0:
            return None
        return Order(self.symbol, price, -clipped)

    def get_order_depth(self, state: TradingState) -> OrderDepth:
        return state.order_depths.get(self.symbol, OrderDepth())

    def best_bid(self, od: OrderDepth) -> Optional[int]:
        return max(od.buy_orders.keys()) if od.buy_orders else None

    def best_ask(self, od: OrderDepth) -> Optional[int]:
        return min(od.sell_orders.keys()) if od.sell_orders else None

    def inventory_tier(self, position: int) -> int:
        abs_pos = abs(position)
        if abs_pos >= self.position_limit:
            return 4
        elif abs_pos >= TIER_AGGRESSIVE:
            return 3
        elif abs_pos >= TIER_NORMAL:
            return 2
        return 1

    def save(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass


# +---------------------------------------------------------------+
# �  ASH_COATED_OSMIUM: Adaptive MM (EMA FV anchored to 10000)  �
# +---------------------------------------------------------------+


class ACOStrategy(Strategy):
    EMA_ALPHA = 2.0 / 14  # window ≈ 13
    SPREAD_ALPHA = 2.0 / 20  # window = 19 for spread tracking

    def __init__(self, symbol: str, position_limit: int, soft_limit: int = 70):
        super().__init__(symbol, position_limit, soft_limit)
        self.ema_fair: Optional[float] = None
        self.ema_spread: Optional[float] = None
        self.last_bid_price: Optional[int] = None
        self.last_ask_price: Optional[int] = None

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []
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

        # Phase 1: TAKE (capped at soft_limit)
        for ask_p in sorted(od.sell_orders.keys()):
            ask_v = abs(od.sell_orders[ask_p])
            if ask_p <= fair - 1:
                o = self.soft_buy(ask_p, ask_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity
            elif ask_p <= fair and position <= 0:
                o = self.soft_buy(ask_p, ask_v, position)
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
            elif bid_p >= fair and position >= 0:
                o = self.soft_sell(bid_p, bid_v, position)
                if o:
                    orders.append(o)
                    position += o.quantity

        # Phase 2: MAKE � 1 tick inside bot's remaining best quote
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())

        make_offset = max(1, int(self.ema_spread * 0.08))  # 1 at spread≤16, adapts
        bid_price = int(bid_wall + 1)
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if bp == self.last_bid_price and od.buy_orders[bp] >= 25:
                continue  # likely includes our own resting order
            if od.buy_orders[bp] > 1 and bp + make_offset < fair:
                bid_price = max(bid_price, bp + make_offset)
                break
        bid_price = min(bid_price, int(fair) - 1)

        ask_price = int(ask_wall - 1)
        for ap in sorted(od.sell_orders.keys()):
            if ap == self.last_ask_price and abs(od.sell_orders[ap]) >= 25:
                continue  # likely includes our own resting order
            if abs(od.sell_orders[ap]) > 1 and ap - make_offset > fair:
                ask_price = min(ask_price, ap - make_offset)
                break
        ask_price = max(ask_price, int(fair) + 1)

        max_buy = self.soft_buy_qty(position)
        max_sell = self.soft_sell_qty(position)

        if max_buy > 0:
            if bid_price - 1 >= int(bid_wall + 1):
                orders.append(Order(self.symbol, bid_price - 1, max_buy))
            else:
                orders.append(Order(self.symbol, bid_price, max_buy))
        if max_sell > 0:
            if ask_price + 1 <= int(ask_wall - 1):
                orders.append(Order(self.symbol, ask_price + 1, -max_sell))
            else:
                orders.append(Order(self.symbol, ask_price, -max_sell))

        self.last_bid_price = bid_price if max_buy > 0 else None
        self.last_ask_price = ask_price if max_sell > 0 else None

        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair, "es": self.ema_spread, "bp": self.last_bid_price, "ap": self.last_ask_price}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")
        self.ema_spread = data.get("es")
        self.last_bid_price = data.get("bp")
        self.last_ask_price = data.get("ap")


# +---------------------------------------------------------------+
# �  INTARIAN_PEPPER_ROOT: EMA-based MM with drift tracking      �
# +---------------------------------------------------------------+


class IPRStrategy(Strategy):
    EMA_ALPHA = 2.0 / 8  # window = 7, slower for smoother fair

    SPREAD_ALPHA = 2.0 / 20  # window = 19 for spread tracking

    def __init__(self, symbol: str, position_limit: int, soft_limit: int = 80):
        super().__init__(symbol, position_limit, soft_limit)
        self.ema_fair: Optional[float] = None
        self.ema_spread: Optional[float] = None
        self.last_ask_price: Optional[int] = None

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []
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
        wmid = (bb * av + ba * bv) / total if total > 0 else mid

        if self.ema_fair is None:
            self.ema_fair = wmid
        else:
            self.ema_fair = self.EMA_ALPHA * wmid + (1 - self.EMA_ALPHA) * self.ema_fair

        # Phase 1: TAKE -- buy everything up to take_cap (capture drift)
        # More aggressive when position is low (need to fill up)
        base_cap = max(4, int(self.ema_spread * 0.4))
        # Continuously scale: +0 at pos=80, +5 at pos=0
        pos_bonus = max(0, int((80 - position) * 0.06))
        take_cap = int(self.ema_fair) + base_cap + pos_bonus
        for ask_p in sorted(od.sell_orders.keys()):
            ask_v = abs(od.sell_orders[ask_p])
            remaining = self.position_limit - position
            if remaining <= 0:
                break
            if ask_p <= take_cap:
                qty = min(ask_v, remaining)
                orders.append(Order(self.symbol, ask_p, qty))
                position += qty

        # Phase 2: MAKE SELL -- at high prices to earn spread
        ask_wall = max(od.sell_orders.keys())
        ask_floor = int(self.ema_fair) + max(5, int(self.ema_spread * 0.5))

        # Join best ask
        ask_price = max(ba, ask_floor)

        sell_qty = min(10, self.position_limit + position)
        if sell_qty > 0:
            orders.append(Order(self.symbol, ask_price, -sell_qty))

        # Phase 3: MAKE BUY -- replenish position at best bid (no penny jump)
        remaining = self.position_limit - position
        if remaining > 0:
            bid_price = bb  # join best bid
            bid_price = min(bid_price, int(self.ema_fair))
            orders.append(Order(self.symbol, bid_price, remaining))

        self.last_ask_price = ask_price if sell_qty > 0 else None

        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair, "es": self.ema_spread, "ap": self.last_ask_price}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")
        self.ema_spread = data.get("es")
        self.last_ask_price = data.get("ap")


# +---------------------------------------------------------------+
# �  TRADER (entry point)                                        �
# +---------------------------------------------------------------+


class Trader:
    def __init__(self):
        self.strategies = [
            ACOStrategy("ASH_COATED_OSMIUM", position_limit=80, soft_limit=70),
            IPRStrategy("INTARIAN_PEPPER_ROOT", position_limit=80),
        ]

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        try:
            saved = {}
            if state.traderData and state.traderData.strip():
                try:
                    saved = json.loads(state.traderData)
                except (json.JSONDecodeError, ValueError):
                    saved = {}

            all_orders: Dict[str, List[Order]] = {}
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

    def bid(self, state: TradingState) -> int:
        # MAF: bid for 25% extra order book flow
        # Top 50% of bids accepted, bid deducted from PnL
        # Our MM strategy is flow-sensitive (~25% more flow � 15-24K extra PnL)
        # Conservative bid: likely above median of all participants
        return 2000