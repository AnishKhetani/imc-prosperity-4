"""
Single-combination runner. Called by combo_test.py via subprocess.
Args: em_skew_thresh em_heavy_thresh tom_skew_thresh imb_weight depth_contrarian stale_guard(0/1) wind_down(0/1)
Prints: RESULT|total|day-2|day-1|em_d2|em_d1|tom_d2|tom_d1
"""
import sys
import os
from pathlib import Path

BACKTESTER_DIR = Path(__file__).parent.parent / "backtester"
sys.path.insert(0, str(BACKTESTER_DIR))
os.chdir(str(BACKTESTER_DIR))

from prosperity3bt.file_reader import FileSystemReader
from prosperity3bt.models import TradeMatchingMode
from prosperity3bt.runner import run_backtest
from prosperity3bt.data import has_day_data, LIMITS

LIMITS["EMERALDS"] = 80
LIMITS["TOMATOES"] = 80

DATA_DIR = BACKTESTER_DIR / "data" / "tutorial"


def write_emeralds(skew_thresh, heavy_thresh):
    code = f'''from strategy import Strategy
from datamodel import TradingState, Order
from typing import List

class EmeraldsStrategy(Strategy):
    FAIR_VALUE = 10_000
    MAKE_WIDTH = 7
    SKEW_THRESHOLD = {skew_thresh}
    HEAVY_THRESHOLD = {heavy_thresh}

    def __init__(self):
        super().__init__(symbol="EMERALDS", position_limit=80)

    def act(self, state: TradingState) -> List[Order]:
        position = self.get_position(state)
        orders: List[Order] = []

        take_buys, position = self.take_best_asks(state, position, self.FAIR_VALUE - 1)
        orders.extend(take_buys)
        take_sells, position = self.take_best_bids(state, position, self.FAIR_VALUE + 1)
        orders.extend(take_sells)

        bid_price = self.FAIR_VALUE - self.MAKE_WIDTH
        ask_price = self.FAIR_VALUE + self.MAKE_WIDTH
        pos_ratio = position / self.position_limit

        if pos_ratio > self.HEAVY_THRESHOLD:
            bid_price -= 1; ask_price -= 1
        elif pos_ratio > self.SKEW_THRESHOLD:
            ask_price -= 1
        elif pos_ratio < -self.HEAVY_THRESHOLD:
            bid_price += 1; ask_price += 1
        elif pos_ratio < -self.SKEW_THRESHOLD:
            bid_price += 1

        max_buy = self.max_buy_qty(position)
        max_sell = self.max_sell_qty(position)
        if max_buy > 0:
            orders.append(Order(self.symbol, bid_price, max_buy))
        if max_sell > 0:
            orders.append(Order(self.symbol, ask_price, -max_sell))
        return orders
'''
    (BACKTESTER_DIR / "strategies" / "emeralds.py").write_text(code, encoding="utf-8")


def write_tomatoes(skew_thresh, imb_weight, depth_contrarian, stale_guard, wind_down):
    stale_code = ""
    if stale_guard:
        stale_code = """
        # Stale EMA guard: clamp fair to within 2 of current mid
        int_mid = int(mid)
        if fair > int_mid + 2:
            fair = int_mid + 2
        elif fair < int_mid - 2:
            fair = int_mid - 2"""

    wd_code = ""
    if wind_down:
        wd_code = """
        # End-of-day wind-down: last 10% of ticks
        if state.timestamp >= 180000:
            if position > 5:
                buy_qty = max(1, buy_qty // 4)
                ask_price -= 1
            elif position < -5:
                sell_qty = max(1, sell_qty // 4)
                bid_price += 1"""

    code = f'''from strategy import Strategy
from datamodel import TradingState, Order
from typing import List

class TomatoesStrategy(Strategy):
    EMA_WINDOW = 5
    TAKE_EDGE = 0
    MAKE_WIDTH = 5
    SKEW_THRESHOLD = {skew_thresh}
    HEAVY_THRESHOLD = 0.6
    HISTORY_LEN = 50
    IMB_WEIGHT = {imb_weight}
    DEPTH_CONTRARIAN = {depth_contrarian}

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
        {stale_code}

        depth_imb = self.depth_imbalance(state)

        take_buys, position = self.take_best_asks(state, position, fair - self.TAKE_EDGE)
        orders.extend(take_buys)
        take_sells, position = self.take_best_bids(state, position, fair + self.TAKE_EDGE)
        orders.extend(take_sells)

        bid_price, ask_price = self._make_prices(fair, position, depth_imb)

        pos_ratio = position / self.position_limit
        remaining_buy = self.max_buy_qty(position)
        remaining_sell = self.max_sell_qty(position)
        buy_qty, sell_qty = self._asymmetric_size(remaining_buy, remaining_sell, pos_ratio)
        {wd_code}

        buy_order = self.buy(bid_price, buy_qty, position) if buy_qty > 0 else None
        if buy_order:
            orders.append(buy_order)
        sell_order = self.sell(ask_price, sell_qty, position) if sell_qty > 0 else None
        if sell_order:
            orders.append(sell_order)
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
            bid -= 1; ask -= 1
        elif pos_ratio > self.SKEW_THRESHOLD:
            ask -= 1
        elif pos_ratio < -self.HEAVY_THRESHOLD:
            ask += 1; bid += 1
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
        return {{
            "prices": self.price_history[-self.HISTORY_LEN:],
            "ema": self.ema,
        }}

    def load(self, data: dict) -> None:
        self.price_history = data.get("prices", [])
        self.ema = data.get("ema", 0.0)
'''
    (BACKTESTER_DIR / "strategies" / "tomatoes.py").write_text(code, encoding="utf-8")


def main():
    args = sys.argv[1:]
    em_skew = float(args[0])
    em_heavy = float(args[1])
    tom_skew = float(args[2])
    imb_w = float(args[3])
    depth_c = int(args[4])
    stale = int(args[5])
    wind = int(args[6])

    write_emeralds(em_skew, em_heavy)
    write_tomatoes(tom_skew, imb_w, depth_c, bool(stale), bool(wind))

    file_reader = FileSystemReader(DATA_DIR)
    from trader import Trader

    results = {}
    total = 0.0

    for day_num in [-2, -1]:
        if not has_day_data(file_reader, 0, day_num):
            continue
        trader = Trader()
        result = run_backtest(
            trader=trader,
            file_reader=file_reader,
            round_num=0,
            day_num=day_num,
            print_output=False,
            trade_matching_mode=TradeMatchingMode.all,
            no_names=True,
            show_progress_bar=False,
        )
        last_ts = result.activity_logs[-1].timestamp
        for row in reversed(result.activity_logs):
            if row.timestamp != last_ts:
                break
            product = row.columns[2]
            profit = row.columns[-1]
            results[f"{product}_day{day_num}"] = profit
            total += profit
        results[f"day{day_num}"] = sum(
            row.columns[-1] for row in reversed(result.activity_logs) if row.timestamp == last_ts
        )

    em_d2 = results.get("EMERALDS_day-2", 0)
    em_d1 = results.get("EMERALDS_day-1", 0)
    tom_d2 = results.get("TOMATOES_day-2", 0)
    tom_d1 = results.get("TOMATOES_day-1", 0)

    print(f"RESULT|{total}|{results.get('day-2',0)}|{results.get('day-1',0)}|{em_d2}|{em_d1}|{tom_d2}|{tom_d1}")


if __name__ == "__main__":
    main()
