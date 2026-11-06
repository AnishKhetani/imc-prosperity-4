"""Check conversion observations and other unexplored data."""
import json
# Run a quick backtest with logging to see what observations are available
code = '''
import json
from datamodel import TradingState, Order

class Trader:
    def run(self, state: TradingState):
        obs = state.observations
        if obs:
            plain = obs.plainValueObservations if obs.plainValueObservations else {}
            conv = {}
            if obs.conversionObservations:
                for sym, co in obs.conversionObservations.items():
                    conv[sym] = {
                        "bid": co.bidPrice,
                        "ask": co.askPrice,
                        "transport": co.transportFees,
                        "export": co.exportTariff,
                        "import": co.importTariff,
                    }
            if state.timestamp == 0:
                print(f"TS={state.timestamp}")
                print(f"  Plain observations: {plain}")
                print(f"  Conversion observations: {conv}")
                print(f"  Listings: {list(state.listings.keys())}")
                print(f"  Products: {[l.product for l in state.listings.values()]}")
                print(f"  Market trades: {list(state.market_trades.keys())}")
                for sym in state.order_depths:
                    od = state.order_depths[sym]
                    print(f"  {sym} book: buy={od.buy_orders}, sell={od.sell_orders}")
                
        return {sym: [] for sym in state.order_depths}, 0, ""
'''

with open('check_obs.py', 'w') as f:
    f.write(code)

print("Created check_obs.py - run with: python -m prosperity4bt check_obs.py 2")
