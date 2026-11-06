import json
from datamodel import TradingState, Order

class Trader:
    def run(self, state: TradingState):
        obs = state.observations
        if state.timestamp == 0:
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
            out = json.dumps([
                [state.timestamp, 0, ""],
                {},
                0,
                "",
                f"Plain:{plain} Conv:{conv} Listings:{list(state.listings.keys())} MktTrades:{list(state.market_trades.keys())}",
            ], separators=(",", ":"))
            print(out)
        else:
            out = json.dumps([
                [state.timestamp, 0, ""],
                {},
                0,
                "",
                "",
            ], separators=(",", ":"))
            print(out)
        return {sym: [] for sym in state.order_depths}, 0, ""
