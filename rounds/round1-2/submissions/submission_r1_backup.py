"""
IMC Prosperity 4 - Single-file submission (Round 1).
Strategy - ADAPTIVE MARKET MAKING:
  Both products use adaptive pricing: place 1 tick inside bot's best quote.
  This guarantees best-quote status on every tick, maximising fill capture.

  ASH_COATED_OSMIUM: fixed FV=10000 (anchored, NOT wall_mid). Take at FV+-1.
    Bot spread 5-21 (modal 16). AC(1)=-0.49, mean-reverting.
  INTARIAN_PEPPER_ROOT: EMA(mid) + L1 imbalance + position skew. Take at fair+-edge.
    Bot spread 2-20 (modal 13). AC(1)=-0.51, mean-reverting. ~+100 drift/day.
"""

import json
from typing import Any, Dict, List, Optional, Tuple

from datamodel import (
    Listing, Observation, Order, OrderDepth, ConversionObservation,
    Trade, TradingState, Symbol, Product, Position,
)

# ╔═══════════════════════════════════════════════════════════════╗
# ║  LOGGER                                                      ║
# ╚═══════════════════════════════════════════════════════════════╝

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


# ╔═══════════════════════════════════════════════════════════════╗
# ║  STRATEGY BASE CLASS                                         ║
# ╚═══════════════════════════════════════════════════════════════╝


class Strategy:
    def __init__(self, symbol: str, position_limit: int):
        self.symbol = symbol
        self.position_limit = position_limit

    def act(self, state: TradingState) -> List[Order]:
        raise NotImplementedError

    # ── Position helpers ──────────────────────────────────────────

    def get_position(self, state: TradingState) -> int:
        return state.position.get(self.symbol, 0)

    def max_buy_qty(self, position: int) -> int:
        return self.position_limit - position

    def max_sell_qty(self, position: int) -> int:
        return self.position_limit + position

    # ── Order creation (clipped to limits) ────────────────────────

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

    # ── Order book helpers ────────────────────────────────────────

    def get_order_depth(self, state: TradingState) -> OrderDepth:
        return state.order_depths.get(self.symbol, OrderDepth())

    def best_bid(self, state: TradingState) -> Optional[int]:
        od = self.get_order_depth(state)
        return max(od.buy_orders.keys()) if od.buy_orders else None

    def best_ask(self, state: TradingState) -> Optional[int]:
        od = self.get_order_depth(state)
        return min(od.sell_orders.keys()) if od.sell_orders else None

    def mid_price(self, state: TradingState) -> Optional[float]:
        bb = self.best_bid(state)
        ba = self.best_ask(state)
        if bb is not None and ba is not None:
            return (bb + ba) / 2.0
        return None

    def spread(self, state: TradingState) -> Optional[int]:
        bb = self.best_bid(state)
        ba = self.best_ask(state)
        if bb is not None and ba is not None:
            return ba - bb
        return None

    def weighted_mid(self, state: TradingState) -> Optional[float]:
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

    def vwap(self, state: TradingState, side: str = "both") -> Optional[float]:
        od = self.get_order_depth(state)
        total_value = 0.0
        total_vol = 0
        if side in ("buy", "both") and od.buy_orders:
            for price, qty in od.buy_orders.items():
                total_value += price * qty
                total_vol += qty
        if side in ("sell", "both") and od.sell_orders:
            for price, qty in od.sell_orders.items():
                total_value += price * abs(qty)
                total_vol += abs(qty)
        return total_value / total_vol if total_vol > 0 else None

    # ── Book imbalance helpers ────────────────────────────────────

    def l1_imbalance(self, state: TradingState) -> float:
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

    def depth_imbalance(self, state: TradingState) -> float:
        od = self.get_order_depth(state)
        bid_depth = sum(od.buy_orders.values()) if od.buy_orders else 0
        ask_depth = sum(abs(v) for v in od.sell_orders.values()) if od.sell_orders else 0
        total = bid_depth + ask_depth
        if total == 0:
            return 0.0
        return (bid_depth - ask_depth) / total

    # ── Market-taking helpers ─────────────────────────────────────

    def take_best_asks(self, state: TradingState, position: int,
                       max_price: int) -> Tuple[List[Order], int]:
        od = self.get_order_depth(state)
        orders = []
        for price in sorted(od.sell_orders.keys()):
            if price > max_price:
                break
            vol = abs(od.sell_orders[price])
            order = self.buy(price, vol, position)
            if order:
                orders.append(order)
                position += order.quantity
        return orders, position

    def take_best_bids(self, state: TradingState, position: int,
                       min_price: int) -> Tuple[List[Order], int]:
        od = self.get_order_depth(state)
        orders = []
        for price in sorted(od.buy_orders.keys(), reverse=True):
            if price < min_price:
                break
            vol = od.buy_orders[price]
            order = self.sell(price, vol, position)
            if order:
                orders.append(order)
                position += order.quantity
        return orders, position

    # ── State persistence ─────────────────────────────────────────

    def save(self) -> dict:
        return {}

    def load(self, data: dict) -> None:
        pass


# ╔═══════════════════════════════════════════════════════════════╗
# ║  FIXED-VALUE MM STRATEGY (EMERALDS / ASH_COATED_OSMIUM)      ║
# ╚═══════════════════════════════════════════════════════════════╝


class FixedValueMMStrategy(Strategy):
    """Fixed-value market-making around a known constant fair value.
    Uses exact FV (not wall_mid) to avoid ±27 tick estimation error.
    Takes all mispriced levels aggressively, flattens at FV boundary."""

    def __init__(self, symbol: str, position_limit: int,
                 fair_value: int = 10_000):
        super().__init__(symbol=symbol, position_limit=position_limit)
        self.fair_value = fair_value

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []
        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            return []

        # Use exact known FV — wall_mid deviates ±27 and causes bad takes/makes
        fair = self.fair_value

        # Phase 1: TAKE — buy below fair-1, sell above fair+1
        # At fair boundary: only flatten existing position
        for ask_price in sorted(od.sell_orders.keys()):
            ask_vol = abs(od.sell_orders[ask_price])
            if ask_price <= fair - 1:
                order = self.buy(ask_price, ask_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity
            elif ask_price <= fair and position < 0:
                # Flatten short at fair value
                flatten_vol = min(ask_vol, abs(position))
                order = self.buy(ask_price, flatten_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity

        for bid_price in sorted(od.buy_orders.keys(), reverse=True):
            bid_vol = od.buy_orders[bid_price]
            if bid_price >= fair + 1:
                order = self.sell(bid_price, bid_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity
            elif bid_price >= fair and position > 0:
                # Flatten long at fair value
                flatten_vol = min(bid_vol, position)
                order = self.sell(bid_price, flatten_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity

        # Phase 2: MAKE — 1 tick inside bot's remaining best quote
        # Overbid the best bid that's below fair, undercut the best ask above fair
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())

        bid_price = int(bid_wall + 1)
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[bp] > 1 and bp + 1 < fair:
                bid_price = max(bid_price, bp + 1)
                break
        bid_price = min(bid_price, int(fair) - 1)

        ask_price = int(ask_wall - 1)
        for ap in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[ap]) > 1 and ap - 1 > fair:
                ask_price = min(ask_price, ap - 1)
                break
        ask_price = max(ask_price, int(fair) + 1)

        max_buy = self.max_buy_qty(position)
        max_sell = self.max_sell_qty(position)

        if max_buy > 0:
            orders.append(Order(self.symbol, bid_price, max_buy))
        if max_sell > 0:
            orders.append(Order(self.symbol, ask_price, -max_sell))

        return orders


# ╔═══════════════════════════════════════════════════════════════╗
# ║  DYNAMIC MM STRATEGY (TOMATOES / INTARIAN_PEPPER_ROOT)       ║
# ╚═══════════════════════════════════════════════════════════════╝


class DynamicMMStrategy(Strategy):
    """EMA-based market-making with L1 imbalance microprice and position skew.
    Uses EMA(mid) + explicit L1 imbalance for better fair value tracking."""

    SKEW_THRESHOLD = 0.15      # pos_ratio above this: start skewing
    HEAVY_THRESHOLD = 0.6      # pos_ratio above this: aggressive unwind
    IMB_WEIGHT = 0.5           # L1 imbalance contribution to fair

    def __init__(self, symbol: str, position_limit: int,
                 skew: float = 0.0, take_edge: int = 1, ema_window: int = 5):
        super().__init__(symbol=symbol, position_limit=position_limit)
        self.skew = skew
        self.take_edge = take_edge
        self.ema_window = ema_window
        self.ema_alpha = 2.0 / (ema_window + 1)
        self.ema_fair: Optional[float] = None

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []

        od = self.get_order_depth(state)
        if not od.buy_orders or not od.sell_orders:
            if self.ema_fair is not None:
                # Use last known fair on one-sided book
                fair = round(self.ema_fair - self.skew * position)
                # Only make, no takes on stale fair
                max_buy = self.max_buy_qty(position)
                max_sell = self.max_sell_qty(position)
                if max_buy > 0:
                    orders.append(Order(self.symbol, fair - 1, max_buy))
                if max_sell > 0:
                    orders.append(Order(self.symbol, fair + 1, -max_sell))
            return orders

        # L1 prices and volumes
        bb = max(od.buy_orders.keys())
        ba = min(od.sell_orders.keys())
        mid = (bb + ba) / 2.0
        bv = od.buy_orders[bb]
        av = abs(od.sell_orders[ba])
        total = bv + av

        # L1 imbalance: predicts short-term direction
        imb = (bv - av) / total if total > 0 else 0.0

        # EMA update on L1 mid (not wmid — only current imbalance should matter)
        if self.ema_fair is None:
            self.ema_fair = mid
        else:
            self.ema_fair = self.ema_alpha * mid + (1 - self.ema_alpha) * self.ema_fair

        # Fair = EMA + current L1 imbalance signal - inventory skew
        fair_adj = self.ema_fair + imb * self.IMB_WEIGHT - self.skew * position
        fair = round(fair_adj)

        # Phase 1: Take — buy asks below fair-edge, sell bids above fair+edge
        # Also flatten at fair boundary
        for ask_price in sorted(od.sell_orders.keys()):
            ask_vol = abs(od.sell_orders[ask_price])
            if ask_price <= fair - self.take_edge:
                order = self.buy(ask_price, ask_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity
            elif ask_price <= fair and position < 0:
                flatten_vol = min(ask_vol, abs(position))
                order = self.buy(ask_price, flatten_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity

        for bid_price in sorted(od.buy_orders.keys(), reverse=True):
            bid_vol = od.buy_orders[bid_price]
            if bid_price >= fair + self.take_edge:
                order = self.sell(bid_price, bid_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity
            elif bid_price >= fair and position > 0:
                flatten_vol = min(bid_vol, position)
                order = self.sell(bid_price, flatten_vol, position)
                if order:
                    orders.append(order)
                    position += order.quantity

        # Phase 2: MAKE — 1 tick inside bot's remaining best quote
        bid_wall = min(od.buy_orders.keys())
        ask_wall = max(od.sell_orders.keys())

        bid_price = int(bid_wall + 1)
        for bp in sorted(od.buy_orders.keys(), reverse=True):
            if od.buy_orders[bp] > 1 and bp + 1 < fair:
                bid_price = max(bid_price, bp + 1)
                break
        bid_price = min(bid_price, fair - 1)

        ask_price = int(ask_wall - 1)
        for ap in sorted(od.sell_orders.keys()):
            if abs(od.sell_orders[ap]) > 1 and ap - 1 > fair:
                ask_price = min(ask_price, ap - 1)
                break
        ask_price = max(ask_price, fair + 1)

        # Depth contrarian: shift makes against full-book imbalance (mean-reversion)
        bid_depth = sum(od.buy_orders.values())
        ask_depth = sum(abs(v) for v in od.sell_orders.values())
        total_depth = bid_depth + ask_depth
        if total_depth > 0:
            depth_imb = (bid_depth - ask_depth) / total_depth
            if depth_imb > 0.1:
                ask_price -= 1  # More aggressive sell into bid pressure
            elif depth_imb < -0.1:
                bid_price += 1  # More aggressive buy into ask pressure

        # Asymmetric sizing: reduce adding-side when heavily positioned
        max_buy = self.max_buy_qty(position)
        max_sell = self.max_sell_qty(position)
        pos_ratio = position / self.position_limit

        if abs(pos_ratio) > self.HEAVY_THRESHOLD:
            if pos_ratio > 0:
                max_buy = max(1, max_buy // 2)
            else:
                max_sell = max(1, max_sell // 2)
        elif abs(pos_ratio) > self.SKEW_THRESHOLD:
            if pos_ratio > 0:
                max_buy = max(1, int(max_buy * 0.7))
            else:
                max_sell = max(1, int(max_sell * 0.7))

        if max_buy > 0:
            orders.append(Order(self.symbol, bid_price, max_buy))
        if max_sell > 0:
            orders.append(Order(self.symbol, ask_price, -max_sell))

        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")


# ╔═══════════════════════════════════════════════════════════════╗
# ║  TRADER (entry point)                                        ║
# ╚═══════════════════════════════════════════════════════════════╝


class Trader:
    def __init__(self):
        self.strategies = [
            # Round 1 products only
            FixedValueMMStrategy("ASH_COATED_OSMIUM", position_limit=50, fair_value=10_000),
            DynamicMMStrategy("INTARIAN_PEPPER_ROOT", position_limit=50, skew=0.1, take_edge=1, ema_window=5),
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

        except Exception as e:
            logger.print(f"CRITICAL ERROR: {e}")
            try:
                logger.flush(state, {}, 0, state.traderData or "")
            except Exception:
                pass
            return {}, 0, state.traderData or ""

    def bid(self, state: TradingState) -> int:
        return 0