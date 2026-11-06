import json
from datamodel import TradingState, Order

class Trader:
    def run(self, state: TradingState):
        if state.timestamp <= 200:
            obs = state.observations
            plain = obs.plainValueObservations if obs and obs.plainValueObservations else {}
            conv = {}
            if obs and obs.conversionObservations:
                for sym, co in obs.conversionObservations.items():
                    conv[sym] = {
                        "bid": co.bidPrice,
                        "ask": co.askPrice,
                        "transport": co.transportFees,
                        "export": co.exportTariff,
                        "import": co.importTariff,
                    }
            mt_keys = list(state.market_trades.keys()) if state.market_trades else []
            mt_data = {}
            for k in mt_keys:
                mt_data[k] = [(t.price, t.quantity, t.buyer, t.seller) for t in state.market_trades[k]]
            
            with open("obs_log.txt", "a") as f:
                f.write(f"TS={state.timestamp}\n")
                f.write(f"  Plain: {plain}\n")
                f.write(f"  Conv: {conv}\n")
                f.write(f"  Listings: {list(state.listings.keys())}\n")
                f.write(f"  MktTrades: {mt_data}\n")
                for sym in state.order_depths:
                    od = state.order_depths[sym]
                    f.write(f"  {sym}: buy={od.buy_orders}, sell={od.sell_orders}\n")
                f.write("\n")
        
        return {sym: [] for sym in state.order_depths}, 0, ""
