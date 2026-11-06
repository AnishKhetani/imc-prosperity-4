"""
IMC Prosperity 4 — Single-file submission.
Key findings from platform sim analysis:
  - Platform is 100% deterministic (same market data, same fills each run)
  - Only 66/2000 TOMATOES ticks have make-order fills; width directly controls edge per fill
  - EMERALDS: 24 make fills (not takes!), bot aggressors cross our resting orders
  - EMERALDS bot spread=16 (9992/10008), max safe WIDTH=7 (9993/10007)
  - TOMATOES bot spread~13, WIDTH=5 optimal; EMERALDS WIDTH=7 → 121*7=847 PnL
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
# ║  EMERALDS STRATEGY                                           ║
# ╚═══════════════════════════════════════════════════════════════╝


class EmeraldsStrategy(Strategy):
    FAIR_VALUE = 10_000
    MAKE_WIDTH = 7
    SKEW_THRESHOLD = 0.3
    HEAVY_THRESHOLD = 0.6

    def __init__(self):
        super().__init__(symbol="EMERALDS", position_limit=80)

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []

        # Phase 1: Take only with positive edge (skip zero-edge 10000 takes)
        take_buys, position = self.take_best_asks(state, position, self.FAIR_VALUE - 1)
        orders.extend(take_buys)

        take_sells, position = self.take_best_bids(state, position, self.FAIR_VALUE + 1)
        orders.extend(take_sells)

        # Phase 2: Wide makes at fair ± MAKE_WIDTH (9993/10007)
        observed_spread = self.spread(state)
        if observed_spread is not None and observed_spread < 12:
            width = max(1, observed_spread // 2 - 1)
        else:
            width = self.MAKE_WIDTH
        bid_price = self.FAIR_VALUE - width
        ask_price = self.FAIR_VALUE + width

        pos_ratio = position / self.position_limit

        if pos_ratio > self.HEAVY_THRESHOLD:
            bid_price -= 1
            ask_price -= 1
        elif pos_ratio > self.SKEW_THRESHOLD:
            ask_price -= 1
        elif pos_ratio < -self.HEAVY_THRESHOLD:
            bid_price += 1
            ask_price += 1
        elif pos_ratio < -self.SKEW_THRESHOLD:
            bid_price += 1

        max_buy = self.max_buy_qty(position)
        max_sell = self.max_sell_qty(position)

        if max_buy > 0:
            orders.append(Order(self.symbol, bid_price, max_buy))
        if max_sell > 0:
            orders.append(Order(self.symbol, ask_price, -max_sell))

        return orders


# ╔═══════════════════════════════════════════════════════════════╗
# ║  TOMATOES STRATEGY                                           ║
# ╚═══════════════════════════════════════════════════════════════╝


class TomatoesStrategy(Strategy):
    EMA_WINDOW = 5
    TAKE_EDGE = 0
    MAKE_WIDTH = 4
    SKEW_THRESHOLD = 0.15
    HEAVY_THRESHOLD = 0.6
    HISTORY_LEN = 50
    IMB_WEIGHT = 0.5
    DEPTH_CONTRARIAN = 1

    def __init__(self):
        super().__init__(symbol="TOMATOES", position_limit=80)
        self.price_history: List[float] = []
        self.ema: float = 0.0

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []

        mid = self.mid_price(state)
        if mid is None:
            return []

        self.price_history.append(mid)
        self.ema = self._compute_ema(mid)

        imb = self.l1_imbalance(state)
        adjusted_fair = self.ema + imb * self.IMB_WEIGHT - position * 0.05
        fair = round(adjusted_fair)

        depth_imb = self.depth_imbalance(state)

        # Phase 1: Take mispriced orders
        take_buys, position = self.take_best_asks(state, position, fair - self.TAKE_EDGE)
        orders.extend(take_buys)

        take_sells, position = self.take_best_bids(state, position, fair + self.TAKE_EDGE)
        orders.extend(take_sells)

        # Phase 2: Two-level make (±4 primary 60%, ±7 secondary 40%)
        bid_price, ask_price = self._make_prices(fair, position, depth_imb)
        bid_price2 = bid_price - 3  # ±7 from fair (outer level)
        ask_price2 = ask_price + 3

        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)

        # Split: 60% at tight level, 40% at wide level
        buy_qty1 = max(1, int(buy_qty * 0.6))
        buy_qty2 = buy_qty - buy_qty1
        sell_qty1 = max(1, int(sell_qty * 0.6))
        sell_qty2 = sell_qty - sell_qty1

        buy_order = self.buy(bid_price, buy_qty1, position) if buy_qty1 > 0 else None
        if buy_order:
            orders.append(buy_order)
            position += buy_order.quantity

        buy_order2 = self.buy(bid_price2, buy_qty2, position) if buy_qty2 > 0 else None
        if buy_order2:
            orders.append(buy_order2)
            position += buy_order2.quantity

        sell_order = self.sell(ask_price, sell_qty1, position) if sell_qty1 > 0 else None
        if sell_order:
            orders.append(sell_order)
            position += sell_order.quantity

        sell_order2 = self.sell(ask_price2, sell_qty2, position) if sell_qty2 > 0 else None
        if sell_order2:
            orders.append(sell_order2)

        return orders

    def _compute_ema(self, new_price: float) -> float:
        if len(self.price_history) <= 1:
            return new_price
        alpha = 2.0 / (self.EMA_WINDOW + 1)
        return alpha * new_price + (1 - alpha) * self.ema

    def _make_prices(self, fair: int, position: int, depth_imb: float) -> tuple:
        bid = fair - self.MAKE_WIDTH
        ask = fair + self.MAKE_WIDTH

        pos_ratio = position / self.position_limit
        if pos_ratio > self.HEAVY_THRESHOLD:
            bid -= 1
            ask -= 1
        elif pos_ratio > self.SKEW_THRESHOLD:
            ask -= 1
        elif pos_ratio < -self.HEAVY_THRESHOLD:
            ask += 1
            bid += 1
        elif pos_ratio < -self.SKEW_THRESHOLD:
            bid += 1

        if depth_imb > 0.1:
            ask -= self.DEPTH_CONTRARIAN
        elif depth_imb < -0.1:
            bid += self.DEPTH_CONTRARIAN

        return bid, ask

    def _asymmetric_size(self, max_buy: int, max_sell: int, pos_ratio: float) -> tuple:
        if abs(pos_ratio) < self.SKEW_THRESHOLD:
            return max_buy, max_sell
        if pos_ratio > 0:
            buy_qty = max(1, int(max_buy * 0.5))
            return buy_qty, max_sell
        else:
            sell_qty = max(1, int(max_sell * 0.5))
            return max_buy, sell_qty

    def save(self) -> dict:
        return {
            "prices": self.price_history[-self.HISTORY_LEN:],
            "ema": self.ema,
        }

    def load(self, data: dict) -> None:
        self.price_history = data.get("prices", [])
        self.ema = data.get("ema", 0.0)


# ╔═══════════════════════════════════════════════════════════════╗
# ║  TRADER (entry point)                                        ║
# ╚═══════════════════════════════════════════════════════════════╝


class Trader:
    def __init__(self):
        self.strategies = [
            EmeraldsStrategy(),
            TomatoesStrategy(),
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

