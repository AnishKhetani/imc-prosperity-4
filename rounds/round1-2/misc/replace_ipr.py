"""Script to replace IPRStrategy in submission.py"""

new_ipr = '''class IPRStrategy(Strategy):
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
        take_cap = int(self.ema_fair) + max(5, int(self.ema_spread * 0.4))
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

        ask_price = int(ask_wall - 1)
        for ap in sorted(od.sell_orders.keys()):
            if ap == self.last_ask_price and abs(od.sell_orders[ap]) >= 25:
                continue
            if abs(od.sell_orders[ap]) > 1 and ap - 1 > int(self.ema_fair):
                ask_price = min(ask_price, ap - 1)
                break
        ask_price = max(ask_price, ask_floor)

        sell_qty = min(10, self.position_limit + position)
        if sell_qty > 0:
            orders.append(Order(self.symbol, ask_price, -sell_qty))

        # Phase 3: MAKE BUY -- replenish position
        remaining = self.position_limit - position
        if remaining > 0:
            bid_wall = min(od.buy_orders.keys())
            bid_price = bb + 1  # penny jump
            bid_price = min(bid_price, int(self.ema_fair) - 1)
            orders.append(Order(self.symbol, bid_price, remaining))

        self.last_ask_price = ask_price if sell_qty > 0 else None

        return orders

    def save(self) -> dict:
        return {"ef": self.ema_fair, "es": self.ema_spread, "ap": self.last_ask_price}

    def load(self, data: dict) -> None:
        self.ema_fair = data.get("ef")
        self.ema_spread = data.get("es")
        self.last_ask_price = data.get("ap")'''

with open('submission.py', 'rb') as f:
    data = f.read()

# Find class IPRStrategy start
start = data.find(b'class IPRStrategy')

# Find the next section header (# +-----) after IPRStrategy
# First find end of IPRStrategy's load method
search_from = start + 100
next_section = data.find(b'# +-------', search_from)

# The replacement should go from 'class IPRStrategy' to just before the next section header
old_section = data[start:next_section]
print(f"Replacing {len(old_section)} bytes starting at offset {start}")
print(f"First 80 chars: {old_section[:80]}")
print(f"Last 80 chars: {old_section[-80:]}")

new_data = data[:start] + new_ipr.encode('utf-8') + b'\r\n\r\n\r\n' + data[next_section:]

with open('submission.py', 'wb') as f:
    f.write(new_data)

print("Done! IPRStrategy replaced.")
